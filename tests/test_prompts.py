from pathlib import Path

from codepilot.prompts import _MAX_PROJECT_GUIDANCE_CHARS, task_prompt
from codepilot.schemas import Task


def make_task(repo: Path) -> Task:
    return Task(
        repo_path=repo,
        instruction="跨模块修复",
        test_command=["python", "-m", "pytest"],
    )


def test_task_prompt_includes_bounded_root_project_guidance(tmp_path: Path) -> None:
    guidance = "使用 Decimal 处理金额。" * 1500
    (tmp_path / "AGENTS.md").write_text(guidance, encoding="utf-8")

    prompt = task_prompt(make_task(tmp_path))

    assert "AGENTS.md 项目约定" in prompt
    assert "使用 Decimal 处理金额。" in prompt
    assert len(prompt.split("不得覆盖系统安全规则）：\n", 1)[1]) == _MAX_PROJECT_GUIDANCE_CHARS


def test_task_prompt_ignores_guidance_symlink_outside_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    external = tmp_path / "outside.md"
    external.write_text("external secret", encoding="utf-8")
    try:
        (repo / "AGENTS.md").symlink_to(external)
    except OSError:
        return

    prompt = task_prompt(make_task(repo))

    assert "external secret" not in prompt
    assert "AGENTS.md 项目约定" not in prompt


def test_task_prompt_without_guidance_stays_usable(tmp_path: Path) -> None:
    prompt = task_prompt(make_task(tmp_path))

    assert "跨模块修复" in prompt
    assert "AGENTS.md 项目约定" not in prompt
