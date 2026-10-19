class Store:
    def __init__(self):
        self.rows = []
        self.record_ids = set()
        self.write_calls = 0

    def insert(self, row):
        self.write_calls += 1
        self.rows.append(row)
        self.record_ids.add(row["record_id"])
