"""Durable LangGraph orchestration for approval-gated repository writeback."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from codepilot.agent import Agent
from codepilot.schemas import RunResult, Task, ToolCall
from codepilot.tools.registry import ToolRegistry
from codepilot.workspace import Workspace, WorkspaceError, WorkspaceManager


APPROVAL_TTL_SECONDS = 30 * 60


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
    approval_expired: bool
    approval_expires_at: str
    delivery: str
    error: str
    runtime: dict[str, Any]


AgentFactory = Callable[[Task, str, dict[str, Any]], Agent]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _approval_window(
    database: Path,
    run_id: str,
    patch_sha256: str,
    *,
    parent_span_id: str,
) -> tuple[dict[str, str], bool]:
    """Create one durable approval deadline; replay must reuse it."""
    requested_at = _utc_now()
    expires_at = requested_at + timedelta(seconds=APPROVAL_TTL_SECONDS)
    with sqlite3.connect(database, timeout=30) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS approval_windows ("
            "run_id TEXT PRIMARY KEY, patch_sha256 TEXT NOT NULL, "
            "requested_at TEXT NOT NULL, expires_at TEXT NOT NULL, "
            "approval_span_id TEXT NOT NULL, parent_span_id TEXT NOT NULL)"
        )
        existing = connection.execute(
            "SELECT patch_sha256, requested_at, expires_at, approval_span_id, parent_span_id "
            "FROM approval_windows WHERE run_id=?",
            (run_id,),
        ).fetchone()
        created = existing is None
        if created:
            record = (
                patch_sha256,
                requested_at.isoformat(),
                expires_at.isoformat(),
                uuid.uuid4().hex,
                parent_span_id,
            )
            connection.execute(
                "INSERT INTO approval_windows "
                "(run_id, patch_sha256, requested_at, expires_at, approval_span_id, parent_span_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, *record),
            )
            existing = record
    if existing[0] != patch_sha256:
        raise WorkspaceError("审批期间补丁摘要发生变化；旧审批窗口不可复用")
    return {
        "patch_sha256": existing[0],
        "requested_at": existing[1],
        "expires_at": existing[2],
        "approval_span_id": existing[3],
        "parent_span_id": existing[4],
    }, created


def _load_approval_window(database: Path, run_id: str) -> dict[str, str] | None:
    if not database.is_file():
        return None
    with sqlite3.connect(database, timeout=30) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approval_windows'"
        ).fetchone()
        if not table:
            return None
        row = connection.execute(
            "SELECT patch_sha256, requested_at, expires_at, approval_span_id, parent_span_id "
            "FROM approval_windows WHERE run_id=?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(zip(
        ("patch_sha256", "requested_at", "expires_at", "approval_span_id", "parent_span_id"),
        row,
        strict=True,
    ))


def _approval_expired(window: dict[str, str]) -> bool:
    try:
        expires_at = datetime.fromisoformat(window["expires_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("审批过期时间缺失或格式错误；拒绝回写") from exc
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("审批过期时间没有时区；拒绝回写")
    return _utc_now() >= expires_at


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
        parent_span_id = str(
            getattr(tracer, "current_span_id", None)
            or getattr(tracer, "root_span_id", "")
        )
        window, first_request = _approval_window(
            database,
            state["run_id"],
            state["patch_sha256"],
            parent_span_id=parent_span_id,
        )
        if first_request:
            trace(
                "writeback_approval_requested",
                state,
                patch_sha256=state["patch_sha256"],
                tests_passed=bool(result.test_result and result.test_result.ok),
                requested_at=window["requested_at"],
                expires_at=window["expires_at"],
                span_id=window["approval_span_id"],
                parent_span_id=window["parent_span_id"],
            )
        decision = interrupt(
            {
                "type": "repository_writeback_approval",
                "run_id": state["run_id"],
                "source": state["source"],
                "base_commit": state["base_commit"],
                "patch_sha256": state["patch_sha256"],
                "tests_passed": bool(result.test_result and result.test_result.ok),
                "requested_at": window["requested_at"],
                "expires_at": window["expires_at"],
                "diff": result.diff,
            }
        )
        if isinstance(decision, dict):
            approved = decision.get("approved") is True
            expired = decision.get("expired") is True
        else:
            approved = bool(decision)
            expired = False
        trace(
            "writeback_approval_decided",
            state,
            approved=approved,
            expired=expired,
            patch_sha256=state["patch_sha256"],
            span_id=window["approval_span_id"],
            parent_span_id=window["parent_span_id"],
        )
        return {
            "approval": approved,
            "approval_expired": expired,
            "approval_expires_at": window["expires_at"],
        }

    def delivery(state: DurableRunState) -> dict[str, Any]:
        result = RunResult.model_validate(state["result"])
        if not state.get("apply_to_repo"):
            trace("writeback_finished", state, outcome="workspace_only")
            return {"delivery": "workspace_only"}
        if result.status != "success":
            trace("writeback_finished", state, outcome="agent_failed")
            return {"delivery": "not_delivered"}
        if state.get("approval_expired"):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "回写审批已过期；请重新发起任务并重新验证，补丁未写回"
            trace("writeback_finished", state, outcome="approval_expired")
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "approval_expired",
            }
        if not state.get("approval"):
            result.status = "needs_approval"
            result.failure_type = "policy"
            result.error = "用户拒绝补丁回写"
            trace("writeback_finished", state, outcome="rejected")
            return {"result": result.model_dump(mode="json"), "delivery": "rejected"}

        window = _load_approval_window(database, state["run_id"])
        if (
            window is None
            or window["expires_at"] != state.get("approval_expires_at")
            or window["patch_sha256"] != state.get("patch_sha256")
        ):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "审批窗口或补丁绑定校验失败；拒绝回写"
            trace("writeback_finished", state, outcome="approval_binding_invalid")
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "approval_invalid",
            }

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
        if _approval_expired(window):
            result.status = "failed"
            result.failure_type = "policy"
            result.error = "回写审批在重新验证期间过期；补丁未写回"
            trace(
                "approval_expired",
                state,
                patch_sha256=window["patch_sha256"],
                expires_at=window["expires_at"],
            )
            trace("writeback_finished", state, outcome="approval_expired")
            return {
                "result": result.model_dump(mode="json"),
                "delivery": "approval_expired",
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
            resume_value: bool | dict[str, bool] = approved
            result_data = snapshot.values.get("result", {})
            approval_pending = bool(
                snapshot.values.get("apply_to_repo")
                and isinstance(result_data, dict)
                and result_data.get("status") == "success"
            )
            if approval_pending:
                window = _load_approval_window(database, run_id)
                if approved and window is None:
                    raise ValueError("审批时间窗记录缺失；拒绝批准回写")
                if window is not None:
                    if window["patch_sha256"] != snapshot.values.get("patch_sha256"):
                        raise ValueError("审批摘要与检查点补丁不匹配；拒绝回写")
                    expired = bool(approved and _approval_expired(window))
                    if expired:
                        trace_event = getattr(tracer, "event", None)
                        if trace_event:
                            trace_event(
                                "approval_expired",
                                0,
                                patch_sha256=window["patch_sha256"],
                                expires_at=window["expires_at"],
                                span_id=window["approval_span_id"],
                                parent_span_id=window["parent_span_id"],
                            )
                    resume_value = {"approved": bool(approved and not expired), "expired": expired}
            return graph.invoke(Command(resume=resume_value), config=config)
        if approved is not None:
            raise ValueError("运行未处于等待审批状态，拒绝重复恢复")
        if not snapshot.next:
            raise ValueError("运行已完成，拒绝重复恢复")
        return graph.invoke(None, config=config)
