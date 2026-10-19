import pytest

from commerce.invoice import create_invoice


def test_percent_discount_is_applied_and_returned() -> None:
    invoice = create_invoice(
        {"unit_price": 100, "quantity": 2, "discount_percent": 15}
    )

    assert invoice == {
        "subtotal": 200,
        "discount_percent": 15,
        "total": 170,
    }


def test_discount_defaults_to_zero() -> None:
    invoice = create_invoice({"unit_price": 12.5, "quantity": 4})

    assert invoice["discount_percent"] == 0
    assert invoice["total"] == 50


@pytest.mark.parametrize("discount", [-0.01, 100.01])
def test_discount_outside_percentage_range_is_rejected(discount: float) -> None:
    with pytest.raises(ValueError):
        create_invoice(
            {"unit_price": 100, "quantity": 1, "discount_percent": discount}
        )
