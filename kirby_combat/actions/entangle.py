"""Entangle attack — applies an entanglement; victims escape via STR.

Note: Dorman's reference does not implement programmatic entangle escape;
the casual STR (str/10) and full STR (str/5) damage formulas are our
interpretation per HERO 6E2. RAW-verify before relying on this.

per HERO 6E1:
- Entangle creates a temporary obstruction with its own BODY, PD, ED
- Target inside the entangle has -2 OCV and -2 DCV
- Casual STR escape (half-phase): BODY damage = STR/10 minus entangle PD
- Full STR escape (full-phase): BODY damage = STR/5 minus entangle PD
- Once entangle BODY ≤ 0, target is free

State tracking: scan event log for EntangleApplied / EntangleEscape pairs.
No Combatant model changes; no apply.py extensions in this task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, EntangleApplied, EntangleEscape,
    make_author_combatant,
)


def _modifier_list(power) -> list:
    return list(getattr(power, "assigned_modifiers", None)
                or getattr(power, "modifiers", None) or [])


def _levels_of(power, xmlid: str) -> int:
    """Total levels of a modifier across every instance on ``power``.

    HD writes stacked purchases either as one modifier with LEVELS=n (the
    corpus shape: "Cannot Be Escaped With Teleportation (x2; +1/2)") or as
    repeated modifier elements; both count, and a level-less instance counts
    as one level."""
    total = 0
    for m in _modifier_list(power):
        if (getattr(m, "xmlid", "") or "").upper() == xmlid:
            total += max(1, int(getattr(m, "levels", 0) or 0))
    return total


def noteleport_levels(power) -> int:
    """Levels of Cannot Be Escaped With Teleportation (NOTELEPORT) on a power.

    6E1 p220 (Entangle) / p175 (Barrier): the advantage stops the one escape
    route an Entangle normally leaves open — 6E1 p217 has an Entangle block
    every Movement Power EXCEPT Teleportation, and 6E1 p218 lists Teleporting
    out among the escape methods. Multiple levels may be bought to outbid an
    escaper's Armor Piercing (see ``can_teleport_escape``)."""
    return _levels_of(power, "NOTELEPORT")


def armor_piercing_levels(power) -> int:
    """Levels of Armor Piercing on a power (each cancels one NOTELEPORT
    level when the power is the Teleportation doing the escaping —
    6E1 p220/p175)."""
    return _levels_of(power, "ARMORPIERCING")


def can_teleport_escape(entangle_power, teleportation_power=None) -> bool:
    """May this Teleportation escape that Entangle/Barrier?

    6E1 p218: Teleportation is a normal escape route. 6E1 p220 (and p175 for
    an englobing Barrier): Cannot Be Escaped With Teleportation blocks it,
    UNLESS the Teleportation is Armor Piercing, which cancels the advantage —
    both sides stack levels, so the escape works when AP levels >= NOTELEPORT
    levels. ``teleportation_power=None`` means a plain teleport (0 AP)."""
    ap = armor_piercing_levels(teleportation_power) if teleportation_power is not None else 0
    return noteleport_levels(entangle_power) <= ap


#: 6E1 p217: an Entangled character is at DCV 0. The one authority for the
#: factor -- ``Entangle.modifiers`` and any row-based driver read THIS, so
#: the number cannot drift between the event-sourced and relational paths.
ENTANGLED_DCV_FACTOR: float = 0.0

#: 6E1 p218: breaking out of an Entangle "doesn't have to make an Attack
#: Roll" -- an escape attempt against the Entangle always connects. Drivers
#: consult this rather than encoding the absence of a to-hit themselves.
ENTANGLE_ESCAPE_AUTO_HITS: bool = True


def str_escape_end_cost(str_value: int, *, casual: bool = False) -> int:
    """END for a STR breakout attempt.

    6E2 p41: STR costs 1 END per 10 points USED. Casual Use is half the
    character's STR and pays only for the amount used (6E1 p134), so the
    casual attempt charges half's worth."""
    used = (str_value // 2) if casual else str_value
    return max(0, used // 10)


def entangle_default_defenses(dice: int) -> tuple[int, int]:
    """The Entangle's own PD and ED when the build states no split.

    6E1 p217: each 1d6 of Entangle has 1 PD and 1 ED (both Resistant), so a
    document that writes no PDLEVELS/EDLEVELS defends at (dice, dice)."""
    return max(0, dice), max(0, dice)


@dataclass(frozen=True)
class BreakoutResult:
    """One breakout attempt's outcome tier (6E2 p126)."""
    escaped: bool
    action_regained: str   # "full" | "half" | "none"


def breakout(damage_body: int, remaining_body: int) -> BreakoutResult:
    """The breakout-margin rule, 6E2 p126: damage of at least TWICE the
    Entangle's remaining BODY frees the victim with a Full Phase still to
    act; at least the remaining BODY frees with a Half Phase; anything
    less leaves them trapped with no more actions that Phase."""
    if remaining_body <= 0:
        return BreakoutResult(escaped=True, action_regained="full")
    if damage_body >= 2 * remaining_body:
        return BreakoutResult(escaped=True, action_regained="full")
    if damage_body >= remaining_body:
        return BreakoutResult(escaped=True, action_regained="half")
    return BreakoutResult(escaped=False, action_regained="none")


def stacked_entangle(
    existing_body: int, existing_pd: int, existing_ed: int,
    new_body: int, new_pd: int, new_ed: int,
) -> tuple[int, int, int]:
    """Combine a fresh Entangle hit with one already holding the target.

    6E1 p217: the combined Entangle has the HIGHEST BODY of all the
    Entangles, +1 BODY for each additional Entangle, and the highest PD
    and ED. With no live existing Entangle the new one applies as-is."""
    if existing_body <= 0:
        return new_body, new_pd, new_ed
    return (max(existing_body, new_body) + 1,
            max(existing_pd, new_pd), max(existing_ed, new_ed))


def str_escape_dice(str_value: int, *, casual: bool = False) -> int:
    """Normal-damage dice for a STR breakout attempt.

    Full STR: STR//5 dice (the standard STR-to-damage conversion). Casual
    STR is HALF the character's STR (6E1 p134), a Zero Phase attempt --
    win or lose, the character keeps their action (6E1 p133-134). The
    CALLER rolls these dice and counts BODY; this function never touches
    dice."""
    if casual:
        str_value = str_value // 2
    return max(0, str_value // 5)


@dataclass(frozen=True)
class EntangleResult:
    target_id: str
    method: str                          # "applied" | "casual_str" | "full_str"
    damage_to_entangle_body: int
    body_remaining: int
    escaped: bool


class Entangle:
    name: str = "entangle"

    # ------------------------------------------------------------------ apply
    @staticmethod
    def apply(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        entangle_body: int,
        entangle_pd: int,
        entangle_ed: int,
        no_teleport_levels: int = 0,
    ) -> tuple[CombatSession, EntangleResult]:
        """Apply an entangle to target. Emits ActionDeclared + ActionResolved + EntangleApplied."""
        from kirby_combat.session.apply import apply_event

        now = datetime.now(timezone.utc)

        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="entangle",
            targets=[target_id],
            parameters={
                "entangle_body": entangle_body,
                "entangle_pd": entangle_pd,
                "entangle_ed": entangle_ed,
                "no_teleport_levels": no_teleport_levels,
            },
        )
        s = apply_event(session, declared)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "entangle_attack",
                "success": True,
                "target_id": target_id,
            },
        )
        s = apply_event(s, resolved)

        applied = EntangleApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            entangle_body=entangle_body,
            entangle_pd=entangle_pd,
            entangle_ed=entangle_ed,
            no_teleport_levels=no_teleport_levels,
        )
        s = apply_event(s, applied)

        return s, EntangleResult(
            target_id=target_id,
            method="applied",
            damage_to_entangle_body=0,
            body_remaining=entangle_body,
            escaped=False,
        )

    # ------------------------------------------------------------------ escape_attempt
    @staticmethod
    def escape_attempt(
        session: CombatSession,
        *,
        target_id: str,
        damage_body: int,
        escape_type: str,
    ) -> tuple[CombatSession, EntangleResult]:
        """Attempt to escape an entangle with BODY the CALLER already rolled.

        ``damage_body`` is the escape attempt's counted BODY with the
        Entangle's own defense already applied (escape damage soaks against
        the ENTANGLE's PD/ED, 6E1 p218 -- never the victim's). The margin
        rule decides the outcome (``breakout``, 6E2 p126). escape_type:
        "full" = the Phase's action; "casual" = the 6E1 p133-134 Zero Phase
        half-STR attempt (the caller keeps its action either way -- phase
        economy is the caller's job; this method only moves BODY)."""
        from kirby_combat.session.apply import apply_event

        if escape_type not in ("casual", "full"):
            raise ValueError(f"unknown escape_type: {escape_type!r}")

        is_e, current_body = Entangle.is_entangled(session, target_id)
        if not is_e:
            raise ValueError(f"{target_id} is not entangled; cannot escape")

        damage = max(0, damage_body)
        res = breakout(damage, current_body or 0)
        escaped = res.escaped
        body_remaining = 0 if escaped else max(0, (current_body or 0) - damage)
        method = "casual_str" if escape_type == "casual" else "full_str"

        evt = EntangleEscape(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            escaped=escaped,
        )
        s = apply_event(session, evt)

        return s, EntangleResult(
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            body_remaining=body_remaining,
            escaped=escaped,
        )

    # ------------------------------------------------------------------ teleport_escape
    @staticmethod
    def teleport_escape(
        session: CombatSession,
        *,
        target_id: str,
        teleport_ap_levels: int = 0,
    ) -> tuple[CombatSession, EntangleResult]:
        """Escape the entangle by Teleporting out of it.

        6E1 p218 lists Teleportation among an Entangle's escape routes; it
        needs no Attack Roll and does no BODY to the Entangle — the victim is
        simply elsewhere. 6E1 p220: an Entangle bought with Cannot Be Escaped
        With Teleportation refuses it, unless the Teleportation carries at
        least as many levels of Armor Piercing (``teleport_ap_levels``, from
        ``armor_piercing_levels`` on the escaper's TELEPORTATION power).

        A blocked attempt emits NO event and returns ``escaped=False`` with
        ``method="teleport_blocked"`` — nothing changed; callers should not
        have offered it (gate with ``can_teleport_escape``)."""
        from kirby_combat.session.apply import apply_event

        is_e, current_body = Entangle.is_entangled(session, target_id)
        if not is_e:
            raise ValueError(f"{target_id} is not entangled; cannot escape")

        ntl = 0
        for evt in reversed(session.event_log):
            if evt.kind == "EntangleApplied" and getattr(evt, "target_id", None) == target_id:
                ntl = int(getattr(evt, "no_teleport_levels", 0) or 0)
                break

        if ntl > teleport_ap_levels:
            return session, EntangleResult(
                target_id=target_id,
                method="teleport_blocked",
                damage_to_entangle_body=0,
                body_remaining=current_body or 0,
                escaped=False,
            )

        evt = EntangleEscape(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            method="teleport",
            damage_to_entangle_body=0,
            escaped=True,
        )
        s = apply_event(session, evt)
        return s, EntangleResult(
            target_id=target_id,
            method="teleport",
            damage_to_entangle_body=0,
            body_remaining=0,
            escaped=True,
        )

    # ------------------------------------------------------------------ is_entangled
    @staticmethod
    def is_entangled(
        session: CombatSession, combatant_id: str,
    ) -> tuple[bool, Optional[int]]:
        """Walk event log accumulating entangle body for combatant_id.

        Returns (True, body_remaining) when entangled; (False, None) when not.
        """
        body: Optional[int] = None
        for evt in session.event_log:
            kind = evt.kind
            if kind == "EntangleApplied" and getattr(evt, "target_id", None) == combatant_id:
                body = evt.entangle_body
            elif kind == "EntangleEscape" and getattr(evt, "target_id", None) == combatant_id:
                if body is None:
                    continue        # escape with no prior entangle (shouldn't happen)
                if evt.escaped:
                    body = None
                else:
                    body = max(0, body - evt.damage_to_entangle_body)
                    if body == 0:
                        body = None
        return (body is not None, body)

    # ------------------------------------------------------------------ modifiers
    @staticmethod
    def modifiers(
        session: CombatSession, combatant_id: str,
    ) -> dict:
        """Return OCV/DCV multipliers while entangled; empty dict otherwise.

        Per Dorman + HERO 6E2: entangled characters have 0 DCV and 1/2 OCV.
        Modeled as multiplicative factors so callers compose: effective_dcv =
        base_dcv * dcv_factor; effective_ocv = base_ocv * ocv_factor.
        """
        is_e, _ = Entangle.is_entangled(session, combatant_id)
        return ({"ocv_factor": 0.5, "dcv_factor": ENTANGLED_DCV_FACTOR}
                if is_e else {})
