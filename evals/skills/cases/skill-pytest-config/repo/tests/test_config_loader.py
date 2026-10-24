from config_loader import parse_options


def test_empty_input_returns_empty_mapping():
    assert parse_options("") == {}


def test_blank_lines_and_comments_are_ignored():
    assert parse_options("\n# mode=off\nmode=fast\n") == {"mode": "fast"}


def test_values_keep_additional_equals():
    assert parse_options("endpoint=https://host/path?a=b") == {
        "endpoint": "https://host/path?a=b"
    }
