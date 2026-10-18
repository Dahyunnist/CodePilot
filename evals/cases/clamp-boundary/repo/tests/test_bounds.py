from bounds import clamp


def test_upper_boundary_is_inclusive() -> None:
    assert clamp(5, 0, 5) == 5


def test_middle_value_is_unchanged() -> None:
    assert clamp(3, 0, 5) == 3
