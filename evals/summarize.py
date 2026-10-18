"""Markdown summaries for evaluation CSV rows."""

from pathlib import Path


def write_summary(rows: list[dict[str, object]], path: Path) -> Path:
    """Write aggregate metrics and truthful failure samples."""
    passed = sum(row["status"] == "success" for row in rows)
    lines = [
        "# Evaluation summary",
        "",
        f"- Cases: {len(rows)}",
        f"- Passed: {passed}",
        f"- Success rate: {passed / len(rows):.1%}" if rows else "- Success rate: n/a",
        f"- Model: `{rows[0]['model']}`" if rows else "- Model: n/a",
        f"- Temperature: `{rows[0]['temperature']}`" if rows else "- Temperature: n/a",
        f"- Prompt version: `{rows[0]['prompt_version']}`" if rows else "- Prompt version: n/a",
        "",
        "## Cases",
        "",
        "| Case | Category | Status | Visible | Hidden | Steps |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['category']} | {row['status']} | "
            f"{row['visible_passed']} | {row['hidden_passed']} | {row['steps']} |"
        )
    failures = [row for row in rows if row["status"] != "success"]
    lines.extend(["", "## Failure samples", ""])
    if not failures:
        lines.append("No scripted baseline failures after repair. Initial visible tests failed for every case.")
    else:
        for row in failures:
            lines.extend(
                [
                    f"### {row['case_id']}",
                    "",
                    f"- Agent status: `{row['agent_status']}`",
                    f"- Error: `{row['error']}`",
                    f"- Trace: `{row['trace_file']}`",
                    "",
                ]
            )
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
