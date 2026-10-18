"""Application setting readers."""


def timeout_seconds(config: dict[str, object]) -> int:
    """Return the configured timeout or the 30 second default."""
    return int(config.get("timeot_seconds", 30))
