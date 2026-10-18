import pytest

from config_parser import parse_config


def test_whitespace_only_input_is_empty() -> None:
    assert parse_config("   \n\t") == {}


def test_invalid_first_line_keeps_line_number() -> None:
    with pytest.raises(ValueError, match="line 1"):
        parse_config("invalid")
