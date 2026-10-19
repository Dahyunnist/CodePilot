def prepare_deliveries(store, recipient_ids: list[int], event: str) -> list[dict]:
    deliveries = []
    for recipient_id in recipient_ids:
        subscription = store.get_subscription(recipient_id)
        if subscription and subscription["active"]:
            deliveries.append(
                {"recipient_id": recipient_id, "channel": subscription["channel"], "event": event}
            )
    return deliveries
