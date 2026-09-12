"""Grab — Attack Roll at -1 OCV / -2 DCV; grabbed status tracked via event log scan.

Per 6E2 p67 §USING GRAB and the maneuver table on p62:
    - Performing a Grab requires a successful Attack Roll at -1 OCV.
      The grabber is also at -2 DCV while holding the grabbed character.
    - The STR-vs-STR contest is for the ESCAPE attempt, not the initial grab.
    - Half-phase action.
    - Successful grab tags the victim as "grabbed by attacker_id".
    - Escape: on the victim's phase, opposed STR — escaper wins iff
      escaper_str > grabber_str (grabber wins ties).

This module tracks grab state by scanning ActionResolved events whose
result_payload has type in {"grab", "grab_escape"}.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)


@dataclass
class GrabResult:
    success: bool
    attacker_id: str
    target_id: str
    attacker_str: int
    target_str: int
    # To-hit details for the initial Grab Attack Roll (per 6E2 p67).
    # Only meaningful when supplied by declare_and_resolve callers; defaults
    # exist for back-compat with code that doesn't yet pass roll info.
    effective_ocv: int = 0
    effective_dcv: int = 0
    attack_roll: int = 0
    hit: bool = False


def _body_of(roller, dice: int) -> int:
    """Normal Damage BODY from `dice` d6 (6E2 p.66 counts BODY, not pips).

    Delegates the per-die rule to the resolver's own
    `_body_for_normal_die` rather than restating 1/2-5/6 here, so a
    struggle and an attack cannot come to disagree about what a die is
    worth.
    """
    from kirby_combat.resolution.damage import _body_for_normal_die

    if dice <= 0:
        return 0
    return sum(_body_for_normal_die(v) for v in roller.roll_dice(dice))


class Grab:
    name: str = "grab"

    # ------------------------------------------------------------------ declare
    @staticmethod
    def declare_and_resolve(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        attacker_str: int,
        target_str: int,
        attacker_ocv: int,
        target_dcv: int,
        attack_roll: int,
    ) -> tuple[CombatSession, GrabResult]:
        """Apply a grab attempt. Emits ActionDeclared + ActionResolved events.

        Per 6E2 p67 (and the maneuver table on p62), Grab requires a
        successful Attack Roll at -1 OCV. The grabber holds the target at
        -2 DCV while the grab is maintained (caller-tracked).

        Args:
            attacker_ocv: Attacker's OCV BEFORE the Grab maneuver penalty.
                The -1 OCV penalty is applied internally.
            target_dcv: Target's DCV (unmodified — the -2 DCV from the
                Grab maneuver applies to the GRABBER, not the target).
            attack_roll: Sum of the attacker's 3d6 to-hit roll.
            attacker_str / target_str: STR values stored on the result for
                later escape resolution. They do NOT determine grab success.

        Returns (new_session, result). The grab succeeds iff
        (effective_OCV + 11 - attack_roll) >= target_DCV.
        """
        from kirby_combat.session.apply import apply_event

        # Per 6E2 p67: -1 OCV on the Grab Attack Roll. -2 DCV applies to
        # the grabber (caller-tracked, applied to the grabber's DCV while
        # holding the grab; not used to resolve this Attack Roll).
        effective_ocv = attacker_ocv - 1
        effective_dcv = target_dcv
        margin = (effective_ocv + 11 - attack_roll) - effective_dcv
        hit = margin >= 0
        success = hit  # Grab succeeds on a successful Attack Roll.

        result = GrabResult(
            success=success,
            attacker_id=attacker_id, target_id=target_id,
            attacker_str=attacker_str, target_str=target_str,
            effective_ocv=effective_ocv,
            effective_dcv=effective_dcv,
            attack_roll=attack_roll,
            hit=hit,
        )

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="grab",
            targets=[target_id],
            parameters={
                "attacker_str": attacker_str,
                "target_str": target_str,
                "attacker_ocv": attacker_ocv,
                "target_dcv": target_dcv,
                "attack_roll": attack_roll,
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
                "type": "grab",
                "success": success,
                "attacker_id": attacker_id,
                "target_id": target_id,
                "attacker_str": attacker_str,
                "target_str": target_str,
                "effective_ocv": effective_ocv,
                "effective_dcv": effective_dcv,
                "attack_roll": attack_roll,
                "hit": hit,
            },
        )
        s = apply_event(s, resolved)
        return s, result

    # ------------------------------------------------------------------ escape
    #: Breaking out hurts nobody. 6E2 p.66 and Western Hero p.104 both
    #: say so in the same words: "This deals no damage to either
    #: character." Named so a reader does not have to infer it from the
    #: absence of a damage field.
    escape_deals_damage = False

    @staticmethod
    def escape_dice(str_value: int) -> int:
        """Dice in a break-out contest: 6E2 p.66, "1d6 for each 5 STR"."""
        return max(0, int(str_value) // 5)

    @staticmethod
    def escape_outcome(*, escaper_body: int, grabber_body: int) -> str:
        """Who wins the struggle, and what it cost.

        THREE STATES, not two. Western Hero p.104: "If the victim rolls
        more BODY damage than the grabber, then they break free but may
        take no other actions. If the victim rolls double the damage of
        the grabber, then the escape took no time and the victim has
        their full phase to take advantage of."

        6E2 p.66 gives ties to the grabber: "if the Grabber's total is
        higher or the rolls tie, the victim remains Grabbed."

        Returns "held" | "free_spent" | "free_acting".
        """
        if escaper_body <= grabber_body:
            return "held"
        # `>=` and not `>`: a grabber who rolls nothing at all has been
        # beaten outright, and `0 >= 2*0` must read as a clean break
        # rather than a narrow one.
        if escaper_body >= 2 * grabber_body:
            return "free_acting"
        return "free_spent"

    @staticmethod
    def escape(
        session: CombatSession,
        *,
        escaper_id: str,
        escaper_str: int,
        grabber_str: int,
    ) -> tuple[CombatSession, GrabResult]:
        """Attempt to escape a grab. Emits action_type="grab_escape" events.

        Raises ValueError if escaper isn't currently grabbed. Escaper wins iff
        escaper_str > grabber_str (grabber wins ties).
        """
        from kirby_combat.session.apply import apply_event

        is_g, grabber_id = Grab.is_grabbed(session, escaper_id)
        if not is_g:
            raise ValueError(f"{escaper_id} is not grabbed; cannot escape")

        # A CONTEST, NOT A COMPARISON. This read `escaper_str >
        # grabber_str`, so a STR 20 man always escaped a STR 10 man and a
        # STR 10 man never escaped a STR 11 one. 6E2 p.66: both roll 1d6
        # per 5 STR and count BODY, which is why a weaker man can get
        # lucky -- the whole reason the book rolls.
        #
        # The dice come from the session's roller so a seeded fight stays
        # reproducible; when there is none, the STR comparison is kept as
        # the degenerate fallback rather than inventing a roller here.
        roller = getattr(session, "dice_roller", None)
        if roller is not None:
            escaper_body = _body_of(roller, Grab.escape_dice(escaper_str))
            grabber_body = _body_of(roller, Grab.escape_dice(grabber_str))
            outcome = Grab.escape_outcome(
                escaper_body=escaper_body, grabber_body=grabber_body)
        else:
            outcome = ("free_spent" if escaper_str > grabber_str else "held")
        success = outcome != "held"
        result = GrabResult(
            success=success,
            attacker_id=grabber_id or "",
            target_id=escaper_id,
            attacker_str=grabber_str,
            target_str=escaper_str,
        )

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(escaper_id),
            combatant_id=escaper_id,
            action_type="grab_escape",
            targets=[grabber_id or ""],
            parameters={"escaper_str": escaper_str, "grabber_str": grabber_str},
        )
        s = apply_event(session, declared)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(escaper_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "grab_escape",
                "success": success,
                "escaper_id": escaper_id,
                "grabber_id": grabber_id,
                "escaper_str": escaper_str,
                "grabber_str": grabber_str,
            },
        )
        s = apply_event(s, resolved)
        return s, result

    # ------------------------------------------------------------------ is_grabbed
    @staticmethod
    def is_grabbed(
        session: CombatSession, combatant_id: str,
    ) -> tuple[bool, Optional[str]]:
        """Scan the event log for the most recent grab/escape pair affecting
        this combatant. Returns (True, grabber_id) if currently grabbed,
        (False, None) otherwise.
        """
        grabber: Optional[str] = None
        for evt in session.event_log:
            if evt.kind != "ActionResolved":
                continue
            payload = getattr(evt, "result_payload", None) or {}
            ptype = payload.get("type")
            if (
                ptype == "grab"
                and payload.get("target_id") == combatant_id
                and payload.get("success") is True
            ):
                grabber = payload.get("attacker_id")
            elif (
                ptype == "grab_escape"
                and payload.get("escaper_id") == combatant_id
                and payload.get("success") is True
            ):
                grabber = None
        return (grabber is not None, grabber)
