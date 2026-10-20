import tracemalloc

import pytest
from urllib3.response import BytesQueueBuffer


@pytest.mark.parametrize("chunk_size,read_size", [(32, 7), (1_048_576, 4096), (16_777_216, 16_384)])
def test_partial_reads_keep_data_and_exact_size(chunk_size, read_size):
    chunk = bytes(range(251)) * (chunk_size // 251) + b"z" * (chunk_size % 251)
    buffer = BytesQueueBuffer()
    buffer.put(chunk)
    output = bytearray()

    while len(buffer):
        part = buffer.get(read_size)
        assert isinstance(part, bytes)
        assert 0 < len(part) <= read_size
        output.extend(part)
        assert len(buffer) == len(chunk) - len(output)

    assert bytes(output) == chunk


def test_large_tail_stays_shared_after_small_read():
    chunk = b"q" * (48 * 1024 * 1024)
    buffer = BytesQueueBuffer()
    buffer.put(chunk)
    tracemalloc.start()
    try:
        assert buffer.get(8192) == b"q" * 8192
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(buffer) == len(chunk) - 8192
    assert peak < 2 * 1024 * 1024
