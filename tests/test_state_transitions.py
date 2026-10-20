import pytest

from codepilot.schemas import AgentState, ChatMessage, Task


def make_state():
    task = Task(repo_path=".", instruction="inspect", test_command=["pytest"])
    return AgentState(task=task, messages=[ChatMessage(role="user", content="inspect")])


def test_default_task_has_total_token_budget():
    assert make_state().task.max_total_tokens == 40_000


def test_state_transition_allows_pause_resume_and_rejects_terminal_resume():
    state = make_state()
    state.transition("needs_approval")
    state.transition("running")
    state.transition("success")
    with pytest.raises(ValueError, match="非法 Agent 状态转移"):
        state.transition("running")
