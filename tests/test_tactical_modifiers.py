"""Tactical modifier action tests."""
import pytest
from datetime import datetime, timezone

from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.haymaker import Haymaker
from kirby_combat.actions.set_action import Set
from kirby_combat.actions.brace import Brace
from kirby_combat.actions.dive_for_cover import DiveForCover, DiveForCoverResult
from kirby_combat.actions.pulling_punch import apply_pulling_punch
from kirby_combat.actions.held_action import HeldAction


def _c(id_: str, dex: int = 18) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_c("alice"), _c("bob", dex=12)],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- Haymaker -----

def test_haymaker_declare_emits_actiondeclared_with_haymaker_type():
    s = _session()
    s2, evt = Haymaker.declare(s, "alice")
    assert evt.combatant_id == "alice"
    assert evt.action_type == "haymaker"
    assert evt in s2.event_log


def test_haymaker_modifiers_present_after_declaration():
    s = _session()
    s2, _ = Haymaker.declare(s, "alice")
    mods = Haymaker.modifiers_for_pending_attack(s2, "alice")
    assert mods == {"dc_bonus": 4, "dcv_delta": -5}


def test_haymaker_modifiers_empty_without_declaration():
    s = _session()
    assert Haymaker.modifiers_for_pending_attack(s, "alice") == {}


def test_haymaker_declare_records_planned_attack_type():
    s = _session()
    s2, evt = Haymaker.declare(s, "alice", planned_attack_action_type="killing_strike")
    assert evt.parameters["planned_attack_action_type"] == "killing_strike"


# ---- Set -----

def test_set_declare_emits_actiondeclared():
    s = _session()
    s2, evt = Set.declare(s, "alice")
    assert evt.action_type == "set"
    assert evt in s2.event_log


def test_set_grants_plus_1_ocv_on_pending_ranged_attack():
    s = _session()
    s2, _ = Set.declare(s, "alice")
    assert Set.ocv_bonus(s2, "alice") == 1


def test_set_no_bonus_without_declaration():
    s = _session()
    assert Set.ocv_bonus(s, "alice") == 0


# ---- Brace -----

def test_brace_grants_half_range_penalty_modifier():
    s = _session()
    s2, _ = Brace.declare(s, "alice")
    mods = Brace.modifiers_for_pending_attack(s2, "alice")
    # Returns half-range-penalty flag and DCV delta
    assert mods.get("range_penalty_factor") == 0.5
    assert mods.get("dcv_factor") == 0.5


def test_brace_no_modifiers_without_declaration():
    s = _session()
    assert Brace.modifiers_for_pending_attack(s, "alice") == {}


def test_brace_declare_emits_actiondeclared():
    s = _session()
    s2, evt = Brace.declare(s, "alice")
    assert evt.action_type == "brace"
    assert evt in s2.event_log


# ---- Dive for Cover -----

def test_dive_for_cover_marks_aborting():
    s = _session()
    from kirby_combat.actions.reactive.abort import is_aborting
    s2, evt = DiveForCover.declare(s, "alice")
    assert is_aborting(s2, "alice") is True
    assert evt.to_action == "dive_for_cover"


def test_dive_for_cover_dex_roll_succeeds_when_under_target():
    # alice DEX=18 → target = 9 + 18//3 = 9 + 6 = 15
    # Roll 3+3+3=9, less than or equal to 15 → success
    result = DiveForCover.resolve_dex_roll(combatant_dex=18, dice=[3, 3, 3])
    assert result.success is True
    assert result.granted_partial_cover is True
    assert result.granted_prone is True


def test_dive_for_cover_dex_roll_fails_when_over_target():
    # alice DEX=18 → target=15. Roll 18 → fail
    result = DiveForCover.resolve_dex_roll(combatant_dex=18, dice=[6, 6, 6])
    assert result.success is False
    assert result.granted_partial_cover is False


def test_dive_for_cover_dex_roll_succeeds_on_equal():
    # DEX=18 → target=15. Roll exactly 15 → success (3d6 ≤ target)
    result = DiveForCover.resolve_dex_roll(combatant_dex=18, dice=[5, 5, 5])
    assert result.success is True


# ---- Pulling Punch -----

def test_pulling_punch_reduces_dc():
    assert apply_pulling_punch(base_dc=10, reduction=4) == 6


def test_pulling_punch_clamps_at_zero():
    assert apply_pulling_punch(base_dc=10, reduction=99) == 0


def test_pulling_punch_negative_reduction_treated_as_zero():
    assert apply_pulling_punch(base_dc=10, reduction=-3) == 10


def test_pulling_punch_zero_reduction_returns_full_dc():
    assert apply_pulling_punch(base_dc=10, reduction=0) == 10


# ---- Held Action -----

def test_held_action_declare_emits_heldactiondeclared():
    s = _session()
    s2, evt = HeldAction.declare(s, "alice", trigger_condition="when bob attacks")
    assert evt.combatant_id == "alice"
    assert evt.trigger_condition == "when bob attacks"
    assert evt in s2.event_log


def test_held_action_pending_lists_undischarged_held_actions():
    s = _session()
    s2, _ = HeldAction.declare(s, "alice", trigger_condition="when bob attacks")
    pending = HeldAction.get_pending(s2, "alice")
    assert len(pending) == 1
    assert pending[0].trigger_condition == "when bob attacks"


def test_held_action_release_emits_heldactionreleased_and_clears_pending():
    s = _session()
    s2, declared = HeldAction.declare(s, "alice", trigger_condition="when bob attacks")
    s3, released = HeldAction.release(s2, declared.id, trigger_observed="bob declared attack")
    assert released.held_event_id == declared.id
    assert released.trigger_observed == "bob declared attack"
    # After release, no pending held actions for alice
    assert HeldAction.get_pending(s3, "alice") == []


def test_held_action_declare_with_for_action():
    s = _session()
    s2, evt = HeldAction.declare(s, "bob", trigger_condition="when alice moves", for_action="strike")
    assert evt.for_action == "strike"
    assert evt.combatant_id == "bob"
