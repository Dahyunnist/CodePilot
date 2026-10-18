from ports import parse_port


def test_none_uses_default() -> None:
    assert parse_port(None, 7000) == 7000


def test_integer_is_preserved() -> None:
    assert parse_port(8081) == 8081
