from pathlib import Path
from codepilot.schemas import RunResult

_STATUS = {
    "success": "成功",
    "failed": "失败",
    "timeout": "超时",
    "budget_exceeded": "超过预算",
    "needs_approval": "需要批准",
    "needs_user_input": "需要用户补充信息",
    "max_steps": "达到步数上限",
}

def format_run_report(result: RunResult) -> str:
    lines = [
        f"运行编号：{result.run_id}",
        f"状态：{_STATUS.get(result.status, result.status)}",
        f"模型步骤：{result.steps}",
        f"Token 数：{result.tokens}",
        f"耗时：{result.elapsed_ms} 毫秒",
    ]
    if result.workspace_path:
        lines.append(f"工作区：{result.workspace_path}")
    if result.trace_file:
        lines.append(f"轨迹：{result.trace_file}")
    if result.report_file:
        lines.append(f"报告：{result.report_file}")
    if result.test_result is None:
        lines.append("测试：未运行")
    else:
        test_status = "通过" if result.test_result.ok else "失败"
        lines.append(
            f"测试：{test_status} "
            f"（退出码={result.test_result.exit_code}，"
            f"耗时={result.test_result.duration_ms} 毫秒）"
        )
        if result.test_result.stdout:
            lines.extend(["", "测试标准输出：", result.test_result.stdout.rstrip()])
        if result.test_result.stderr:
            lines.extend(["", "测试错误输出：", result.test_result.stderr.rstrip()])
    if result.error:
        lines.append(f"错误（原始诊断）：{result.error}")
    if result.final_text:
        lines.extend(["", "模型总结：", result.final_text])
    lines.extend(["", "Git 差异：", result.diff or "（无差异）"])
    return "\n".join(lines)

def write_markdown_report(result: RunResult, path: Path) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# CodePilot 运行记录 {result.run_id}",
        "",
        f"- 状态：{_STATUS.get(result.status, result.status)}",
        f"- 模型步骤：{result.steps}",
        f"- Token 数：{result.tokens}",
        f"- 耗时：{result.elapsed_ms} 毫秒",
        f"- 失败类型：{result.failure_type or '无'}",
        f"- 工作区：{result.workspace_path or '无'}",
        f"- 轨迹：{result.trace_file or '无'}",
    ]
    if result.error:
        body.extend(["", "## 错误", "", result.error])
    if result.test_result:
        body.extend([
            "",
            "## 测试摘要",
            "",
            f"- 是否通过：{result.test_result.ok}",
            f"- 退出码：{result.test_result.exit_code}",
            f"- 耗时：{result.test_result.duration_ms} 毫秒",
            f"- 错误类型：{result.test_result.error_type or '无'}",
        ])
    body.extend(["", "## Git 差异", "", result.diff.rstrip(), ""])
    path.write_text("\n".join(body), encoding="utf-8")
    return path
