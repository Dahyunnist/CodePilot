from importer import import_records
from storage import Store

def test_deduplicates_and_bulk_writes_once():
    store = Store()
    rows = [{"record_id":"a","value":1},{"record_id":"a","value":2},{"record_id":"b","value":3}]
    assert import_records(store, rows) == 2
    assert [r["value"] for r in store.rows] == [1,3]
    assert store.write_calls == 1

def test_invalid_batch_is_atomic():
    store = Store()
    try:
        import_records(store, [{"record_id":"a","value":1},{"record_id":"b"}])
    except ValueError:
        pass
    else:
        assert False, "invalid row must be rejected"
    assert store.rows == []
    assert store.write_calls == 0
