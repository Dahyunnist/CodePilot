def parse_options(text: str) -> dict[str, str]:
    options = {}
    for line in text.splitlines():
        key, value = line.split("=", 1)
        options[key.strip()] = value.strip()
    return options
