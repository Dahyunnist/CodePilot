from notify.dispatch import prepare_deliveries
from notify.store import SubscriptionStore


def test_batch_lookup_reduces_query_count_and_preserves_delivery_contract() -> None:
    store = SubscriptionStore(
        {
            1: {"active": True, "channel": "email"},
            2: {"active": False, "channel": "sms"},
            3: {"active": True, "channel": "push"},
        }
    )

    deliveries = prepare_deliveries(store, [3, 1, 3, 2, 999], "invoice.ready")

    assert deliveries == [
        {"recipient_id": 3, "channel": "push", "event": "invoice.ready"},
        {"recipient_id": 1, "channel": "email", "event": "invoice.ready"},
    ]
    assert store.query_count == 1


def test_empty_batch_does_not_query_the_store() -> None:
    store = SubscriptionStore({})

    assert prepare_deliveries(store, [], "noop") == []
    assert store.query_count == 0
