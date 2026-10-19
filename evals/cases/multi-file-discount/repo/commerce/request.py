"""Parse and validate public order request data."""


def parse_order(payload: dict[str, object]) -> dict[str, float | int]:
    unit_price = float(payload["unit_price"])
    quantity = int(payload["quantity"])
    discount_percent = float(payload.get("discount", 0))
    if not 0 <= discount_percent <= 1:
        raise ValueError("discount must be between 0 and 1")
    return {
        "unit_price": unit_price,
        "quantity": quantity,
        "discount_percent": discount_percent,
    }
