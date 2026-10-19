from storage import Store

def import_records(store: Store, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        if row["record_id"] not in store.record_ids:
            store.insert(row)
            inserted += 1
    return inserted
