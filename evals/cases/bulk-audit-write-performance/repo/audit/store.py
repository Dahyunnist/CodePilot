class AuditStore:
    def __init__(self, existing_ids: set[str] | None = None):
        self.events: list[dict] = []
        self.event_ids = set(existing_ids or set())
        self.write_count = 0

    def insert_event(self, event: dict) -> None:
        self.write_count += 1
        self.events.append(event)
        self.event_ids.add(event["event_id"])
