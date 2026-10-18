"""Human-readable CLI result formatting."""

from pathlib import Path

from codepilot.schemas import RunResult


def format_run_report(result: RunResult) -> str:
    """Render one complete run without hiding failure state."""
    lines = [
        f"Run ID: {result.run_id}",
        f"Status: {result.status}",
        f"Steps: {result.steps}",
        f"Tokens: {result.tokens}",
        f"Elapsed: {result.elapsed_ms} ms",
    ]
    if result.workspace_path:
        lines.append(f"Workspace: {result.workspace_path}")
    if result.trace_file:
        lines.append(f"Trace: {result.trace_file}")
    if result.report_file:
        lines.append(f"Report: {result.report_file}")
    if result.test_result is None:
        lines.append("Tests: not run")
    else:
        lines.append(
            "Tests: "
            f"{'passed' if result.test_result.ok else 'failed'} "
            f"(exit={result.test_result.exit_code}, "
            f"duration={result.test_result.duration_ms} ms)"
        )
        if result.test_result.stdout:
            lines.extend(["", "Test stdout:", result.test_result.stdout.rstrip()])
        if result.test_result.stderr:
            lines.extend(["", "Test stderr:", result.test_result.stderr.rstrip()])
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.final_text:
        lines.extend(["", "Model summary:", result.final_text])
    lines.extend(["", "Git diff:", result.diff or "(no diff)"])
    return "\n".join(lines)


def write_markdown_report(result: RunResult, path: Path) -> Path:
    """Persist the same bounded result as a reviewable Markdown artifact."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# CodePilot run `{result.run_id}`",
        "",
        f"- Status: `{result.status}`",
        f"- Steps: `{result.steps}`",
        f"- Tokens: `{result.tokens}`",
        f"- Elapsed: `{result.elapsed_ms} ms`",
        f"- Failure type: `{result.failure_type or 'none'}`",
        f"- Workspace: `{result.workspace_path or 'none'}`",
        f"- Trace: `{result.trace_file or 'none'}`",
    ]
    if result.error:
        body.extend(["", "## Error", "", result.error])
    if result.test_result:
        body.extend(
            [
                "",
                "## Test summary",
                "",
                f"- Passed: `{result.test_result.ok}`",
                f"- Exit code: `{result.test_result.exit_code}`",
                f"- Duration: `{result.test_result.duration_ms} ms`",
                f"- Error type: `{result.test_result.error_type or 'none'}`",
            ]
        )
    body.extend(["", "## Git diff", "", "```diff", result.diff.rstrip(), "```", ""])
    path.write_text("\n".join(body), encoding="utf-8")
    return path

