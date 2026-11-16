from config_loader import parse_options


def test_whitespace_only_input_is_empty():
    assert parse_options(" \t\n  ") == {}


def test_whitespace_before_comment_is_ignored():
    assert parse_options("  # ignored\nkey = value ") == {"key": "value"}
