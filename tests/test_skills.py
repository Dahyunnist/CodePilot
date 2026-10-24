from collections.abc import Sequence

import pytest

from codepilot.agent import Agent
from codepilot.prompts import task_prompt
from codepilot.schemas import ChatMessage, ModelReply, Task, ToolCall, ToolResult, ToolSpec
from codepilot.skills import SKILLS, get_skill


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        function={
            "name": name,
            "description": f"{name} tool",
            "parameters": {"type": "object", "properties": {}},
        }
    )


def test_builtin_skills_define_inputs_tools_budgets_and_exit_guidance():
    pytest_skill = get_skill("pytest-failure-triage")
    api_skill = get_skill("api-contract-check")

    assert pytest_skill is not None and api_skill is not None
    assert "run_tests" in pytest_skill.allowed_tools
    assert "apply_patch" in api_skill.allowed_tools
    assert pytest_skill.max_total_tokens == 18_000
    assert api_skill.max_steps == 12
    assert "完整测试" in pytest_skill.instructions
    assert "兼容性" in api_skill.instructions
    assert any("完整测试通过" in item for item in pytest_skill.exit_conditions)
    assert any("询问用户" in item for item in api_skill.exit_conditions)
    with pytest.raises(ValueError, match="未知修复 Skill"):
        get_skill("not-a-skill")


def test_task_prompt_includes_selected_skill_and_limits(tmp_path):
    task = Task(
        repo_path=tmp_path,
        instruction="排查失败的 API 契约测试",
        test_command=["python", "-m", "pytest"],
        skill_id="api-contract-check",
    )

    prompt = task_prompt(task)

    assert "API 契约检查与跨文件修复" in prompt
    assert "公开入口、schema/类型定义" in prompt
    assert "24000 tokens" in prompt
    assert "退出条件" in prompt
    assert "apply_patch" in prompt


class SkillModel:
    def __init__(self):
        self.tools_by_request = []
        self.replies = [
            ModelReply(tool_calls=[ToolCall(id="rogue", name="delete_repo", arguments={})]),
            ModelReply(tool_calls=[ToolCall(id="tests", name="run_tests", arguments={})]),
            ModelReply(text="测试通过，修复完成。"),
        ]

    def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        *,
        max_completion_tokens: int | None = None,
    ) -> ModelReply:
        self.tools_by_request.append({tool.function.name for tool in tools})
        return self.replies.pop(0)


class SkillTools:
    def __init__(self):
        self.specs = (_spec("delete_repo"), _spec("run_tests"), _spec("git_diff"))
        self.executed = []

    def read_tools(self):
        return self.specs

    def execute(self, call):
        self.executed.append(call.name)
        if call.name == "git_diff":
            return ToolResult(tool_name=call.name, ok=True)
        return ToolResult(tool_name=call.name, ok=True, exit_code=0)


def test_skill_tool_allowlist_is_enforced_in_prompt_and_execution(tmp_path):
    (tmp_path / ".git").mkdir()
    model = SkillModel()
    tools = SkillTools()
    task = Task(
        repo_path=tmp_path,
        instruction="修复测试失败",
        test_command=["python", "-m", "pytest"],
        skill_id="pytest-failure-triage",
    )

    result = Agent(model, tools).run(task)

    assert result.status == "success"
    assert all("delete_repo" not in names for names in model.tools_by_request)
    assert "run_tests" in model.tools_by_request[0]
    assert tools.executed == ["run_tests", "git_diff"]
    assert result.tool_results[0].error_type == "policy"
