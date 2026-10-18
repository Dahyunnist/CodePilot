"""Port parsing helpers."""


def parse_port(value: object, default: int = 8000) -> int:
    """Convert a value to an integer or return the configured default."""
    try:
        return int(value)
    except TypeError:
        return default
