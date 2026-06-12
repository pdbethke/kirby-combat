from kirby_combat.actions.cv_parser import parse_cv, CVMod


def test_flat_positive():
    assert parse_cv("+2") == CVMod(kind="flat", value=2, velocity_divisor=0)


def test_flat_negative():
    assert parse_cv("-1") == CVMod(kind="flat", value=-1, velocity_divisor=0)


def test_flat_zero_forms():
    assert parse_cv("+0") == CVMod(kind="flat", value=0, velocity_divisor=0)
    assert parse_cv("0") == CVMod(kind="flat", value=0, velocity_divisor=0)


def test_not_applicable():
    assert parse_cv("--") == CVMod(kind="none", value=0, velocity_divisor=0)
    assert parse_cv("") == CVMod(kind="none", value=0, velocity_divisor=0)
    assert parse_cv(None) == CVMod(kind="none", value=0, velocity_divisor=0)


def test_velocity_based():
    # Velocity sign is carried in the `sign` field (value stays 0). A positive
    # divisor with sign=+1/-1 distinguishes +v/N from -v/N.
    assert parse_cv("+v/5") == CVMod(
        kind="velocity", value=0, velocity_divisor=5, sign=1
    )
    assert parse_cv("-v/10") == CVMod(
        kind="velocity", value=0, velocity_divisor=10, sign=-1
    )


def test_flat_value_helper_resolves_velocity_to_zero_without_velocity():
    # The integer a maneuver_view passes to MartialArtsModifiers when no velocity is known.
    assert parse_cv("+2").flat() == 2
    assert parse_cv("--").flat() == 0
    assert parse_cv("+v/5").flat() == 0  # velocity unknown at view time → 0 (documented v1)


def test_velocity_resolves_with_velocity():
    # +v/5 at velocity 20m → +4
    assert parse_cv("+v/5").resolve(velocity_m=20) == 4
    assert parse_cv("+2").resolve(velocity_m=20) == 2  # flat ignores velocity
    assert parse_cv("--").resolve(velocity_m=20) == 0
    # -v/10 at velocity 20m → -2
    assert parse_cv("-v/10").resolve(velocity_m=20) == -2
