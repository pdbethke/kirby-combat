"""Flash attack — sense-group blinding, counted in Segments.

per HERO 6E1 p.228:
- Flash targets a specific sense group (sight, hearing, smell/taste, mental, radio)
- Segments flashed = max(0, body_dealt - flash_defense): "the number of
  Segments the target's Sense(s) is (are) disabled"
- "Begin counting the Segments in the Segment in which the character uses
  the Flash attack", so the count falls by one each Segment the clock
  leaves (``Flash.tick_all``, wound by ``Encounter.advance_segment``). This
  docstring used to say "1 segment recovers per phase", and nothing called
  ``recover`` at all, so a Flash never ended.
- A man already Flashed in a Sense Group "can't suffer any further effect
  from other Flashes of the same Sense Group" until the first wears off
- The CV penalties are 6E2 p.9's, folded by ``kirby_combat.sense_penalties``

Multi-sense tracking: a combatant can be flashed in multiple groups
simultaneously; each tracked independently via the event log.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, FlashApplied, FlashRecovered,
    make_author_combatant,
)


@dataclass(frozen=True)
class FlashResult:
    target_id: str
    sense_group: str
    method: str                      # "applied" | "recovered" | "fully_recovered"
    segments_remaining: int
    cleared: bool


class Flash:
    name: str = "flash"

    # ------------------------------------------------------------------ apply
    @staticmethod
    def apply(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        sense_group: str,
        body_dealt: int,
        flash_defense: int,
    ) -> tuple[CombatSession, FlashResult]:
        from kirby_combat.session.apply import apply_event

        segments = max(0, body_dealt - flash_defense)
        # 6E1 p.228: "If a character's affected by a Flash, generally he
        # can't suffer any further effect from other Flashes of the same
        # Sense Group ... until the first Flash wears off." The roll is
        # still recorded; the blinding it would have caused is not, so the
        # first Flash's count is not reset by the second.
        already, _ = Flash.is_flashed(session, target_id, sense_group)
        landed = 0 if already else segments
        now = datetime.now(timezone.utc)

        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="flash",
            targets=[target_id],
            parameters={
                "sense_group": sense_group,
                "body_dealt": body_dealt,
                "flash_defense": flash_defense,
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
                "type": "flash_attack",
                "target_id": target_id,
                "sense_group": sense_group,
                "segments": landed,
                "already_flashed": already,
            },
        )
        s = apply_event(s, resolved)
        if already:
            return s, FlashResult(
                target_id=target_id, sense_group=sense_group,
                method="applied", segments_remaining=Flash.is_flashed(
                    s, target_id, sense_group)[1][sense_group],
                cleared=False,
            )

        applied = FlashApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            sense_group=sense_group,
            segments=segments,
        )
        s = apply_event(s, applied)

        return s, FlashResult(
            target_id=target_id,
            sense_group=sense_group,
            method="applied",
            segments_remaining=segments,
            cleared=(segments == 0),
        )

    # ------------------------------------------------------------------ recover
    @staticmethod
    def recover(
        session: CombatSession,
        *,
        target_id: str,
        sense_group: str,
        segments_to_recover: int = 1,
    ) -> tuple[CombatSession, FlashResult]:
        from kirby_combat.session.apply import apply_event

        flashed, groups = Flash.is_flashed(session, target_id)
        if sense_group not in groups:
            raise ValueError(
                f"{target_id} is not flashed in {sense_group!r}; cannot recover"
            )

        current = groups[sense_group]
        new_remaining = max(0, current - segments_to_recover)
        cleared = new_remaining == 0

        evt = FlashRecovered(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            sense_group=sense_group,
            segments_remaining=new_remaining,
        )
        s = apply_event(session, evt)

        return s, FlashResult(
            target_id=target_id,
            sense_group=sense_group,
            method="fully_recovered" if cleared else "recovered",
            segments_remaining=new_remaining,
            cleared=cleared,
        )

    # ------------------------------------------------------------------ tick_all
    @staticmethod
    def tick_all(session: CombatSession) -> CombatSession:
        """One Segment off every live Flash in this session (6E1 p.228).

        What ``Encounter.advance_segment`` calls on both of its branches,
        beside ``PresenceEffects.tick_all``: a Flash is counted in
        Segments, and the Segment it landed in is the first one counted, so
        leaving that Segment is the first recovery. A 3-Segment Flash used
        in Segment 5 blinds through Segments 5, 6 and 7 and is gone in 8.
        """
        for combatant_id in list(session.combatants):
            _, groups = Flash.is_flashed(session, combatant_id)
            for sense_group in sorted(groups):
                session, _ = Flash.recover(
                    session, target_id=combatant_id, sense_group=sense_group,
                    segments_to_recover=1,
                )
        return session

    # ------------------------------------------------------------------ is_flashed
    @staticmethod
    def is_flashed(
        session: CombatSession,
        combatant_id: str,
        sense_group: str | None = None,
    ) -> tuple[bool, dict[str, int]]:
        """Walk the log accumulating per-sense-group segments_remaining."""
        groups: dict[str, int] = {}
        for evt in session.event_log:
            if getattr(evt, "target_id", None) != combatant_id:
                continue
            if evt.kind == "FlashApplied":
                # 6E1 p.228: no further effect while the first one lasts.
                if groups.get(evt.sense_group, 0) <= 0:
                    groups[evt.sense_group] = evt.segments
            elif evt.kind == "FlashRecovered":
                groups[evt.sense_group] = evt.segments_remaining

        # Drop fully-recovered groups
        groups = {g: n for g, n in groups.items() if n > 0}

        if sense_group is not None:
            filtered = {g: n for g, n in groups.items() if g == sense_group}
            return (bool(filtered), filtered)
        return (bool(groups), groups)

    # ------------------------------------------------------------------ modifiers
    @staticmethod
    def modifiers(
        session: CombatSession,
        combatant_id: str,
        attack_type: str = "hth",
    ) -> dict:
        """Return the OCV/DCV factors for a flashed combatant making an attack.

        **SUPERSEDED by ``kirby_combat.sense_penalties``, which is what the
        CV seam actually folds.** This function is correct for the narrow
        question it asks and is kept for the callers that ask it, but it
        cannot express three things the same rule requires, so do not
        build on it:

        * the penalties are **per-opponent** (6E2 p.9's blinded Orion is
          1/2 DCV against one attacker and -1 DCV against another in the
          same Segment); this returns one global answer;
        * mitigation by a Nontargeting PER Roll is a **flat -1 DCV**, not
          a factor, so no return value of this shape can carry it;
        * the penalty is owed to being unable to perceive with a
          **Targeting** Sense, and this triggers on a Flash to ANY Sense
          Group -- so it reports a blinded normal human after a Flash to
          the Hearing Group, which 6E2 p.9 does not.

        Per 6E2 p127 §Inability To Sense An Opponent:
          - HTH attacks:    ½ OCV / ½ DCV
          - Ranged attacks: 0 OCV / ½ DCV  (cannot meaningfully aim)

        Args:
            session: combat session.
            combatant_id: the (possibly-flashed) combatant.
            attack_type: "hth" (default) or "ranged". Anything else is
                treated as "hth" for safety.

        Returns:
            {} if not flashed; otherwise a dict with ocv_factor and dcv_factor.
        """
        flashed, _ = Flash.is_flashed(session, combatant_id)
        if not flashed:
            return {}
        if attack_type == "ranged":
            return {"ocv_factor": 0.0, "dcv_factor": 0.5}
        return {"ocv_factor": 0.5, "dcv_factor": 0.5}
