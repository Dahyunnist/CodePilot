"""Durable LangGraph orchestration for approval-gated repository writeback."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from codepilot.agent import Agent
from codepilot.schemas import RunResult, Task, ToolCall
from codepilot.tools.registry import ToolRegistry
from codepilot.workspace import Workspace, WorkspaceError, WorkspaceManager


class DurableRunState(TypedDict, total=False):
    task: dict[str, Any]
    run_id: str
    source: str
    workspace: str
    base_commit: str
    apply_to_repo: bool
    result: dict[str, Any]
    patch_sha256: str
    approval: bool
    delivery: str
    error: str
    runtime: dict[str, Any]


AgentFactory = Callable[[Task, str, dict[str, Any]], Agent]


def _save_agent_progress(database: Path, run_id: str, progress: dict[str, Any]) -> None:
    with sqlite3.connect(database, timeout=30) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS agent_progress (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO agent_progress(run_id, payload) VALUES (?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
            (run_id, json.dumps(progress, ensure_ascii=False)),
        )


def _load_agent_progress(database: Path, run_id: str) -> dict[str, Any] | None:
    if not database.exists():
        return None
    with sqlite3.connect(database, timeout=30) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_progress'"
        ).fetchone()
        if not exists:
            return None
        row = connection.execute(
            "SELECT payload FROM agent_progress WHERE run_id=?", (run_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def _git_patch(workspace: Path, base_commit: str) -> bytes:
    completed = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", base_commit, "--"],
        cwd=workspace,
        capture_output=True,
        timeout=30,
        check=False,
        shell=False,
    )
    if completed.returncode:
        raise WorkspaceError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _build_graph(
    *,
    database: Path,
    manager: WorkspaceManager,
    agent_factory: AgentFactory,
    tracer: Any | None = None,
):
    def trace(event: str, state: DurableRunState, **fields: Any) -> None:
        if tracer is not None:
            tracer.event(event, 0, **fields)

    def run_agent(state: DurableRunState) -> dict[str, Any]:
        task = Task.model_validate(state["task"])
        progress = _load_agent_progress(database, state["run_id"])
        if progress and progress.get("done"):
            result = RunResult.model_validate(progress["result"])
            if result.diff != _git_patch(
                Path(state["workspace"]), state["base_commit"]
            ).decode("utf-8", errors="replace"):
                raise WorkspaceError("恢复时工作副本差异与已验证结果不符")
        else:
            result = agent_factory(
                task, state["run_id"], state.get("runtime", {})
            ).run(
                task,
                progress_callback=lambda snapshot: _save_agent_progress(
                    database, state["run_id"], snapshot
                ),
                resume_data=progress,
            )
        workspace = Path(state["workspace"])
        patch = _git_patch(workspace, state["base_commit"])
        patch_hash = hashlib.sha256(patch).hexdigest()
        if (
            state.get("apply_to_repo")
            and result.status == "success"
            and result.diff != patch.decode("utf-8", errors="replace")
        ):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "补丁完整差异无法被审批预览完整呈现；已拒绝回写"
            trace("writeback_finished", state, outcome="unreviewable_diff")
        return {"result": result.model_dump(mode="json"), "patch_sha256": patch_hash}

    def approval_gate(state: DurableRunState) -> dict[str, Any]:
        result = RunResult.model_validate(state["result"])
        if not state.get("apply_to_repo") or result.status != "success":
            return {"approval": False}
        trace(
            "writeback_approval_requested",
            state,
            patch_sha256=state["patch_sha256"],
            tests_passed=bool(result.test_result and result.test_result.ok),
        )
        approved = interrupt(
            {
                "type": "repository_writeback_approval",
                "run_id": state["run_id"],
                "source": state["source"],
                "base_commit": state["base_commit"],
                "patch_sha256": state["patch_sha256"],
                "tests_passed": bool(result.test_result and result.test_result.ok),
                "diff": result.diff,
            }
        )
        trace(
            "writeback_approval_decided",
            state,
            approved=bool(approved),
            patch_sha256=state["patch_sha256"],
        )
        return {"approval": bool(approved)}

    def delivery(state: DurableRunState) -> dict[str, Any]:
        result = RunResult.model_validate(state["result"])
        if not state.get("apply_to_repo"):
            trace("writeback_finished", state, outcome="workspace_only")
            return {"delivery": "workspace_only"}
        if result.status != "success":
            trace("writeback_finished", state, outcome="agent_failed")
            return {"delivery": "not_delivered"}
        if not state.get("approval"):
            result.status = "needs_approval"
            result.failure_type = "policy"
            result.error = "用户拒绝补丁回写"
            trace("writeback_finished", state, outcome="rejected")
            return {"result": result.model_dump(mode="json"), "delivery": "rejected"}

        workspace = Workspace(
            source=Path(state["source"]),
            path=Path(state["workspace"]),
            base_commit=state["base_commit"],
        )
        current_hash = hashlib.sha256(
            _git_patch(workspace.path, workspace.base_commit)
        ).hexdigest()
        if current_hash != state["patch_sha256"]:
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "等待审批期间补丁已变化；旧测试和审批均作废"
            trace("writeback_finished", state, outcome="stale_patch")
            return {"result": result.model_dump(mode="json"), "delivery": "stale_patch"}
        patch = _git_patch(workspace.path, workspace.base_commit)
        if result.diff != patch.decode("utf-8", errors="replace"):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "补丁完整差异无法被审批预览完整呈现；已拒绝回写"
            trace("writeback_finished", state, outcome="unreviewable_diff")
            return {"result": result.model_dump(mode="json"), "delivery": "unreviewable_diff"}
        runtime = state.get("runtime", {})
        if (
            runtime.get("execution_mode", "docker") == "host"
            and not runtime.get("host_tests_approved", False)
        ):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "恢复写回前需明确授权主机测试；旧测试结果不再有效"
            trace("writeback_finished", state, outcome="revalidation_not_approved")
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "revalidation_failed",
            }
        task = Task.model_validate(state["task"])
        registry = ToolRegistry(
            workspace.path,
            task.test_command,
            test_timeout_seconds=float(runtime.get("test_timeout_seconds", 30)),
            execution_mode=str(runtime.get("execution_mode", "docker")),
            docker_image=str(runtime.get("docker_image", "codepilot-runner:0.1")),
            docker_python=str(runtime.get("docker_python", "python")),
            host_tests_approved=bool(runtime.get("host_tests_approved", False)),
        )
        revalidation = registry.execute(
            ToolCall(id=f"resume-test-{state['run_id']}", name="run_tests", arguments={})
        )
        result.test_result = revalidation
        result.tool_results.append(revalidation)
        if not revalidation.ok:
            result.status = "failed"
            result.failure_type = (
                "tool"
                if revalidation.error_type in {"execution", "timeout"}
                else "test"
            )
            result.error = "恢复后的完整测试未通过；补丁未回写"
            trace(
                "writeback_finished",
                state,
                outcome="revalidation_failed",
                exit_code=revalidation.exit_code,
                error_type=revalidation.error_type,
            )
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "revalidation_failed",
            }
        revalidated_hash = hashlib.sha256(
            _git_patch(workspace.path, workspace.base_commit)
        ).hexdigest()
        if revalidated_hash != current_hash:
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "恢复验证期间补丁发生变化；已拒绝回写"
            trace("writeback_finished", state, outcome="patch_changed_during_revalidation")
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "stale_patch",
            }
        trace(
            "writeback_started",
            state,
            patch_sha256=state["patch_sha256"],
            base_commit=state["base_commit"],
        )
        try:
            changed = manager.apply_changes(workspace)
        except WorkspaceError as exc:
            result.status = "failed"
            result.failure_type = "policy"
            result.error = f"补丁未能回写到源仓库：{exc}"
            trace("writeback_finished", state, outcome="rejected", error=str(exc))
            return {"result": result.model_dump(mode="json"), "delivery": "rejected"}
        result.final_text += (
            "\n修复补丁已应用到源仓库。" if changed else "\n源仓库没有需要回写的补丁。"
        )
        trace("writeback_finished", state, outcome="applied", patch_sha256=current_hash)
        return {"result": result.model_dump(mode="json"), "delivery": "applied"}

    builder = StateGraph(DurableRunState)
    builder.add_node("run_agent", run_agent)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("delivery", delivery)
    builder.add_edge(START, "run_agent")
    builder.add_edge("run_agent", "approval_gate")
    builder.add_edge("approval_gate", "delivery")
    builder.add_edge("delivery", END)
    return builder


def start_durable_run(
    *,
    database: Path,
    manager: WorkspaceManager,
    agent_factory: AgentFactory,
    task: Task,
    workspace: Workspace,
    run_id: str,
    apply_to_repo: bool,
    runtime: dict[str, Any] | None = None,
    tracer: Any | None = None,
) -> dict[str, Any]:
    """Run and checkpoint one task; return an interrupt payload if approval waits."""
    config = {"configurable": {"thread_id": run_id}}
    database.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = _build_graph(
            database=database, manager=manager, agent_factory=agent_factory, tracer=tracer
        ).compile(checkpointer=saver)
        return graph.invoke(
            {
                "task": task.model_dump(mode="json"),
                "run_id": run_id,
                "source": str(workspace.source),
                "workspace": str(workspace.path),
                "base_commit": workspace.base_commit,
                "apply_to_repo": apply_to_repo,
                "runtime": runtime or {},
            },
            config=config,
        )


def resume_durable_run(
    *,
    database: Path,
    manager: WorkspaceManager,
    agent_factory: AgentFactory,
    run_id: str,
    approved: bool | None,
    tracer: Any | None = None,
) -> dict[str, Any]:
    """Resume a paused approval or an interrupted graph node; reject replays."""
    config = {"configurable": {"thread_id": run_id}}
    database.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = _build_graph(
            database=database, manager=manager, agent_factory=agent_factory, tracer=tracer
        ).compile(checkpointer=saver)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise ValueError(f"未找到运行记录：{run_id}")
        interrupted = any(task.interrupts for task in snapshot.tasks)
        if interrupted:
            if approved is None:
                raise ValueError("运行正在等待审批；请指定 --approve 或 --reject")
            return graph.invoke(Command(resume=approved), config=config)
        if approved is not None:
            raise ValueError("运行未处于等待审批状态，拒绝重复恢复")
        if not snapshot.next:
            raise ValueError("运行已完成，拒绝重复恢复")
        return graph.invoke(None, config=config)
