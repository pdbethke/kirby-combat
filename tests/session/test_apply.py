"""apply_event dispatcher tests — total function over the event union."""
from datetime import datetime, timezone
import pytest

from dataclasses import replace

from lxml import etree

from kirby_cost.objects.talents.lightning_reflexes_all import LightningReflexesAll

from kirby_combat.encounter import Encounter
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import (
    ActingOrderResolved, PhaseSpent, SegmentAdvanced, make_author_engine,
    ActionDeclared, make_author_combatant,
    StatusEffectsChanged,
)
from kirby_combat.session.tie_rule import TieRule
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller
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


def test_apply_status_effects_changed_folds_the_condition():
    """IT USED TO BE LOG-ONLY, and this test said so: "applying it must
    append to the log and otherwise leave the session untouched". That
    made `StatusEffectsChanged` a row nothing read --- and since nothing
    emitted one either, no condition this engine produced ever reached
    the record at all.

    It is the one door now: `apply_event` folds it onto
    `CombatSession.statuses`, which is what `state_view` reads."""
    s = _session()
    assert s.statuses["alice"] == frozenset()
    evt = StatusEffectsChanged(
        id="evt-x", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="alice",
        added=frozenset({"stunned"}),
        removed=frozenset({"entangled"}),
    )
    s2 = apply_event(s, evt)

    assert evt in s2.event_log
    assert s2.statuses["alice"] == frozenset({"stunned"})
    assert s.statuses["alice"] == frozenset(), "the input session is untouched"
    # Nothing besides the log, the fold (and updated_at) changed.
    assert replace(
        s2, event_log=s.event_log, updated_at=s.updated_at,
        statuses=s.statuses,
    ) == s


def test_a_status_row_addressed_to_a_stranger_raises():
    """The same refusal `_fold_vitals` makes, for the same reason: a
    replay that quietly drops a condition is a replay that disagrees with
    the fight and says nothing."""
    s = _session()
    evt = StatusEffectsChanged(
        id="evt-x", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="ghost", added=frozenset({"stunned"}),
    )
    with pytest.raises(ValueError, match="ghost"):
        apply_event(s, evt)


def test_apply_unknown_event_raises():
    s = _session()

    class WeirdEvent:
        kind = "Unknown"
        sequence = len(s.event_log) + 1
        session_id = "s1"

    with pytest.raises(TypeError, match="unhandled event"):
        apply_event(s, WeirdEvent())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The loop's own decisions: the acting order, and a slot spent
# ---------------------------------------------------------------------------

def _two_fighter_session() -> CombatSession:
    """Two combatants, both with a Phase in Segment 12 at SPD 4."""
    def _c(id_: str, dex: int):
        return synthetic_combatant(
            id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
            spd=4, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
            pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
            max_stun=30, max_body=15, max_end=30,
            current_stun=30, current_body=15, current_end=30,
        )
    return CombatSession.create(
        id="s1", combatants=[_c("alice", 20), _c("bob", 15)], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _order_resolved(session, order, segment=12, turn=1):
    return ActingOrderResolved(
        id="evt-order", session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        order=list(order), segment=segment, turn=turn,
    )


def test_apply_acting_order_resolved_puts_the_order_on_the_timeline():
    """The event carries the ids; the slots are rebuilt from the fighters.

    The stat values on each slot are DERIVED (that is why the event does
    not carry them), so this checks them too -- a restored order whose DEX
    values were wrong would sort a later resolution wrongly and nothing
    else would say so.
    """
    s = _two_fighter_session()
    s2 = apply_event(s, _order_resolved(s, ["alice", "bob"]))

    assert [slot.combatant_id for slot in s2.timeline.acting_order] == ["alice", "bob"]
    assert [slot.has_acted for slot in s2.timeline.acting_order] == [False, False]
    assert [slot.dex_at_phase for slot in s2.timeline.acting_order] == [20, 15]
    assert all(slot.segment == 12 for slot in s2.timeline.acting_order)
    assert s2.timeline.current_slot_index == 0


def test_apply_acting_order_resolved_brings_the_clock_with_it():
    """The order describes ONE Segment, so it arrives with that Segment."""
    s = _two_fighter_session()
    assert (s.timeline.segment, s.timeline.turn) == (12, 1)

    s2 = apply_event(s, _order_resolved(s, ["alice"], segment=3, turn=4))

    assert (s2.timeline.segment, s2.timeline.turn) == (3, 4)
    assert s2.timeline.acting_order[0].segment == 3


def test_apply_acting_order_resolved_refuses_a_stranger():
    """A man who is not in this fight cannot be in its order."""
    s = _two_fighter_session()
    with pytest.raises(ValueError, match="carol"):
        apply_event(s, _order_resolved(s, ["alice", "carol"]))


def test_apply_phase_spent_marks_the_slot():
    s = _two_fighter_session()
    s = apply_event(s, _order_resolved(s, ["alice", "bob"]))

    spent = PhaseSpent(
        id="evt-spent", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="alice", segment=12, turn=1,
    )
    s2 = apply_event(s, spent)

    assert {slot.combatant_id: slot.has_acted
            for slot in s2.timeline.acting_order} == {"alice": True, "bob": False}
    # And the session the caller still holds is unchanged -- the flag is a
    # new slot, not a mutation of a shared one.
    assert [slot.has_acted for slot in s.timeline.acting_order] == [False, False]


def test_apply_segment_advanced_still_clears_the_order():
    """Leaving the Segment invalidates the order, as it always has.

    Restoring an order on one event must not quietly stop another event
    from throwing it away: a surviving order would carry its spent flags
    into the next Segment and skip everyone who had only acted in the last.
    """
    s = _two_fighter_session()
    s = apply_event(s, _order_resolved(s, ["alice", "bob"]))
    assert s.timeline.acting_order != []

    s2 = apply_event(s, SegmentAdvanced(
        id="evt-adv", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    ))

    assert s2.timeline.acting_order == []
    assert s2.timeline.current_slot_index == 0


def _replayed(session: CombatSession) -> CombatSession:
    """The same fight, rebuilt from its log and nothing else.

    A fresh combatant (the same build, undamaged) and an EMPTY log, then
    every event applied in order -- so anything the rebuilt session knows,
    it knows because the log said so.
    """
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    c.hero.talents = list(_hero_with_single_scope_lightning_reflexes().talents)
    rebuilt = CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    )
    assert rebuilt.event_log == []
    for event in session.event_log:
        rebuilt = apply_event(rebuilt, event)
    return rebuilt


def test_the_replayed_fight_refuses_the_declaration_the_live_one_refused():
    """6E1 p.116(c), enforced at BOTH doors.

    The election is not derivable from the acting order's ids: a man who
    elected Lightning Reflexes for "strike" may not then dodge, and that
    rule reads `ActingSlot.intent`. With the intents left out of
    `ActingOrderResolved`, the replayed fight rebuilt every slot with
    `intent=None` and ACCEPTED the dodge the live fight refused -- the
    same rule live at one door and asleep at the other.
    """
    live = _driven_encounter_session()
    replayed = _replayed(live)

    assert [slot.intent for slot in replayed.timeline.acting_order] == \
        [slot.intent for slot in live.timeline.acting_order]

    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(live, _declare(live, "dodge"))
    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(replayed, _declare(replayed, "dodge"))


def test_the_replayed_fight_still_permits_the_elected_action():
    """The other half: the restriction must not become a blanket refusal."""
    replayed = _replayed(_driven_encounter_session())
    assert apply_event(replayed, _declare(replayed, "strike")).event_log[-1].kind \
        == "ActionDeclared"


def test_apply_phase_spent_refuses_a_slot_that_is_not_there():
    """A spend nothing can spend is a replay one Phase ahead of the fight."""
    s = _two_fighter_session()
    s = apply_event(s, _order_resolved(s, ["alice", "bob"]))

    def _spent(who: str):
        return PhaseSpent(
            id=f"evt-spent-{who}", session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            combatant_id=who, segment=12, turn=1,
        )

    with pytest.raises(ValueError, match="carol"):
        apply_event(s, _spent("carol"))

    spent_once = apply_event(s, _spent("alice"))
    with pytest.raises(ValueError, match="alice"):
        apply_event(spent_once, PhaseSpent(
            id="evt-again", session_id=s.id,
            sequence=len(spent_once.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            combatant_id="alice", segment=12, turn=1,
        ))
