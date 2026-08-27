"""Tests for the canonical status-id vocabulary (kirby_combat.statuses)."""
from __future__ import annotations

import re

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.entangle import Entangle
from kirby_combat.actions.flash import Flash
from kirby_combat.actions.grab import Grab
from kirby_combat.actions.held_action import HeldAction
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
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
    statuses_for,
)
from kirby_combat.template import CombatTemplate


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


# ---------------------------------------------------------------------------
# statuses_for -- the read model: one fold over every condition source
# ---------------------------------------------------------------------------

def _c(id_: str, **overrides) -> "HeroCombatant":
    kwargs = dict(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=20, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=3,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    kwargs.update(overrides)
    return synthetic_combatant(**kwargs)


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=list(combatants),
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def test_statuses_for_empty_when_no_conditions():
    s = _session(_c("alice"), _c("bob"))
    assert statuses_for(s, "bob") == frozenset()


def test_statuses_for_knocked_out():
    s = _session(_c("alice"), _c("bob", current_stun=0))
    assert KNOCKED_OUT in statuses_for(s, "bob")
    # covering: a conscious combatant does not get the id
    assert KNOCKED_OUT not in statuses_for(s, "alice")


def test_statuses_for_entangled():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    assert ENTANGLED in statuses_for(s2, "bob")
    assert ENTANGLED not in statuses_for(s2, "alice")


def test_statuses_for_grabbed():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = Grab.declare_and_resolve(
        s, attacker_id="alice", target_id="bob",
        attacker_str=20, target_str=15,
        attacker_ocv=8, target_dcv=5, attack_roll=10,
    )
    assert GRAB in statuses_for(s2, "bob")
    assert GRAB not in statuses_for(s2, "alice")


def test_statuses_for_flashed_maps_specific_sense_group():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="hearing", body_dealt=8, flash_defense=0,
    )
    result = statuses_for(s2, "bob")
    assert HEARING_SENSE_DISABLED in result
    # not a generic / wrong sense group
    assert BLIND not in result
    assert MENTAL_SENSE_DISABLED not in result


def test_statuses_for_flashed_in_two_groups_gets_both_ids():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=0,
    )
    s3, _ = Flash.apply(
        s2, attacker_id="alice", target_id="bob",
        sense_group="mental", body_dealt=8, flash_defense=0,
    )
    result = statuses_for(s3, "bob")
    assert BLIND in result
    assert MENTAL_SENSE_DISABLED in result


def test_statuses_for_aborted():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = mark_aborting(s, "bob", to_action="dodge")
    assert ABORTED in statuses_for(s2, "bob")
    assert ABORTED not in statuses_for(s2, "alice")


def test_statuses_for_holding():
    s = _session(_c("alice"), _c("bob"))
    s2, _ = HeldAction.declare(
        s, "bob", trigger_condition="enemy enters range",
    )
    assert HOLDING in statuses_for(s2, "bob")
    assert HOLDING not in statuses_for(s2, "alice")


def test_statuses_for_returns_frozenset_not_none():
    s = _session(_c("alice"))
    result = statuses_for(s, "alice")
    assert isinstance(result, frozenset)


def test_statuses_for_folds_several_simultaneous_conditions():
    """Spec §5d: a combatant can be entangled AND flashed in two groups
    AND knocked out at once -- a set is the whole point."""
    s = _session(_c("alice"), _c("bob", current_stun=0))
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, _ = Flash.apply(
        s2, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=0,
    )
    s4, _ = Flash.apply(
        s3, attacker_id="alice", target_id="bob",
        sense_group="hearing", body_dealt=8, flash_defense=0,
    )
    s5, _ = Grab.declare_and_resolve(
        s4, attacker_id="alice", target_id="bob",
        attacker_str=20, target_str=15,
        attacker_ocv=8, target_dcv=5, attack_roll=10,
    )

    result = statuses_for(s5, "bob")
    assert result == frozenset(
        {KNOCKED_OUT, ENTANGLED, GRAB, BLIND, HEARING_SENSE_DISABLED}
    )
