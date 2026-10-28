"""The menu's Aid, Drain, Healing and Dispel offers.

Moved out of `enumerate_actions` so the rule each offer follows sits beside
the resolution in `actions/adjust.py` and `actions/dispel.py` rather than
being re-derived in a 4,000-line function.

WHAT CHANGED (2026-10-26):

- Aid and Healing were offered with ``target_id=None`` "so the driver picks
  the most-needed ally at resolve time", and the engine resolver then used
  the ACTOR. Every Aid and every Healing in every fight went on the man
  using it. They are offered on the actor and on each ally now, by name.
- An Adjustment Power whose INPUT names nothing this engine can adjust (a
  special-effect group such as "Fire Powers", or a ratio split it cannot
  read) is NOT OFFERED: an offer the resolver would have to guess at is
  the shape this engine has removed everywhere else.
- Aid and Healing are No Range (6E1 p.169, p.234): an ally across the map
  is not offered. Drain's range is "10m x Base Points" (p.197), Dispel's
  the same (p.195); both come from the cost engine.
- Healing is offered only on someone who has lost something it restores:
  "A character can only use Healing to restore Characteristics or Powers
  that have been lost or reduced" (6E1 p.234).
"""
from __future__ import annotations

from typing import Any, Callable

from kirby_combat.actions.adjust import (
    healing_targets, is_ranged, power_action_suffix, range_m,
)
from kirby_combat.adjustments import characteristic_targets, effect_dice, power_targets_on

_EPS_M = 1e-6


def _powers(actor, xmlid: str) -> list:
    # What he owns in the identity he is in (6E1 p.388; `identity.py`).
    from kirby_combat.identity import build_in_play

    return [p for p in (build_in_play(actor).powers or [])
            if (getattr(p, "xmlid", "") or "").upper() == xmlid]


def _dice_text(power) -> str:
    full, half, pips = effect_dice(power)
    text = f"{full}{'½' if half else ''}d6"
    return text + (f"{pips:+d}" if pips else "")


def _distance(scene, a, b) -> float | None:
    if scene is None:
        return None
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    here, there = position_of(scene, a.id), position_of(scene, b.id)
    if here is None or there is None:
        return None
    return distance_3d(here, there)


def _in_range(actor, other, power, scene, distances) -> bool:
    """Whether ``power`` reaches ``other`` from where ``actor`` stands.

    Unknown distance (a fight with no map) is not gated, the same reading
    `enumerate_actions` gives every other offer. Yourself is always in reach.
    """
    if other.id == actor.id:
        return True
    d = (distances or {}).get(other.id)
    if d is None:
        d = _distance(scene, actor, other)
    if d is None:
        return True
    if is_ranged(power):
        return d <= range_m(power) + _EPS_M
    reach = float(getattr(actor.combat_stats(), "reach_m", 1.0) or 1.0)
    return d <= reach + _EPS_M


def _has_lost(target, chars) -> bool:
    """Has he lost something this Healing restores: damage, or a Drain
    (6E1 p.234, "lost in any manner, such as ... Drains")? A live net Drain
    is on his ``state.drains`` (`adjustments.project_onto`)."""
    from kirby_combat.adjustments import _stat_attr

    for c in chars:
        vital = {"STUN": "stun", "BODY": "body", "END": "end"}.get(c.xmlid)
        if vital is not None:
            maximum = int(getattr(target.combat_stats(), f"max_{vital}"))
            if int(getattr(target.state, f"current_{vital}")) < maximum:
                return True
        if int((getattr(target.state, "drains", None) or {}).get(_stat_attr(c.xmlid), 0)) > 0:
            return True
    return False


def adjustment_offers(
    actor, *, enemies: list, allies: list, scene: Any,
    distances: dict[str, float] | None,
    limitation_label: Callable[[Any, Any], str],
) -> list:
    """Every Aid, Drain and Healing offer this actor has."""
    from kirby_combat.enumeration import LegalAction, _friendly, _power_action_id, is_down

    out: list = []
    standing_allies = [a for a in allies if not is_down(a) and a.id != actor.id]
    friends = [actor, *standing_allies]

    def _offer(kind, target, power, summary, suffix=None):
        action_id = _power_action_id(kind, target.id, power)
        if suffix:
            action_id = f"{action_id}:{suffix}"
        out.append(LegalAction(
            action_id=action_id, kind=kind, target_id=target.id,
            power_xmlid=power.xmlid,
            power_name=getattr(power, "name", None) or power.xmlid.title(),
            summary=summary + limitation_label(actor, power),
            _attack_view=power,
        ))

    for ap in _powers(actor, "AID"):
        chars = characteristic_targets(ap)
        for friend in friends:
            if not _in_range(actor, friend, ap, scene, distances):
                continue
            who = "yourself" if friend.id == actor.id else _friendly(friend)
            if chars is not None:
                named = ", ".join(c.xmlid for c in chars)
                _offer("aid", friend, ap,
                       f"AID {who}'s {named} ({_dice_text(ap)} Character Points; "
                       f"half effect on a defence; fades 5 points a Turn, "
                       f"6E1 p169)")
                continue
            for target in power_targets_on(ap, friend):
                _offer("aid", friend, ap,
                       f"AID {who}'s {ap.input} ({_dice_text(ap)} Character "
                       f"Points of extra dice; fades 5 a Turn, 6E1 p169)",
                       suffix=power_action_suffix(target))

    for ap in _powers(actor, "HEALING"):
        chars = healing_targets(ap)
        if chars is None:
            continue
        for friend in [actor, *[a for a in allies if a.id != actor.id]]:
            if not _has_lost(friend, chars):
                continue
            if not _in_range(actor, friend, ap, scene, distances):
                continue
            who = "yourself" if friend.id == actor.id else _friendly(friend)
            named = " and ".join(c.xmlid for c in chars)
            _offer("heal", friend, ap,
                   f"HEAL {who}'s {named} ({_dice_text(ap)}; up to his full "
                   f"value, does not fade; stops Bleeding, 6E1 p234)")

    for ap in _powers(actor, "DRAIN"):
        chars = characteristic_targets(ap)
        for enemy in enemies:
            if is_down(enemy) or not _in_range(actor, enemy, ap, scene, distances):
                continue
            if chars is not None:
                named = ", ".join(c.xmlid for c in chars)
                _offer("drain", enemy, ap,
                       f"DRAIN {_friendly(enemy)}'s {named} ({_dice_text(ap)} "
                       f"Character Points less his Power Defense, on an Attack "
                       f"Roll; half effect on a defence; returns 5 a Turn, "
                       f"6E1 p197)")
                continue
            for target in power_targets_on(ap, enemy):
                _offer("drain", enemy, ap,
                       f"DRAIN {_friendly(enemy)}'s {ap.input} "
                       f"({_dice_text(ap)} Character Points of its dice, on an "
                       f"Attack Roll; returns 5 a Turn, 6E1 p197)",
                       suffix=power_action_suffix(target))
    return out


def dispel_offers(
    actor, *, enemies: list, scene: Any, distances: dict[str, float] | None,
    limitation_label: Callable[[Any, Any], str],
) -> list:
    """One Dispel offer per enemy power the Dispel is bought against.

    The power is named on the offer (6E1 p.195: "the character must declare
    what power or ability he's trying to Dispel"); the old offer said "one
    of his defenses" and let the resolver pick the biggest.
    """
    from kirby_combat.actions.dispel import dispellable_on, resistance
    from kirby_combat.enumeration import LegalAction, _friendly, _power_action_id, is_down

    out: list = []
    for ap in _powers(actor, "DISPEL"):
        for enemy in enemies:
            if is_down(enemy) or not _in_range(actor, enemy, ap, scene, distances):
                continue
            for power in dispellable_on(ap, enemy):
                name = getattr(power, "name", None) or power.xmlid.title()
                out.append(LegalAction(
                    action_id=f"{_power_action_id('dispel', enemy.id, ap)}:power={power.id}",
                    kind="dispel", target_id=enemy.id, power_xmlid=ap.xmlid,
                    power_name=getattr(ap, "name", None) or "Dispel",
                    summary=(
                        f"DISPEL {_friendly(enemy)}'s {name} ({_dice_text(ap)} "
                        f"less his Power Defense must beat its {resistance(power)} "
                        f"Active Points, on an Attack Roll; off until he turns "
                        f"it back on at his next Phase, 6E1 p195)"
                    ) + limitation_label(actor, ap),
                    _attack_view=ap,
                ))
    return out
