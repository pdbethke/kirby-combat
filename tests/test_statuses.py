"""Tests for the canonical status-id vocabulary (kirby_combat.statuses)."""
from __future__ import annotations

import re

from kirby_combat.statuses import (
    ABORTED,
    ALL_STATUS_IDS,
    BLIND,
    DEAD,
    ENTANGLED,
    GRAB,
    HEARING_SENSE_DISABLED,
    HOLDING,
    KNOCKED_OUT,
    MENTAL_SENSE_DISABLED,
    RADIO_SENSE_DISABLED,
    SENSE_GROUP_TO_STATUS_ID,
    SMELL_TASTE_SENSE_DISABLED,
    STUNNED,
)


def test_ids_are_foundry_shaped_slugs():
    """Foundry's ids are lowercase camel, not the engine's title-case
    internals ("Knocked Out" -> "knockedOut")."""
    for sid in ALL_STATUS_IDS:
        assert re.fullmatch(r"[a-z][a-zA-Z]*", sid), sid


def test_every_id_is_one_the_engine_can_produce():
    """An id the engine never emits is a promise it cannot keep."""
    assert KNOCKED_OUT in ALL_STATUS_IDS
    assert "haymaker" not in ALL_STATUS_IDS   # Foundry has it; this engine does not model it


def test_the_engines_internal_names_are_not_the_canon():
    """resolution/status.py returns "Stunned"/"Knocked Out"/"Dead"."""
    assert "Knocked Out" not in ALL_STATUS_IDS
    assert "Stunned" not in ALL_STATUS_IDS


def test_all_expected_ids_present():
    expected = {
        STUNNED, KNOCKED_OUT, DEAD, ENTANGLED, GRAB, ABORTED, HOLDING,
        BLIND, HEARING_SENSE_DISABLED, MENTAL_SENSE_DISABLED,
        RADIO_SENSE_DISABLED, SMELL_TASTE_SENSE_DISABLED,
    }
    assert ALL_STATUS_IDS == expected


def test_unconscious_is_not_a_distinct_id():
    """The engine has only one signal for this condition (is_ko /
    current_stun <= 0), which resolution/status.py already labels
    "Knocked Out" -- a separate "unconscious" id would duplicate it."""
    assert "unconscious" not in ALL_STATUS_IDS


def test_prone_is_not_emittable():
    """prone is a maneuver/cover parameter, not a stored per-combatant
    status anywhere in the engine -- there is nothing to emit."""
    assert "prone" not in ALL_STATUS_IDS


def test_sense_group_mapping_matches_engine_groups():
    """Every engine sense group (perception.py:20-24) maps to exactly one
    Foundry status id; sight maps to "blind" since Foundry has no
    "sightSenseDisabled" id."""
    assert SENSE_GROUP_TO_STATUS_ID == {
        "sight": BLIND,
        "hearing": HEARING_SENSE_DISABLED,
        "mental": MENTAL_SENSE_DISABLED,
        "radio": RADIO_SENSE_DISABLED,
        "smell": SMELL_TASTE_SENSE_DISABLED,
    }


def test_sense_disabled_ids_omit_ungrouped_foundry_senses():
    """Foundry's danger/detect/sonar/spatialAwareness/touch SenseDisabled
    ids have no engine sense group and must not appear."""
    for omitted in (
        "dangerSenseDisabled", "detectSenseDisabled", "sonarSenseDisabled",
        "spatialAwarenessSenseDisabled", "touchSenseDisabled",
    ):
        assert omitted not in ALL_STATUS_IDS


# ---------------------------------------------------------------------------
# Foundry-existence check
#
# Hardcoded, NOT parsed from hero6e-kirby at test time: kirby-combat must
# stay self-contained and must not depend on a sibling repo's presence or
# file layout (a checkout without hero6e-kirby would otherwise fail this
# suite for no engine-side reason).
#
# Provenance: all 43 `id: "..."` string literals read directly from
# hero6e-kirby/module/actor/actor-active-effects.mjs on 2026-08-27.
#
# DRIFT RISK: this list is a snapshot, not a live check. If Foundry's module
# adds, renames, or removes a status id after 2026-08-27, this constant goes
# stale and nothing here will notice -- re-read the .mjs and update this set
# by hand when hero6e-kirby's status effects change.
# ---------------------------------------------------------------------------

FOUNDRY_STATUS_IDS_20260827 = frozenset({
    "stunned", "bleeding", "unconscious", "knockedOut", "dead", "asleep",
    "prone", "entangled", "paralysis", "mindControl", "fear",
    "regeneration", "upgrade", "downgrade", "invisible", "target",
    "holding", "underwater", "standingInWater", "holdingBreath", "aborted",
    "block", "brace", "club-weapon", "desolidification", "dodge", "grab",
    "haymaker", "strike", "fly", "nonCombatMovement", "tunneling",
    "dangerSenseDisabled", "detectSenseDisabled", "hearingSenseDisabled",
    "mentalSenseDisabled", "radioSenseDisabled", "blind", "silence",
    "smellTasteSenseDisabled", "sonarSenseDisabled",
    "spatialAwarenessSenseDisabled", "touchSenseDisabled",
})


def test_foundry_status_ids_snapshot_has_43_entries():
    """Sanity check on the hardcoded snapshot itself, so a future hand-edit
    that silently drops or duplicates an id is caught."""
    assert len(FOUNDRY_STATUS_IDS_20260827) == 43


def test_every_engine_id_exists_in_foundry():
    """Every id this engine claims to be able to emit must actually be one
    of Foundry's published status ids -- a typo'd or invented id would
    otherwise pass every other test in this file (they only check
    self-consistency against ALL_STATUS_IDS) and silently do nothing on a
    token client-side."""
    assert ALL_STATUS_IDS <= FOUNDRY_STATUS_IDS_20260827
