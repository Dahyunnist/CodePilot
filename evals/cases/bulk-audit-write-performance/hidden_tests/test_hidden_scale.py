import pytest

from audit.store import AuditStore
from audit.writer import record_events


def test_large_batch_uses_one_write_and_preserves_input_order() -> None:
    store = AuditStore()
    events = [{"event_id": f"e-{index}", "actor_id": "worker"} for index in range(1000)]

    assert record_events(store, events) == 1000
    assert store.write_count == 1
    assert [event["event_id"] for event in store.events] == [f"e-{i}" for i in range(1000)]


def test_empty_or_all_existing_batch_performs_no_write() -> None:
    store = AuditStore(existing_ids={"old"})

    assert record_events(store, []) == 0
    assert record_events(store, [{"event_id": "old", "actor_id": "u"}]) == 0
    assert store.write_count == 0


@pytest.mark.parametrize("event", [{"event_id": "x"}, {"actor_id": "u"}])
def test_missing_required_identity_rejects_batch(event) -> None:
    store = AuditStore()
    with pytest.raises(ValueError):
        record_events(store, [event])
    assert store.write_count == 0
