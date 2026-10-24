def make_response(events: list[str], cursor: int = 0, limit: int = 2) -> dict:
    page = events[cursor : cursor + limit]
    next_cursor = cursor + len(page) if cursor + len(page) < len(events) else None
    return {"data": page, "nextCursor": next_cursor}
