from pathlib import Path

def write_summary(rows: list[dict[str, object]], path: Path) -> Path:
    passed = sum(row["status"] == "success" for row in rows)
    categories = {
        "empty-input": "空输入",
        "exception-handling": "异常处理",
        "configuration": "配置读取",
        "boundary-condition": "边界条件",
        "small-refactor": "小型重构",
    }
    lines = [
        "# 评测摘要",
        "",
        f"- 案例数：{len(rows)}",
        f"- 通过数：{passed}",
        f"- 通过率：{passed / len(rows):.1%}" if rows else "- 通过率：无",
        f"- 模型：{rows[0]['model']}" if rows else "- 模型：无",
        f"- Temperature：{rows[0]['temperature']}" if rows else "- Temperature：无",
        f"- Prompt 版本：{rows[0]['prompt_version']}" if rows else "- Prompt 版本：无",
        "",
        "## 案例",
        "",
        "| 案例 | 类型 | 状态 | 可见测试 | 隐藏测试 | 步数 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        status = "通过" if row["status"] == "success" else "失败"
        category = categories.get(str(row["category"]), str(row["category"]))
        lines.append(
            f"| {row['case_id']} | {category} | {status} | "
            f"{row['visible_passed']} | {row['hidden_passed']} | {row['steps']} |"
        )
    failures = [row for row in rows if row["status"] != "success"]
    lines.extend(["", "## 失败详情", ""])
    if not failures:
        lines.append("所有案例修复后均通过；每个案例的基线可见测试最初均失败。")
    else:
        for row in failures:
            lines.extend([
                f"### {row['case_id']}",
                "",
                f"- Agent 状态：{row['agent_status']}",
                f"- 错误：{row['error']}",
                f"- 轨迹：{row['trace_file']}",
                "",
            ])
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
