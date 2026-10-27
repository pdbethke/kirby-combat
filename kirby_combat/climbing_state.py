"""Which wall a man is on, and what being on it costs him (6E2 p.48-49).

`climbing.py` has priced climbing since it was written --- "During easy
climbs (such as a ladder), characters suffer -1 DCV; more difficult ones can
reduce DCV by up to half and subtract 2 DCs from all attacks" (6E2 p.48's
table, p.49's text) --- and nothing read it, because nothing knew who was on
a wall. `climbing.climb_status` names a status token no fold ever wrote.

WHO IS ON A WALL is folded from the log, the way every condition here is:

- ON: a ``climb`` / ``climb_fast`` row of his that climbed (``climbed``)
  and did not top out --- he is on that face, part way up.
- OFF: a later climb that topped out (he is standing on top), or a fall off
  it, or any move of his that was not a climb (Knockback, a Throw, a fall,
  a run: a man carried off a face is not on it).

THE PENALTIES, read by the attack door through the two seams every
condition uses: the DCV through `cv_modifiers`' per-opponent sources, the
DCs through `AttackInput.dc_modifier`, which the pure resolver trims the way
it trims Damage Negation (6E1 p.185's DC arithmetic).

"In either case, a character can eliminate these penalties with a successful
Climbing roll. This roll is separate from any roll needed to keep climbing
or not fall; typically it takes no time" (p.49). RULING: a man with the
Skill makes it as part of each climb, at the face's difficulty, and it
holds until he climbs again; without the Skill he cannot. The roll is on the
climb's row (``penalties_roll``). The GM's Half Phase for it is not taken.

6E1 p.70's summary ("A climbing character's OCV and DCV are halved") is the
one `climbing.ClimbModifiers` already records as disagreeing with the
detailed 6E2 text it defers to; 6E2 is implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kirby_combat.climbing import ClimbModifiers, climb_modifiers

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

CLIMB_KINDS = frozenset({"climb", "climb_fast"})


@dataclass(frozen=True)
class OnTheWall:
    """He is on a face: which, how hard it is, and what it costs him."""

    wall_id: str
    difficulty: int
    penalties_eliminated: bool

    @property
    def modifiers(self) -> ClimbModifiers | None:
        """The penalties he is under, or None when his roll removed them."""
        if self.penalties_eliminated:
            return None
        return climb_modifiers(self.difficulty)


def on_the_wall(session: "CombatSession", combatant_id: str) -> OnTheWall | None:
    """The face he is climbing now, or None. See the module docstring."""
    on: OnTheWall | None = None
    for event in getattr(session, "event_log", None) or []:
        kind = getattr(event, "kind", "")
        if kind == "MovementResolved":
            if (event.combatant_id == combatant_id
                    and getattr(event, "move_type", "") != "climbing"):
                on = None
            continue
        if kind != "ActionResolved":
            continue
        payload = getattr(event, "result_payload", None) or {}
        if payload.get("kind") not in CLIMB_KINDS:
            continue
        if getattr(getattr(event, "author", None), "id", None) != combatant_id:
            continue
        if payload.get("fall") is not None or payload.get("topped_out"):
            on = None
        elif payload.get("climbed"):
            roll = payload.get("penalties_roll")
            on = OnTheWall(
                wall_id=str(payload["wall_id"]),
                difficulty=int(payload.get("difficulty", 0) or 0),
                penalties_eliminated=bool(roll and roll.get("made")),
            )
    return on


def climbing_cv_modifiers(session: "CombatSession", combatant_id: str,
                          opponent_id: str, combat_type: str) -> dict[str, float]:
    """The DCV a man on a wall fights at (6E2 p.48-49), for `cv_modifiers`.

    "The OCV, DCV, and DC penalties for Climbing and other conditions apply
    to both HTH and Ranged Combat" (6E2 p.48), so the opponent and the kind
    of combat do not change it. "Reduce DCV by up to half" is taken at its
    most, half (`climbing.climb_modifiers`).
    """
    on = on_the_wall(session, combatant_id)
    mods = on.modifiers if on is not None else None
    if mods is None:
        return {}
    out: dict[str, float] = {}
    if mods.dcv_multiplier != 1.0:
        out["dcv_factor"] = mods.dcv_multiplier
    if mods.dcv_delta:
        out["dcv_delta"] = mods.dcv_delta
    return out


def climbing_dc_penalty(session: "CombatSession", combatant_id: str) -> int:
    """DCs off every attack he makes from a difficult face (6E2 p.49: "subtract
    2 DCs from all attacks"), as a negative number; 0 otherwise."""
    on = on_the_wall(session, combatant_id)
    mods = on.modifiers if on is not None else None
    return int(mods.dc_penalty) if mods is not None else 0
