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

    @classmethod
    def from_maneuver_view(
        cls,
        mv: "MartialManeuverView",
        *,
        csl_allocation: Optional[dict[str, int]] = None,
        extra_dc_levels: int = 0,
    ) -> "MartialArtsModifiers":
        """Build modifiers from a per-character ``MartialManeuverView``
        (kirby_combat.hero_view) WITHOUT consulting the static
        ``MARTIAL_MANEUVERS`` table — this is the §3 seam that lets a character
        fight with the exact maneuvers they bought (custom names included).

        The CSL + extra-DC folding mirrors ``_compute_modifiers`` exactly so a
        custom maneuver behaves identically to a static-table one:
        ``ocv += csl["ocv"]``; ``dcv += csl["dcv"]``;
        ``dc_bonus += csl["dc"] + extra_dc_levels``. The view already carries
        the parsed flat OCV/DCV (HD CV grammar resolved at view-build time) and
        the derived damage-type / target-falls / is-block flags, so this method
        only layers the per-action CSL/extra-DC adjustments on top.
        """
        csl = csl_allocation or {}
        ocv = mv.ocv + int(csl.get("ocv", 0) or 0)
        dcv = mv.dcv + int(csl.get("dcv", 0) or 0)
        dc_bonus = mv.dc_bonus + int(csl.get("dc", 0) or 0) + int(extra_dc_levels or 0)
        return cls(
            maneuver_id=mv.maneuver_id,
            ocv=ocv, dcv=dcv, dc_bonus=dc_bonus,
            damage_type=mv.damage_type,
            target_falls=mv.target_falls,
            is_block=mv.is_block,
        )

    def as_params(self) -> dict[str, Any]:
        """JSON-friendly dict for storing pre-built modifiers in an event's
        ``parameters`` (keeps the event log serializable like the static path,
        which stores only ints/strings)."""
        return {
            "maneuver_id": self.maneuver_id,
            "ocv": self.ocv,
            "dcv": self.dcv,
            "dc_bonus": self.dc_bonus,
            "damage_type": self.damage_type,
            "target_falls": self.target_falls,
            "is_block": self.is_block,
        }


def modifiers_for_maneuver_view(
    mv: "MartialManeuverView",
    *,
    csl_allocation: Optional[dict[str, int]] = None,
    extra_dc_levels: int = 0,
) -> MartialArtsModifiers:
    """Module-level convenience wrapper around
    ``MartialArtsModifiers.from_maneuver_view``. This is the entry point §4
    (kirby-api driver) calls to turn a per-character ``MartialManeuverView``
    into applied modifiers, which it then passes to
    ``MartialArts.declare(session, cid, modifiers=...)`` to flow through the
    existing declare → ``modifiers_for_pending_attack`` → resolve_attack path.
    """
    return MartialArtsModifiers.from_maneuver_view(
        mv, csl_allocation=csl_allocation, extra_dc_levels=extra_dc_levels,
    )


class MartialArts:
    """Martial Arts maneuver declaration + modifier projection."""

    name: str = "martial_arts"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
        *,
        maneuver_id: Optional[str] = None,
        csl_allocation: Optional[dict[str, int]] = None,
        extra_dc_levels: int = 0,
        modifiers: Optional["MartialArtsModifiers"] = None,
    ) -> tuple[CombatSession, ActionDeclared]:
        """Declare a martial maneuver. Records all parameters in event_log.

        Two paths, sharing one resolve seam:

        - **Static** (``maneuver_id=...``): the maneuver is looked up in
          ``MARTIAL_MANEUVERS``; unknown ids are rejected. CSL/extra-DC fold in
          at ``modifiers_for_pending_attack`` time via ``_compute_modifiers``.
          This path is unchanged from before — same guard, same params shape.

        - **Per-character** (``modifiers=...``): a caller (§4's kirby-api driver,
          via ``modifiers_for_maneuver_view``) passes pre-built
          ``MartialArtsModifiers`` derived from the character's OWN bought
          maneuver — which need NOT exist in ``MARTIAL_MANEUVERS``. The static
          table guard is skipped; the already-folded modifiers (CSL + extra-DC
          baked in at ``from_maneuver_view`` time) are stored as a plain dict and
          replayed verbatim. This is the smallest non-breaking seam: it reuses
          the existing declare → ``modifiers_for_pending_attack`` → resolve flow
          rather than adding a parallel resolver, and leaves the static-id path
          byte-for-byte identical.
        """
        from kirby_combat.session.apply import apply_event

        if modifiers is not None:
            params: dict[str, Any] = {"prebuilt_modifiers": modifiers.as_params()}
        else:
            if maneuver_id not in MARTIAL_MANEUVERS:
                raise ValueError(f"unknown martial maneuver: {maneuver_id!r}")

            params = {
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
    """Pure: combine maneuver row + CSL allocation + extra DC levels.

    If the declaration carried ``prebuilt_modifiers`` (the per-character §3
    path), those are replayed verbatim — CSL/extra-DC were already folded in at
    ``from_maneuver_view`` time, and there's no static-table row to consult.
    """
    pre = params.get("prebuilt_modifiers")
    if pre is not None:
        return MartialArtsModifiers(
            maneuver_id=pre["maneuver_id"],
            ocv=int(pre["ocv"]),
            dcv=int(pre["dcv"]),
            dc_bonus=int(pre["dc_bonus"]),
            damage_type=pre["damage_type"],
            target_falls=bool(pre["target_falls"]),
            is_block=bool(pre["is_block"]),
        )

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
