"""Clean per-run Git workspaces."""

from __future__ import annotations

import subprocess
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    """Raised when an isolated workspace cannot be prepared."""


@dataclass(frozen=True)
class Workspace:
    """Metadata for one clean repository clone."""

    source: Path
    path: Path
    base_commit: str


class WorkspaceManager:
    """Create a clean local clone for every task run."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()

    def prepare(self, source: Path, run_id: str) -> Workspace:
        """Clone committed source state into a new, unique directory."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise WorkspaceError("run_id must be a safe directory name")
        source = source.resolve(strict=True)
        if not (source / ".git").exists():
            raise WorkspaceError("source must be a Git repository")
        tracked = _git_output(source, ["ls-files"]).splitlines()
        sensitive = [
            path
            for path in tracked
            if Path(path).name == ".env" or Path(path).suffix.lower() in {".key", ".pem"}
        ]
        if sensitive:
            raise WorkspaceError(
                "source tracks sensitive files: " + ", ".join(sensitive[:5])
            )

        destination = self.base_dir / run_id
        if destination.exists():
            raise WorkspaceError(f"workspace already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            completed = subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", str(source), str(destination)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                shell=False,
            )
            if completed.returncode != 0:
                raise WorkspaceError(completed.stderr.strip() or "git clone failed")

            commit = _git_output(destination, ["rev-parse", "HEAD"])
            if _git_output(destination, ["status", "--porcelain"]):
                raise WorkspaceError("new workspace is not clean")
            return Workspace(source=source, path=destination, base_commit=commit)
        except Exception:
            if destination.exists() and destination.parent == self.base_dir:
                shutil.rmtree(destination)
            raise


def _git_output(repo: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise WorkspaceError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()
