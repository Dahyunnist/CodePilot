from settings import timeout_seconds


def test_configured_timeout_is_used() -> None:
    assert timeout_seconds({"timeout_seconds": 45}) == 45


def test_default_timeout_is_30() -> None:
    assert timeout_seconds({}) == 30
