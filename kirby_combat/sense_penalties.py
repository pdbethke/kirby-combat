"""Inability to sense an opponent — the CV consequence, per opponent.

**The rule this module implements — 6E2 p.9**, restated in our own words
(this project ships no rules text; open your own copy to check us). The
same numbers appear on p.127 under "Inability To Sense An Opponent";
both pages were read before this was written and both support every
claim made here.

    A character normally needs a TARGETING Sense to detect an opponent in
    combat, and while he has one his CVs are unaffected. When he can
    perceive an opponent with no Targeting Sense at all -- blinded by a
    Flash, say, or facing someone Invisible -- he takes CV penalties, and
    the page is explicit that each applies whether he is attacking or
    being attacked in that kind of combat:

      * hand-to-hand: half OCV and half DCV;
      * at Range: OCV drops to zero, DCV is halved.

    He can mitigate that against ONE opponent by spending a Half Phase
    Action on a PER Roll with a NONTARGETING Sense. Against that opponent
    only, he is then at -1 DCV and half OCV hand-to-hand, and at FULL DCV
    and half OCV at Range. Against everyone else the unmitigated
    penalties above still stand. The benefit lapses at the start of his
    next Phase, and continuing it costs another Half Phase Action and
    another successful roll.

**Three things that rule forces, and any design missing one is wrong:**

1. **Per-opponent.** The 6E2 p.9 worked example (Orion, blinded by a
   Flash, who makes his Hearing PER Roll against Durak) has the same
   combatant at different CVs against different attackers in the same
   Segment. So the CV seam this plugs into cannot be
   ``(session, combatant_id) -> factors``; it needs the opponent.
2. **A flat modifier, not a factor.** Mitigated HTH DCV is **-1**, not a
   second halving. ``apply_cv_factor`` refuses any factor but 1.0/0.5/0.0
   *by design* (it has no page to ground other arithmetic in), so the
   seam grew a second, additive channel — ``*_delta`` keys — rather than
   an ungrounded factor like 0.875.
3. **Mitigation is asymmetric across HTH and Range.** Perceiving Durak by
   Hearing restores **full** DCV at Range but only improves HTH DCV to
   -1, and lifts Ranged OCV from 0 to 1/2 while leaving HTH OCV at 1/2.
   A single "blind, mitigated" boolean folded into one factor cannot
   express that; the table below is read per (combat_type, mitigated).

**Why "combat_type" and not "attack_type".** p.9 is explicit that each
row applies to a character both when he attacks and when he is attacked
in that kind of combat. The parameter names the KIND OF COMBAT taking
place between these two combatants, and it governs this combatant's OCV
and DCV alike. ``Flash.modifiers``'s older ``attack_type`` parameter
reads as "the attack I am making", which is only half of it.

**This module supersedes ``Flash.modifiers``** (``actions/flash.py``).
That function is not deleted — it is the shape several tests pin, and it
remains a correct answer to the narrower question it asks ("what are the
global factors for a flashed combatant") — but it cannot express any of
the three points above, and it is not wired into ``cv_modifiers``. New
callers want ``sense_penalty_modifiers`` or, better, the
``effective_*_for`` functions in ``cv_modifiers``. See that function's
docstring for the pointer back here.

**What counts as being unable to perceive with a Targeting Sense.** 6E2
p.9 draws the Targeting/Nontargeting line explicitly, and defines a
Targeting Sense as one that locates a target EXACTLY. It names Sight as
the only Targeting Sense a normal human has, with Hearing and Smell
Nontargeting. So a Flash against the Hearing Group costs a
normal human no CV at all, while one against the Sight Group costs him
everything — and a character who bought Active Sonar (a Targeting Sense
in the Hearing Group, ``perception._TARGETING_SENSE_XMLIDS``) still aims
after a Sight Flash. ``_targeting_senses_blocked`` reads the combatant's
actual senses rather than assuming a normal human.

**Deliberately NOT treated as an inability to sense here: line-of-sight
occlusion.** A wall between two combatants does block Sight, and by a
literal reading of p.9 would trigger these penalties. It is left out
because occlusion is already the province of ``resolution/line_of_sight``
and the driver's targeting gate (which refuses the attack outright rather
than pricing it), and folding it in here would silently re-price every
existing cover interaction in the engine. Darkness, which p.127 names in
the same breath as Flash, DOES belong here and arrives with Task 3 of the
sense-affecting-powers plan; it converges on ``_targeting_senses_blocked``
rather than growing a second implementation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


#: The two kinds of combat 6E2 p.9 gives separate rows for.
HTH = "hth"
RANGED = "ranged"


# ---------------------------------------------------------------------------
# 6E2 p.9's table, written out rather than computed
# ---------------------------------------------------------------------------
#
# Keys: (combat_type, mitigated_by_nontargeting_per_roll). Values are the
# modifier dict the CV seam folds. ``*_factor`` entries go through
# ``apply_cv_factor`` (grounded for 1.0/0.5/0.0 only); ``*_delta`` entries
# are added afterwards. An absent key means "unmodified", which is how
# "full DCV" in the mitigated Ranged row is expressed.
_SENSE_PENALTY_TABLE: dict[tuple[str, bool], dict[str, float]] = {
    # Unmitigated, hand-to-hand: half OCV, half DCV.
    (HTH, False): {"ocv_factor": 0.5, "dcv_factor": 0.5},
    # Unmitigated, at Range: OCV to zero, DCV halved.
    (RANGED, False): {"ocv_factor": 0.0, "dcv_factor": 0.5},
    # Nontargeting PER Roll made, hand-to-hand: -1 DCV, half OCV.
    (HTH, True): {"ocv_factor": 0.5, "dcv_delta": -1.0},
    # Nontargeting PER Roll made, at Range: FULL DCV, half OCV -- the
    # absent dcv key is the "full DCV" half of that row.
    (RANGED, True): {"ocv_factor": 0.5},
}


def _normalise_combat_type(combat_type: str) -> str:
    """``"ranged"`` or ``"hth"``; anything unrecognised reads as HTH.

    Matches ``Flash.modifiers``'s existing tolerance rather than raising:
    the HTH row is the less punishing of the two (1/2 OCV rather than 0),
    so an unrecognised value cannot silently make a combatant worse off
    than the book allows.
    """
    return RANGED if str(combat_type).lower() == RANGED else HTH


# ---------------------------------------------------------------------------
# Is this combatant blind to that opponent?
# ---------------------------------------------------------------------------

def _targeting_senses_blocked(
    session: "CombatSession", observer_id: str, opponent_id: str,
) -> bool:
    """True when NO Targeting Sense of ``observer_id`` can reach
    ``opponent_id`` — the condition 6E2 p.9 attaches its CV penalties to.

    Deterministic by construction: it consults only sense-disabling state
    (Flash today; Darkness from Task 3), never a die roll. A CV is read
    many times while an attack is built, and a predicate that rolled
    would return a different answer each time it was asked.

    **A combatant with no ``senses()`` falls back to the book's normal
    human, and does NOT fail open.** Only ``HeroCombatant`` (a build)
    exposes ``senses()``; ``StatBlockCombatant`` — which every example
    script, much of the suite, and any driver working from a flat stat
    block uses — does not. Failing open there would have meant the rule
    applied to build-backed combatants and silently did nothing for
    everyone else, which is precisely the "a structure half the engine
    ignores" outcome. Caught by ``examples/raw_orion.py`` on its first
    run: Orion, Flashed, reported a full 8 DCV. The fallback is grounded
    rather than invented — 6E2 p.9 names Sight as the only Targeting
    Sense a normal human has — so a stat block flashed in the Sight Group
    is blind and one flashed in the Hearing Group is not, matching what
    the same character would do as a build with no bought senses.

    A combatant the session does not know at all is treated as unblocked;
    there is nothing to reason about.
    """
    from kirby_combat.actions.flash import Flash
    from kirby_combat.perception import (
        SIGHT, SenseCapability, _darkness_blocks,
    )

    combatant = session.combatants.get(observer_id)
    opponent = session.combatants.get(opponent_id)
    if combatant is None:
        return False

    _, flashed = Flash.is_flashed(session, observer_id)
    blocked_groups = set(flashed)

    senses = combatant.senses() if hasattr(combatant, "senses") else None
    if senses is None:
        # 6E2 p.9's normal human: Sight, and only Sight, aims.
        senses = [SenseCapability(xmlid="NORMALSIGHT", name="Normal Sight",
                                  group=SIGHT)]

    scene = getattr(session, "scene", None)
    for sense in senses:
        if not getattr(sense, "is_targeting", True):
            continue
        if not getattr(sense, "functional", True):
            continue
        if getattr(sense, "group", None) in blocked_groups:
            continue                       # Flashed in this sense's Group
        if opponent is not None and _darkness_blocks(
                combatant, opponent, scene, sense):
            continue                       # a Darkness field on the ray
        return False        # at least one Targeting Sense still reaches
    return True


# ---------------------------------------------------------------------------
# The Nontargeting PER Roll (6E2 p.9) — mitigation, per observer per target
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NontargetingPerceptionResult:
    observer_id: str
    target_id: str
    sense_group: str
    succeeded: bool
    roll: int
    target_number: int


class NontargetingPerception:
    """Orion's Hearing PER Roll against Durak, as engine state.

    **Why this is its own action rather than a call into
    ``perception.perceive``:** ``perceive()`` answers "does a TARGETING
    Sense reach this target", and its own docstring records
    non-Targeting-sense perception as a v1 deferral ("``senses()`` returns
    only Targeting senses, so ``perceive()`` never emits a
    'perceived_nontargeting' kind"). Rather than widen that resolver — and
    with it every caller's meaning of "perceived" — the p.9 mitigation is
    modelled as what the book actually calls it: a Half Phase Action with
    a PER Roll, recorded on the log, readable back per (observer, target).

    **Expiry follows the engine's existing precedent for "until the
    holder's next Phase", not a new one.** ``HeldAction`` faces the
    identical duration wording (6E2 p.61) and resolves it with an explicit
    ``expire_for_combatant_next_phase`` call from the driver, because this
    engine's session carries a Segment-granularity timeline and no SPD
    chart to derive a combatant's next Phase from. This class mirrors that
    exactly; inventing a derived phase fold here would have been a second,
    disagreeing answer to a question the engine has already settled.
    """

    name: str = "nontargeting_perception"

    @staticmethod
    def acquire(
        session: "CombatSession",
        *,
        observer_id: str,
        target_id: str,
        sense_group: str,
        target_number: int | None = None,
        roller=None,
    ) -> tuple["CombatSession", NontargetingPerceptionResult]:
        """Spend a Half Phase Action on a Nontargeting PER Roll.

        ``target_number`` defaults to the observer's own PER roll target
        (``perception.per_roll_target``). It is exposed so a caller that
        has already applied situational modifiers — the Range Modifier
        applies to PER rolls (6E2 p.13/p.40) and this function does not
        know the distance — can pass the modified number rather than have
        this recompute a worse one.

        Records the attempt whether it succeeds or fails: a failed roll is
        still a spent Half Phase, and a driver that only saw successes
        could not charge for the miss.
        """
        from kirby_combat.perception import per_roll_target
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import (
            ActionDeclared, ActionResolved, make_author_combatant,
        )

        if roller is None:
            roller = session.dice_roller

        observer = session.combatants.get(observer_id)
        if target_number is None:
            target_number = per_roll_target(observer) if observer is not None else 11

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(observer_id),
            combatant_id=observer_id,
            action_type=NontargetingPerception.name,
            targets=[target_id],
            parameters={
                "sense_group": sense_group,
                "target_number": int(target_number),
                # 6E2 p.9 names the cost in the rule itself: "a Half Phase
                # Action". Surfaced as a declared parameter so a driver can
                # charge for it without re-deriving the rule.
                "phase_cost": "half",
            },
        )
        s = apply_event(session, declared)

        roll = sum(roller.roll_dice(3))
        succeeded = roll <= int(target_number)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(observer_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "nontargeting_perception",
                "observer_id": observer_id,
                "target_id": target_id,
                "sense_group": sense_group,
                "roll": roll,
                "target_number": int(target_number),
                "succeeded": succeeded,
            },
        )
        s = apply_event(s, resolved)

        return s, NontargetingPerceptionResult(
            observer_id=observer_id,
            target_id=target_id,
            sense_group=sense_group,
            succeeded=succeeded,
            roll=roll,
            target_number=int(target_number),
        )

    @staticmethod
    def holds(session: "CombatSession", observer_id: str, target_id: str) -> bool:
        """True while ``observer_id``'s PER Roll against ``target_id`` is
        still in force.

        Derived from the log, never from mutated combatant state, matching
        ``Flash.is_flashed`` / ``is_entangled`` / ``is_grabbed``. The last
        event about this (observer, target) pair wins: a later expiry
        clears an earlier success, and a later success re-establishes it
        (which is what p.9 requires to keep the benefit going: another
        Half Phase Action and another successful roll).
        """
        held = False
        for evt in session.event_log:
            payload = getattr(evt, "result_payload", None)
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            if kind == "nontargeting_perception":
                if (payload.get("observer_id") == observer_id
                        and payload.get("target_id") == target_id):
                    held = bool(payload.get("succeeded"))
            elif kind == "nontargeting_perception_expired":
                if (payload.get("observer_id") == observer_id
                        and payload.get("target_id") in (target_id, None)):
                    held = False
        return held

    @staticmethod
    def targets_held(session: "CombatSession", observer_id: str) -> set[str]:
        """Every target ``observer_id`` currently holds a PER Roll against."""
        out: set[str] = set()
        for other_id in session.combatants:
            if other_id != observer_id and NontargetingPerception.holds(
                    session, observer_id, other_id):
                out.add(other_id)
        return out

    @staticmethod
    def expire_for_combatant_next_phase(
        session: "CombatSession", observer_id: str,
    ) -> tuple["CombatSession", list[str]]:
        """Clear every PER-Roll benefit ``observer_id`` holds.

        6E2 p.9 ends the benefit at the start of the character's next
        Phase. Called by the driver at that edge, mirroring
        ``HeldAction.expire_for_combatant_next_phase`` (6E2 p.61) — see
        this class's docstring for why the engine does not derive the edge
        itself. Returns the ids whose benefit was cleared, so a caller can
        report what lapsed.
        """
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import ActionResolved, make_author_engine

        s = session
        cleared: list[str] = []
        for target_id in sorted(NontargetingPerception.targets_held(session, observer_id)):
            evt = ActionResolved(
                id=str(uuid.uuid4()),
                session_id=s.id,
                sequence=len(s.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine(),
                declaration_event_id="",
                result_payload={
                    "type": "nontargeting_perception_expired",
                    "observer_id": observer_id,
                    "target_id": target_id,
                },
            )
            s = apply_event(s, evt)
            cleared.append(target_id)
        return s, cleared


# ---------------------------------------------------------------------------
# The CV-seam source
# ---------------------------------------------------------------------------

def sense_penalty_modifiers(
    session: "CombatSession",
    combatant_id: str,
    opponent_id: str,
    combat_type: str = HTH,
) -> dict[str, float]:
    """6E2 p.9's modifiers for ``combatant_id`` against ``opponent_id``.

    ``{}`` when the combatant can perceive that opponent with a Targeting
    Sense — so a caller that always folds this gets today's numbers back
    for everyone who can see.

    This is the function wired into ``cv_modifiers``'s per-opponent seam;
    it is not usually called directly. Prefer
    ``cv_modifiers.effective_dcv_for(session, id, against=..., combat_type=...)``.
    """
    if not _targeting_senses_blocked(session, combatant_id, opponent_id):
        return {}
    mitigated = NontargetingPerception.holds(session, combatant_id, opponent_id)
    return dict(_SENSE_PENALTY_TABLE[(_normalise_combat_type(combat_type), mitigated)])
