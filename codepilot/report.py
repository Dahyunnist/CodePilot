"""Human-readable CLI result formatting."""

from codepilot.schemas import RunResult


def format_run_report(result: RunResult) -> str:
    """Render one complete run without hiding failure state."""
    lines = [
        f"Status: {result.status}",
        f"Steps: {result.steps}",
        f"Elapsed: {result.elapsed_ms} ms",
    ]
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

