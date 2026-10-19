class Store:
    def __init__(self, items):
        self.items = list(items)
        self.read_calls = 0

    def all_items(self):
        self.read_calls += 1
        return list(self.items)
