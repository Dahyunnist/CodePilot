"""Calculate monetary totals for an order."""


def calculate_total(
    unit_price: float, quantity: int, discount_percent: float
) -> float:
    subtotal = unit_price * quantity
    return round(subtotal * (1 - discount_percent), 2)
