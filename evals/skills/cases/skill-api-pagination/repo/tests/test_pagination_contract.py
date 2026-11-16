from pagination_api import make_response
from pagination_client import parse_response


def test_server_emits_canonical_fields_and_client_reads_them():
    response = make_response(["a", "b", "c"])
    assert response == {"items": ["a", "b"], "next_cursor": 2}
    assert parse_response(response) == (["a", "b"], 2)


def test_last_page_uses_null_cursor():
    response = make_response(["a", "b", "c"], cursor=2)
    assert response == {"items": ["c"], "next_cursor": None}
    assert parse_response(response) == (["c"], None)
