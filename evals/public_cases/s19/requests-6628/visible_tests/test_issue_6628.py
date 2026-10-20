from __future__ import annotations

import pickle

from requests.exceptions import JSONDecodeError


def test_json_decode_error_can_be_pickled() -> None:
    original = JSONDecodeError("Extra data", '{"value": 1}{"value": 2}', 12)

    restored = pickle.loads(pickle.dumps(original))

    assert type(restored) is JSONDecodeError
    assert repr(restored) == repr(original)
    assert restored.msg == original.msg
    assert restored.doc == original.doc
    assert restored.pos == original.pos
