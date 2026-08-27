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

Two ids, `STUNNED` and `DEAD`, are the acknowledged exception to that rule
today: both are real, engine-defined conditions
(`resolution/status.py::determine_status_changes`) with no persisted
source `statuses_for` can fold from yet -- see that function's
"Deliberately NOT read here" section for exactly why. They are kept in
`ALL_STATUS_IDS` rather than dropped because the condition genuinely
exists in this engine's rules and is expected to gain a source (a later
persistence task), not because this module is being loose about its own
stated rule.

This is a vocabulary module only: constants and a frozenset. It does not
compute any status (that is `statuses_for`, Task 2), does not define a delta
event (Task 3), and does not touch emission or `resolution/status.py`
(Tasks 4/5).
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
# from TWO sites -- both compute this and neither persists it:
# kirby_combat/actions/base.py:190 (physical attacks; folded into an
# audit-trail string only) and kirby_combat/mental/mental_blast.py:45
# (`target_stunned`, mental attacks; same fate). See `statuses_for`'s
# "Deliberately NOT read here" section below: this engine has no source
# to fold this id from yet.

KNOCKED_OUT = "knockedOut"
# current STUN <= 0. See kirby_combat/participant.py:139 `is_ko`
# ("Unconscious. 6E: at 0 STUN or below, not merely below zero.") and
# kirby_combat/resolution/status.py `determine_status_changes`.
#
# NOTE: Foundry separately defines an "unconscious" id
# (`unconsciousEffect`, distinct changes from `knockedOutEffect`) but this
# engine has only ONE source for this condition -- `is_ko` /
# `current_stun <= 0` -- which `resolution/status.py` itself already labels
# "Knocked Out". There is no second, independent engine signal (e.g. sleep,
# drugging) that would justify a distinct `unconscious` id here, so it is
# deliberately NOT included: it would be a promise (a second, different
# trigger) this engine cannot keep. `KNOCKED_OUT` is the one id emitted for
# `is_ko`.

DEAD = "dead"
# BODY <= -max_body (double negative BODY). See
# kirby_combat/resolution/status.py `determine_status_changes`, called
# from kirby_combat/actions/base.py:190, which folds the result into an
# audit-trail string only -- never persisted. Same gap as STUNNED: kept
# in ALL_STATUS_IDS as a real, engine-defined condition, but see
# `statuses_for`'s "Deliberately NOT read here" section -- this engine
# has no source to fold this id from yet either.

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
# Eleven of twelve ids map identically; only SIGHT_SENSE_DISABLED differs,
# because Foundry's wire id for that condition is the legacy "blind" (see
# the note on SIGHT_SENSE_DISABLED above). Divergence should mean something;
# where Foundry and Kirby already agree, the mapping is the identity.
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
# to map. Empty today: every id in ALL_STATUS_IDS happens to have a Foundry
# counterpart. This set is where a future Kirby-only condition (one Foundry
# has no id for at all) would be declared, so it stays even though nothing
# populates it yet -- see the module docstring: a Kirby id with no Foundry
# equivalent is expected and fine, never a test failure.
NO_FOUNDRY_EQUIVALENT: frozenset[str] = frozenset()

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

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def statuses_for(session: "CombatSession", combatant_id: str) -> frozenset[str]:
    """Fold every condition source into one status set for a combatant.

    Sources read, and why each is read at this layer rather than another:

    - KO: ``session.combatants[combatant_id].is_ko`` -- a property,
      ``current_stun <= 0`` (``participant.py:139``, "Unconscious. 6E: at 0
      STUN or below, not merely below zero.").
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

    Deliberately NOT read here:

    - ``prone`` -- not stored per-combatant anywhere in this engine (see the
      module-level NOTE above); there is nothing to fold in.
    - ``stunned`` -- computed at attack time by both
      ``resolution/status.py::determine_status_changes`` (physical attacks,
      called from ``actions/base.py:190``) and
      ``mental/mental_blast.py:45``'s ``target_stunned`` (mental attacks),
      and in both cases the result is folded into an audit-trail string,
      never persisted as an event or written onto combatant state. This
      function has **no branch that adds ``STUNNED``**, and cannot until a
      later task makes one of those results persist -- there is a real gap
      here today, not merely a future improvement; whichever mechanism ends
      up persisting it will need a new source read added to this function,
      not just "start working" on its own.
    - ``dead`` -- same shape as ``stunned`` above: computed by
      ``resolution/status.py::determine_status_changes`` (called from
      ``actions/base.py:190``) as the ``"Dead"`` string, folded into the
      same discarded audit trail, never persisted. This function has no
      branch that adds ``DEAD`` either, for the same reason.

    Preconditions -- this function requires a session whose ``event_log``
    contains the *complete* history for the four sources that walk it
    (Entangled, Grabbed, Flashed, Holding), and a
    ``timeline.aborted_this_phase`` that has been populated by every abort
    applied so far. **kirby-api's rehydrated session supplies neither:**

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
    both snapshots read as clean). Consuming this surface from kirby-api's
    live path needs the log replayed first, or a session variant that
    accumulates it -- neither is done by this module. The one id
    unaffected by this: ``KNOCKED_OUT``, read from
    ``participant.is_ko`` / ``current_stun <= 0`` -- combatant state, not
    the log -- so it is correct even under rehydration.

    Performance: ``is_entangled``, ``is_grabbed``, ``is_flashed`` and
    ``HeldAction.get_pending`` each walk the entire event log
    independently, so a single call to this function is O(events) per
    source, i.e. O(4 * events) for those four plus O(1) for KO/aborted.
    Fine for the combats this engine runs (short logs, called per
    combatant per emission, not per tick); no caching is added here --
    measure before optimising.

    Returns an empty frozenset (never ``None``) for a combatant with no
    conditions.
    """
    statuses: set[str] = set()

    participant = session.combatants[combatant_id]
    if participant.is_ko:
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

    return frozenset(statuses)
