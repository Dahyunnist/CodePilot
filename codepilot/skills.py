"""Small, bounded repair workflows for common repository tasks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairSkill:
    skill_id: str
    title: str
    objective: str
    instructions: str
    exit_conditions: tuple[str, ...]
    allowed_tools: frozenset[str]
    max_steps: int
    max_test_attempts: int
    max_total_tokens: int


_READ_AND_PATCH = frozenset(
    {
        "read_project_instructions",
        "project_map",
        "search_symbols",
        "find_references",
        "list_files",
        "search_code",
        "read_file",
        "run_selected_tests",
        "run_tests",
        "apply_patch",
        "git_diff",
    }
)

SKILLS: dict[str, RepairSkill] = {
    "pytest-failure-triage": RepairSkill(
        skill_id="pytest-failure-triage",
        title="pytest 失败定位与修复",
        objective="根据 pytest 失败证据定位根因，提交最小修复并验证回归。",
        instructions=(
            "先读取失败测试和对应实现；区分测试环境错误与产品代码错误。"
            "有明确测试节点时先运行定向测试；避免无关重构。"
            "修复后运行定向测试和完整测试。若依赖缺失或需求有歧义，停止并说明需要用户处理的具体事项。"
        ),
        exit_conditions=(
            "完整测试通过后总结修复与验证证据。",
            "依赖缺失、无法复现或根因证据不足时停止，并说明用户需补充/执行的事项。",
            "需求存在歧义时暂停并向用户确认，不猜测行为契约。",
        ),
        allowed_tools=_READ_AND_PATCH | {"suggest_tests"},
        max_steps=10,
        max_test_attempts=3,
        max_total_tokens=18_000,
    ),
    "api-contract-check": RepairSkill(
        skill_id="api-contract-check",
        title="API 契约检查与跨文件修复",
        objective="核对 API 输入、输出、错误语义及调用方，修复跨文件契约不一致。",
        instructions=(
            "先识别公开入口、schema/类型定义、实现和直接调用方。"
            "不要只改单个实现而破坏兼容性；明确检查成功、边界和错误返回。"
            "按契约选择定向测试，再运行完整测试。若兼容策略不明确，先向用户询问。"
        ),
        exit_conditions=(
            "完整测试通过后总结 API 契约、修改文件和验证结果。",
            "兼容策略或错误语义不明确时暂停并询问用户。",
            "缺少测试环境或运行依赖时停止，并说明具体阻塞。",
        ),
        allowed_tools=_READ_AND_PATCH,
        max_steps=12,
        max_test_attempts=4,
        max_total_tokens=24_000,
    ),
}


def get_skill(skill_id: str | None) -> RepairSkill | None:
    """Return a known workflow or reject unknown profile names."""
    if skill_id is None:
        return None
    try:
        return SKILLS[skill_id]
    except KeyError as exc:
        raise ValueError(f"未知修复 Skill：{skill_id}") from exc
