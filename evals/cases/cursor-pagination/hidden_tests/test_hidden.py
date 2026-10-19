import pytest
from catalog.page import get_page
from catalog.store import Store

def test_bad_limit_and_empty_after_cursor():
    store = Store([])
    with pytest.raises(ValueError):
        get_page(store, 0)
    assert get_page(store, 3, (100, "z")) == []
