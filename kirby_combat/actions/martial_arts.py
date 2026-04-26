"""Martial Arts — declare a 6E martial maneuver and project its modifiers.

Per 6E2 p90-93 §MARTIAL MANEUVERS. The character chooses one maneuver from
the MARTIAL_MANEUVERS table; the maneuver's OCV/DCV/DC modifiers apply to
the next attack made this segment.

Special semantics encoded by `notes`:
- ``HKA`` in notes → Killing Strike: damage type becomes "killing".
- ``Target Falls`` in notes → opposing combatant ends up prone after a hit
  (Martial Throw, Legsweep, Sacrifice Throw).
- ``Block`` in notes → can be declared as a reactive Abort (Martial Block).

CSL allocation: a per-action `csl_allocation` dict shifts OCV/DCV/DC by the
amounts specified — e.g. {"ocv": 2, "dcv": 1} means two CSL points to OCV,
one to DCV. Total must not exceed the combatant's available levels (caller's
responsibility — engine assumes valid input).

`extra_dc_levels` adds further DCs (one DC per level) on top of the base
maneuver DC bonus. Models the +1 Damage Class element from the table.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)
from kirby_combat.tables import MARTIAL_MANEUVERS, MartialManeuver


@dataclass(frozen=True)
class MartialArtsModifiers:
    """Net modifiers from a declared maneuver (already including CSL + extra DCs)."""
    maneuver_id: str
    ocv: int
    dcv: int
    dc_bonus: int
    damage_type: str          # "normal" | "killing"
    target_falls: bool        # True if maneuver knocks target prone
    is_block: bool            # True if maneuver is reactive Block (Martial Block)


class MartialArts:
    """Martial Arts maneuver declaration + modifier projection."""

    name: str = "martial_arts"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
        *,
        maneuver_id: str,
        csl_allocation: Optional[dict[str, int]] = None,
        extra_dc_levels: int = 0,
    ) -> tuple[CombatSession, ActionDeclared]:
        """Declare a martial maneuver. Records all parameters in event_log."""
        from kirby_combat.session.apply import apply_event

        if maneuver_id not in MARTIAL_MANEUVERS:
            raise ValueError(f"unknown martial maneuver: {maneuver_id!r}")

        params: dict[str, Any] = {
            "maneuver_id": maneuver_id,
            "csl_allocation": dict(csl_allocation or {}),
            "extra_dc_levels": int(extra_dc_levels),
        }

        evt = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            action_type="martial_arts",
            targets=[],
            parameters=params,
        )
        return apply_event(session, evt), evt

    @staticmethod
    def modifiers_for_pending_attack(
        session: CombatSession, combatant_id: str,
    ) -> dict[str, Any]:
        """Return the OCV/DCV/DC modifier payload for the most recent unresolved
        martial-arts declaration by this combatant. Empty dict if none.

        The format matches the existing tactical-modifier dicts (see Haymaker)
        so it composes with the to-hit pipeline cleanly.
        """
        declared: ActionDeclared | None = None
        for evt in reversed(session.event_log):
            if (
                isinstance(evt, ActionDeclared)
                and evt.combatant_id == combatant_id
                and evt.action_type == "martial_arts"
            ):
                declared = evt
                break

        if declared is None:
            return {}

        # Already resolved? Skip.
        for evt in session.event_log:
            if (
                isinstance(evt, ActionResolved)
                and evt.declaration_event_id == declared.id
            ):
                return {}

        mods = _compute_modifiers(declared.parameters)
        return {
            "maneuver_id": mods.maneuver_id,
            "ocv_delta": mods.ocv,
            "dcv_delta": mods.dcv,
            "dc_bonus": mods.dc_bonus,
            "damage_type": mods.damage_type,
            "target_falls": mods.target_falls,
            "is_block": mods.is_block,
        }


def _compute_modifiers(params: dict[str, Any]) -> MartialArtsModifiers:
    """Pure: combine maneuver row + CSL allocation + extra DC levels."""
    maneuver_id = params.get("maneuver_id", "")
    csl = params.get("csl_allocation") or {}
    extra_dc = int(params.get("extra_dc_levels", 0) or 0)
    m: MartialManeuver = MARTIAL_MANEUVERS[maneuver_id]

    ocv = m.ocv + int(csl.get("ocv", 0) or 0)
    dcv = m.dcv + int(csl.get("dcv", 0) or 0)
    dc_bonus = m.dc_bonus + int(csl.get("dc", 0) or 0) + extra_dc

    damage_type = "killing" if "HKA" in m.notes else "normal"
    target_falls = "Target Falls" in m.notes
    is_block = "Block" in m.notes and "Abort" in m.notes

    return MartialArtsModifiers(
        maneuver_id=maneuver_id,
        ocv=ocv, dcv=dcv, dc_bonus=dc_bonus,
        damage_type=damage_type,
        target_falls=target_falls,
        is_block=is_block,
    )
