"""Mental Entangle — paralysis state, EGO escape."""
import pytest

from kirby_combat.mental.mental_entangle import (
    apply_mental_entangle, attempt_mental_escape,
    can_use_mental_powers, can_use_physical_powers,
    MentalEntangleState, MentalEntangleResult, MentalEscapeResult,
)
from kirby_combat.models import Combatant


def _mentalist(id_: str = "a") -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str = "t", ego: int = 10, md: int = 0) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=ego, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=md, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_mental_entangle_applies_mental_paralysis_state():
    a = _mentalist()
    t = _target(ego=10, md=0)
    r = apply_mental_entangle(a, t, [4, 4, 4, 4])  # 16 BODY
    assert r.body_dealt_to_entangle == 16
    assert r.state.blocks_mental_powers is True


def test_mental_entangle_body_defended_by_mental_defense_only():
    a = _mentalist()
    t = _target(ego=10, md=8)
    r = apply_mental_entangle(a, t, [4, 4, 4, 4])  # 16 - 8 = 8
    assert r.body_dealt_to_entangle == 8


def test_mental_entangle_escape_uses_ego_not_str():
    t = _target(ego=15, md=0)
    state = MentalEntangleState(
        target_id=t.id, entangle_body=10, initial_body=10,
        blocks_mental_powers=True,
    )
    # EGO 15 -> TN 12 (9 + 3). roll 12 -> success
    r = attempt_mental_escape(t, state, [4, 4, 4])
    assert r.method == "ego_contest"
    assert r.success is True


def test_mental_entangled_combatant_cannot_use_mental_powers():
    state = MentalEntangleState(
        target_id="t", entangle_body=10, initial_body=10,
        blocks_mental_powers=True,
    )
    assert can_use_mental_powers(state) is False


def test_mental_entangled_combatant_can_still_use_physical_powers():
    state = MentalEntangleState(
        target_id="t", entangle_body=10, initial_body=10,
        blocks_mental_powers=True, blocks_physical_powers=False,
    )
    assert can_use_physical_powers(state) is True
