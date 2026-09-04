"""Entangle action tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.entangle import Entangle, EntangleResult


def _c(id_: str, str_: int = 20) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=str_, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("alice", str_=30), _c("bob", str_=20)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- apply ----

def test_apply_creates_entangle_state_on_target():
    s = _session()
    s2, result = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    assert isinstance(result, EntangleResult)
    assert result.target_id == "bob"
    assert result.method == "applied"
    assert result.body_remaining == 8
    assert result.escaped is False


def test_apply_emits_entangleapplied_event():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    kinds = [e.kind for e in s2.event_log]
    assert "EntangleApplied" in kinds
    # Most recent EntangleApplied should reference bob
    last_ea = next(e for e in reversed(s2.event_log) if e.kind == "EntangleApplied")
    assert last_ea.target_id == "bob"
    assert last_ea.entangle_body == 8


def test_apply_emits_action_declared_and_resolved_too():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    kinds = [e.kind for e in s2.event_log]
    assert "ActionDeclared" in kinds
    assert "ActionResolved" in kinds


# ---- is_entangled ----

def test_is_entangled_false_when_no_entangle():
    s = _session()
    assert Entangle.is_entangled(s, "bob") == (False, None)


def test_is_entangled_returns_remaining_body():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    is_e, body = Entangle.is_entangled(s2, "bob")
    assert is_e is True
    assert body == 8


# ---- modifiers ----

def test_modifiers_zero_dcv_half_ocv_when_entangled():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    mods = Entangle.modifiers(s2, "bob")
    assert mods == {"ocv_factor": 0.5, "dcv_factor": 0.0}


def test_modifiers_empty_when_not_entangled():
    s = _session()
    assert Entangle.modifiers(s, "bob") == {}


# ---- escape: casual STR ----

def test_casual_str_escape_reduces_body_by_str_over_10_minus_pd():
    # caller rolled 3 BODY; entangle PD 4 soaked it all -> damage_body=0
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=0, escape_type="casual",
    )
    assert esc.method == "casual_str"
    assert esc.damage_to_entangle_body == 0      # 30//10 = 3, minus pd 4 → 0
    assert esc.body_remaining == 8
    assert esc.escaped is False


def test_casual_str_escape_with_high_str_chips_away():
    # caller counted 8 BODY; entangle PD 4 -> damage_body=4
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=4, escape_type="casual",
    )
    assert esc.damage_to_entangle_body == 4
    assert esc.body_remaining == 4
    assert esc.escaped is False


# ---- escape: full STR ----

def test_full_str_escape_uses_str_over_5_minus_pd():
    # caller counted 6 BODY; entangle PD 4 -> damage_body=2
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=2, escape_type="full",
    )
    assert esc.method == "full_str"
    assert esc.damage_to_entangle_body == 2
    assert esc.body_remaining == 6


def test_full_str_escape_can_break_free_in_one_attempt():
    # caller counted 16 BODY; entangle PD 4 -> damage_body=12 >= BODY 8: free
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=12, escape_type="full",
    )
    assert esc.escaped is True
    assert esc.body_remaining == 0


def test_escape_emits_entangleescape_event():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, _ = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=12, escape_type="full",
    )
    kinds = [e.kind for e in s3.event_log]
    assert "EntangleEscape" in kinds


def test_escape_when_not_entangled_raises():
    s = _session()
    with pytest.raises(ValueError, match="not entangled"):
        Entangle.escape_attempt(
            s, target_id="bob", damage_body=2, escape_type="full",
        )


def test_unknown_escape_type_raises():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    with pytest.raises(ValueError, match="escape_type"):
        Entangle.escape_attempt(
            s2, target_id="bob", damage_body=0, escape_type="bogus",
        )


# ---- multi-attempt scenario ----

def test_multiple_casual_attempts_eventually_break_through():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=2, entangle_ed=4,    # weak entangle
    )
    # caller counted 8 BODY; entangle PD 2 -> damage_body=6. After 1 attempt: body=2.
    s3, esc1 = Entangle.escape_attempt(s2, target_id="bob", damage_body=6, escape_type="casual")
    assert esc1.body_remaining == 2
    assert esc1.escaped is False

    # Another 6 damage attempt → body 2 - 6 → escaped, body_remaining=0
    s4, esc2 = Entangle.escape_attempt(s3, target_id="bob", damage_body=6, escape_type="casual")
    assert esc2.escaped is True
    assert esc2.body_remaining == 0

    # No longer entangled
    assert Entangle.is_entangled(s4, "bob") == (False, None)


def test_modifiers_clear_after_escape():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, _ = Entangle.escape_attempt(s2, target_id="bob", damage_body=12, escape_type="full")
    assert Entangle.modifiers(s3, "bob") == {}


# ---- Cannot Be Escaped With Teleportation (NOTELEPORT, 6E1 p220) ----

class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _power(xmlid, mods=()):
    return _Stub(xmlid=xmlid, assigned_modifiers=[
        _Stub(xmlid=x, levels=lv) for x, lv in mods])


def test_noteleport_levels_reads_stacked_levels():
    from kirby_combat.actions.entangle import noteleport_levels
    assert noteleport_levels(_power("ENTANGLE")) == 0
    assert noteleport_levels(_power("ENTANGLE", [("NOTELEPORT", 0)])) == 1
    # corpus shape: "Cannot Be Escaped With Teleportation (x2; +1/2)"
    assert noteleport_levels(_power("FORCEWALL", [("NOTELEPORT", 2)])) == 2
    # repeated purchases also stack
    assert noteleport_levels(
        _power("ENTANGLE", [("NOTELEPORT", 1), ("NOTELEPORT", 1)])) == 2


def test_can_teleport_escape_ap_cancels_level_for_level():
    from kirby_combat.actions.entangle import can_teleport_escape
    plain_ent = _power("ENTANGLE")
    locked_ent = _power("ENTANGLE", [("NOTELEPORT", 2)])
    plain_tp = _power("TELEPORTATION")
    ap1_tp = _power("TELEPORTATION", [("ARMORPIERCING", 1)])
    ap2_tp = _power("TELEPORTATION", [("ARMORPIERCING", 2)])
    # 6E1 p218: teleport escape works normally
    assert can_teleport_escape(plain_ent, plain_tp)
    assert can_teleport_escape(plain_ent, None)
    # 6E1 p220: NOTELEPORT blocks; AP cancels level for level
    assert not can_teleport_escape(locked_ent, plain_tp)
    assert not can_teleport_escape(locked_ent, ap1_tp)
    assert can_teleport_escape(locked_ent, ap2_tp)


def test_teleport_escape_frees_target():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, res = Entangle.teleport_escape(s2, target_id="bob")
    assert res.escaped is True and res.method == "teleport"
    assert res.damage_to_entangle_body == 0     # no BODY done — just gone
    is_e, _body = Entangle.is_entangled(s3, "bob")
    assert is_e is False


def test_teleport_escape_blocked_by_noteleport():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
        no_teleport_levels=1,
    )
    s3, res = Entangle.teleport_escape(s2, target_id="bob")
    assert res.escaped is False and res.method == "teleport_blocked"
    is_e, body = Entangle.is_entangled(s3, "bob")
    assert is_e is True and body == 8
    # a blocked attempt leaves no event behind
    assert len(s3.event_log) == len(s2.event_log)


def test_teleport_escape_armor_piercing_cancels():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
        no_teleport_levels=2,
    )
    # AP 1 < NOTELEPORT 2 → still trapped
    _s, res = Entangle.teleport_escape(s2, target_id="bob", teleport_ap_levels=1)
    assert res.escaped is False
    # AP 2 meets NOTELEPORT 2 → free (6E1 p220: AP cancels the advantage)
    s3, res = Entangle.teleport_escape(s2, target_id="bob", teleport_ap_levels=2)
    assert res.escaped is True
    assert Entangle.is_entangled(s3, "bob") == (False, None)


# ---- breakout margins (6E2 p126) ----

def test_breakout_margin_tiers():
    from kirby_combat.actions.entangle import breakout
    # >= 2x remaining -> free + Full Phase
    assert breakout(8, 4) == breakout(8, 4)  # deterministic
    assert breakout(8, 4).escaped and breakout(8, 4).action_regained == "full"
    assert breakout(4, 2).action_regained == "full"      # exactly 2x
    # >= 1x but < 2x -> free + Half Phase
    r = breakout(5, 4)
    assert r.escaped and r.action_regained == "half"
    assert breakout(4, 4).action_regained == "half"      # exactly 1x
    # < remaining -> still trapped
    r = breakout(3, 4)
    assert not r.escaped and r.action_regained == "none"
    assert not breakout(0, 4).escaped


def test_stacked_entangle_highest_plus_one():
    from kirby_combat.actions.entangle import stacked_entangle
    # 6E1 p217: highest BODY +1 for the additional Entangle; highest PD/ED
    assert stacked_entangle(6, 4, 4, 3, 2, 5) == (7, 4, 5)
    assert stacked_entangle(3, 2, 2, 6, 5, 3) == (7, 5, 3)
    # no existing entangle -> the new one, unmodified
    assert stacked_entangle(0, 0, 0, 6, 5, 3) == (6, 5, 3)


def test_str_escape_dice():
    from kirby_combat.actions.entangle import str_escape_dice
    assert str_escape_dice(30) == 6                 # full STR: STR//5 dice
    assert str_escape_dice(30, casual=True) == 3    # casual = half STR (6E1 p134)
    assert str_escape_dice(43) == 8
    assert str_escape_dice(43, casual=True) == 4    # (43//2)//5
    assert str_escape_dice(4) == 0


def test_escape_attempt_takes_rolled_body():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    # caller rolled 5 BODY (already past the entangle's defense)
    s3, res = Entangle.escape_attempt(
        s2, target_id="bob", damage_body=5, escape_type="full",
    )
    assert not res.escaped and res.body_remaining == 3
    # 2x the remaining 3 -> full-phase breakout
    s4, res = Entangle.escape_attempt(
        s3, target_id="bob", damage_body=6, escape_type="full",
    )
    assert res.escaped
    assert Entangle.is_entangled(s4, "bob") == (False, None)


def test_str_escape_end_cost():
    from kirby_combat.actions.entangle import str_escape_end_cost
    assert str_escape_end_cost(30) == 3          # 1 per 10 STR used (6E2 p41)
    assert str_escape_end_cost(30, casual=True) == 1   # half used (6E1 p134)
    assert str_escape_end_cost(60, casual=True) == 3
    assert str_escape_end_cost(5) == 0


def test_entangle_default_defenses():
    from kirby_combat.actions.entangle import entangle_default_defenses
    assert entangle_default_defenses(6) == (6, 6)      # 1 PD + 1 ED per 1d6
    assert entangle_default_defenses(0) == (0, 0)


def test_entangled_dcv_factor_single_source():
    from kirby_combat.actions.entangle import ENTANGLED_DCV_FACTOR
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    assert Entangle.modifiers(s2, "bob")["dcv_factor"] == ENTANGLED_DCV_FACTOR
