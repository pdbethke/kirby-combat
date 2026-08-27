"""Canonical status-id vocabulary for combat state emission.

Foundry's status ids are the canon: they are an already-published,
already-consumed contract (`hero6e-kirby/module/actor/actor-active-effects.mjs`
defines 42 of them; `module/combatant.mjs:48` reads
`actor.statuses.has("holding")` directly). The engine's own internal names
(`"Stunned"` / `"Knocked Out"` / `"Dead"`, from
`kirby_combat/resolution/status.py`) are title-case-with-spaces and are NOT
the canon — they exist only inside this engine and must never leak out.

This module defines **only the ids this engine can actually produce.**
Foundry defines 42 status ids in total; this engine is deliberately narrower.
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
# A combatant has declared an abort (Dodge/Block/Dive for Cover) this phase,
# forfeiting their next action. See
# kirby_combat.actions.reactive.abort.is_aborting /
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
