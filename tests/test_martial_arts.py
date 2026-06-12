"""Martial Arts action — declare + modifier projection.

Per 6E2 p90-93 §MARTIAL MANEUVERS, verified via Codex (throwback) on 2026-04-25.
"""
from __future__ import annotations

from kirby_combat.actions.martial_arts import MartialArts
from kirby_combat.dice import FakeRoller
from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


def _session() -> CombatSession:
    fighter = Combatant(
        id="fighter", name="Fighter",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=20, con=20, pre=15, rec=8,
        pd=8, ed=8, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
    )
    return CombatSession.create(
        id="ma1", combatants=[fighter], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def test_declare_martial_strike_applies_ocv_dcv_and_dc_modifiers():
    """Martial Strike per 6E2 p93: +0 OCV, +2 DCV, STR +2d6."""
    s = _session()
    s, _ = MartialArts.declare(s, "fighter", maneuver_id="martial_strike")
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert mods["maneuver_id"] == "martial_strike"
    assert mods["ocv_delta"] == 0
    assert mods["dcv_delta"] == 2
    assert mods["dc_bonus"] == 2
    assert mods["damage_type"] == "normal"


def test_martial_throw_puts_target_prone():
    """Martial Throw per 6E2 p93 — 'STR +v/5; Target Falls'.

    The target_falls flag tells the resolver to apply the Prone status to the
    target after a successful Throw.
    """
    s = _session()
    s, _ = MartialArts.declare(s, "fighter", maneuver_id="martial_throw")
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert mods["target_falls"] is True


def test_martial_block_declared_as_abort_gets_plus_ocv_for_opposed_roll():
    """Martial Block per 6E2 p93: +2 OCV, +2 DCV, Block + Abort.

    The block flag tells the reactive layer to wire this through Block.resolve
    rather than through the standard attack pipeline; +2 OCV is bonus over
    normal Block.
    """
    s = _session()
    s, _ = MartialArts.declare(s, "fighter", maneuver_id="martial_block")
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert mods["is_block"] is True
    assert mods["ocv_delta"] == 2
    assert mods["dcv_delta"] == 2


def test_martial_killing_strike_changes_damage_type_to_killing():
    """Killing Strike per 6E2 p93: -2 OCV, +0 DCV, HKA 1/2d6 (killing damage)."""
    s = _session()
    s, _ = MartialArts.declare(s, "fighter", maneuver_id="killing_strike")
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert mods["damage_type"] == "killing"
    assert mods["ocv_delta"] == -2


def test_csl_applied_per_csl_allocation_field():
    """CSL allocation shifts the base maneuver values."""
    s = _session()
    s, _ = MartialArts.declare(
        s, "fighter",
        maneuver_id="martial_strike",
        csl_allocation={"ocv": 2, "dcv": 1, "dc": 1},
    )
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    # base: +0 OCV, +2 DCV, +2 DC
    assert mods["ocv_delta"] == 0 + 2
    assert mods["dcv_delta"] == 2 + 1
    assert mods["dc_bonus"] == 2 + 1


def test_extra_dc_levels_add_to_dc_bonus():
    """+1 Damage Class element stacks on top of base maneuver dc_bonus."""
    s = _session()
    s, _ = MartialArts.declare(
        s, "fighter",
        maneuver_id="offensive_strike",   # base = +4 DC
        extra_dc_levels=3,
    )
    mods = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert mods["dc_bonus"] == 4 + 3


def test_unknown_maneuver_raises():
    s = _session()
    try:
        MartialArts.declare(s, "fighter", maneuver_id="not_a_maneuver")
    except ValueError:
        return
    raise AssertionError("declare() should reject unknown maneuver ids")


# ─────────────────────────────────────────────────────────────────────────────
# Task 3.3 — per-character maneuvers (NOT in the static MARTIAL_MANEUVERS table)
# flow through MartialArtsModifiers + the existing declare/resolve seam.
# ─────────────────────────────────────────────────────────────────────────────

from kirby_combat.actions.martial_arts import (  # noqa: E402
    MartialArtsModifiers,
    modifiers_for_maneuver_view,
)
from kirby_combat.hero_view import MartialManeuverView  # noqa: E402


def _mv(**kw) -> MartialManeuverView:
    base = dict(
        maneuver_id="MANEUVER:Aikijutsu Strike", name="Aikijutsu Strike",
        ocv=0, dcv=2, dc_bonus=4, add_str=True, damage_type="normal",
        phase="1/2", category_is_ranged=False, reach_m=2.0, is_attack=True,
        is_block=False, is_dodge=False, target_falls=False, effect="",
    )
    base.update(kw)
    return MartialManeuverView(**base)


def test_modifiers_from_a_custom_maneuver_not_in_the_static_table():
    # "Aikijutsu Strike" is NOT in MARTIAL_MANEUVERS — must still build modifiers.
    mods = MartialArtsModifiers.from_maneuver_view(_mv())
    assert mods.ocv == 0
    assert mods.dcv == 2
    assert mods.dc_bonus == 4          # before extra DCs / CSL
    assert mods.damage_type == "normal"
    assert mods.is_block is False


def test_from_maneuver_view_applies_extra_dc_and_csl():
    mods = MartialArtsModifiers.from_maneuver_view(
        _mv(), extra_dc_levels=2, csl_allocation={"dc": 1})
    assert mods.dc_bonus == 4 + 2 + 1


def test_from_maneuver_view_folds_csl_into_ocv_and_dcv():
    mods = MartialArtsModifiers.from_maneuver_view(
        _mv(), csl_allocation={"ocv": 2, "dcv": 1})
    assert mods.ocv == 0 + 2
    assert mods.dcv == 2 + 1


def test_block_maneuver_marks_is_block():
    mods = MartialArtsModifiers.from_maneuver_view(
        _mv(name="Defensive Block", is_block=True, is_attack=False))
    assert mods.is_block is True


def test_custom_maneuver_flows_through_declare_and_resolve_seam():
    """The per-character maneuver round-trips through the SAME declare →
    modifiers_for_pending_attack path the static maneuvers use, without ever
    being present in MARTIAL_MANEUVERS."""
    from kirby_combat.tables import MARTIAL_MANEUVERS

    s = _session()
    mods = modifiers_for_maneuver_view(
        _mv(target_falls=True), extra_dc_levels=1, csl_allocation={"ocv": 1})
    assert mods.maneuver_id not in MARTIAL_MANEUVERS  # truly custom

    s, _ = MartialArts.declare(s, "fighter", modifiers=mods)
    out = MartialArts.modifiers_for_pending_attack(s, "fighter")
    assert out["maneuver_id"] == "MANEUVER:Aikijutsu Strike"
    assert out["ocv_delta"] == 0 + 1
    assert out["dcv_delta"] == 2
    assert out["dc_bonus"] == 4 + 1
    assert out["target_falls"] is True
    assert out["damage_type"] == "normal"
