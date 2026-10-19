class SubscriptionStore:
    def __init__(self, subscriptions: dict[int, dict]):
        self._subscriptions = subscriptions
        self.query_count = 0

    def get_subscription(self, recipient_id: int) -> dict | None:
        self.query_count += 1
        return self._subscriptions.get(recipient_id)
