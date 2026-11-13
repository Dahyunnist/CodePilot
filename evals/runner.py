"""Repeatable five-case evaluation with independent hidden verification."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import uuid
import hashlib
import json
import re
from datetime import datetime, timezone
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from codepilot.agent import Agent
from codepilot.schemas import ChatMessage, ModelReply, Task, ToolCall, ToolSpec
from codepilot.tools.execute import run_tests
from codepilot.tools.registry import ToolRegistry
from codepilot.tracing import TraceLogger
from codepilot.workspace import WorkspaceManager
from evals.summarize import write_summary


MODEL_NAME = "scripted-oracle"
PROMPT_VERSION = "explicit-loop-v1"
TEMPERATURE = 0.0
RUN_MANIFEST_FIELDS = {"schema_version", "project", "git_sha", "dataset_id", "dataset_sha256", "split", "model_id", "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps", "max_tokens", "scorer_sha", "gold_source", "cost_usd_estimate", "run_id", "trace_id", "started_at", "ended_at", "status"}


def validate_run_manifest(manifest: dict[str, object]) -> None:
    if set(manifest) != RUN_MANIFEST_FIELDS:
        raise ValueError("run manifest fields mismatch")
    if manifest["schema_version"] != 1 or not re.fullmatch(r"[0-9a-f]{40}", str(manifest["git_sha"])):
        raise ValueError("invalid run manifest schema or git sha")
    for field in ("dataset_sha256", "prompt_sha", "tool_schema_sha", "scorer_sha"):
        value = manifest[field]
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", str(value)):
            raise ValueError(f"invalid {field}")
    if manifest["model_id"] != "scripted-oracle" or manifest["cost_usd_estimate"] != 0:
        raise ValueError("scripted-oracle identity/cost mismatch")
    for field in ("runtime_digest",):
        if manifest[field] is not None and not isinstance(manifest[field], str):
            raise ValueError(f"invalid {field}")
    for field in ("project", "dataset_id", "split", "gold_source", "run_id", "trace_id", "status"):
        if not isinstance(manifest[field], str) or not manifest[field]:
            raise ValueError(f"invalid {field}")
    for field in ("max_steps", "max_tokens"):
        if manifest[field] is not None and (type(manifest[field]) is not int or manifest[field] < 0):
            raise ValueError(f"invalid {field}")
    for field in ("started_at", "ended_at"):
        try:
            datetime.fromisoformat(str(manifest[field]))
        except ValueError as exc:
            raise ValueError(f"invalid {field}") from exc


def write_run_manifest(path: Path, manifest: dict[str, object]) -> None:
    validate_run_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_run_manifest(*, run_id: str, trace_id: str, git_sha: str, dataset_sha256: str | None, started_at: str, ended_at: str, status: str) -> dict[str, object]:
    prompt_sha = hashlib.sha256(PROMPT_VERSION.encode()).hexdigest()
    manifest = {"schema_version": 1, "project": "codepilot-lite", "git_sha": git_sha, "dataset_id": "evals/cases", "dataset_sha256": dataset_sha256, "split": "fixed-cases", "model_id": MODEL_NAME, "prompt_sha": prompt_sha, "tool_schema_sha": None, "runtime_digest": None, "max_steps": 8, "max_tokens": None, "scorer_sha": None, "gold_source": "case.json patch plan; scripted oracle", "cost_usd_estimate": 0, "run_id": run_id, "trace_id": trace_id, "started_at": started_at, "ended_at": ended_at, "status": status}
    return manifest


class PatchSpec(BaseModel):
    """One exact edit in a deterministic repair plan."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    old_text: str = Field(min_length=1)
    new_text: str


class CaseSpec(BaseModel):
    """Versioned task metadata and deterministic baseline repair."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    test_command: list[str] = Field(min_length=1)
    search_query: str = ""
    patches: list[PatchSpec] = Field(default_factory=list)
    source_url: str | None = None
    source_release: str | None = None
    source_exclusions: list[str] = Field(default_factory=list)
    source_commit: str | None = None
    source_tree_sha: str | None = None
    issue_url: str | None = None
    pull_request_url: str | None = None
    archive_sha256: str | None = None
    hidden_test_patch: str | None = None
    hidden_test_command: list[str] | None = None
    docker_image: str | None = None
    baseline_expected_failure: bool = True
    test_timeout_seconds: int = Field(default=30, ge=1, le=600)
    docker_python: str = Field(default="python", min_length=1)
    generated_version_sha256: str | None = None
    compiled_extensions_sha256: str | None = None
    visible_test_sha256: str | None = None
    case_dir: Path | None = None


class ScriptedRepairModel:
    """Deterministic tool policy used to validate the evaluation machinery."""

    def __init__(self, case: CaseSpec) -> None:
        if not case.search_query or not case.patches:
            raise ValueError("scripted cases require search_query and patches")
        self.replies = [
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="search",
                        name="search_code",
                        arguments={"query": case.search_query, "path": "."},
                    )
                ]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id=f"read-{index}",
                        name="read_file",
                        arguments={
                            "path": patch.path,
                            "reason": "检查修复涉及的源码文件。",
                        },
                    )
                    for index, patch in enumerate(case.patches, start=1)
                ]
            ),
            ModelReply(
                tool_calls=[ToolCall(id="baseline-test", name="run_tests", arguments={})]
            ),
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id=f"patch-{index}",
                        name="apply_patch",
                        arguments={
                            "path": patch.path,
                            "old_text": patch.old_text,
                            "new_text": patch.new_text,
                        },
                    )
                    for index, patch in enumerate(case.patches, start=1)
                ]
            ),
            ModelReply(
                tool_calls=[ToolCall(id="fixed-test", name="run_tests", arguments={})]
            ),
            ModelReply(text="\u5df2\u5b8c\u6210\u9488\u5bf9\u6027\u4fee\u590d\uff0c\u5e76\u901a\u8fc7\u53ef\u89c1\u6d4b\u8bd5\u3002"),
        ]

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        *,
        max_completion_tokens: int | None = None,
    ) -> ModelReply:
        if not self.replies:
            raise RuntimeError("scripted model exhausted")
        return self.replies.pop(0)


def load_cases(cases_root: Path) -> list[CaseSpec]:
    """Load cases in stable order and attach their private directories."""
    cases: list[CaseSpec] = []
    for metadata in sorted(cases_root.glob("*/case.json")):
        case = CaseSpec.model_validate_json(metadata.read_text(encoding="utf-8"))
        case.case_dir = metadata.parent.resolve()
        cases.append(case)
    return cases


def run_evaluation(
    cases_root: Path,
    output_csv: Path,
    work_root: Path,
    reports_root: Path,
    docker_image: str,
    execution: str = "docker",
) -> list[dict[str, object]]:
    """Reset, repair, independently verify, and record every fixed case."""
    eval_run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    run_root = work_root.resolve() / eval_run_id
    rows: list[dict[str, object]] = []
    demo_trace: Path | None = None

    for case in load_cases(cases_root):
        assert case.case_dir is not None
        base = _prepare_base(case, run_root / "bases" / case.case_id)
        baseline = run_tests(
            base,
            case.test_command,
            execution_mode=execution,
            docker_image=docker_image,
        )
        if baseline.ok:
            invalid = _invalid_case_row(case, "initial visible tests unexpectedly passed")
            invalid["execution"] = execution
            rows.append(invalid)
            continue

        run_id = f"{eval_run_id}-{case.case_id}"
        workspace = WorkspaceManager(run_root / "workspaces").prepare(base, run_id)
        trace = TraceLogger(reports_root / "traces" / f"{run_id}.jsonl", run_id)
        if case.case_id == "parse-config":
            demo_trace = trace.path
        task = Task(
            task_id=case.case_id,
            repo_path=workspace.path,
            instruction=case.instruction,
            test_command=case.test_command,
            max_steps=8,
            max_test_attempts=3,
            max_elapsed_seconds=120,
        )
        tools = ToolRegistry(
            workspace.path,
            case.test_command,
            test_timeout_seconds=30,
            execution_mode=execution,
            docker_image=docker_image,
            host_tests_approved=execution == "host",
        )
        result = Agent(
            ScriptedRepairModel(case),
            tools,
            tracer=trace,
            run_id=run_id,
        ).run(task)
        hidden = run_tests(
            workspace.path,
            [
                "python",
                "-m",
                "pytest",
                "/hidden"
                if execution == "docker"
                else str(case.case_dir / "hidden_tests"),
                "-q",
            ],
            timeout_seconds=30,
            execution_mode=execution,
            docker_image=docker_image,
            additional_mounts=(
                ((case.case_dir / "hidden_tests", "/hidden"),)
                if execution == "docker"
                else ()
            ),
        )
        success = result.status == "success" and hidden.ok
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "status": "success" if success else "failed",
                "agent_status": result.status,
                "baseline_exit_code": baseline.exit_code,
                "visible_passed": bool(result.test_result and result.test_result.ok),
                "hidden_passed": hidden.ok,
                "steps": result.steps,
                "tokens": result.tokens,
                "elapsed_ms": result.elapsed_ms,
                "model": MODEL_NAME,
                "execution": execution,
                "temperature": TEMPERATURE,
                "prompt_version": PROMPT_VERSION,
                "base_commit": workspace.base_commit,
                "trace_file": _portable_path(trace.path),
                "error": result.error or hidden.stderr[:500],
            }
        )

    ended_at = datetime.now(timezone.utc).isoformat()
    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        git_sha = "0" * 40
    dataset_sha = hashlib.sha256("".join(sorted(case.case_id for case in load_cases(cases_root))).encode()).hexdigest()
    manifest = build_run_manifest(run_id=eval_run_id, trace_id=eval_run_id, git_sha=git_sha,
                                  dataset_sha256=dataset_sha, started_at=started_at,
                                  ended_at=ended_at,
                                  status="success" if all(row.get("status") == "success" for row in rows) else "failed")
    reports_root.mkdir(parents=True, exist_ok=True)
    manifest_path = reports_root / "run_manifest.json"
    write_run_manifest(manifest_path, manifest)
    _write_csv(output_csv, rows)
    write_summary(rows, output_csv.with_suffix(".md"))
    if demo_trace and demo_trace.exists():
        shutil.copyfile(demo_trace, reports_root / "demo-trace.jsonl")
    return rows


def _prepare_base(case: CaseSpec, destination: Path) -> Path:
    assert case.case_dir is not None
    shutil.copytree(
        case.case_dir / "repo",
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    _git(destination, ["init", "-q"])
    _git(destination, ["config", "user.email", "evals@example.invalid"])
    _git(destination, ["config", "user.name", "CodePilot Evals"])
    _git(destination, ["add", "."])
    _git(destination, ["commit", "-q", "-m", f"baseline: {case.case_id}"])
    return destination


def _git(repo: Path, arguments: list[str]) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        shell=False,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
        },
    )


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _invalid_case_row(case: CaseSpec, error: str) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "category": case.category,
        "status": "invalid_case",
        "agent_status": "not_run",
        "baseline_exit_code": 0,
        "visible_passed": False,
        "hidden_passed": False,
        "steps": 0,
        "tokens": 0,
        "elapsed_ms": 0,
        "model": MODEL_NAME,
        "execution": "",
        "temperature": TEMPERATURE,
        "prompt_version": PROMPT_VERSION,
        "base_commit": "",
        "trace_file": "",
        "error": error,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("evaluation has no cases")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.runner")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    parser.add_argument("--output", type=Path, default=Path("reports/eval_results.csv"))
    parser.add_argument("--work-root", type=Path, default=Path(".tmp/evals"))
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument("--docker-image", default="codepilot-runner:0.1")
    parser.add_argument("--execution", choices=("docker", "host"), default="docker")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = run_evaluation(
        args.cases,
        args.output,
        args.work_root,
        args.reports_root,
        args.docker_image,
        args.execution,
    )
    succeeded = sum(row["status"] == "success" for row in rows)
    print(f"\u8bc4\u6d4b\uff1a{succeeded}/{len(rows)} \u9879\u901a\u8fc7")
    print(f"\u7ed3\u679c\u6587\u4ef6\uff1a{args.output.resolve()}")
    return 0 if succeeded == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
