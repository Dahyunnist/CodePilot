from pagination_api import make_response
from pagination_client import parse_response


def test_zero_cursor_is_not_treated_as_missing():
    assert parse_response({"items": ["first"], "next_cursor": 0}) == (["first"], 0)


def test_empty_page_keeps_canonical_contract():
    assert make_response([], cursor=0) == {"items": [], "next_cursor": None}
