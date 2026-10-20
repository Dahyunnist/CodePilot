from io import BytesIO

from urllib3.response import HTTPResponse


def test_full_read_appends_unconsumed_decoded_buffer_after_remaining_stream():
    original = b"prefix-middle-suffix"
    response = HTTPResponse(
        BytesIO(b"prefix-suffix"), preload_content=False
    )

    prefix = response.read(6, decode_content=True)
    response._decoded_buffer.put(b"middle")

    assert prefix + response.read(decode_content=True) == original


def test_full_read_with_cache_caches_complete_decoded_payload():
    original = b"left-middle-right"
    response = HTTPResponse(
        BytesIO(b"left-right"), preload_content=False
    )

    assert response.read(4, decode_content=True) == b"left"
    response._decoded_buffer.put(b"middle")

    assert response.read(decode_content=True, cache_content=True) == b"middle-right"
    assert response._body == b"middle-right"

