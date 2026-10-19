from importer import import_records
from storage import Store

def test_empty_and_existing_ids_do_not_write():
    store = Store()
    store.record_ids.add("old")
    assert import_records(store, []) == 0
    assert import_records(store, [{"record_id":"old","value":4}]) == 0
    assert store.write_calls == 0
