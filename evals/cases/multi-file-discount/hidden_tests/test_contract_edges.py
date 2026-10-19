import pytest

from commerce.invoice import create_invoice


def test_fractional_percent_and_rounding_across_invoice_layers() -> None:
    invoice = create_invoice(
        {"unit_price": 19.99, "quantity": 3, "discount_percent": 12.5}
    )

    assert invoice["discount_percent"] == 12.5
    assert invoice["total"] == 52.47


def test_full_discount_returns_zero_without_changing_subtotal() -> None:
    invoice = create_invoice(
        {"unit_price": 42.75, "quantity": 2, "discount_percent": 100}
    )

    assert invoice["subtotal"] == 85.5
    assert invoice["total"] == 0
