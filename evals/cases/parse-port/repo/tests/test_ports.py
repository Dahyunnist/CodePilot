from ports import parse_port


def test_invalid_text_uses_default() -> None:
    assert parse_port("invalid", 9000) == 9000


def test_numeric_text_is_parsed() -> None:
    assert parse_port("8080") == 8080
