from __future__ import annotations

from urllib3._collections import HTTPHeaderDict


def test_bytes_keys_support_read_membership_getlist_and_delete() -> None:
    headers = HTTPHeaderDict()
    headers.add("Warning", "first")
    headers.add("warning", "second")

    assert headers[b"WARNING"] == "first, second"
    assert b"warning" in headers
    assert headers.getlist(b"Warning") == ["first", "second"]

    del headers[b"WARNING"]

    assert b"warning" not in headers
