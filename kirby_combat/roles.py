"""What KIND of combatant this is.

Five roles, first match wins. The classification decides which tactical
profile a combatant fights under, so getting it wrong changes behaviour
rather than merely labelling it -- the martial-artist branch exists because
abort-readiness gates a brawler OFF at or above 50% STUN, and a misclassified
martial artist therefore eats hits instead of aborting to its Martial Dodge.

Moved from the web wrapper unchanged. The heuristics are debatable: 50m is a
magic number no rulebook states, and "has any martial maneuver" catches a
brick who bought Martial Block. Improving them is a separate change needing
its own evidence; tests/test_roles.py pins what exists.
"""
from __future__ import annotations

from typing import Any

#: Mental / control attacks. First branch of the tree, so a long-ranged
#: mental attack is a controller rather than a blaster.
MENTAL_XMLIDS = frozenset({
    "MINDCONTROL", "MENTALILLUSIONS", "MIND_CONTROL", "MENTAL_ILLUSIONS",
    "EGO_ATTACK", "EGOATTACK", "MINDSCAN", "MIND_SCAN", "TELEPATHY",
    "MENTALBLAST",
})

#: Powers that help someone else rather than hurt an enemy.
SUPPORT_XMLIDS = frozenset({"AID", "HEALING", "SUCCOR"})

#: Every role classify_role can return, in decision-tree order.
ROLES: tuple[str, ...] = (
    "controller", "support", "ranged_blaster", "martial_artist",
    "aggressive_brawler",
)

def classify_role(
    combatant: Any,
) -> str:
    """PR-30: heuristic default profile name for combatants without
    a character_tactic_profile assignment.

    Decision tree (first match wins):
      * has mental / control attack → "controller"
      * has support power (Aid / Healing / Succor) → "support"
      * primary attack has range_m ≥ 50 → "ranged_blaster"
      * fallback → "aggressive_brawler"

    The names match the four starter profiles seeded by PR-1's
    migration. Future profile additions can land alongside without
    reshaping this function.
    """
    powers = list(getattr(combatant, "attacks", []) or [])
    xmlids = {(p.xmlid or "").upper() for p in powers}
    if xmlids & MENTAL_XMLIDS:
        return "controller"
    if xmlids & SUPPORT_XMLIDS:
        return "support"
    longest_range = max(
        (float(getattr(p, "range_m", 0) or 0) for p in powers),
        default=0.0,
    )
    if longest_range >= 50:
        return "ranged_blaster"
    # A character with bought martial maneuvers (Martial Dodge / Block / Strike)
    # fights like a martial artist — it dances and ABORTS to its defensive
    # maneuvers — not an aggressive brawler that holds and trades blows. This is
    # load-bearing: abort-readiness gates a brawler OFF while it's ≥50% STUN, so
    # misclassifying a martial artist here makes it stubbornly eat hits instead
    # of using its (e.g. +5) Martial Dodge. Engine view is best-effort.
    try:
        if any(
            getattr(m, "is_attack", False) or getattr(m, "is_dodge", False)
            or getattr(m, "is_block", False)
            for m in (combatant.maneuver_view() or [])
        ):
            return "martial_artist"
    except Exception:  # noqa: BLE001 — maneuver_view is best-effort
        pass
    return "aggressive_brawler"

