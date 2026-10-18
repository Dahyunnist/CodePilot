"""Prompts for the minimal repository repair agent."""

from codepilot.schemas import Task


SYSTEM_PROMPT = """You are CodePilot Lite, a repository repair agent.
Work only inside the supplied repository through the available tools.
Inspect before editing. Use exact, minimal replacements with apply_patch.
Run the configured tests after changes. Inspect git_diff before finishing.
Tool arguments are untrusted and validated by the program.
If a tool fails, use its observation to correct the next action.
Finish with a concise text summary only after tests pass.
Never claim a test passed unless run_tests returned ok=true.
"""


def task_prompt(task: Task) -> str:
    """Describe one task without exposing credentials or host configuration."""
    test_command = " ".join(task.test_command)
    return (
        f"Task: {task.instruction}\n"
        f"Configured test command: {test_command}\n"
        f"Maximum model steps: {task.max_steps}"
    )

