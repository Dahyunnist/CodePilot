from typing import Any


def parse_order(payload: dict[str, Any]) -> dict[str, Any]:
    discount = float(payload.get("discount", 0.0))
    if not 0.0 <= discount <= 1.0:
        raise ValueError("discount must be between 0 and 1")
    return {"items": payload["items"], "discount": discount}
