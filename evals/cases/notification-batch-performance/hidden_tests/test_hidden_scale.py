from notify.dispatch import prepare_deliveries
from notify.store import SubscriptionStore


def test_query_cost_is_constant_for_large_recipient_batches() -> None:
    subscriptions = {
        recipient_id: {"active": True, "channel": "push"}
        for recipient_id in range(100)
    }
    store = SubscriptionStore(subscriptions)

    deliveries = prepare_deliveries(store, list(range(100)), "daily.digest")

    assert len(deliveries) == 100
    assert store.query_count == 1


def test_empty_batch_performs_no_repeated_lookups() -> None:
    store = SubscriptionStore({})
    assert prepare_deliveries(store, [], "noop") == []
    assert store.query_count == 0
