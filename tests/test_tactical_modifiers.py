"""Tactical modifier action tests."""
import pytest
from datetime import datetime, timezone

from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.haymaker import Haymaker
from kirby_combat.actions.set_action import Set
from kirby_combat.actions.brace import Brace, apply_brace_to_range_modifier
from kirby_combat.actions.dive_for_cover import DiveForCover, DiveForCoverResult
from kirby_combat.actions.pulling_punch import resolve_pulled_punch, PulledPunchOutcome
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

def test_brace_grants_plus_2_range_offset_and_half_dcv_per_6e2_p62():
    """Per 6E2 p62 §BRACE: +2 OCV that only offsets the Range Modifier; ½ DCV."""
    s = _session()
    s2, _ = Brace.declare(s, "alice")
    mods = Brace.modifiers_for_pending_attack(s2, "alice")
    assert mods.get("range_offset_bonus") == 2
    assert mods.get("dcv_factor") == 0.5


def test_brace_offsets_range_modifier_by_2_capped_at_zero():
    """Per 6E2 p62 §BRACE: the +2 OCV ONLY offsets the Range Modifier — it
    cannot produce a positive net OCV contribution from the range axis."""
    # Range -3 → effective -1 (offset by +2)
    assert apply_brace_to_range_modifier(-3) == -1
    # Range -8 → effective -6 (offset by +2)
    assert apply_brace_to_range_modifier(-8) == -6
    # Range -1 → effective 0 (offset by +2, capped at 0)
    assert apply_brace_to_range_modifier(-1) == 0
    # Range -2 → effective 0 (offset by +2, capped at 0)
    assert apply_brace_to_range_modifier(-2) == 0
    # Range 0 → effective 0 (no positive bonus from the range axis)
    assert apply_brace_to_range_modifier(0) == 0


def test_brace_no_modifiers_without_declaration():
    s = _session()
    assert Brace.modifiers_for_pending_attack(s, "alice") == {}


def test_brace_declare_emits_actiondeclared():
    s = _session()
    s2, evt = Brace.declare(s, "alice")
    assert evt.action_type == "brace"
    assert evt in s2.event_log


# ---- Dive for Cover (per 6E2 p87) -----

def test_dive_for_cover_marks_aborting():
    s = _session()
    from kirby_combat.actions.reactive.abort import is_aborting
    s2, evt = DiveForCover.declare(s, "alice")
    assert is_aborting(s2, "alice") is True
    assert evt.to_action == "dive_for_cover"


def test_dive_for_cover_success_prone_half_dcv_no_attacker_bonus():
    """Per 6E2 p87: successful Dive → prone at destination, ½ DCV, no attacker bonus."""
    # DEX=18 → target = 9 + 18//5 = 12. Roll 9 → success.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3],
        requested_destination=(10.0, 5.0, 0.0),
    )
    assert result.success is True
    assert result.diver_prone is True
    assert result.diver_dcv_factor == 0.5
    assert result.attacker_ocv_bonus == 0
    assert result.destination == (10.0, 5.0, 0.0)


def test_dive_for_cover_failure_half_dcv_no_movement_attacker_plus_2_ocv():
    """Per 6E2 p87: failed Dive → ½ DCV, no movement, attacker +2 OCV."""
    # DEX=18 → target = 9 + 18//5 = 12. Roll 18 → fail.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[6, 6, 6],
        requested_destination=(10.0, 5.0, 0.0),
    )
    assert result.success is False
    assert result.diver_prone is True
    assert result.diver_dcv_factor == 0.5
    assert result.attacker_ocv_bonus == 2
    assert result.destination is None    # didn't move


def test_dive_for_cover_dex_roll_succeeds_on_equal():
    """3d6 ≤ target → roll == target succeeds (HERO Characteristic Roll convention)."""
    # DEX=30 → target = 9 + 30//5 = 15. Roll 15 → success at boundary.
    result = DiveForCover.resolve_dex_roll(combatant_dex=30, dice=[5, 5, 5])
    assert result.success is True


def test_dive_for_cover_distance_penalty_applies_per_2m_per_6e2_p87():
    """Per 6E2 p87: -1 to DEX Roll per 2m moved (or fraction)."""
    # DEX=18 → base target = 9 + 18//5 = 12. Move 6m → -3 penalty → effective target 9.
    # Roll 9 → success at boundary.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3], distance_m=6.0,
    )
    assert result.success is True
    assert result.target == 9
    # Move 8m → -4 penalty → effective target 8. Roll 9 → fail.
    result_fail = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3], distance_m=8.0,
    )
    assert result_fail.success is False
    assert result_fail.target == 8


def test_dive_for_cover_distance_penalty_rounds_up_per_6e2_p87():
    """Per 6E2 p87: distance penalty applies for every 2m moved 'or fraction thereof'."""
    # 1m moved → ceil(1/2) = 1m penalty step; 3m moved → ceil(3/2) = 2 steps.
    # DEX=18 → base target 12. With 3m move → effective target 10.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3], distance_m=3.0,
    )
    assert result.target == 10


def test_dive_for_cover_underwater_penalty_doubled_per_6e2_p170():
    """Per 6E2 p170: underwater the distance penalty doubles to -1 per 1m moved."""
    # DEX=18, 6m underwater → -6 penalty. Base target 12 → effective 6.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3], distance_m=6.0, underwater=True,
    )
    assert result.target == 6


def test_dive_for_cover_avoids_aoe_when_destination_outside_radius():
    """Per 6E2 p87: AoE attack misses iff diver's destination is outside the AoE radius."""
    # DEX=18 → target = 9 + 18//5 = 12. Roll 9 → success. Destination (20, 0, 0)
    # is 20m from origin (0, 0, 0) — outside a 10m AoE.
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3],
        requested_destination=(20.0, 0.0, 0.0),
        attack_is_aoe=True,
        aoe_origin=(0.0, 0.0, 0.0),
        aoe_radius_m=10.0,
    )
    assert result.success is True
    assert result.avoids_aoe is True


def test_dive_for_cover_does_not_avoid_aoe_when_destination_inside_radius():
    """If destination is inside the AoE, the diver is still hit."""
    result = DiveForCover.resolve_dex_roll(
        combatant_dex=18, dice=[3, 3, 3],
        requested_destination=(3.0, 0.0, 0.0),
        attack_is_aoe=True,
        aoe_origin=(0.0, 0.0, 0.0),
        aoe_radius_m=10.0,
    )
    assert result.success is True
    assert result.avoids_aoe is False


# ---- Pulling Punch (per 6E2 p89) -----


def test_pull_one_5dc_increment_costs_neg_1_ocv():
    """Per 6E2 p89: -1 OCV per 5 DCs pulled. 5 DCs pulled → -1 OCV."""
    out = resolve_pulled_punch(base_dcs=12, dcs_pulled=5)
    assert isinstance(out, PulledPunchOutcome)
    assert out.ocv_modifier == -1
    assert out.dcs_pulled == 5


def test_pull_3_increments_costs_neg_3_ocv():
    """15 DCs pulled (3×5) → -3 OCV."""
    out = resolve_pulled_punch(base_dcs=30, dcs_pulled=15)
    assert out.ocv_modifier == -3
    assert out.dcs_pulled == 15


def test_pulling_halves_body_only_not_stun():
    """Per 6E2 p89: pulling halves BODY (full STUN)."""
    out = resolve_pulled_punch(base_dcs=10, dcs_pulled=4)
    assert out.body_multiplier == 0.5
    assert out.stun_multiplier == 1.0


def test_pulling_capped_at_half_attack_dcs():
    """Per 6E2 p89: max DCs pulled = base_dcs // 2."""
    out = resolve_pulled_punch(base_dcs=10, dcs_pulled=99)
    assert out.dcs_pulled == 5   # 10 // 2 = 5
    # 5 // 5 = 1 → -1 OCV
    assert out.ocv_modifier == -1


def test_pulling_overridden_when_attack_rolled_exactly_per_6e2_p89():
    """Per 6E2 p89: if Attack Roll exactly meets DCV (margin==0), the pull
    is forfeited and full damage applies. OCV cost still stands."""
    out = resolve_pulled_punch(
        base_dcs=20, dcs_pulled=10, rolled_exactly=True,
    )
    assert out.ocv_modifier == -2   # 10 // 5 = 2; cost still applies
    assert out.body_multiplier == 1.0
    assert out.stun_multiplier == 1.0
    assert out.rolled_exactly is True


def test_pulling_zero_dcs_no_changes():
    """Pulling 0 DCs → no OCV cost, no body change."""
    out = resolve_pulled_punch(base_dcs=10, dcs_pulled=0)
    assert out.ocv_modifier == 0
    assert out.body_multiplier == 1.0
    assert out.stun_multiplier == 1.0


def test_pulling_negative_dcs_treated_as_zero():
    out = resolve_pulled_punch(base_dcs=10, dcs_pulled=-5)
    assert out.dcs_pulled == 0
    assert out.body_multiplier == 1.0


def test_pulling_4_dcs_costs_0_ocv_under_5dc_threshold():
    """Pulling 4 DCs → -1 OCV per 5 DCs → 0 OCV cost (integer division)."""
    out = resolve_pulled_punch(base_dcs=20, dcs_pulled=4)
    assert out.ocv_modifier == 0
    assert out.body_multiplier == 0.5


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
