def record_events(store, events: list[dict]) -> int:
    inserted = 0
    for event in events:
        if event["event_id"] not in store.event_ids:
            store.insert_event(event)
            inserted += 1
    return inserted
