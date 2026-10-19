import pytest

from audit.store import AuditStore
from audit.writer import record_events


def test_batch_is_deduplicated_in_order_and_written_once() -> None:
    store = AuditStore(existing_ids={"persisted"})
    events = [
        {"event_id": "a", "actor_id": "u1"},
        {"event_id": "persisted", "actor_id": "u2"},
        {"event_id": "b", "actor_id": "u3"},
        {"event_id": "a", "actor_id": "u4"},
    ]

    assert record_events(store, events) == 2
    assert [event["event_id"] for event in store.events] == ["a", "b"]
    assert store.write_count == 1


def test_invalid_event_rejects_the_whole_batch_before_any_write() -> None:
    store = AuditStore()

    with pytest.raises(ValueError, match="requires event_id and actor_id"):
        record_events(
            store,
            [
                {"event_id": "valid-first", "actor_id": "u1"},
                {"event_id": "missing-actor"},
            ],
        )

    assert store.events == []
    assert store.write_count == 0
