import pytest

from bounds import clamp


def test_values_outside_range_are_clamped() -> None:
    assert clamp(-2, 0, 5) == 0
    assert clamp(9, 0, 5) == 5


def test_reversed_bounds_are_rejected() -> None:
    with pytest.raises(ValueError):
        clamp(1, 2, 1)
