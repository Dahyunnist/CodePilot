"""Small configuration parser used as CodePilot's first repair task."""


def parse_config(text: str) -> dict[str, str]:
    """Parse ``key=value`` lines into a dictionary.

    Blank lines are ignored. Invalid lines raise an error that includes the
    source line number.
    """
    config: dict[str, str] = {}

    # Intentional baseline bug: an empty string still produces one empty line.
    for line_number, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.strip()
        if not line and text:
            continue

        try:
            key, value = line.split("=", maxsplit=1)
        except ValueError as exc:
            raise ValueError(f"invalid config at line {line_number}") from exc

        config[key.strip()] = value.strip()

    return config

