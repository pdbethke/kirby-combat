"""A one-target Flash or Entangle: the Attack Roll first.

6E1 p.228: "To use Flash, a character must make an Attack Roll. If he
succeeds, he rolls the Flash dice and counts the Normal Damage BODY." 6E1
p.217, Entangle, word for word the same. `loop/resolvers._resolve_flash` and
`_resolve_entangle` made no roll at all --- every Flash and every Entangle in
every fight landed --- and the Flash summed the pips for its BODY, so a 6d6
Flash blinded for about 21 Segments where the book's count gives about 7.

THE ONE DOOR. The roll is `actions/adjust.attack_roll`, the Drain/Aid/Dispel
roll: an `AttackInput` folded by `recording._fold_session_cvs` (Dodge,
Surprise, Stunned, Drained CV, the blind rows of 6E2 p.9 ...) and rolled by
`resolution/to_hit.resolve_to_hit`, Range Modifier included. The Area versions
(`actions/area_effects.py`, kirby-combat #21) roll the same way per target for
a Selective or Nonselective Area and count BODY the same way
(`entangle.counted_body`), so one-target and Area cannot disagree.

A miss records the roll and does nothing else: no effect dice are rolled for
it, as the mental powers' misses (`mental/recording.record_mental_miss`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.models import ToHitResult
    from kirby_combat.session.combat_session import CombatSession


def effect_attack_roll(session: "CombatSession", actor, target, power: Any,
                       roller, template) -> "ToHitResult":
    """The Attack Roll against DCV (6E1 p.217, p.228), through the one door."""
    from kirby_combat.actions.adjust import attack_roll

    return attack_roll(session, actor, target, power, roller, template)


def roll_record(to_hit: "ToHitResult") -> dict:
    """What the log keeps of the roll, on the hit's row or the miss's."""
    return {
        "hit": bool(to_hit.hit), "roll": int(to_hit.roll),
        "target_number": int(to_hit.target_number),
        "effective_ocv": int(to_hit.effective_ocv),
        "target_dcv": int(to_hit.effective_dcv),
    }


def record_miss(session: "CombatSession", actor, action: "LegalAction",
                to_hit: "ToHitResult", *, effect_type: str) -> "CombatSession":
    """A declaration and a resolution saying the roll missed, and nothing else."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    now = datetime.now(timezone.utc)
    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=action.kind, targets=[action.target_id], parameters={},
    )
    s = apply_event(session, declared)
    return apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id),
        declaration_event_id=declared.id,
        result_payload={
            "type": effect_type, "kind": action.kind,
            "target_id": action.target_id, "success": False,
            **roll_record(to_hit),
        },
    ))
