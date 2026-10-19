import pytest

from billing.invoice import create_invoice


def test_percentage_contract_decimal_rounding_and_invoice_fields() -> None:
    invoice = create_invoice(
        {"items": [{"unit_price": "0.335", "quantity": 3}], "discount_percent": 10}
    )

    assert invoice == {
        "subtotal": 1.01,
        "discount_amount": 0.10,
        "total": 0.91,
        "discount_percent": 10.0,
    }


def test_default_and_full_discount_keep_subtotal_correct() -> None:
    items = [{"unit_price": "12.50", "quantity": 2}]

    assert create_invoice({"items": items})["total"] == 25.0
    full = create_invoice({"items": items, "discount_percent": 100})
    assert full["subtotal"] == 25.0
    assert full["total"] == 0.0


@pytest.mark.parametrize("discount", [-0.01, 100.01, "NaN", "Infinity", "bad"])
def test_invalid_discount_percent_is_rejected(discount) -> None:
    with pytest.raises(ValueError, match="discount_percent"):
        create_invoice({"items": [{"unit_price": 1, "quantity": 1}], "discount_percent": discount})
