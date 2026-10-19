from client import fetch_with_retry

def test_retries_transient_errors_with_exponential_delay():
    calls = []
    delays = []
    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError()
        return "ok"
    assert fetch_with_retry(operation, delays.append) == "ok"
    assert len(calls) == 3
    assert delays == [0.1, 0.2]

def test_does_not_retry_permanent_error():
    calls = []
    def operation():
        calls.append(1)
        raise ValueError("bad input")
    try:
        fetch_with_retry(operation, lambda delay: None)
    except ValueError:
        pass
    else:
        assert False, "permanent error should propagate"
    assert len(calls) == 1
