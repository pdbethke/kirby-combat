"""Telepathy — degree ladder + awareness."""
import pytest

from kirby_combat.mental.telepathy import resolve_telepathy, TelepathyResult
from tests.fixtures.synthetic_hero import synthetic_combatant


def _mentalist(id_: str = "a"):
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str = "t", ego: int = 10, is_mentalist: bool = False):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=ego, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=3, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        is_mentalist=is_mentalist,
    )


def test_telepathy_ego_plus_0_surface_thoughts():
    a = _mentalist()
    t = _target(ego=10)
    # roll 10 vs EGO 10 -> margin 0 -> surface_thoughts
    r = resolve_telepathy(a, t, [4, 3, 3])
    assert r.degree == "surface_thoughts"


def test_telepathy_ego_plus_10_specific_memories():
    a = _mentalist()
    t = _target(ego=10)
    # 10d6 sum to 20 -> margin 10 -> specific_memories
    r = resolve_telepathy(a, t, [2] * 10)
    assert r.degree == "specific_memories"


def test_telepathy_ego_plus_20_deep_thoughts_and_beliefs():
    a = _mentalist()
    t = _target(ego=10)
    r = resolve_telepathy(a, t, [3] * 10)   # 30 -> margin 20
    assert r.degree == "deep_thoughts"


def test_telepathy_ego_plus_30_subconscious_and_blocked_memories():
    a = _mentalist()
    t = _target(ego=10)
    r = resolve_telepathy(a, t, [4] * 10)   # 40 -> margin 30
    assert r.degree == "subconscious"


def test_telepathy_target_aware_only_if_mentalist_or_mental_awareness():
    a = _mentalist()
    # Plain target — no awareness
    r = resolve_telepathy(a, _target(ego=10, is_mentalist=False), [4, 3, 3])
    assert r.target_is_aware is False
    # Mentalist target — aware
    r2 = resolve_telepathy(a, _target(ego=10, is_mentalist=True), [4, 3, 3])
    assert r2.target_is_aware is True
    # Plain target with explicit Mental Awareness flag
    r3 = resolve_telepathy(
        a, _target(ego=10, is_mentalist=False), [4, 3, 3],
        target_has_mental_awareness=True,
    )
    assert r3.target_is_aware is True


def test_telepathy_does_not_cause_stun_or_body_damage():
    a = _mentalist()
    t = _target(ego=10)
    r = resolve_telepathy(a, t, [4, 3, 3])
    # Result has no damage fields whatsoever
    assert not hasattr(r, "stun")
    assert not hasattr(r, "body")
