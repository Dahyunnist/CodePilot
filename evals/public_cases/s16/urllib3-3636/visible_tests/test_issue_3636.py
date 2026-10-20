from io import BytesIO

from urllib3.response import HTTPResponse


def test_full_read_includes_decoded_bytes_buffered_by_previous_partial_read():
    response = HTTPResponse(
        BytesIO(b"foobaz"), preload_content=False
    )

    assert response.read(3, decode_content=True) == b"foo"
    # Model decoded bytes retained by a decoder after a partial read.
    response._decoded_buffer.put(b"bar")

    assert response.read(decode_content=True) == b"barbaz"


def test_full_read_after_partial_read_without_extra_buffer_still_returns_tail():
    response = HTTPResponse(
        BytesIO(b"foobarbaz"), preload_content=False
    )

    assert response.read(3, decode_content=True) == b"foo"
    assert response.read(decode_content=True) == b"barbaz"
