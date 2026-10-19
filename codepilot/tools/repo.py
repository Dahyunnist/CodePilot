"""Read-only repository tools with path and output boundaries."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from codepilot.security import is_sensitive_file


IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache"}
_IGNORED_PARTS_CASEFOLD = {part.casefold() for part in IGNORED_PARTS}


class RepositoryToolError(RuntimeError):
    """Base error for repository inspection tools."""


class PathPolicyError(RepositoryToolError):
    """Raised when a requested path leaves the repository or targets a secret."""


def resolve_repo_path(
    repo_root: Path,
    raw_path: str,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve a relative path and enforce the repository boundary."""
    root = repo_root.resolve(strict=True)
    relative = Path(raw_path)
    if relative.is_absolute():
        raise PathPolicyError("absolute paths are not allowed")
    if any(part.casefold() in _IGNORED_PARTS_CASEFOLD for part in relative.parts):
        raise PathPolicyError("internal repository paths are not allowed")
    if is_sensitive_file(relative):
        raise PathPolicyError("sensitive files are not allowed")

    candidate = (root / relative).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise PathPolicyError("path escapes repository root")
    resolved_relative = candidate.relative_to(root)
    if any(part.casefold() in _IGNORED_PARTS_CASEFOLD for part in resolved_relative.parts):
        raise PathPolicyError("internal repository paths are not allowed")
    if is_sensitive_file(resolved_relative):
        raise PathPolicyError("sensitive files are not allowed")
    if must_exist and not candidate.exists():
        raise FileNotFoundError(raw_path)
    return candidate


def list_files(repo_root: Path, path: str = ".", max_files: int = 200) -> str:
    """List repository-relative files without entering ignored directories."""
    target = resolve_repo_path(repo_root, path)
    candidates = [target] if target.is_file() else target.rglob("*")
    files: list[str] = []
    root = repo_root.resolve(strict=True)

    for candidate in candidates:
        relative = candidate.relative_to(root)
        if any(part.casefold() in _IGNORED_PARTS_CASEFOLD for part in relative.parts):
            continue
        if is_sensitive_file(candidate):
            continue
        if candidate.is_file():
            files.append(relative.as_posix())
            if len(files) >= max_files:
                break

    return "\n".join(sorted(files))


def read_file(
    repo_root: Path,
    path: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_chars: int = 12_000,
) -> str:
    """Read a bounded inclusive line range from one UTF-8 source file."""
    target = resolve_repo_path(repo_root, path)
    if not target.is_file():
        raise RepositoryToolError("path is not a file")
    if end_line is not None and end_line < start_line:
        raise RepositoryToolError("end_line must be greater than or equal to start_line")

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RepositoryToolError("file is not UTF-8 text") from exc

    selected = lines[start_line - 1 : end_line]
    numbered = "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(selected, start=start_line)
    )
    return _truncate(numbered, max_chars)


def search_code(
    repo_root: Path,
    query: str,
    path: str = ".",
    max_results: int = 50,
    max_chars: int = 12_000,
) -> str:
    """Search source text with ripgrep, falling back to Python scanning."""
    target = resolve_repo_path(repo_root, path)
    root = repo_root.resolve(strict=True)
    relative_target = target.relative_to(root).as_posix() or "."
    rg = shutil.which("rg")

    if rg:
        command = [
            rg,
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--glob",
            "!.git/**",
            "--glob",
            "!__pycache__/**",
            "--iglob",
            "!.env",
            "--iglob",
            "!**/.env",
            "--iglob",
            "!.env.*",
            "--iglob",
            "!**/.env.*",
            "--iglob",
            "!*.key",
            "--iglob",
            "!**/*.key",
            "--iglob",
            "!*.pem",
            "--iglob",
            "!**/*.pem",
            "--",
            query,
            relative_target,
        ]
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if completed.returncode not in (0, 1):
            raise RepositoryToolError(completed.stderr.strip() or "ripgrep failed")
        lines = completed.stdout.splitlines()[:max_results]
        return _truncate("\n".join(lines), max_chars)

    matches: list[str] = []
    paths = [target] if target.is_file() else target.rglob("*")
    for candidate in paths:
        if not candidate.is_file() or candidate.stat().st_size > 1_000_000:
            continue
        relative = candidate.relative_to(root)
        if any(part.casefold() in _IGNORED_PARTS_CASEFOLD for part in relative.parts):
            continue
        if is_sensitive_file(candidate):
            continue
        if not candidate.resolve(strict=False).is_relative_to(root):
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if query in line:
                matches.append(f"{relative.as_posix()}:{line_number}:{line}")
                if len(matches) >= max_results:
                    return _truncate("\n".join(matches), max_chars)
    return _truncate("\n".join(matches), max_chars)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n... truncated {omitted} characters"

