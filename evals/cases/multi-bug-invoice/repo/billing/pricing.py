from typing import Any


def calculate_totals(items: list[dict[str, Any]], discount: float) -> dict[str, float]:
    subtotal = sum(round(float(item["unit_price"]) * int(item["quantity"]), 2) for item in items)
    discount_amount = round(subtotal * discount, 2)
    return {"subtotal": subtotal, "discount_amount": discount_amount, "total": round(subtotal - discount_amount, 2)}
