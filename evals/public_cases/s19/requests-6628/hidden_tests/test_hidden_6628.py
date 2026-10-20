from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import pytest

from requests.exceptions import JSONDecodeError


def _raise_json_decode_error() -> None:
    raise JSONDecodeError("Extra data", '{"value": 1}{"value": 2}', 12)


def test_process_pool_transmits_error_and_remains_usable() -> None:
    with ProcessPoolExecutor(max_workers=1) as pool:
        failed = pool.submit(_raise_json_decode_error)

        with pytest.raises(JSONDecodeError, match="Extra data"):
            failed.result(timeout=10)

        assert pool.submit(pow, 2, 5).result(timeout=10) == 32
