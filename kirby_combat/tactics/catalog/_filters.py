"""Shared gate helpers for the tactics catalog.

Extracted from the offensive modules (fight_from_cover, keep_range,
sustained_fire, close_and_strike, grab_and_throw, push_when_winning)
to avoid copy-paste drift. Used by both offensive and defensive modules.

DO NOT import from kirby.combat.services.* here — tactics must remain
DB-free so they can be used in unit tests without a Postgres connection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.tactics.base import Situation

# Mental attacks resolve against OMCV/DMCV + Mental Defense, not the
# physical defenses that protect constructs (walls, barriers). Ranged
# helpers exclude these so construct-targeting logic isn't confused.
# NOTE: action_enumeration._MENTAL_ATTACK_XMLIDS holds the canonical
# attack-shaped set ({MENTALBLAST, EGO_ATTACK, EGOATTACK}); this is a
# SUPERSET of it — it adds MENTALTRANSFORM and TELEPATHY because the
# tactic layer also wants non-damaging mental powers excluded from
# "ranged attack" reasoning. Kept local so the tactic layer stays
# DB-free (no cross-module import).
_MENTAL_XMLIDS: frozenset[str] = frozenset(
    {"EGOATTACK", "EGO_ATTACK", "MENTALBLAST", "MENTALTRANSFORM", "TELEPATHY"}
)

# Movement power xmlids that indicate a mobility-focused combatant.
_MOVEMENT_XMLIDS: frozenset[str] = frozenset(
    {"RUNNING", "FLIGHT", "TELEPORTATION"}
)


# ── attack helpers ────────────────────────────────────────────────────────────


def _best_attack(situation: "Situation") -> Any | None:
    """Return the highest-damage-dice attack the actor has, or None.

    Used by close_and_strike, grab_and_throw, push_when_winning and the
    defensive modules that check for melee capability.
    """
    attacks = getattr(situation.actor, "attacks", [])
    damaging = [a for a in attacks if (a.damage_dice or 0) > 0]
    if not damaging:
        return None
    return max(damaging, key=lambda a: a.damage_dice)


def _best_ranged_attack(situation: "Situation") -> Any | None:
    """Return the highest-damage ranged non-mental attack, or None.

    Used by fight_from_cover, keep_range, sustained_fire and the
    defensive modules that gate on ranged capability.
    """
    best = None
    for a in getattr(situation.actor, "attacks", []):
        if (
            (a.damage_dice or 0) > 0
            and a.range_m is not None
            and a.range_m > 0
            and (a.xmlid or "").upper() not in _MENTAL_XMLIDS
        ):
            if best is None or a.damage_dice > best.damage_dice:
                best = a
    return best


def _is_melee(attack: Any) -> bool:
    """True when the attack has no range (HTH / melee).

    Used by close_and_strike, grab_and_throw, abort_to_block,
    mobility_defense and any defensive tactic that verifies HTH capacity.
    """
    return attack.range_m is None or attack.range_m == 0.0


def _has_ranged_enemy(situation: "Situation") -> bool:
    """True if any living enemy has at least one ranged non-mental attack."""
    for e in situation.enemies:
        for a in getattr(e, "attacks", []):
            if (
                (a.damage_dice or 0) > 0
                and a.range_m is not None
                and a.range_m > 0
                and (a.xmlid or "").upper() not in _MENTAL_XMLIDS
            ):
                return True
    return False
