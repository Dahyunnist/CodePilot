from billing.pricing import calculate_totals
from billing.request import parse_order


def create_invoice(payload: dict) -> dict:
    order = parse_order(payload)
    totals = calculate_totals(order["items"], order["discount"])
    return {**totals, "discount_percent": order["discount"] * 100}
