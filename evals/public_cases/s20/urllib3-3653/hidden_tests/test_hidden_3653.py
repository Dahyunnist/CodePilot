from __future__ import annotations

import pytest

from urllib3._collections import HTTPHeaderDict


def test_bytes_key_write_and_string_key_read_remain_compatible() -> None:
    headers = HTTPHeaderDict()
    headers[b"X-Trace"] = "abc"

    assert headers["x-trace"] == "abc"
    assert headers.getlist("X-TRACE") == ["abc"]
    assert "X-TRACE" in headers


def test_missing_bytes_key_raises_key_error() -> None:
    with pytest.raises(KeyError):
        _ = HTTPHeaderDict()[b"missing"]
