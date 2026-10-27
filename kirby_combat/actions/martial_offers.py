"""What the menu offers a martial artist, and anyone a weapon is lying near.

Enumeration (`kirby_combat/enumeration.py`) asks here for three groups of
offers, each gated on the fact its rule turns on:

* MANEUVERS (``maneuver``), one per (attack maneuver x enemy) the engine can
  resolve (`maneuver_effects.decode_maneuver`), gated by what the maneuver
  must follow and how it reaches him:
    - Must Follow Grab: only the man he is HOLDING (6E2 p.64);
    - Must Follow Block: only the man whose blow he Blocked, in the Phase
      after (`reactive.blocking.block_follow_ups`);
    - Disarm / Takeaway: one offer per weapon in the target's hand
      (`kirby_combat.weapons`) --- a Disarm "knocks a weapon or other object
      out of the target's hand" (6E2 p.62), so a man holding nothing is not
      offered one;
    - FMove: a charge that can END in contact on his full Running (6E2 p.72),
      the gate `move_by` takes; everything else: within reach now.
* DISARM (``disarm``), the plain maneuver (6E2 p.62), per weapon in reach.
* PICK UP (``pick_up_weapon``), per weapon on the ground within reach, or
  within a Half Move (6E2 p.62: "a Half Phase Action to move to the weapon
  ... plus another Half Phase Action to pick it up").
"""
from __future__ import annotations

from typing import Any, Callable

from kirby_combat.actions.maneuver_effects import (
    MustFollow, UnbuildableManeuver, decode_maneuver, describe_effect,
)


def _legal_action(**kw):
    from kirby_combat.enumeration import LegalAction

    return LegalAction(**kw)


def charge_connects(actor, enemy_id: str, *, scene, budget_m: float, reach_m: float) -> bool:
    """Can a charge on ``budget_m`` of Running END within ``reach_m`` of him?

    The `move_by` offer's own gate (`enumeration.py`, 6E2 p.56 + p.72), asked
    of the same engine predicate. No geometry to judge means no gate, the
    contract every scene gate in enumeration follows.
    """
    from kirby_combat.enumeration import _xyz_dist
    from kirby_combat import within_reach
    from kirby_combat.reach import movement_reach

    positions = (getattr(scene, "combatant_positions", None) or {}) if scene is not None else {}
    here, there = positions.get(actor.id), positions.get(enemy_id)
    if here is None or there is None:
        return True
    if budget_m <= 0.0:
        return False
    out = movement_reach("running", here, there, budget_m, scene, combatant_id=actor.id)
    return bool(out.reachable) and within_reach(_xyz_dist(out.landing, there), reach_m).in_reach


def maneuver_offers(
    actor, *, maneuvers: list, enemies: list, melee_gate: Callable[[str], str],
    friendly: Callable[[Any], str], strength: int, scene, held_target_ids: frozenset[str],
    block_follow_ups: frozenset[str], weapons,
) -> list:
    """Every ``maneuver`` offer (see the module docstring)."""
    out: list = []
    running_m = float(actor.hero.characteristic_value("RUNNING") or 0)
    for mv in maneuvers:
        if not getattr(mv, "is_attack", False) or getattr(mv, "category_is_ranged", False):
            continue
        # ONLY WHAT THE ENGINE CAN RESOLVE. A refused maneuver is not offered:
        # the menu does not promise what the resolver would have to
        # approximate.
        try:
            effect = decode_maneuver(mv)
        except UnbuildableManeuver:
            continue
        name = getattr(mv, "name", None) or "Maneuver"
        does = describe_effect(effect, strength=int(strength))
        for enemy in enemies:
            if effect.must_follow is MustFollow.GRAB and enemy.id not in held_target_ids:
                continue
            if effect.must_follow is MustFollow.BLOCK and enemy.id not in block_follow_ups:
                continue
            if effect.fmove:
                if not charge_connects(actor, enemy.id, scene=scene,
                                       budget_m=running_m, reach_m=float(mv.reach_m)):
                    continue
            elif melee_gate(enemy.id) != "direct":
                # A maneuver at the end of a Half Move is not offered:
                # `move_strike` does not compose with one.
                continue
            targets: list = [None]
            if effect.disarm or effect.grab_weapon:
                if weapons is None:
                    continue
                targets = list(weapons.held_by(enemy.id))
            for weapon in targets:
                suffix = f":{weapon.owner_id}:{weapon.weapon_id}" if weapon else ""
                what = f" — his {weapon.name}" if weapon else ""
                out.append(_legal_action(
                    action_id=f"maneuver:{enemy.id}:{mv.maneuver_id}{suffix}",
                    kind="maneuver", target_id=enemy.id,
                    power_xmlid="MANEUVER", power_name=name,
                    summary=(f"{name} vs {friendly(enemy)}{what} "
                             f"(OCV {mv.ocv:+d}/DCV {mv.dcv:+d} until your next "
                             f"phase; {does})"),
                    _maneuver_view=mv, _weapon=weapon,
                ))
    return out


def disarm_offers(*, enemies: list, melee_gate: Callable[[str], str],
                  friendly: Callable[[Any], str], weapons) -> list:
    """The plain Disarm (6E2 p.62), per weapon in an enemy's hand in reach."""
    out: list = []
    if weapons is None:
        return out
    for enemy in enemies:
        # Reach spec §2 (extended): Disarm is a pure STR melee maneuver ---
        # offered ONLY within reach.
        if melee_gate(enemy.id) != "direct":
            continue
        for w in weapons.held_by(enemy.id):
            out.append(_legal_action(
                action_id=f"disarm:{enemy.id}:{w.owner_id}:{w.weapon_id}",
                kind="disarm", target_id=enemy.id,
                power_xmlid="DISARM", power_name="Disarm",
                summary=(f"Disarm {friendly(enemy)} of his {w.name}: half-phase, "
                         f"-2 OCV, then STR vs STR; it flies 1d6+1m (6E2 p.62)"),
                _weapon=w,
            ))
    return out


def pick_up_offers(actor, *, scene, weapons, reach_m: float, half_move_m: float) -> list:
    """One offer per weapon on the ground he can reach this Phase."""
    from kirby_combat.enumeration import _xyz_dist
    from kirby_combat import within_reach
    from kirby_combat.reach import movement_reach

    out: list = []
    if weapons is None:
        return out
    positions = (getattr(scene, "combatant_positions", None) or {}) if scene is not None else {}
    here = positions.get(actor.id)
    for w, spot in weapons.on_ground:
        whose = "your" if w.owner_id == actor.id else f"{w.owner_id}'s"
        dest = None
        if spot is not None and here is not None:
            if not within_reach(_xyz_dist(here, spot), reach_m).in_reach:
                if half_move_m <= 0.0:
                    continue
                moved = movement_reach("running", here, spot, half_move_m, scene,
                                       combatant_id=actor.id)
                if not (moved.reachable and within_reach(
                        _xyz_dist(moved.landing, spot), reach_m).in_reach):
                    continue
                dest = (float(spot.x), float(spot.y), float(spot.z))
        out.append(_legal_action(
            action_id=f"pick_up_weapon:{w.owner_id}:{w.weapon_id}",
            kind="pick_up_weapon", target_id=None,
            power_xmlid=None, power_name=w.name,
            summary=(f"{'Move to and pick' if dest else 'Pick'} up {whose} "
                     f"{w.name} (6E2 p.62)"
                     + ("" if w.owner_id == actor.id else
                        " --- it is no use to you, but he cannot have it")),
            reposition_dest=dest, _weapon=w,
        ))
    return out
