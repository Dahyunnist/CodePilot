"""Precise repository editing and diff tools."""

import subprocess
from pathlib import Path

from codepilot.tools.repo import RepositoryToolError, resolve_repo_path


class PatchError(RepositoryToolError):
    """Raised when an exact replacement cannot be applied safely."""


def apply_patch(repo_root: Path, path: str, old_text: str, new_text: str) -> str:
    """Replace exactly one matching text block in a UTF-8 file."""
    if not old_text:
        raise PatchError("old_text must not be empty")
    target = resolve_repo_path(repo_root, path)
    if not target.is_file():
        raise PatchError("path is not a file")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError("file is not UTF-8 text") from exc

    matches = content.count(old_text)
    if matches != 1:
        raise PatchError(f"old_text must match exactly once; found {matches}")

    target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"updated {path}"


def git_diff(repo_root: Path, max_chars: int = 20_000) -> str:
    """Return the current unstaged Git diff without external diff drivers."""
    root = repo_root.resolve(strict=True)
    if not (root / ".git").exists():
        raise RepositoryToolError("repository has no .git directory")

    completed = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-color",
            "--",
            ".",
            ":(exclude).env",
            ":(exclude)**/.env",
            ":(exclude)*.key",
            ":(exclude)**/*.key",
            ":(exclude)*.pem",
            ":(exclude)**/*.pem",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise RepositoryToolError(completed.stderr.strip() or "git diff failed")
    if len(completed.stdout) <= max_chars:
        return completed.stdout
    return completed.stdout[:max_chars] + "\n... diff truncated"

