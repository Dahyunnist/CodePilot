import pytest

from config_parser import parse_config


def test_parses_one_setting() -> None:
    assert parse_config("host=localhost") == {"host": "localhost"}


def test_empty_input_returns_empty_config() -> None:
    """Expected to fail until the repair agent fixes the baseline bug."""
    assert parse_config("") == {}


def test_invalid_line_reports_line_number() -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_config("host=localhost\ninvalid")

