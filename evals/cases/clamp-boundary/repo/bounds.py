"""Numeric boundary helpers."""


def clamp(value: int, lower: int, upper: int) -> int:
    """Limit value to the inclusive lower and upper bounds."""
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    return max(lower, min(value, upper - 1))
