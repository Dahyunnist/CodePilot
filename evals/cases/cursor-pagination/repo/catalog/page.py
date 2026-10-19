def get_page(store, limit: int, cursor=None):
    items = sorted(store.all_items(), key=lambda item: item["created_at"])
    start = 0
    if cursor is not None:
        for index, item in enumerate(items):
            if item["created_at"] >= cursor:
                start = index + 1
    return items[start : start + limit]
