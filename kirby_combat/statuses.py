"""Canonical status-id vocabulary for combat state emission.

Foundry's status ids are the canon: they are an already-published,
already-consumed contract (`hero6e-kirby/module/actor/actor-active-effects.mjs`
defines 43 of them; `module/combatant.mjs:48` reads
`actor.statuses.has("holding")` directly). The engine's own internal names
(`"Stunned"` / `"Knocked Out"` / `"Dead"`, from
`kirby_combat/resolution/status.py`) are title-case-with-spaces and are NOT
the canon — they exist only inside this engine and must never leak out.

This module defines **only the ids this engine can actually produce.**
Foundry defines 43 status ids in total; this engine is deliberately narrower.
An id the engine never emits is a promise it cannot keep, so ids that have
no engine-side source are omitted on purpose (see the two notes below) rather
than transcribed wholesale from Foundry's list.

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
# kirby_combat/resolution/status.py `determine_status_changes`.

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
# kirby_combat/resolution/status.py `determine_status_changes`.

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
# strings. Foundry's *SenseDisabled ids that have a matching engine sense
# group are mapped below; Foundry also defines danger / detect / sonar /
# spatialAwareness / touch SenseDisabled ids, which have NO corresponding
# engine sense group and are deliberately OMITTED (not an oversight).
# ---------------------------------------------------------------------------

BLIND = "blind"
# Flash vs the Sight Group. Foundry has no "sightSenseDisabled" id; its
# sight-disabled status id is "blind"
# (`sightSenseDisabledEffect` -> id "blind" in
# hero6e-kirby/module/actor/actor-active-effects.mjs). See
# kirby_combat/actions/flash.py (Flash targets sight group per HERO 6E1) and
# kirby_combat/perception.py SIGHT.

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

# Engine sense-group string -> Foundry status id, for the groups that exist
# on both sides. kirby_combat/perception.py's SIGHT group has no Foundry
# "*SenseDisabled" counterpart -- Foundry uses "blind" instead.
SENSE_GROUP_TO_STATUS_ID: dict[str, str] = {
    "sight": BLIND,
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
        BLIND,
        HEARING_SENSE_DISABLED,
        MENTAL_SENSE_DISABLED,
        RADIO_SENSE_DISABLED,
        SMELL_TASTE_SENSE_DISABLED,
    }
)

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
    - ``stunned`` -- computed at attack time by
      ``resolution/status.py::determine_status_changes`` and currently
      dropped rather than persisted. This function still returns
      ``STUNNED`` correctly once a later task makes that persist (nothing
      here needs to change for that); until then no source exists to add.

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
