"""apply_event dispatcher tests — total function over the event union."""
from datetime import datetime, timezone
import pytest

from dataclasses import replace

from lxml import etree

from kirby_cost.objects.talents.lightning_reflexes_all import LightningReflexesAll

from kirby_combat.encounter import Encounter
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import (
    SegmentAdvanced, make_author_engine,
    ActionDeclared, make_author_combatant,
)
from kirby_combat.session.tie_rule import TieRule
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session.timeline import ActingSlot, ActionIntent
from kirby_combat.talents.lightning_reflexes import LightningReflexesGrant


def _session() -> CombatSession:
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    return CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def test_apply_segment_advanced_updates_timeline():
    s = _session()
    evt = SegmentAdvanced(
        id="evt-x", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    s2 = apply_event(s, evt)
    assert s2.timeline.segment == 1
    assert s2.timeline.turn == 2
    assert evt in s2.event_log


def test_apply_sequence_must_be_next():
    s = _session()
    evt = SegmentAdvanced(
        id="evt-x", session_id="s1", sequence=5,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    with pytest.raises(ValueError, match="sequence"):
        apply_event(s, evt)


def test_apply_action_declared_does_not_mutate_combatants():
    s = _session()
    declared = ActionDeclared(
        id="evt-2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice", action_type="strike", targets=[], parameters={},
    )
    s2 = apply_event(s, declared)
    assert s2.combatants["alice"].current_stun == 30
    assert s2.event_log[-1].kind == "ActionDeclared"


def _session_with_lightning_reflexes_slot(*, option_id: str, option_alias: str = "strike"):
    """A session whose timeline already carries a *resolved* ActingSlot for
    "alice" (segment == the session's current segment, 12) electing
    Lightning Reflexes for "strike" -- the shape a driver that ran
    resolve_acting_order and stored the result would produce. See
    apply.py's `_enforce_lightning_reflexes_phase_restriction` docstring
    for why nothing in this codebase writes that shape today."""
    s = _session()
    slot = ActingSlot(
        combatant_id="alice",
        segment=s.timeline.segment,
        dex_at_phase=20,
        int_tiebreak=15,
        pre_tiebreak=15,
        ego=15,
        intent=ActionIntent("strike", elect_lightning_reflexes=True),
        lightning_reflexes_grants=(
            LightningReflexesGrant(
                levels=4, option_id=option_id, option_alias=option_alias),
        ),
    )
    return replace(s, timeline=replace(s.timeline, acting_order=[slot]))


def _declare(s: CombatSession, action_type: str) -> ActionDeclared:
    return ActionDeclared(
        id="evt-2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice", action_type=action_type, targets=[], parameters={},
    )


def test_electing_lightning_reflexes_forbids_a_different_declared_action():
    """6E1 p.116(c): "no movement, acrobatics, or other Actions" in the
    Phase where the elected bonus is used. Integration-level: this goes
    through apply_event, not phase_restricted_to directly, so it proves
    the restriction is actually enforced and not merely advisory."""
    s = _session_with_lightning_reflexes_slot(option_id="SINGLE")
    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(s, _declare(s, "move"))


def test_electing_lightning_reflexes_permits_the_elected_action():
    s = _session_with_lightning_reflexes_slot(option_id="SINGLE")
    s2 = apply_event(s, _declare(s, "strike"))
    assert s2.event_log[-1].kind == "ActionDeclared"


def test_all_scope_election_does_not_restrict_the_phase():
    """An ALL-scope grant covers every Action, so electing it is not
    meaningfully restricted (6E1 p.116(c)) -- a different declared action
    must go through."""
    s = _session_with_lightning_reflexes_slot(
        option_id="ALL", option_alias="All Actions")
    s2 = apply_event(s, _declare(s, "move"))
    assert s2.event_log[-1].kind == "ActionDeclared"


def _hero_with_single_scope_lightning_reflexes(*, option_alias: str = "strike"):
    """A hero stub carrying one real LightningReflexesAll Talent scoped to
    a single named Action, built to the same verbatim OPTION/OPTIONID
    shape as ``tests/talents/test_lightning_reflexes.py::
    _hero_with_talent`` (confirmed against 76 real instances -- see that
    module's docstring): OPTIONID="SINGLE" is what produces a
    restriction; the XMLID is LIGHTNING_REFLEXES_ALL regardless of scope."""
    elem = etree.Element("TALENT")
    elem.set("XMLID", "LIGHTNING_REFLEXES_ALL")
    elem.set("LEVELS", "4")
    elem.set("ALIAS", "Lightning Reflexes")
    elem.set("OPTION", "SINGLE")
    elem.set("OPTIONID", "SINGLE")
    elem.set("OPTION_ALIAS", option_alias)
    talent = LightningReflexesAll(elem)

    class _Hero:
        talents = [talent]
        powers: list = []

    return _Hero()


def _driven_encounter_session():
    """One combatant ("alice") with a SINGLE-scope Lightning Reflexes
    grant for "strike", run through ``Encounter.run_segment`` (the driver
    Task 1 built) with an intent electing the bonus. Returns the
    resulting ``CombatSession`` whose ``timeline.acting_order`` was
    populated BY THE DRIVER, not hand-built -- this is what proves
    ``apply.py``'s guard now fires through a real call path."""
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    # Graft the Lightning Reflexes talent onto the synthetic hero already
    # inside the combatant (same pattern as `test_lightning_reflexes.py`'s
    # `_c_with_hero`) so `combat_stats()`/defenses keep working normally.
    c.hero.talents = list(_hero_with_single_scope_lightning_reflexes().talents)

    session = CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()

    encounter = Encounter(
        id="enc-1",
        sessions=[session],
        # INT_THEN_PRE (not the book-default DEX_ROLL) needs no roller --
        # irrelevant here anyway since there is only one combatant to
        # order, so no tie is ever broken.
        template=CombatTemplate(name="test-template", tie_rule=TieRule.INT_THEN_PRE),
    )
    intents = {"alice": ActionIntent("strike", elect_lightning_reflexes=True)}
    new_encounter = encounter.run_segment(intents=intents)
    return new_encounter.sessions[0]


def test_lightning_reflexes_restriction_fires_through_driver_built_session():
    """6E1 p.116(c): electing Lightning Reflexes for "strike" forfeits the
    rest of the Phase. Unlike
    `test_electing_lightning_reflexes_forbids_a_different_declared_action`
    (which hand-builds a timeline already carrying a resolved
    ``ActingSlot`` -- exactly the shape a driver would produce, done by
    hand), this session's ``acting_order`` comes from
    ``Encounter.run_segment`` itself. This is the proof that the DRIVER,
    not just the guard, is wired end to end."""
    s = _driven_encounter_session()
    assert s.timeline.acting_order  # sanity: the driver actually populated it
    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(s, _declare(s, "move"))


def test_lightning_reflexes_restriction_fires_at_a_non_segment_12_phase():
    """Regression for a Critical bug the coordinator caught: `run_segment`
    used to write ONLY `acting_order`/`current_slot_index` onto a
    session's Timeline, never `segment`/`turn` -- and `CombatSession.
    create()` hardcodes `Timeline(turn=1, segment=12, ...)` (6E2 p.20's
    combat-start default). `apply.py`'s guard matches a resolved
    `ActingSlot` against `session.timeline.segment`, so before the fix
    that guard only ever fired when the Encounter itself happened to be
    on Segment 12 -- `test_lightning_reflexes_restriction_fires_through_
    driver_built_session` above passed only because `Encounter`'s own
    default segment (12) coincides with that hardcoded value, not because
    the guard generally worked. This test drives Segment 3 instead --
    still a real Phase for a SPD 4 combatant (segments 3/6/9/12) -- to
    prove the guard fires at a segment OTHER than 12 too."""
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    c.hero.talents = list(_hero_with_single_scope_lightning_reflexes().talents)
    session = CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()
    encounter = Encounter(
        id="enc-1", segment=3, sessions=[session],
        template=CombatTemplate(name="test-template", tie_rule=TieRule.INT_THEN_PRE),
    )
    intents = {"alice": ActionIntent("strike", elect_lightning_reflexes=True)}
    new_encounter = encounter.run_segment(intents=intents)
    s = new_encounter.sessions[0]
    assert s.timeline.acting_order  # sanity: the driver populated it
    assert s.timeline.segment == 3  # run_segment must sync this to the Encounter
    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(s, _declare(s, "move"))


def test_lightning_reflexes_restriction_is_inert_without_the_driver():
    """Contrast case for the test above: the SAME scenario (SINGLE-scope
    grant, "strike" elected), but built the old way -- a session whose
    timeline was never run through ``Encounter.run_segment``, so
    ``acting_order`` is empty. ``apply_event`` must NOT raise here. This
    is what proves the *driver*, not the guard itself, is what changed:
    the guard's logic is identical in both tests; only how the session
    got its ``acting_order`` differs."""
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    c.hero.talents = list(_hero_with_single_scope_lightning_reflexes().talents)
    s = CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()
    assert s.timeline.acting_order == []  # never driven -- still empty
    s2 = apply_event(s, _declare(s, "move"))
    assert s2.event_log[-1].kind == "ActionDeclared"


def test_apply_unknown_event_raises():
    s = _session()

    class WeirdEvent:
        kind = "Unknown"
        sequence = len(s.event_log) + 1
        session_id = "s1"

    with pytest.raises(TypeError, match="unhandled event"):
        apply_event(s, WeirdEvent())  # type: ignore[arg-type]
