import pickle

from requests.exceptions import JSONDecodeError


def test_json_decode_error_can_round_trip_through_pickle():
    document = '{"responseCode":["706"],"data":null}{"responseCode":["706"],"data":null}'
    original = JSONDecodeError("Extra data", document, 36)

    restored = pickle.loads(pickle.dumps(original))

    assert type(restored) is JSONDecodeError
    assert repr(restored) == repr(original)
    assert restored.msg == original.msg
    assert restored.doc == original.doc
    assert restored.pos == original.pos
