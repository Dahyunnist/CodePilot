import tracemalloc

from urllib3.response import BytesQueueBuffer


def test_partial_read_does_not_copy_the_unconsumed_large_tail():
    chunk = b"x" * (64 * 1024 * 1024)
    buffer = BytesQueueBuffer()
    buffer.put(chunk)

    tracemalloc.start()
    try:
        result = buffer.get(64 * 1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result == b"x" * (64 * 1024)
    assert len(buffer) == len(chunk) - len(result)
    assert peak < 2 * 1024 * 1024


def test_partial_reads_reconstruct_original_content():
    payload = bytes(range(251)) * 4096
    buffer = BytesQueueBuffer()
    buffer.put(payload)

    output = bytearray()
    while len(buffer):
        output.extend(buffer.get(7777))

    assert bytes(output) == payload
