"""Tests for the canonical status-id vocabulary (kirby_combat.statuses)."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions import resolve_attack
from kirby_combat.actions.entangle import Entangle
from kirby_combat.actions.flash import Flash
from kirby_combat.actions.grab import Grab
from kirby_combat.actions.held_action import HeldAction
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.dice import FakeRoller
from kirby_combat.encounter import Encounter
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    RecoveryTaken, SegmentAdvanced, make_author_engine,
)
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
    RECOVERING_FROM_STUNNED,
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
        STUNNED, KNOCKED_OUT, DEAD, RECOVERING_FROM_STUNNED, ENTANGLED, GRAB,
        ABORTED, HOLDING, SIGHT_SENSE_DISABLED, HEARING_SENSE_DISABLED,
        MENTAL_SENSE_DISABLED, RADIO_SENSE_DISABLED, SMELL_TASTE_SENSE_DISABLED,
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
    KNOCKED_OUT: "participant.is_ko (current_stun <= 0) UNION "
                 "_is_knocked_out_from_payload (status_changes, cleared by RecoveryTaken)",
    ENTANGLED: "Entangle.is_entangled",
    GRAB: "Grab.is_grabbed",
    ABORTED: "session.timeline.aborted_this_phase",
    HOLDING: "HeldAction.get_pending",
    SIGHT_SENSE_DISABLED: "Flash.is_flashed (sight) via SENSE_GROUP_TO_STATUS_ID",
    HEARING_SENSE_DISABLED: "Flash.is_flashed (hearing) via SENSE_GROUP_TO_STATUS_ID",
    MENTAL_SENSE_DISABLED: "Flash.is_flashed (mental) via SENSE_GROUP_TO_STATUS_ID",
    RADIO_SENSE_DISABLED: "Flash.is_flashed (radio) via SENSE_GROUP_TO_STATUS_ID",
    SMELL_TASTE_SENSE_DISABLED: "Flash.is_flashed (smell) via SENSE_GROUP_TO_STATUS_ID",
    STUNNED: "_is_stunned -- ActionResolved.result_payload['status_changes'] "
             "contains 'Stunned' (set), cleared by the first SegmentAdvanced "
             "afterward whose to_segment is a Phase for this combatant "
             "(6E2 p.107)",
    DEAD: "_is_dead -- ActionResolved.result_payload['status_changes'] "
          "contains 'Dead' (never clears)",
    RECOVERING_FROM_STUNNED: "_is_recovering_from_stunned -- "
          "stunned_or_recovering_for AND NOT _is_stunned (6E2 p.39's own "
          "named row, distinct from Stunned)",
}

# statuses.py's own "Deliberately NOT read here" list is now empty for these
# two -- both moved into PRODUCED_BY above (Task 4). Kept as an empty dict,
# not deleted, so the exhaustiveness assertion below and the module
# docstring's structure stay in the same shape a future deferred id would
# use.
NOT_YET_PRODUCED: dict[str, str] = {}


def test_producibility_table_is_exhaustive_over_all_status_ids():
    """Every id in ALL_STATUS_IDS is accounted for as either produced or
    explicitly not-yet-produced, and the two lists don't overlap. This is
    the guard the module docstring's claim ("only ids this engine can
    actually produce") never had: an id added to ALL_STATUS_IDS without a
    matching row here (in either map) fails; a row added here for an id
    not in ALL_STATUS_IDS also fails."""
    assert set(PRODUCED_BY).isdisjoint(NOT_YET_PRODUCED)
    assert set(PRODUCED_BY) | set(NOT_YET_PRODUCED) == ALL_STATUS_IDS


def test_stunned_and_dead_are_not_derived_from_raw_combatant_state():
    """Task 4 closed the gap the old `test_not_yet_produced_ids_never_
    actually_come_out_of_statuses_for` guarded: STUNNED/DEAD are no longer
    NOT_YET_PRODUCED. But they must still never be inferred from a
    combatant's raw current_stun/current_body -- only from an
    ActionResolved's recorded status_changes. A combatant created directly
    in this deeply-negative state, with NO ActionResolved on the log at
    all, must show neither id."""
    s = _session(_c("alice"), _c("bob", current_stun=-40, current_body=-40))
    result = statuses_for(s, "bob")
    assert STUNNED not in result
    assert DEAD not in result


# ---------------------------------------------------------------------------
# Stunned / Dead — derived from ActionResolved.status_changes
# (resolve_attack_in_session, kirby_combat/actions/recording.py) plus, for
# Stunned's clear edge, SegmentAdvanced (Encounter.advance_segment /
# kirby_combat/session/events.py).
#
# 6E2 p.107, "RECOVERING FROM BEING STUNNED": "Recovering from being
# Stunned requires a Full Phase, and is the only thing the character can
# do during that Phase" -- the character "recovers from being Stunned when
# his DEX occurs in the Segment" of his next full Phase. So the SET edge is
# an ActionResolved naming this combatant with "Stunned" in
# status_changes; the CLEAR edge is the first SegmentAdvanced afterward
# whose to_segment is one of this combatant's Phase segments
# (`segments_for_spd`, kirby_combat/tables.py:117).
# ---------------------------------------------------------------------------

def _attacker_for_stun(con: int = 15) -> "HeroCombatant":
    return synthetic_combatant(
        id="attacker", name="Attacker",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[
            AttackPower(
                xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
    )


def _target_for_stun(
    spd: int = 4, con: int = 15, current_stun: int = 30, current_body: int = 15,
) -> "HeroCombatant":
    return synthetic_combatant(
        id="bob", name="bob",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=spd, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=current_stun, current_body=current_body, current_end=30,
    )


def _hitting_attack_for_stun(attacker, target) -> AttackInput:
    # Roll 9 to-hit (well within range); 10d6 normal EB, no defenses on
    # target so STUN dealt = 36, blowing through any reasonable CON.
    return AttackInput(
        attacker=attacker,
        target=target,
        power=attacker.attacks[0],
        distance_m=0,
        aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
        ),
    )


def _advance(session: CombatSession, to_segment: int, to_turn: int) -> CombatSession:
    """Append one SegmentAdvanced (session/events.py:60) to `session`'s own
    log, mirroring encounter.py's `_record_segment_advanced` -- a session
    fixture here has no owning `Encounter`, so this drives the same event
    `Encounter.advance_segment` (Task 1) would append, without needing one."""
    evt = SegmentAdvanced(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        from_segment=session.timeline.segment,
        to_segment=to_segment,
        to_turn=to_turn,
    )
    return apply_event(session, evt)


def test_statuses_for_stunned_appears_after_qualifying_hit():
    # bob: SPD 4 -> Phases at segments 3, 6, 9, 12 (tables.py SPEED_TO_SEGMENTS).
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Stunned" in result.status_changes  # sanity: the hit really qualifies

    assert STUNNED in statuses_for(session, "bob")


def test_statuses_for_stunned_disappears_after_the_combatants_next_phase():
    """The clear edge: SPD 4 (Phases 3/6/9/12). Session starts on Segment
    12 (CombatSession.create -- 6E2 p.20, combat begins Segment 12), so the
    hit lands on bob's own Phase. Advance 12->1 (Turn wrap, not a Phase for
    SPD 4) then 1->2 (not a Phase) then 2->3 (a Phase) -- 6E2 p.107 says
    Stunned clears once a Segment that is a Phase for the combatant has
    elapsed after the hit, and this is the first one."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, _ = resolve_attack_in_session(session, attack, session.template)
    assert STUNNED in statuses_for(session, "bob")

    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)
    session = _advance(session, to_segment=3, to_turn=2)  # bob's next Phase

    assert STUNNED not in statuses_for(session, "bob")


def test_statuses_for_stunned_survives_a_segment_that_is_not_the_combatants_phase():
    """This is the test that must be able to fail: a Segment elapsing is
    NOT enough on its own -- it must be one of THIS combatant's Phase
    segments (6E2 p.107). SPD 4's Phases are 3/6/9/12, so 12->1->2 must
    leave Stunned still set."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, _ = resolve_attack_in_session(session, attack, session.template)
    assert STUNNED in statuses_for(session, "bob")

    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)

    assert STUNNED in statuses_for(session, "bob")


def test_statuses_for_dead_appears_and_persists():
    # con=15, current_stun=30, current_body=-10, max_body=15: a 36-STUN/
    # 11-BODY hit drives body_after to -21 <= -15 -> Dead (and, along the
    # way, Stunned + Knocked Out too -- resolution/status.py's three
    # checks are independent, not exclusive).
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Dead" in result.status_changes  # sanity: the hit really qualifies

    assert DEAD in statuses_for(session, "bob")

    # Dead never clears -- unlike Stunned, advancing through bob's own
    # Phase segments must not remove it.
    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)
    session = _advance(session, to_segment=3, to_turn=2)

    assert DEAD in statuses_for(session, "bob")


def test_statuses_for_dead_does_not_also_read_as_recovering_from_stunned():
    """Review finding (LOW, ``2026-08-28-conditions-must-bite`` final-fix
    pass): a corpse cannot "recover" from anything -- 6E2 p.107,
    "recovering from being Stunned is all he can do that Phase", names an
    active process. A lethal hit (Stunned + Dead together, same fixture
    as ``test_statuses_for_dead_appears_and_persists``) followed by one
    at-Phase ``SegmentAdvanced`` used to yield ``{dead, knockedOut,
    recoveringFromStunned}`` -- this pins the fix: DEAD implies NOT
    RECOVERING_FROM_STUNNED, same call site as the pre-existing DEAD =>
    KNOCKED_OUT implication just above it in ``statuses.py``."""
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Stunned" in result.status_changes
    assert "Dead" in result.status_changes

    # bob's recovery Phase (SPD 4 -> Phases 3/6/9/12; session starts
    # Segment 12, so the hit lands on his own Phase, and Segment 3 is his
    # next full Phase) -- the exact Segment `_is_recovering_from_stunned`
    # would otherwise fire in for a living combatant.
    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)
    session = _advance(session, to_segment=3, to_turn=2)

    result_ids = statuses_for(session, "bob")
    assert DEAD in result_ids
    assert KNOCKED_OUT in result_ids
    assert RECOVERING_FROM_STUNNED not in result_ids
    assert STUNNED not in result_ids  # sanity: not the OTHER Stunned id either


# ---------------------------------------------------------------------------
# Knocked Out coherence (Task 4 follow-up) -- surfaced by Task 5's example:
# a payload naming "Stunned"/"Knocked Out"/"Dead" together, on a session
# whose driver never mutates vitals (`resolve_attack_in_session` is
# deliberately log-only, `session/apply.py`), previously produced `dead`
# and `stunned` with NO `knockedOut` at all -- self-contradictory to any
# consumer. `KNOCKED_OUT` now unions the live `is_ko` source with
# `_is_knocked_out_from_payload`, the same payload fold STUNNED/DEAD use.
# ---------------------------------------------------------------------------

def _recover(
    session: CombatSession, combatant_id: str,
    stun_recovered: int = 5, end_recovered: int = 5,
) -> CombatSession:
    """Append one RecoveryTaken (session/events.py:84) to `session`'s own
    log -- the event `_apply_post_12_recovery` (encounter.py) emits for
    6E2 p.131's Post-Segment 12 Recovery, driven here directly so a
    fixture doesn't need a full Encounter."""
    evt = RecoveryTaken(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        combatant_id=combatant_id,
        stun_recovered=stun_recovered,
        end_recovered=end_recovered,
    )
    return apply_event(session, evt)


def test_statuses_for_lethal_hit_yields_both_dead_and_knocked_out():
    """The coherence property, pinned directly: a hit whose status_changes
    names Stunned + Knocked Out + Dead together must surface ALL THREE
    from statuses_for -- not dead+stunned with knockedOut silently
    missing, even though `is_ko` (live current_stun) never moves, because
    resolve_attack_in_session is deliberately log-only."""
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)  # same fixture as the Dead test
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert result.status_changes == ["Stunned", "Knocked Out", "Dead"]

    # Sanity: vitals genuinely never moved -- is_ko alone would miss this.
    assert session.combatants["bob"].is_ko is False

    result_ids = statuses_for(session, "bob")
    assert DEAD in result_ids
    assert STUNNED in result_ids
    assert KNOCKED_OUT in result_ids


def test_statuses_for_knocked_out_from_payload_alone_when_vitals_never_move():
    """A hit that drives stun_after <= 0 (Knocked Out) but not Dead, on a
    combatant whose live current_stun stays at its starting value --
    KNOCKED_OUT must still appear, sourced purely from the payload."""
    attacker, target = _attacker_for_stun(), _target_for_stun()  # current_stun=30
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Knocked Out" in result.status_changes  # sanity: 30 - 36 <= 0
    assert "Dead" not in result.status_changes

    assert session.combatants["bob"].is_ko is False  # vitals untouched
    assert KNOCKED_OUT in statuses_for(session, "bob")


def test_statuses_for_knocked_out_payload_clears_on_recovery_taken():
    """The clear edge this fold was given, asserted rather than
    incidental: _is_knocked_out_from_payload clears on the very next
    RecoveryTaken for this combatant (6E2 p.131), a deliberately
    conservative choice over never clearing (see that function's
    docstring)."""
    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, _ = resolve_attack_in_session(session, attack, session.template)
    assert KNOCKED_OUT in statuses_for(session, "bob")

    session = _recover(session, "bob")

    assert KNOCKED_OUT not in statuses_for(session, "bob")


def test_statuses_for_knocked_out_payload_unaffected_by_unrelated_recovery():
    """A RecoveryTaken for a DIFFERENT combatant must not clear this
    combatant's payload-derived Knocked Out."""
    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, _ = resolve_attack_in_session(session, attack, session.template)
    assert KNOCKED_OUT in statuses_for(session, "bob")

    session = _recover(session, "attacker")

    assert KNOCKED_OUT in statuses_for(session, "bob")


# ---------------------------------------------------------------------------
# Review finding #1 (CRITICAL): `dead` without `knockedOut` returns one Turn
# later. `_apply_post_12_recovery` (encounter.py) emits a `RecoveryTaken`
# for EVERY combatant unconditionally on every Turn wrap (6E2 p.131, "even
# Stunned ones" -- corpses included), which is exactly the clear edge
# `_is_knocked_out_from_payload` listens for. So a lethal hit's KNOCKED_OUT
# (sourced only from the payload fold, since `resolve_attack_in_session`
# never mutates vitals) used to disappear the instant a Turn wrapped, while
# DEAD never clears -- reproducing "dead but not knocked out" within at
# most one Turn (12 Segments). Fixed by making DEAD imply KNOCKED_OUT in
# `statuses_for` directly, so the implication does not depend on which of
# KNOCKED_OUT's other sources happens to still be live.
#
# These are the tests that were missing before this task: the four
# existing coherence tests above all assert the status set AT THE HIT or
# after a single hand-built `RecoveryTaken` -- none of them drive the
# clock past a full Turn wrap, which is the only way this contradiction
# ever surfaces.
# ---------------------------------------------------------------------------

def test_statuses_for_dead_still_implies_knocked_out_after_one_recovery_taken():
    """Minimal reproduction: one hand-built RecoveryTaken (mirroring
    `_apply_post_12_recovery`'s per-Turn-wrap emission) must not strip
    KNOCKED_OUT off a DEAD combatant."""
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)  # same fixture as the Dead test
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert result.status_changes == ["Stunned", "Knocked Out", "Dead"]
    assert set(statuses_for(session, "bob")) == {DEAD, KNOCKED_OUT, STUNNED}

    # The exact clear edge _is_knocked_out_from_payload listens for.
    session = _recover(session, "bob")

    result_ids = statuses_for(session, "bob")
    assert DEAD in result_ids
    assert KNOCKED_OUT in result_ids  # must NOT have cleared


def test_statuses_for_dead_survives_a_full_turn_wrap_via_encounter():
    """The reviewer's exact repro, driven through the real machinery
    (`Encounter.advance_segment`, not a hand-built event): a lethal hit,
    then one Segment-12-to-Segment-1 Turn wrap, which is where
    `_apply_post_12_recovery` actually lives and fires unconditionally for
    every combatant -- corpses included. `dead` and `knockedOut` must both
    still be present afterward."""
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert result.status_changes == ["Stunned", "Knocked Out", "Dead"]

    encounter = Encounter(id="e1", turn=1, segment=12, sessions=[session])
    encounter = encounter.advance_segment()  # wraps: Segment 12 -> Turn 2, Segment 1
    assert encounter.turn == 2
    assert encounter.segment == 1

    wrapped_session = encounter.sessions[0]
    result_ids = statuses_for(wrapped_session, "bob")
    assert DEAD in result_ids
    assert KNOCKED_OUT in result_ids  # this is the finding: used to be gone


def test_statuses_for_dead_implies_knocked_out_even_with_no_payload_source():
    """Pins the fix's actual mechanism, not just its symptom: DEAD alone
    (with no live is_ko and no surviving payload-derived KO source at
    all -- both already cleared) must still force KNOCKED_OUT. This is
    the test that distinguishes "gate the payload clear on `not
    _is_dead(...)`" from "make DEAD imply KNOCKED_OUT in statuses_for" --
    it only passes under the latter."""
    attacker = _attacker_for_stun()
    target = _target_for_stun(current_body=-10)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, _ = resolve_attack_in_session(session, attack, session.template)
    assert session.combatants["bob"].is_ko is False  # live KO source never available

    # Clear the payload-derived KO source directly, same as any other
    # payload-KO test does -- if DEAD's implication lived only inside
    # _is_knocked_out_from_payload's own clear-gate, this recovery would
    # have nothing left to gate and KNOCKED_OUT would vanish.
    session = _recover(session, "bob")

    result_ids = statuses_for(session, "bob")
    assert DEAD in result_ids
    assert KNOCKED_OUT in result_ids


# ---------------------------------------------------------------------------
# Review finding #6 (minor): segments_for_spd(0) is empty, so _is_stunned
# could latch forever for a SPD-0 combatant -- no engine path produces one
# today, but this is exactly the never-turns-off case the branch is built
# to avoid.
# ---------------------------------------------------------------------------

def test_statuses_for_stunned_clears_on_next_segment_advanced_when_spd_is_zero():
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=0)
    session = _session(attacker, target)
    attack = _hitting_attack_for_stun(attacker, target)

    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Stunned" in result.status_changes
    assert STUNNED in statuses_for(session, "bob")

    # SPD 0 has no Phase segments at all (SPEED_TO_SEGMENTS[0] == []), so
    # without the guard no SegmentAdvanced could ever match and this would
    # never clear. Any SegmentAdvanced at all must clear it.
    session = _advance(session, to_segment=1, to_turn=2)

    assert STUNNED not in statuses_for(session, "bob")
