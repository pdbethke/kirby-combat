"""Canonical status-id vocabulary for combat state emission.

**Kirby owns this vocabulary.** Each id here is named for the HERO System
condition this engine actually models (per HERO 6E), not transcribed from
another product's list. The engine's own internal names (`"Stunned"` /
`"Knocked Out"` / `"Dead"`, from `kirby_combat/resolution/status.py`) are
title-case-with-spaces and are NOT the wire vocabulary — they exist only
inside this engine and must never leak out; the ids below are what leaks
out instead.

Foundry (`hero6e-kirby/module/actor/actor-active-effects.mjs`, 43 ids) is a
**compatibility target and a coverage reference — never the authority.**
It is a fairly complete, already-published enumeration of HERO conditions,
which is exactly why it is worth reading: (a) `FOUNDRY_ID` below records
where our id and Foundry's *wire id* happen to differ, purely at the
serialization boundary, so a Foundry client can still be driven; (b) the
known-unmodelled section further down records HERO conditions Foundry
already has ids for that this engine does not produce yet — a checklist
for what a more complete implementation would cover. Neither role lets
Foundry's list cap what Kirby is allowed to define: a Kirby id with no
Foundry equivalent is expected and fine (see `NO_FOUNDRY_EQUIVALENT`
below), and adding a HERO condition Foundry lacks is ordinary work, not a
test failure. (Corrects `2026-08-26-statuses-must-be-emitted-design.md`
§5a / §6 bullet 1, which called Foundry's list "the canon" — see
`2026-08-27-kirby-owns-its-vocabulary-design.md`.)

This module defines **only the ids this engine can actually produce.**
Foundry defines 43 status ids in total; this engine is deliberately narrower.
An id the engine never emits is a promise it cannot keep, so ids that have
no engine-side source are omitted on purpose (see the two notes below) rather
than transcribed wholesale from Foundry's list.

`STUNNED` and `DEAD` were, for three earlier tasks on this branch, the
acknowledged exception to that rule: both are real, engine-defined
conditions (`resolution/status.py::determine_status_changes`) whose
result was computed and then discarded (`actions/base.py:190` folded it
into an audit-trail string only) -- there was no persisted source
`statuses_for` could fold from. Task 4 (this one) closes that gap for
both: `resolve_attack_in_session` (`actions/recording.py`) now records the
outcome as an `ActionResolved` whose `result_payload["status_changes"]`
survives on the event log, and `_is_stunned`/`_is_dead` below fold it back
out -- see `statuses_for`'s docstring for exactly what each reads and why
`STUNNED` additionally needs `SegmentAdvanced` to answer its clear edge.

Follow-up coherence fix (same task): that payload also names "Knocked
Out" whenever STUN falls to 0 or below, but `resolve_attack_in_session`
deliberately never mutates a combatant's live vitals (`session/apply.py`'s
log-only design), so `KNOCKED_OUT`'s pre-existing `is_ko` source (reading
live `current_stun`) never saw it -- a session could report `dead` and
`stunned` for a combatant with NO `knockedOut`, which is self-contradictory
to any consumer. `_is_knocked_out_from_payload` below adds the same
payload fold as a second, additive source for `KNOCKED_OUT`, unioned with
`is_ko` -- see that function's docstring for its clear edge.

This module is a vocabulary module (constants and a frozenset) PLUS,
below, `statuses_for` -- the one fold over every condition source. It does
not define a delta event (Task 3) and does not touch emission or
`resolution/status.py` itself.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# STUN / BODY thresholds
#
# Produced by kirby_combat.resolution.status.determine_status_changes, which
# returns the internal strings "Stunned" / "Knocked Out" / "Dead" for these
# same three checks. That module does not cite a page number for the
# thresholds it implements (stun_dealt > CON; current STUN <= 0; BODY <=
# -max_body) -- these are the well-known HERO 6E Stunning / Being Knocked Out
# / Death rules, but this module does not assert an unverified page citation.
# ---------------------------------------------------------------------------

STUNNED = "stunned"
# stun_dealt (from a single attack) > target's CON. See
# kirby_combat/resolution/status.py `determine_status_changes`, called
# from kirby_combat/actions/base.py:190 (physical attacks) --
# `resolve_attack_in_session` (actions/recording.py) records the result on
# the event log as an `ActionResolved` whose `result_payload["status_changes"]`
# carries "Stunned"; `_is_stunned` below folds that back out. See
# `statuses_for`'s docstring for the clear edge (6E2 p.107).
#
# `mental/mental_blast.py:45`'s own `target_stunned` (mental attacks) used
# to be a SEPARATE computation that nothing recorded onto the event log
# the same way a physical Stunned was -- that gap is CLOSED as of
# `resolve_mental_blast_in_session` (`actions/recording.py`, commit
# `df2486c`), which builds the SAME `status_changes` payload (via
# `resolution/status.py::determine_status_changes`) a physical attack's
# `resolve_attack_in_session` does. `_is_stunned` below folds a mental
# Stunned exactly the way it folds a physical one -- it reads
# `payload["status_changes"]` and never looks at `action_type`/`kind`, so
# it can't distinguish the two sources and doesn't need to.

KNOCKED_OUT = "knockedOut"
# current STUN <= 0. See kirby_combat/participant.py:139 `is_ko`
# ("Unconscious. 6E: at 0 STUN or below, not merely below zero.") and
# kirby_combat/resolution/status.py `determine_status_changes`.
#
# THREE sources fold into this id (Task 4 follow-up, "coherence" finding,
# plus a second coherence fix on top of that): live vitals (`is_ko` /
# `current_stun <= 0`, unchanged), the same
# `ActionResolved.result_payload["status_changes"]` fold used for STUNNED/
# DEAD (`_is_knocked_out_from_payload` below), and `_is_dead` itself (DEAD
# implies KNOCKED_OUT, unconditionally -- see `statuses_for`). The second
# source exists because `resolve_attack_in_session` deliberately never
# mutates vitals (`session/apply.py`'s log-only design) -- a payload naming
# "Stunned"/"Knocked Out"/"Dead" together, with vitals never touched,
# previously surfaced `dead`+`stunned` WITHOUT `knockedOut`, which is
# self-contradictory to any consumer (a dead combatant who was never
# knocked out). See `_is_knocked_out_from_payload`'s docstring for why its
# clear edge is deliberately conservative rather than latching. The third
# source exists because that clear edge (`RecoveryTaken`) fires for EVERY
# combatant unconditionally at every Turn wrap (6E2 p.131), corpses
# included, so the payload fold alone would clear KNOCKED_OUT out from
# under a DEAD combatant within one Turn -- reproducing the exact
# contradiction above, just delayed. DEAD never clears (see below), so
# forcing KNOCKED_OUT whenever DEAD is true closes that gap for good.
#
# NOTE: Foundry separately defines an "unconscious" id
# (`unconsciousEffect`, distinct changes from `knockedOutEffect`) but this
# engine has only ONE *condition* here -- `resolution/status.py` already
# labels both its sources "Knocked Out" -- so there is still no second,
# independent SIGNAL (e.g. sleep, drugging) that would justify a distinct
# `unconscious` id; the two folds above are two ways of observing the same
# condition, not two conditions. `KNOCKED_OUT` remains the one id emitted.

DEAD = "dead"
# BODY <= -max_body (double negative BODY). See
# kirby_combat/resolution/status.py `determine_status_changes`, called
# from kirby_combat/actions/base.py:190. `resolve_attack_in_session`
# (actions/recording.py) records the result on the event log as an
# `ActionResolved` whose `result_payload["status_changes"]` carries "Dead";
# `_is_dead` below folds that back out. Unlike STUNNED, this condition
# never clears (see `statuses_for`'s docstring).

RECOVERING_FROM_STUNNED = "recoveringFromStunned"
# 6E2 p.39's condition-modifier table gives this its OWN named row,
# separate from "Stunned" -- "Recovering from being Stunned, Dcv = 1/2.
# Recovering from being Stunned, hit locations = 1/2" -- the SAME penalty
# as Stunned outright, but the book treats it as its own condition, not a
# lingering tail of the first. 6E2 p.107, "RECOVERING FROM BEING STUNNED":
# "In the character's next full Phase after becoming Stunned, he recovers
# from being Stunned when his DEX occurs in the Segment... but he still
# cannot act until his next Phase -- recovering from being Stunned is all
# he can do that Phase."
#
# Named for camelCase-multiword parity with KNOCKED_OUT ("knockedOut")
# rather than a Stunned-prefixed variant -- this is p.39's own name for a
# distinct row, not a qualifier on STUNNED.
#
# Coherence gap this closes (found by `examples/stunned.py` step 5, the
# same shape as two prior Criticals on this branch): `cv_modifiers.py`'s
# CV penalty and `actions/reactive/abort.py`'s Abort denial both already
# read the WIDER `statuses.stunned_or_recovering_for` window (Task 3),
# but nothing surfaced that window as a status id of its own -- so a
# combatant past the narrower `stunned` clear edge but still inside that
# wider window showed an EMPTY status set while still losing half his DCV
# and his Abort, which is self-contradictory to any consumer (an
# apparently-unconditioned fighter who inexplicably can't act). See
# `_is_recovering_from_stunned` below for the derivation -- it does not
# duplicate `stunned_or_recovering_for`'s fold; it is defined directly in
# terms of it and `_is_stunned`, so the two ids stay mutually exclusive by
# construction (see `statuses_for`'s docstring for the exhaustive-and-
# exclusive proof).

# ---------------------------------------------------------------------------
# Entangle / Grab / Held Action / Abort
# ---------------------------------------------------------------------------

ENTANGLED = "entangled"
# HERO 6E1 Entangle; entangled while entangle BODY > 0. See
# kirby_combat.session.effects.entangle_state -> EntangleState.is_entangled,
# and kirby_combat/actions/entangle.py (6E2, entangled characters have 0 DCV
# and 1/2 OCV).

GRAB = "grab"
# 6E2 p67 SS USING GRAB (maneuver table p62). See
# kirby_combat.actions.grab.Grab.is_grabbed.

ABORTED = "aborted"
# A state description, not itself a single cited rule: true whenever a
# combatant has declared an abort this phase (Dodge, Block, or Dive for
# Cover), forfeiting their next action. The underlying maneuvers each carry
# their own citation -- Block 6E2 p59 SS USING BLOCK
# (kirby_combat/actions/reactive/block.py), Dive for Cover 6E2 p87 SS USING
# DIVE FOR COVER (kirby_combat/actions/dive_for_cover.py), Dodge per the
# maneuver table (kirby_combat/tables.py "martial_dodge" /
# kirby_combat/actions/reactive/dodge.py, no page cited in source) -- but
# "aborted" itself is this engine's shared bookkeeping flag for all three.
# See kirby_combat.actions.reactive.abort.is_aborting /
# session.timeline.aborted_this_phase.
#
# ONE-WAY LATCH, not a toggle: nothing in this package ever removes a
# combatant id from `aborted_this_phase` -- `apply_event`'s
# `SegmentAdvanced` branch (`session/apply.py`) replaces only
# `segment`/`turn` on the timeline, never touches `aborted_this_phase`.
# Verified: abort, then apply 26 `SegmentAdvanced` events (two full Turns)
# later, the id is still set. So despite the field's name, in an
# engine-built session this id never clears on its own once set -- it
# reads as "aborted for the rest of the fight", not "aborted this phase".
# This is pre-existing engine state (the clearing, if it belongs
# anywhere, is `apply_event`'s to add, and is its own separate change);
# this module just surfaces it as-is, so a consumer of `ABORTED` should
# not expect it to fall off phase-to-phase.

HOLDING = "holding"
# 6E2 p61 SS HOLD AN ACTION -- phase consumed, waiting on a declared trigger.
# See kirby_combat/actions/held_action.py (HeldActionDeclared without a
# matching HeldActionReleased).

# NOTE: Foundry's "prone" id is deliberately OMITTED. It is not stored as a
# per-combatant status anywhere in this engine: it appears only as an input
# *parameter* into cover resolution (`scene/cover.py:102`,
# `target_is_prone_or_diving`) and as a maneuver flag
# (`actions/martial_arts.py:43`, `target_falls`). There is no per-combatant
# source to read, so there is nothing this engine could emit -- a known gap,
# not an oversight.

# ---------------------------------------------------------------------------
# Flash — per-Sense-Group blinding
#
# Engine sense groups (kirby_combat/perception.py:20-24): sight, hearing,
# mental, radio, smell. These MUST match actions/flash.py's sense_group
# strings. HERO's Flash can target ANY Sense Group (6E1) -- a Mental-group
# Flash is as much a sensory blackout as a Sight-group one -- so this
# engine names all five with the same *SenseDisabled pattern rather than
# giving the Sight case a sight-specific folk name ("blind"). Foundry also
# defines danger / detect / sonar / spatialAwareness / touch SenseDisabled
# ids, which have NO corresponding engine sense group and are deliberately
# OMITTED (not an oversight; see the known-unmodelled section below).
# ---------------------------------------------------------------------------

SIGHT_SENSE_DISABLED = "sightSenseDisabled"
# Flash vs the Sight Group. See kirby_combat/actions/flash.py (Flash targets
# sight group per HERO 6E1) and kirby_combat/perception.py SIGHT.
#
# Kirby names this per its own per-Sense-Group pattern (matching the other
# four ids below) rather than borrowing Foundry's sight-specific "blind".
# Foundry's own *model* already agrees with the per-group naming --
# its object for this is `sightSenseDisabledEffect`, localized as
# "EFFECT.StatusSenseSightDisabled"
# (`hero6e-kirby/module/actor/actor-active-effects.mjs:406-408`) -- only its
# wire *id* is the legacy "blind". `FOUNDRY_ID` below records that
# divergence at the wire boundary only; it does not change how Kirby names
# the condition.

HEARING_SENSE_DISABLED = "hearingSenseDisabled"
# Flash vs the Hearing Group (HERO 6E1). See kirby_combat/perception.py
# HEARING and kirby_combat/actions/flash.py.

MENTAL_SENSE_DISABLED = "mentalSenseDisabled"
# Flash vs the Mental Group (HERO 6E1). See kirby_combat/perception.py
# MENTAL and kirby_combat/actions/flash.py.

RADIO_SENSE_DISABLED = "radioSenseDisabled"
# Flash vs the Radio Group (HERO 6E1). See kirby_combat/perception.py RADIO
# and kirby_combat/actions/flash.py.

SMELL_TASTE_SENSE_DISABLED = "smellTasteSenseDisabled"
# Flash vs the Smell/Taste Group (HERO 6E1). See kirby_combat/perception.py
# SMELL and kirby_combat/actions/flash.py (sense_group "smell").

# Engine sense-group string -> Kirby status id, for the groups this engine
# models (kirby_combat/perception.py:20-24).
SENSE_GROUP_TO_STATUS_ID: dict[str, str] = {
    "sight": SIGHT_SENSE_DISABLED,
    "hearing": HEARING_SENSE_DISABLED,
    "mental": MENTAL_SENSE_DISABLED,
    "radio": RADIO_SENSE_DISABLED,
    "smell": SMELL_TASTE_SENSE_DISABLED,
}

# ---------------------------------------------------------------------------
# The full canonical vocabulary
# ---------------------------------------------------------------------------

ALL_STATUS_IDS: frozenset[str] = frozenset(
    {
        STUNNED,
        KNOCKED_OUT,
        DEAD,
        RECOVERING_FROM_STUNNED,
        ENTANGLED,
        GRAB,
        ABORTED,
        HOLDING,
        SIGHT_SENSE_DISABLED,
        HEARING_SENSE_DISABLED,
        MENTAL_SENSE_DISABLED,
        RADIO_SENSE_DISABLED,
        SMELL_TASTE_SENSE_DISABLED,
    }
)

# ---------------------------------------------------------------------------
# FOUNDRY_ID -- one-directional wire mapping, Kirby id -> Foundry id
#
# This is the ONLY place Foundry's vocabulary touches this module. It exists
# purely at the serialization boundary, for a client that wants to drive an
# actual Foundry token; it is not consulted anywhere else in this package
# (`statuses_for`, `status_deltas`, `apply_event` all speak Kirby ids only).
#
# Eleven of thirteen ids map identically; only SIGHT_SENSE_DISABLED differs,
# because Foundry's wire id for that condition is the legacy "blind" (see
# the note on SIGHT_SENSE_DISABLED above). RECOVERING_FROM_STUNNED has no
# entry here at all -- see NO_FOUNDRY_EQUIVALENT below. Divergence should
# mean something; where Foundry and Kirby already agree, the mapping is
# the identity.
#
# Every value here must be a real id in FOUNDRY_STATUS_IDS_20260827
# (tests/test_statuses.py) -- but that snapshot no longer bounds
# ALL_STATUS_IDS itself (see NO_FOUNDRY_EQUIVALENT below): it validates
# mapping *targets* only, not the existence of Kirby ids.
FOUNDRY_ID: dict[str, str] = {
    STUNNED: "stunned",
    KNOCKED_OUT: "knockedOut",
    DEAD: "dead",
    ENTANGLED: "entangled",
    GRAB: "grab",
    ABORTED: "aborted",
    HOLDING: "holding",
    SIGHT_SENSE_DISABLED: "blind",
    HEARING_SENSE_DISABLED: "hearingSenseDisabled",
    MENTAL_SENSE_DISABLED: "mentalSenseDisabled",
    RADIO_SENSE_DISABLED: "radioSenseDisabled",
    SMELL_TASTE_SENSE_DISABLED: "smellTasteSenseDisabled",
}

# Kirby ids with no Foundry equivalent at all -- a *stated decision*, not an
# oversight, so an id missing from FOUNDRY_ID doesn't read as one we forgot
# to map. RECOVERING_FROM_STUNNED lives here: checked against
# `hero6e-kirby/module/actor/actor-active-effects.mjs` (the 43-id snapshot
# this module already reads elsewhere) and against 6E1's own Foundry-side
# HERO condition coverage -- neither defines any wire id for "recovering
# from being Stunned" as its own condition (Foundry's Stunned handling is
# a single `stunnedEffect`; the 6E2 p.39 table row this engine models has
# no Foundry-side counterpart at all). This is expected and fine per the
# module docstring, not an oversight -- Foundry's list is a coverage
# reference, never the authority on what Kirby is allowed to define.
NO_FOUNDRY_EQUIVALENT: frozenset[str] = frozenset({RECOVERING_FROM_STUNNED})

# ---------------------------------------------------------------------------
# Known-unmodelled -- Foundry ids for HERO Sense Groups this engine does not
# produce yet (coverage reference only; §3b of the design doc)
#
# HERO 6E1 p.211 ("SENSE GROUPS") lists the Sense Groups: "Hearing Group;
# Mental Group; Radio Group; Sight Group; Smell/Taste Group: Normal Smell,
# Normal Taste; Touch Group; Unusual Group: Active Sonar." (6E1 p.279 is a
# different table -- sense-group Flash/Images COST, not the enumeration --
# and is not the citation for this claim.) This engine's perception.py:20-24
# models five of those seven (sight, hearing, mental, radio, smell/taste);
# it does not model Touch or Unusual (Active Sonar) as sense groups a Flash
# can target. Foundry already has ids for several conditions in this space:
#
#   touchSenseDisabled              -- Flash vs the Touch Group (6E1 p.211)
#   sonarSenseDisabled               -- Flash vs the Unusual Group / Active
#                                        Sonar (6E1 p.211)
#   spatialAwarenessSenseDisabled    -- Spatial Awareness, a Targeting Sense
#                                        this engine currently files under
#                                        the Sight group (perception.py
#                                        _TARGETING_SENSE_XMLIDS), not its
#                                        own sense group
#   detectSenseDisabled               -- Detect, a Sense not modelled by this
#                                        engine's Flash/perception layer
#   dangerSenseDisabled               -- Danger Sense, a Sense not modelled by
#                                        this engine's Flash/perception layer
#
# These are recorded here as a checklist, not emitted: this engine has no
# per-combatant source for any of them today, so none appear in
# ALL_STATUS_IDS. This is Foundry's list doing its one genuinely useful job
# -- a coverage reference -- without being treated as an authority to match.
KNOWN_UNMODELLED_FOUNDRY_IDS: frozenset[str] = frozenset({
    "touchSenseDisabled",
    "sonarSenseDisabled",
    "spatialAwarenessSenseDisabled",
    "detectSenseDisabled",
    "dangerSenseDisabled",
})

# ---------------------------------------------------------------------------
# statuses_for -- one fold over every condition source
#
# This is the read model: "what conditions does this combatant have right
# now", folding sources that already exist and already treat status as a
# derivation over the event log (see is_entangled / is_grabbed / is_flashed
# docstrings in actions/entangle.py, actions/grab.py, actions/flash.py).
# This function invents no new derivation; it names one that already existed
# in five separate places and gives it one vocabulary (this module's ids).
# ---------------------------------------------------------------------------

from typing import TYPE_CHECKING

from kirby_combat.actions.entangle import Entangle
from kirby_combat.actions.flash import Flash
from kirby_combat.actions.grab import Grab
from kirby_combat.actions.held_action import HeldAction
from kirby_combat.tables import segments_for_spd

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def _is_stunned(session: "CombatSession", combatant_id: str) -> bool:
    """Fold Stunned's SET/CLEAR edges out of the event log (Task 4).

    SET: an ``ActionResolved`` whose ``result_payload`` names this
    combatant (``"target_id"``, written by ``resolve_attack_in_session``,
    ``actions/recording.py``) and whose ``"status_changes"`` contains
    ``"Stunned"`` (``resolution/status.py::determine_status_changes``:
    ``stun_dealt > con``).

    CLEAR (APPROXIMATE -- clears a Phase-fraction early; see below): 6E2
    p.107, "RECOVERING FROM BEING STUNNED" -- "In the character's next full
    Phase after becoming Stunned, he recovers from being Stunned when his
    DEX occurs in the Segment. He regains his full DCV... but he still
    cannot act until his next Phase -- recovering from being Stunned is
    all he can do that Phase." The precise rule clears Stunned PARTWAY
    THROUGH the Segment, at the character's DEX-ordered acting position,
    not at the Segment's start. This module has no acting-order position
    at this layer -- ``statuses_for`` folds a log of events, not a live
    per-Segment DEX ordering -- so there is nothing to clear "at DEX" against.
    The approximation actually implemented: this combatant's Phase segments
    (``segments_for_spd``, ``tables.py:117``, keyed off this combatant's own
    SPD -- 6E2's SPD chart is per-character) are computed once, and the flag
    clears on the first ``SegmentAdvanced`` (``session/events.py:60``,
    emitted per session by ``Encounter.advance_segment``) whose
    ``to_segment`` falls among them, walked in the log's own order so it
    can only be a ``SegmentAdvanced`` that comes AFTER the qualifying
    ``ActionResolved`` -- his next full Phase's Segment, but at its START,
    not at his DEX within it.

    This means ``statuses_for`` reports him un-Stunned for the entire
    Segment his recovery Phase falls in, including the portion of that
    Segment (everyone whose DEX is higher than his) during which 6E2 says
    "recovering from being Stunned is all he can do." The error is
    deliberately in the direction of clearing EARLY rather than of
    latching -- this branch's stated governing rule (see
    ``_is_knocked_out_from_payload``'s docstring: a status that never
    turns off is worse than one that never turns on) -- and it is
    contained: nothing in this engine currently gates action selection on
    the ``stunned`` id, so an early clear here does not let anyone act who
    shouldn't. Do not "fix" this by moving the clear edge later without
    also giving this layer real intra-Segment acting-order information;
    that would trade the contained early-clear error for the latching
    error this branch is built to avoid.

    A later qualifying hit re-sets the flag even if a prior one had
    already cleared it (or vice versa) -- this is a plain left-to-right
    fold over the whole log, not a first-match short-circuit, so repeated
    Stunned/recovery cycles across a long fight are handled correctly.

    GUARD: SPD 0 has no Phase at all (``SPEED_TO_SEGMENTS[0] == []``,
    ``tables.py``), so ``phase_segments`` is empty and no
    ``SegmentAdvanced.to_segment`` could ever match it -- without a guard
    this flag would latch forever, exactly the never-turns-off failure
    mode this branch is built to avoid (see above). No engine path
    produces a SPD-0 combatant today, but this function should not rely on
    that: when ``phase_segments`` is empty, the flag clears on the very
    next ``SegmentAdvanced`` event for this session, regardless of
    ``to_segment`` -- there is no valid Phase to wait for, so clearing
    immediately is the same "clear early rather than latch" bias the rest
    of this function already takes.
    """
    combatant = session.combatants[combatant_id]
    phase_segments = segments_for_spd(combatant.combat_stats().spd)

    stunned = False
    for evt in session.event_log:
        kind = evt.kind
        if kind == "ActionResolved":
            payload = getattr(evt, "result_payload", None) or {}
            if (
                payload.get("target_id") == combatant_id
                and "Stunned" in payload.get("status_changes", ())
            ):
                stunned = True
        elif kind == "SegmentAdvanced" and stunned:
            if not phase_segments or evt.to_segment in phase_segments:
                stunned = False
    return stunned


def stunned_or_recovering_for(session: "CombatSession", combatant_id: str) -> bool:
    """True while Stunned OR recovering from being Stunned (Task 3,
    ``conditions-must-bite``; window corrected in the merge-blocker fix
    below -- read the CORRECTED WINDOW section before touching this
    function again).

    6E2 p.106, "Stunning": "A character who's Stunned or recovering from
    being Stunned can take no Actions, take no Recoveries (except his
    free Post-Segment 12 Recovery), cannot move, and cannot be affected
    by Presence Attacks." -- this is a WIDER window than the ``stunned``
    status id above: ``_is_stunned`` clears at the START of the
    combatant's recovery Phase (see its own docstring for why that is
    the right edge for the ``stunned`` id specifically), but this
    consequence -- no Actions/no movement/PRE-Attack immunity -- is
    explicitly extended to "recovering from being Stunned" as its own
    named state, by the same sentence that lists it.

    **CORRECTED WINDOW (6E2 p.107, quoted in full, since an earlier
    version of this function got the edge wrong by a whole Phase):**

    > "In the character's next full Phase after becoming Stunned, he
    > recovers from being Stunned when his DEX occurs in the Segment. He
    > regains his full DCV (and Placed Shot modifiers return to normal),
    > but he still cannot act until his next Phase -- recovering from
    > being Stunned is all he can do that Phase. However, after
    > recovering from being Stunned, a character may, if he wishes,
    > Abort to a defensive Action (even in the same Segment in which he
    > recovers from being Stunned). Example: Andarra (DEX 20, SPD 3) is
    > Stunned by an attack on Segment 6. She must use her Phase on
    > Segment 8 to recover; she recovers on DEX 20 (so an enemy attacking
    > her in Segment 8 with, say, DEX 15 would have to hit her at her
    > full DCV). Andarra cannot take any other Action until her next
    > Phase on Segment 12, but may Abort her Phase in Segment 12 in
    > Segments 8 (after her DEX occurs), 9, 10, or 11 if she so desires."

    So the book's own example runs DCV and Abort back to normal for
    Andarra in Segments 9, 10, and 11 -- the whole stretch between her
    recovery Phase (Segment 8) and her NEXT full Phase (Segment 12). The
    earlier version of this function stopped the window at that NEXT
    full Phase instead of at the recovery Phase's own Segment, which
    denied Andarra's Abort and halved her DCV for three Segments (9, 10,
    11) the book explicitly restores her in -- one full Phase too long.

    **The fix: the window runs from the Stunning hit through the END of
    the Segment containing the recovery Phase, and is gone from the next
    ``SegmentAdvanced`` onward.** In fold terms: the same SET edge (a
    qualifying "Stunned" in an ``ActionResolved.status_changes``) enters
    "stunned"; the first matching ``SegmentAdvanced`` (the recovery
    Phase, same edge ``_is_stunned`` clears on) enters "recovering"; and
    the VERY NEXT ``SegmentAdvanced`` after that -- regardless of whether
    it is one of the combatant's own Phase segments -- clears back to
    "none". That is exactly one Segment of "recovering", matching
    Andarra's Segment 8 alone, not Segments 8-11.

    **Residual approximation, documented rather than hidden (matching
    ``_is_stunned``'s own honesty about its early-clear bias):** the book
    restores full DCV and allows the Abort PARTWAY THROUGH the recovery
    Segment -- "she recovers on DEX 20", i.e. once her DEX has come up in
    that Segment, not from the top of it. This fold has no intra-Segment
    DEX-order information (``statuses_for`` folds a Segment-granularity
    log, not a DEX-ordered action queue), so it cannot represent that
    precise edge. Ending the window at the CLOSE of the recovery Segment
    (rather than at Andarra's DEX within it) over-penalises by at most
    the post-DEX portion of that ONE Segment -- versus the prior bug's
    over-penalisation by up to a full Phase (three Segments, in
    Andarra's case). The direction of the residual error is
    "conservative": a combatant who should already be free to Abort or
    act at full DCV, for the sliver of the recovery Segment before their
    own DEX comes up, is still shown as recovering. No engine layer this
    function feeds (``cv_modifiers.py``, ``actions/reactive/abort.py``,
    ``scene/movement_legality.py``) has DEX-ordered intra-Segment timing
    to do better with; closing that gap would need the acting-order
    model this branch does not have, not a change to this fold.

    The single source of truth for this window -- ``cv_modifiers.py``'s
    Stunned CV penalty (6E2 p.39: the SAME DCV-1/2/hit-location-1/2 row
    for "recovering from being Stunned" as for "Stunned" outright) reads
    this function rather than re-deriving the fold, so the two consumers
    (a CV penalty, an action denial) cannot silently drift to different
    boundaries.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        raise KeyError(
            f"stunned_or_recovering_for: unknown combatant {combatant_id!r} "
            "-- this session has no combatant with that id"
        )
    phase_segments = segments_for_spd(combatant.combat_stats().spd)

    stage = "none"  # "none" -> "stunned" -> "recovering" -> "none"
    for evt in session.event_log:
        kind = evt.kind
        if kind == "ActionResolved":
            payload = getattr(evt, "result_payload", None) or {}
            if (
                payload.get("target_id") == combatant_id
                and "Stunned" in payload.get("status_changes", ())
            ):
                stage = "stunned"
        elif kind == "SegmentAdvanced":
            if stage == "stunned":
                at_phase = not phase_segments or evt.to_segment in phase_segments
                if at_phase:
                    stage = "recovering"
            elif stage == "recovering":
                # The VERY NEXT SegmentAdvanced after entering "recovering"
                # clears it, regardless of to_segment -- see CORRECTED
                # WINDOW above. "Recovering" lasts exactly the one Segment
                # in which the combatant's recovery Phase falls, not until
                # their next full Phase.
                stage = "none"
    return stage in ("stunned", "recovering")


def _is_recovering_from_stunned(session: "CombatSession", combatant_id: str) -> bool:
    """Fold RECOVERING_FROM_STUNNED out of the event log: exactly the gap
    between ``stunned_or_recovering_for``'s wider window and ``_is_stunned``'s
    narrower one -- true while the combatant is in the "recovering" stage
    of ``stunned_or_recovering_for``'s own fold but ``_is_stunned`` no
    longer holds.

    Deliberately NOT a re-derivation: this reuses both existing folds
    rather than re-walking the event log a third time, which is what
    keeps ``STUNNED`` and ``RECOVERING_FROM_STUNNED`` mutually exclusive
    BY CONSTRUCTION (see ``statuses_for``'s docstring) -- one is exactly
    "wide AND NOT narrow", so the two can never both be true for the same
    combatant at the same time, and (since ``stunned_or_recovering_for``
    is the strict superset) they can never both be false while
    ``stunned_or_recovering_for`` itself is true either -- closing the gap
    ``examples/stunned.py`` step 5 printed (an empty status set while
    ``stunned_or_recovering_for`` was still gating the CV penalty and the
    Abort denial).

    6E2 p.39's condition table gives "Recovering from being Stunned" its
    own named row (DCV 1/2, hit locations 1/2 -- identical to "Stunned"),
    and 6E2 p.107 narrates the same window: "recovering from being
    Stunned is all he can do that Phase."
    """
    return stunned_or_recovering_for(session, combatant_id) and not _is_stunned(
        session, combatant_id
    )


def _is_dead(session: "CombatSession", combatant_id: str) -> bool:
    """Fold Dead out of the event log (Task 4): an ``ActionResolved``
    naming this combatant (``"target_id"``, ``resolve_attack_in_session``)
    whose ``"status_changes"`` contains ``"Dead"``
    (``resolution/status.py::determine_status_changes``:
    ``body_after <= -max_body``). Unlike Stunned, this never clears --
    HERO 6E has no "recovering from Dead" rule, so once set this is set
    for the rest of the fold.
    """
    for evt in session.event_log:
        if evt.kind == "ActionResolved":
            payload = getattr(evt, "result_payload", None) or {}
            if (
                payload.get("target_id") == combatant_id
                and "Dead" in payload.get("status_changes", ())
            ):
                return True
    return False


def _is_knocked_out_from_payload(session: "CombatSession", combatant_id: str) -> bool:
    """Fold a payload-derived Knocked Out out of the event log (Task 4
    coherence follow-up): an ``ActionResolved`` naming this combatant
    whose ``"status_changes"`` contains ``"Knocked Out"``
    (``resolution/status.py::determine_status_changes``: ``stun_after <=
    0``). This is a SECOND, additive source for ``KNOCKED_OUT`` --
    ``statuses_for`` also still reads the live ``is_ko`` /
    ``current_stun <= 0`` predicate, unioned with this one -- added
    because ``resolve_attack_in_session`` deliberately never mutates
    vitals (``session/apply.py``'s log-only design), so a payload naming
    "Stunned"/"Knocked Out"/"Dead" together, on a session that never
    touches ``current_stun``, previously produced ``dead``+``stunned``
    with NO ``knockedOut`` -- self-contradictory to any consumer.

    CLEAR EDGE, decided deliberately: this flag clears on the next
    ``RecoveryTaken`` event for this combatant (``combatant_id`` field),
    rather than never clearing (like DEAD) or clearing on a Phase-based
    rule (like STUNNED). Reasoning:

    - Being Knocked Out is not a fixed-duration condition the way Stunned
      is (6E2 p.107 names an exact clearing Segment). It ends when STUN
      rises back above 0 -- a live-vitals fact this fold, deliberately,
      never reconstructs (that would mean replaying a full STUN ledger
      from the log, which is a materially bigger derivation this task
      does not attempt, and would duplicate what live vitals already
      answer correctly whenever a caller DOES mutate them).
    - ``RecoveryTaken`` (6E2 p.131, "POST-SEGMENT 12 RECOVERY") is the one
      log event that represents STUN being restored, so it is the most
      rule-relevant signal available for "this combatant may have
      recovered" -- but seeing the event proves neither that enough STUN
      was restored nor that it wasn't; it is a conservative proxy, not an
      exact replay.
    - Given that imprecision, this branch's own governing rule (a status
      that never turns off is worse than one that never turns on --
      exactly why STUNNED was deferred three times) means the tie goes to
      NOT latching: clearing on the first plausible recovery signal,
      accepting an occasional early clear, rather than a flag that can
      never come down once a caller's driver stops mutating vitals.
    """
    ko = False
    for evt in session.event_log:
        kind = evt.kind
        if kind == "ActionResolved":
            payload = getattr(evt, "result_payload", None) or {}
            if (
                payload.get("target_id") == combatant_id
                and "Knocked Out" in payload.get("status_changes", ())
            ):
                ko = True
        elif kind == "RecoveryTaken" and ko:
            if getattr(evt, "combatant_id", None) == combatant_id:
                ko = False
    return ko


def statuses_for(session: "CombatSession", combatant_id: str) -> frozenset[str]:
    """Fold every condition source into one status set for a combatant.

    Sources read, and why each is read at this layer rather than another:

    - KO: the UNION of two sources (Task 4 coherence follow-up) --
      ``session.combatants[combatant_id].is_ko``, a property,
      ``current_stun <= 0`` (``participant.py:139``, "Unconscious. 6E: at 0
      STUN or below, not merely below zero."), OR
      ``_is_knocked_out_from_payload(session, combatant_id)`` (this
      module), which folds ``ActionResolved.result_payload["status_changes"]``
      the same way STUNNED/DEAD do. Additive, not a replacement: a session
      whose driver DOES mutate vitals keeps working exactly as before via
      ``is_ko``; the payload fold exists for the log-only case
      ``resolve_attack_in_session`` produces, where nothing else would
      ever set KNOCKED_OUT even though the payload plainly says so. See
      ``_is_knocked_out_from_payload``'s docstring for its clear edge.
      A THIRD condition also forces KNOCKED_OUT regardless of the two
      above: ``_is_dead(session, combatant_id)`` -- DEAD implies
      KNOCKED_OUT unconditionally (added below, after the Dead bullet),
      because a dead combatant is definitionally knocked out and nothing
      in 6E2 lets that reverse. This closes a real bug: without it, a
      lethal hit's KNOCKED_OUT (sourced from the payload fold) clears on
      the next ``RecoveryTaken`` -- emitted for every combatant
      unconditionally at every Turn wrap, 6E2 p.131 -- while DEAD never
      clears, so the combatant would read back as dead-but-not-knocked-out
      within at most one Turn (12 Segments).
    - Entangled: ``Entangle.is_entangled(session, combatant_id)``
      (``actions/entangle.py``) -- the ``actions/`` function, not
      ``session.effects.EntangleState``, because the ``actions/`` layer is
      the one whose own docstring says "scan event log" and is what the
      rest of the engine (tests, other actions) already calls; reading two
      layers for the same fact risks them drifting out of sync, so this
      picks one.
    - Grabbed: ``Grab.is_grabbed(session, combatant_id)``
      (``actions/grab.py``, 6E2 p67 SS USING GRAB) -- same reasoning.
    - Flashed: ``Flash.is_flashed(session, combatant_id)``
      (``actions/flash.py``, HERO 6E1) -- same reasoning; the ``session
      .effects.FlashState.is_flashed`` property is the alternate layer, not
      used here for the same reason. Each affected sense group is mapped
      through ``SENSE_GROUP_TO_STATUS_ID`` independently -- a combatant
      flashed in two groups gets both ids, never collapsed to one.
    - Aborted: ``session.timeline.aborted_this_phase`` (``session/timeline
      .py``), a ``set[str]`` of combatant ids maintained by
      ``actions/reactive/abort.py``.
    - Holding: ``HeldAction.get_pending(session, combatant_id)``
      (``actions/held_action.py``, 6E2 p61 SS HOLD AN ACTION) -- **not**
      ``session.timeline.held_actions``, despite that field's name and
      shape looking like the obvious source: nothing in this codebase ever
      appends to it (``apply_event``'s ``HeldActionDeclared`` branch is a
      declaration-only no-op, like ``ActionDeclared``), so that list is
      always empty. ``get_pending`` is the real, event-log-derived source
      (un-released ``HeldActionDeclared`` events for this combatant),
      matching the ``is_entangled`` / ``is_grabbed`` / ``is_flashed``
      pattern this whole function already follows.
    - Stunned: ``_is_stunned(session, combatant_id)`` (this module) --
      folds ``ActionResolved.result_payload["status_changes"]`` (set,
      written by ``resolve_attack_in_session``) against ``SegmentAdvanced``
      (clear, 6E2 p.107 -- see that function's docstring for the exact
      SET/CLEAR fold). Covers a mental Stunned too, as of
      ``resolve_mental_blast_in_session`` (``actions/recording.py``,
      commit ``df2486c``) -- ``_is_stunned`` reads
      ``payload["status_changes"]`` without looking at ``action_type``,
      so a mental attack's payload folds in exactly the same way a
      physical one's does.
    - Recovering from being Stunned:
      ``_is_recovering_from_stunned(session, combatant_id)`` (this
      module) -- 6E2 p.39's own separate condition-table row for this
      window (see ``RECOVERING_FROM_STUNNED``'s and
      ``_is_recovering_from_stunned``'s docstrings). Folded via an
      ``elif`` against ``_is_stunned`` immediately above, so ``STUNNED``
      and ``RECOVERING_FROM_STUNNED`` are mutually exclusive in the
      returned set BOTH by ``_is_recovering_from_stunned``'s own
      definition (wide window AND NOT narrow window) AND by this
      call-site branch -- belt and suspenders on purpose, given this
      branch's history of exactly this shape of coherence gap.
    - Dead: ``_is_dead(session, combatant_id)`` (this module) -- same
      ``status_changes`` source as Stunned, no clear edge (see that
      function's docstring).
    - Knocked Out (payload half): ``_is_knocked_out_from_payload(session,
      combatant_id)`` (this module) -- same ``status_changes`` source
      again, unioned into the KO bullet above; see that function's
      docstring for why its clear edge is ``RecoveryTaken``, not never
      (unlike Dead) and not Phase-based (unlike Stunned).

    Deliberately NOT read here:

    - ``prone`` -- not stored per-combatant anywhere in this engine (see the
      module-level NOTE above); there is nothing to fold in.

    Formerly NOT read here, now covered (corrects earlier text in this
    docstring): a **mental** Stunned/Knocked Out. ``mental/mental_blast.py
    :45``'s own ``target_stunned``/``target_ko`` used to be computed by a
    resolver ``resolve_attack_in_session`` didn't wrap, so nothing
    persisted them onto the event log. ``resolve_mental_blast_in_session``
    (``actions/recording.py``, commit ``df2486c``) closed that gap by
    building the same ``status_changes`` payload
    (``resolution/status.py::determine_status_changes``) a physical
    attack's wrapper does -- ``_is_stunned`` and
    ``_is_knocked_out_from_payload`` both fold it with no code change of
    their own, since neither reads ``action_type``.

    Preconditions -- this function requires a session whose ``event_log``
    contains the *complete* history for the seven sources that walk it
    (Entangled, Grabbed, Flashed, Holding, Stunned, Dead, and the
    payload half of Knocked Out), and a ``timeline.aborted_this_phase``
    that has been populated by every abort applied so far. **kirby-api's
    rehydrated session supplies neither:**

    - ``kirby-api/kirby/combat/services/session_service.py:237`` sets
      ``event_log=_FakeLog(row.last_sequence)``, whose ``__iter__`` always
      returns ``iter([])`` -- the persisted log lives in Postgres and is
      never handed back to the engine outside the rewind-rebuild path.
    - ``kirby-api/kirby/combat/services/session_service.py:219`` builds
      ``Timeline(turn=..., segment=..., acting_order=[],
      current_slot_index=...)`` -- ``aborted_this_phase`` is never
      populated.

    So on that path, ``before.event_log`` is empty and ``after.event_log``
    holds only the event just applied: the stream can only ever turn a
    token **on** (e.g. an ``EntangleApplied`` looks like a fresh condition
    by luck, but the later ``EntangleEscape`` produces nothing, because
    both snapshots read as clean). ``_is_stunned``/``_is_dead``/
    ``_is_knocked_out_from_payload`` inherit this exact hazard -- a
    qualifying ``ActionResolved`` looks fresh by the same luck, and
    ``_is_stunned``'s clear edge (a *subsequent* ``SegmentAdvanced``) and
    ``_is_knocked_out_from_payload``'s (a *subsequent* ``RecoveryTaken``)
    can never be seen at all on a log that never accumulates past one
    event. Consuming this surface from kirby-api's live path needs the
    log replayed first, or a session variant that accumulates it --
    neither is done by this module. The live half of KO --
    ``participant.is_ko`` / ``current_stun <= 0``, combatant state, not
    the log -- is unaffected and stays correct even under rehydration;
    only the payload half of KO (unioned in) shares the log-based hazard
    the other five sources have.

    Performance: ``is_entangled``, ``is_grabbed``, ``is_flashed``,
    ``HeldAction.get_pending``, ``_is_stunned``, ``_is_dead`` and
    ``_is_knocked_out_from_payload`` each walk the entire event log
    independently, so a single call to this function is O(events) per
    source, i.e. O(7 * events) for those seven plus O(1) for the live
    ``is_ko``/aborted checks. Fine for the combats this engine runs (short
    logs, called per combatant per emission, not per tick); no caching is
    added here -- measure before optimising.

    Returns an empty frozenset (never ``None``) for a combatant with no
    conditions.
    """
    statuses: set[str] = set()

    participant = session.combatants[combatant_id]
    if participant.is_ko or _is_knocked_out_from_payload(session, combatant_id):
        statuses.add(KNOCKED_OUT)

    is_entangled, _ = Entangle.is_entangled(session, combatant_id)
    if is_entangled:
        statuses.add(ENTANGLED)

    is_grabbed, _ = Grab.is_grabbed(session, combatant_id)
    if is_grabbed:
        statuses.add(GRAB)

    _, flashed_groups = Flash.is_flashed(session, combatant_id)
    for sense_group in flashed_groups:
        status_id = SENSE_GROUP_TO_STATUS_ID.get(sense_group)
        if status_id is not None:
            statuses.add(status_id)

    if combatant_id in session.timeline.aborted_this_phase:
        statuses.add(ABORTED)

    if HeldAction.get_pending(session, combatant_id):
        statuses.add(HOLDING)

    if _is_stunned(session, combatant_id):
        statuses.add(STUNNED)
    elif _is_recovering_from_stunned(session, combatant_id):
        # `elif`, not a second independent `if`: `_is_recovering_from_stunned`
        # is already defined as "wide window AND NOT narrow window" (see its
        # own docstring), so this branch is dead when STUNNED fires above --
        # the `elif` just makes that mutual exclusivity visible at the call
        # site too, rather than relying only on the callee's own guarantee.
        statuses.add(RECOVERING_FROM_STUNNED)

    if _is_dead(session, combatant_id):
        statuses.add(DEAD)
        # A dead combatant is definitionally knocked out (this is a rule
        # implication, not a patch over the payload fold below): 6E2 has no
        # state "dead but conscious/acting", so DEAD => KNOCKED_OUT always,
        # regardless of what the KO sources above concluded. This closes a
        # real coherence gap found in review: `_is_knocked_out_from_payload`
        # clears on the very next `RecoveryTaken` (6E2 p.131's Post-Segment
        # 12 Recovery, emitted for EVERY combatant unconditionally on every
        # Turn wrap -- `encounter.py::_apply_post_12_recovery` -- corpses
        # included), while `_is_dead` never clears. Without this line, a
        # lethal hit produces {dead, knockedOut, stunned} at the moment of
        # the hit, then loses `knockedOut` the instant the Turn wraps once
        # (a `RecoveryTaken` a dead combatant does not "take" in any
        # meaningful sense, but the log emits one anyway) -- reintroducing
        # the exact "dead combatant who was never knocked out"
        # self-contradiction this module's KNOCKED_OUT comment above says is
        # unacceptable, just delayed rather than immediate. Folding the
        # implication in here, rather than gating
        # `_is_knocked_out_from_payload`'s clear on `not _is_dead(...)`,
        # keeps that function's own clear-edge reasoning (a plain
        # "recovery signal seen" proxy) uncomplicated by a second
        # combatant's-worth of DEAD-awareness; the implication belongs at
        # the point where two sources are already being reconciled into
        # one combatant's status set, not smuggled into a single source's
        # clear edge.
        statuses.add(KNOCKED_OUT)

        # DEAD also implies NOT recovering-from-Stunned (review finding,
        # ``2026-08-28-conditions-must-bite`` final-fix pass): "recovering"
        # names an active process -- 6E2 p.107, "recovering from being
        # Stunned is all he can do that Phase" -- and a corpse cannot
        # undertake any process, active or passive. Without this, a lethal
        # hit followed by one at-Phase `SegmentAdvanced` produces
        # ``{dead, knockedOut, recoveringFromStunned}``, which names an
        # ongoing recovery for a combatant who, per this same line, is
        # unconditionally KNOCKED_OUT and DEAD. Discarding rather than
        # gating `_is_recovering_from_stunned`'s own fold on `not
        # _is_dead(...)` keeps that function's contract (exactly
        # `stunned_or_recovering_for` AND NOT `_is_stunned`) uncomplicated
        # by a second combatant's-worth of DEAD-awareness -- the same
        # reasoning the KNOCKED_OUT implication just above already uses.
        #
        # KNOCKED_OUT ALONE (not DEAD) deliberately does NOT get the same
        # implication here, even though an unconscious combatant cannot
        # actively "recover from being Stunned" either in principle.
        # Decided against, not merely deferred: unlike DEAD (exact,
        # irreversible, no clear edge), the KNOCKED_OUT id is the UNION of
        # three sources (see this function's own KO bullet above), and its
        # payload half is its own docstring's self-described "conservative
        # proxy... an occasional early clear... not an exact replay" that
        # can read true for a combatant who, moments later in the same log,
        # is genuinely conscious and legitimately recovering (this
        # engine's own test suite exercises exactly that combination as
        # correct today -- e.g.
        # ``tests/test_stunned_enforcement.py::test_recovering_from_stunned_fills_the_gap_stunned_leaves``,
        # where the qualifying hit also drives payload STUN below zero).
        # Layering "no recovering while knocked out" on top of a signal
        # that is already documented as over-inclusive would suppress
        # RECOVERING_FROM_STUNNED for combatants the log cannot actually
        # prove are still unconscious -- trading one coherence gap (a
        # corpse "recovering") for a worse one (a conscious, recovering
        # combatant silently losing the id a CV-penalty/Abort-denial
        # consumer already keys on). DEAD has no such false-positive risk,
        # so only DEAD gets the implication.
        statuses.discard(RECOVERING_FROM_STUNNED)

    return frozenset(statuses)
