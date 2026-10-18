from settings import timeout_seconds


def test_numeric_string_is_supported() -> None:
    assert timeout_seconds({"timeout_seconds": "12"}) == 12


def test_unrelated_keys_do_not_change_default() -> None:
    assert timeout_seconds({"other": 1}) == 30
