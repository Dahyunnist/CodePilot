from concurrent.futures import ProcessPoolExecutor

from requests.exceptions import JSONDecodeError


def raise_json_error():
    raise JSONDecodeError("Extra data", '{"a":1}{"b":2}', 7)


def test_process_pool_transports_json_error_and_remains_usable():
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(raise_json_error)
        try:
            future.result(timeout=10)
        except JSONDecodeError as error:
            assert error.msg == "Extra data"
            assert error.doc == '{"a":1}{"b":2}'
            assert error.pos == 7
        else:
            raise AssertionError("worker exception should reach the caller")

        assert executor.submit(pow, 2, 5).result(timeout=10) == 32
