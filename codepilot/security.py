"""Shared path rules for files that must not enter model context."""

import re
from pathlib import Path


_SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
_SENSITIVE_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "application_default_credentials.json",
    "credentials",
    "credentials.ini",
    "credentials.json",
    "credentials.xml",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "service-account.json",
    "token.json",
}
_SENSITIVE_DIRECTORIES = {".aws", ".azure", ".gcloud", ".ssh"}
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:aws[_-]?secret[_-]?access[_-]?key|aws[_-]?access[_-]?key(?:[_-]?id)?|"
    r"secret[_-]?access[_-]?key|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|private[_-]?key|authorization|credential|credentials|"
    r"password|passwd|secret|token)\b[\"']?(\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;#}]+)"
)
_KNOWN_SECRET = re.compile(
    r"(?i)\b(?:sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)
_BEARER_TOKEN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}")


def is_sensitive_file(path: str | Path) -> bool:
    """Recognize common credential stores and private-key files by path."""
    candidate = Path(path)
    name = candidate.name.casefold()
    parts = {part.casefold() for part in candidate.parts}
    config_parts = [part.casefold() for part in candidate.parts]
    cloud_config = any(
        config_parts[index : index + 2] == [".config", "gcloud"]
        for index in range(max(0, len(config_parts) - 1))
    )
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in _SENSITIVE_NAMES
        or bool(parts & _SENSITIVE_DIRECTORIES)
        or cloud_config
        or candidate.suffix.casefold() in _SENSITIVE_SUFFIXES
    )


def redact_sensitive_text(text: str) -> str:
    """Redact common credential forms before repository data reaches a model."""
    text = _PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = _KNOWN_SECRET.sub("[REDACTED TOKEN]", text)
    return _BEARER_TOKEN.sub(r"\1[REDACTED TOKEN]", text)
