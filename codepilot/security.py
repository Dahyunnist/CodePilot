"""Shared path rules for files that must not enter model context."""

from pathlib import Path


_SENSITIVE_SUFFIXES = {".key", ".pem"}


def is_sensitive_file(path: str | Path) -> bool:
    """Recognize dotenv variants and private-key files by their path name."""
    candidate = Path(path)
    name = candidate.name.casefold()
    return (
        name == ".env"
        or name.startswith(".env.")
        or candidate.suffix.casefold() in _SENSITIVE_SUFFIXES
    )
