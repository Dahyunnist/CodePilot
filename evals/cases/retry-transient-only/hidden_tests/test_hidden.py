from client import fetch_with_retry

def test_transient_failure_gives_up_after_three_attempts():
    calls = []
    waits = []
    def operation():
        calls.append(1)
        raise ConnectionError("offline")
    try:
        fetch_with_retry(operation, waits.append)
    except ConnectionError:
        pass
    else:
        assert False, "last transient error should propagate"
    assert len(calls) == 3
    assert waits == [0.1, 0.2]
