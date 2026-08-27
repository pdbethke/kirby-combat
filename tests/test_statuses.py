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
    DEAD,
    ENTANGLED,
    FOUNDRY_ID,
    GRAB,
    HEARING_SENSE_DISABLED,
    HOLDING,
    KNOCKED_OUT,
    KNOWN_UNMODELLED_FOUNDRY_IDS,
    MENTAL_SENSE_DISABLED,
    NO_FOUNDRY_EQUIVALENT,
    RADIO_SENSE_DISABLED,
    SENSE_GROUP_TO_STATUS_ID,
    SIGHT_SENSE_DISABLED,
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


def test_known_ids_present_and_unmodeled_ids_absent():
    """Smoke check only -- this does NOT test producibility (see
    `test_producibility_table_is_exhaustive_and_matches_reality` below for
    that); it just checks two ids land where expected."""
    assert KNOCKED_OUT in ALL_STATUS_IDS
    assert "haymaker" not in ALL_STATUS_IDS   # Foundry has it; this engine does not model it


def test_the_engines_internal_names_are_not_the_canon():
    """resolution/status.py returns "Stunned"/"Knocked Out"/"Dead"."""
    assert "Knocked Out" not in ALL_STATUS_IDS
    assert "Stunned" not in ALL_STATUS_IDS


def test_all_expected_ids_present():
    expected = {
        STUNNED, KNOCKED_OUT, DEAD, ENTANGLED, GRAB, ABORTED, HOLDING,
        SIGHT_SENSE_DISABLED, HEARING_SENSE_DISABLED, MENTAL_SENSE_DISABLED,
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
    Kirby status id, named per the engine's own per-Sense-Group pattern
    (sight -> SIGHT_SENSE_DISABLED, not the Foundry-only "blind")."""
    assert SENSE_GROUP_TO_STATUS_ID == {
        "sight": SIGHT_SENSE_DISABLED,
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


# ---------------------------------------------------------------------------
# FOUNDRY_ID mapping -- Foundry no longer caps ALL_STATUS_IDS (that ceiling
# was the defect this branch corrects: see
# 2026-08-27-kirby-owns-its-vocabulary-design.md §1a/§3c). Instead:
#   - every FOUNDRY_ID *value* must be a real, published Foundry id
#     (a typo'd or invented mapping target would otherwise silently do
#     nothing on a token client-side);
#   - every Kirby id must be accounted for as either mapped or explicitly
#     declared to have no Foundry equivalent, so an unmapped id reads as a
#     stated decision, never an oversight.
# ---------------------------------------------------------------------------

def test_every_foundry_id_mapping_target_is_a_real_foundry_id():
    """FOUNDRY_ID's values (not ALL_STATUS_IDS itself) are what must exist
    in Foundry's published vocabulary -- the snapshot now validates mapping
    targets only."""
    for kirby_id, foundry_id in FOUNDRY_ID.items():
        assert foundry_id in FOUNDRY_STATUS_IDS_20260827, (
            f"{kirby_id!r} maps to {foundry_id!r}, which is not a real "
            f"Foundry status id"
        )


def test_every_kirby_id_is_mapped_or_declared_to_have_no_foundry_equivalent():
    """An id in ALL_STATUS_IDS that is neither in FOUNDRY_ID nor in
    NO_FOUNDRY_EQUIVALENT would be a silently unmapped id -- this test
    forces every id to be one or the other, on purpose."""
    accounted_for = set(FOUNDRY_ID) | set(NO_FOUNDRY_EQUIVALENT)
    assert accounted_for == ALL_STATUS_IDS
    # and the two categories don't overlap -- an id doesn't get to be both
    # "mapped" and "declared as having no equivalent"
    assert set(FOUNDRY_ID).isdisjoint(NO_FOUNDRY_EQUIVALENT)


def test_sight_sense_disabled_is_the_one_divergent_mapping():
    """Eleven of twelve ids map identically to their own string; only
    SIGHT_SENSE_DISABLED differs, because Foundry's wire id for that
    condition is the legacy "blind"."""
    divergent = {k: v for k, v in FOUNDRY_ID.items() if k != v}
    assert divergent == {SIGHT_SENSE_DISABLED: "blind"}


def test_known_unmodelled_foundry_ids_are_not_produced():
    """The known-unmodelled record (§3b) is a checklist, not a promise --
    none of these ids should appear in ALL_STATUS_IDS, since this engine
    has no per-combatant source for any of them."""
    assert KNOWN_UNMODELLED_FOUNDRY_IDS.isdisjoint(ALL_STATUS_IDS)
    for fid in KNOWN_UNMODELLED_FOUNDRY_IDS:
        assert fid in FOUNDRY_STATUS_IDS_20260827


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
    assert SIGHT_SENSE_DISABLED not in result
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
    assert SIGHT_SENSE_DISABLED in result
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
        {KNOCKED_OUT, ENTANGLED, GRAB, SIGHT_SENSE_DISABLED, HEARING_SENSE_DISABLED}
    )


# ---------------------------------------------------------------------------
# Producibility table -- enforces the module docstring's own claim
# (statuses.py:11-15): "This module defines only the ids this engine can
# actually produce... An id the engine never emits is a promise it cannot
# keep." That was a claim in a docstring, not a guard, until now.
#
# Every id in ALL_STATUS_IDS must appear in exactly one of the two maps
# below: PRODUCED_BY (a real statuses_for source) or NOT_YET_PRODUCED
# (statuses.py's own "Deliberately NOT read here" list -- STUNNED and
# DEAD, both real conditions with no fold source yet). The table and that
# docstring section are made to agree by construction: this is literally
# the same list, asserted, not just written down.
# ---------------------------------------------------------------------------

PRODUCED_BY = {
    KNOCKED_OUT: "participant.is_ko (current_stun <= 0)",
    ENTANGLED: "Entangle.is_entangled",
    GRAB: "Grab.is_grabbed",
    ABORTED: "session.timeline.aborted_this_phase",
    HOLDING: "HeldAction.get_pending",
    SIGHT_SENSE_DISABLED: "Flash.is_flashed (sight) via SENSE_GROUP_TO_STATUS_ID",
    HEARING_SENSE_DISABLED: "Flash.is_flashed (hearing) via SENSE_GROUP_TO_STATUS_ID",
    MENTAL_SENSE_DISABLED: "Flash.is_flashed (mental) via SENSE_GROUP_TO_STATUS_ID",
    RADIO_SENSE_DISABLED: "Flash.is_flashed (radio) via SENSE_GROUP_TO_STATUS_ID",
    SMELL_TASTE_SENSE_DISABLED: "Flash.is_flashed (smell) via SENSE_GROUP_TO_STATUS_ID",
}

# statuses.py's own "Deliberately NOT read here" list: real conditions,
# computed by resolution/status.py::determine_status_changes (and, for
# STUNNED, also mental/mental_blast.py:45), but discarded into an
# audit-trail string rather than persisted -- statuses_for has no branch
# for either.
NOT_YET_PRODUCED = {
    STUNNED: "computed by determine_status_changes + mental_blast.py:45 "
             "target_stunned, discarded by actions/base.py:190 -- no "
             "statuses_for branch",
    DEAD: "computed by determine_status_changes, discarded by "
          "actions/base.py:190 -- no statuses_for branch",
}


def test_producibility_table_is_exhaustive_over_all_status_ids():
    """Every id in ALL_STATUS_IDS is accounted for as either produced or
    explicitly not-yet-produced, and the two lists don't overlap. This is
    the guard the module docstring's claim ("only ids this engine can
    actually produce") never had: an id added to ALL_STATUS_IDS without a
    matching row here (in either map) fails; a row added here for an id
    not in ALL_STATUS_IDS also fails."""
    assert set(PRODUCED_BY).isdisjoint(NOT_YET_PRODUCED)
    assert set(PRODUCED_BY) | set(NOT_YET_PRODUCED) == ALL_STATUS_IDS


def test_not_yet_produced_ids_never_actually_come_out_of_statuses_for():
    """The declared exceptions are real gaps, not just labels: drive a
    combatant to the exact state that would trigger Stunned/Dead via
    determine_status_changes (STUN dealt > CON; BODY <= -max_body) and
    confirm statuses_for still omits both."""
    s = _session(_c("alice"), _c("bob", current_stun=-40, current_body=-40))
    result = statuses_for(s, "bob")
    assert STUNNED not in result
    assert DEAD not in result
