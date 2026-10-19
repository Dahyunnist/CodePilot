from decimal import Decimal

import pytest

from billing.invoice import create_invoice
from billing.request import parse_order


def test_fractional_percent_is_not_truncated_or_reinterpreted() -> None:
    invoice = create_invoice(
        {"items": [{"unit_price": "19.99", "quantity": 3}], "discount_percent": "12.5"}
    )
    assert invoice["discount_percent"] == 12.5
    assert invoice["subtotal"] == 59.97
    assert invoice["discount_amount"] == 7.50
    assert invoice["total"] == 52.47


def test_request_keeps_decimal_precision_until_pricing() -> None:
    parsed = parse_order({"items": [], "discount_percent": "0.125"})
    assert parsed["discount_percent"] == Decimal("0.125")


def test_missing_discount_uses_zero_percent_not_zero_fraction() -> None:
    invoice = create_invoice({"items": [{"unit_price": 0.1, "quantity": 3}]})
    assert invoice["discount_percent"] == 0.0
    assert invoice["total"] == 0.30


@pytest.mark.parametrize("discount", [True, None])
def test_non_numeric_discount_is_rejected(discount) -> None:
    with pytest.raises(ValueError):
        parse_order({"items": [], "discount_percent": discount})
