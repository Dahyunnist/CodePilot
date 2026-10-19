from catalog.page import get_page
from catalog.store import Store

def entries():
    return [{"created_at":1,"item_id":"b"},{"created_at":1,"item_id":"a"},{"created_at":2,"item_id":"c"}]

def test_stable_cursor_pages_without_duplicates():
    store = Store(entries())
    first = get_page(store, 2)
    second = get_page(store, 2, (first[-1]["created_at"], first[-1]["item_id"]))
    assert [x["item_id"] for x in first + second] == ["a","b","c"]
    assert store.read_calls == 2

def test_one_read_per_page():
    store = Store(entries())
    get_page(store, 1)
    assert store.read_calls == 1
