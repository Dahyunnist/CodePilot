"""Compose request parsing and pricing into an invoice response."""

from commerce.pricing import calculate_total
from commerce.request import parse_order


def create_invoice(payload: dict[str, object]) -> dict[str, float | int]:
    order = parse_order(payload)
    subtotal = order["unit_price"] * order["quantity"]
    return {
        "subtotal": round(subtotal, 2),
        "discount_percent": order["discount_percent"],
        "total": calculate_total(
            order["unit_price"], order["quantity"], order["discount_percent"]
        ),
    }
