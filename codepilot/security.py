"""Shared path rules for files that must not enter model context."""

import re
from pathlib import Path


_SENSITIVE_SUFFIXES = {".key", ".pem"}
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd|credential)\b"
    r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;#]+)"
)
_KNOWN_SECRET = re.compile(
    r"(?i)\b(?:sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)
_BEARER_TOKEN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}")


def is_sensitive_file(path: str | Path) -> bool:
    """Recognize dotenv variants and private-key files by their path name."""
    candidate = Path(path)
    name = candidate.name.casefold()
    return (
        name == ".env"
        or name.startswith(".env.")
        or candidate.suffix.casefold() in _SENSITIVE_SUFFIXES
    )


def redact_sensitive_text(text: str) -> str:
    """Redact common credential forms before repository data reaches a model."""
    text = _PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = _KNOWN_SECRET.sub("[REDACTED TOKEN]", text)
    return _BEARER_TOKEN.sub(r"\1[REDACTED TOKEN]", text)
