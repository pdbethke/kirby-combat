"""Every Multipower opens the fight with a stated split (spec §5.2, decision 7).

6E1 p.404-406: a Multipower's reserve is divided among its slots, a fixed
slot whole or not at all, a variable one in any share. Before Segment 12,
`run_phase` asks each combatant's seat for the split each of his
Multipowers starts with, in roster order and then framework order, one per
call. The fight does not start until every one is on the log, and none is
chosen for anybody. An opening is not a re-split, so it does not spend
p.410's once-a-Phase allowance.

Kerendor's Magic (6E1 p.406, as a stub with stand-in rungs): reserve 60;
`wind` variable 60, `bolt` variable 60, `wall` fixed 45. Synthetic, so the
loop's mechanics run everywhere without a licensed template.
"""
from __future__ import annotations

import dataclasses

import pytest

from conftest import fighter                           # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.framework import StandingSplit, reallocated_this_phase
from kirby_combat.hero_view import SlotEffect, SlotStep
from kirby_combat.loop import run_encounter, run_phase
from kirby_combat.loop.chooser import FirstLegalChooser, InvalidChoice
from kirby_combat.loop.run import NoOpeningSplit, _advance_to_an_actor, pending_openings
from kirby_combat.models import FrameworkView, PricedSlotView, SlotView
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import _SyntheticCombatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from tests.support.splits import open_with


def _rungs(top, every):
    return tuple(SlotStep(p, f"{p} pts", SlotEffect.nothing())
                 for p in (*range(0, top, every), top))


def _magic(fid="kmp", name="Kerendor's Magic"):
    return FrameworkView(
        framework_id=fid, xmlid="MULTIPOWER", name=name, kind="multipower",
        reserve_or_pool=60,
        slots=[PricedSlotView("wind", "Wind", 60, True, "other", steps=_rungs(60, 5)),
               PricedSlotView("bolt", "Bolt", 60, True, "other", steps=_rungs(60, 5)),
               PricedSlotView("wall", "Wall", 45, False, "other", steps=_rungs(45, 45))])


def _fixed_only(fid="fmp"):
    """Two fixed slots that cannot both be on: 30 + 30 against 45."""
    return FrameworkView(
        framework_id=fid, xmlid="MULTIPOWER", name="Claws and Legs",
        kind="multipower", reserve_or_pool=45,
        slots=[PricedSlotView("claws", "Claws", 30, False, "other", steps=_rungs(30, 30)),
               PricedSlotView("legs", "Legs", 30, False, "other", steps=_rungs(30, 30))])


def _vpp():
    return FrameworkView(framework_id="pool", xmlid="VPP", name="Gadgets",
                         kind="vpp", reserve_or_pool=30, slots=[])


@dataclasses.dataclass
class _Multipowered(_SyntheticCombatant):
    """A synthetic fighter carrying the frameworks it is given. A FIELD, so
    it survives the `dataclasses.replace` the engine does on every change."""

    _frameworks: tuple = ()

    def framework_view(self):
        return [FrameworkView(v.framework_id, v.xmlid, v.name, v.kind,
                              v.reserve_or_pool,
                              [SlotView(s.slot_id, s.name, s.active_points,
                                        s.variable, s.kind) for s in v.slots])
                for v in self._frameworks]

    def priced_framework(self, framework_id):
        return next((v for v in self._frameworks if v.framework_id == framework_id), None)


def _carrying(id, side, *views, standing=None):
    base = fighter(id, side=Side.named(side))
    fields = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}
    man = _Multipowered(**fields, _frameworks=tuple(views))
    if standing:
        man = dataclasses.replace(man, state=dataclasses.replace(
            man.state, standing_splits=standing))
    return man


def _encounter(*combatants):
    session = CombatSession.create(
        id="s", combatants=list(combatants), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=7)).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


class _States:
    """A seat that states each opening it is given and plays the rest
    first-legal. Records every situation it was shown."""

    def __init__(self, answers):
        self.answers = answers
        self.seen = []
        self._rest = FirstLegalChooser()

    def choose(self, situation):
        self.seen.append(situation)
        if situation.opening:
            (offer,) = situation.menu
            fid = offer.choice.framework_id
            return offer.action_id + "=" + self.answers[(situation.actor.id, fid)]
        return self._rest.choose(situation)


def _roller():
    return RandomRoller(seed=7)


# ── the opening ────────────────────────────────────────────────────────────

def test_the_first_phase_is_kerendors_opening():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    seat = _States({("kerendor", "kmp"): "wall@45+wind@15"})

    first = run_phase(enc, seat, roller=_roller())

    (situation,) = seat.seen
    assert situation.opening is True
    (offer,) = situation.menu
    assert (offer.kind, offer.action_id) == ("opening_split", "opening_split:kmp:split")
    assert offer.choice.current == {}
    assert first.actor_id == "kerendor"
    assert first.kind == "opening_split"
    kinds = [e.kind for e in first.events]
    assert "SlotsAllocated" in kinds
    assert "ActingOrderResolved" not in kinds, "no Segment begins at an opening"
    (alloc,) = [e for e in first.events if e.kind == "SlotsAllocated"]
    assert alloc.opening is True
    assert first.session.combatants["kerendor"].state.slot_points["kmp"] == {
        "wind": 15, "bolt": 0, "wall": 45}
    # 6E1 p.410: the opening is not the Phase's one re-split
    assert not reallocated_this_phase(first.session, "kerendor")


def test_after_the_opening_segment_12_starts():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    seat = _States({("kerendor", "kmp"): "wall@45+wind@15"})

    first = run_phase(enc, seat, roller=_roller())
    second = run_phase(first.encounter, seat, roller=_roller())

    assert seat.seen[1].opening is False
    assert "ActingOrderResolved" in [e.kind for e in second.events]
    assert second.session.timeline.segment == 12
    assert second.actor_id in ("kerendor", "foe")


def test_every_multipower_opens_in_roster_then_framework_order():
    enc = _encounter(
        _carrying("kerendor", "heroes", _magic("kmp"), _vpp(), _magic("kmp2", "Second Magic")),
        fighter("plain", side=Side.named("heroes")),
        _carrying("foe", "villains", _fixed_only()),
    )
    assert pending_openings(enc.sessions[0]) == [
        ("kerendor", "kmp"), ("kerendor", "kmp2"), ("foe", "fmp")]
    seat = _States({("kerendor", "kmp"): "bolt@60", ("kerendor", "kmp2"): "wind@60",
                    ("foe", "fmp"): "claws@30"})

    for expected in [("kerendor", "kmp"), ("kerendor", "kmp2"), ("foe", "fmp")]:
        phase = run_phase(enc, seat, roller=_roller())
        enc = phase.encounter
        assert (phase.actor_id, phase.action_id.split(":")[1]) == expected
        assert "ActingOrderResolved" not in [e.kind for e in phase.events]
    assert pending_openings(enc.sessions[0]) == []
    after = run_phase(enc, seat, roller=_roller())
    assert "ActingOrderResolved" in [e.kind for e in after.events]


def test_the_bare_opening_id_is_not_an_answer():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))

    class Bare:
        def choose(self, situation):
            return situation.menu[0].action_id

    with pytest.raises(InvalidChoice):
        run_phase(enc, Bare(), roller=_roller())


def test_a_rule_break_is_refused_at_the_opening():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    with pytest.raises(InvalidChoice):
        run_phase(enc, _States({("kerendor", "kmp"): "wall@45+bolt@20"}), roller=_roller())


def test_first_legal_does_not_choose_a_split_for_him():
    """No defaults: a seat that only takes the first offer cannot state a
    split, and says so rather than picking one."""
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    with pytest.raises(InvalidChoice, match="split"):
        run_phase(enc, FirstLegalChooser(), roller=_roller())


def test_a_seat_that_cannot_answer_now_stops_the_fight_where_it_is():
    """A human seat raises (kirby-ai's NoChoice; kirby-api pauses on it). The
    opening propagates it exactly as a Phase question does: nothing is
    written, and asking again poses the same opening."""
    class NoChoice(Exception):
        pass

    class Human:
        def choose(self, situation):
            raise NoChoice(situation.actor.id)

    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    with pytest.raises(NoChoice):
        run_phase(enc, Human(), roller=_roller())
    assert pending_openings(enc.sessions[0]) == [("kerendor", "kmp")]


# ── what the offer carries ────────────────────────────────────────────────

PATROL = StandingSplit(name="Patrol", points={"wind": 30, "bolt": 30},
                       standard=False, position=1)
COMBAT = StandingSplit(name="Combat", points={"wall": 45, "bolt": 15},
                       standard=True, position=0)


def test_the_standard_combat_set_is_shown_and_not_applied():
    man = _carrying("kerendor", "heroes", _magic(), standing={"kmp": (PATROL, COMBAT)})
    enc = _encounter(man, fighter("foe", side=Side.named("villains")))

    class Looks:
        def choose(self, situation):
            self.situation = situation
            raise LookupError

    seat = Looks()
    with pytest.raises(LookupError):
        run_phase(enc, seat, roller=_roller())
    choice = seat.situation.menu[0].choice
    assert [p.name for p in choice.presets[:2]] == ["Combat", "Patrol"]
    assert choice.standard is not None and choice.standard.name == "Combat"
    assert choice.standard.points == {"wind": 0, "bolt": 15, "wall": 45}
    # never applied by itself
    assert enc.sessions[0].combatants["kerendor"].state.slot_points == {}


def test_no_standard_set_means_none():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    seat = _States({("kerendor", "kmp"): "bolt@60"})
    run_phase(enc, seat, roller=_roller())
    assert seat.seen[0].menu[0].choice.standard is None


def test_a_fixed_only_multipower_opens_on_the_same_shape():
    """Its presets are the whole sets the reserve can carry (6E1 p.404-405)."""
    enc = _encounter(_carrying("foe", "villains", _fixed_only()), fighter("hero", side=Side.named("heroes")))
    seat = _States({("foe", "fmp"): "legs@30"})
    phase = run_phase(enc, seat, roller=_roller())
    (offer,) = seat.seen[0].menu
    assert offer.action_id == "opening_split:fmp:split"
    assert [p.points for p in offer.choice.presets] == [
        {"claws": 30, "legs": 0}, {"claws": 0, "legs": 30}]
    assert phase.session.combatants["foe"].state.slot_points["fmp"] == {
        "claws": 0, "legs": 30}


def test_nothing_on_is_a_split_he_may_state_at_the_opening():
    """Stated, not defaulted: an empty answer at the opening is "every slot
    off", which is a legal split; only a RE-split to the split in force
    changes nothing."""
    enc = _encounter(_carrying("foe", "villains", _fixed_only()), fighter("hero", side=Side.named("heroes")))
    phase = run_phase(enc, _States({("foe", "fmp"): ""}), roller=_roller())
    assert phase.session.combatants["foe"].state.slot_points["fmp"] == {
        "claws": 0, "legs": 0}


# ── the guard, the helper, the driver ─────────────────────────────────────

def test_no_segment_begins_with_an_opening_pending():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    template = enc._resolve_template(None)
    with pytest.raises(NoOpeningSplit):
        _advance_to_an_actor(enc, campaign=None, tie_roller=lambda: [3, 3, 3],
                             roller=_roller(), template=template)


def test_open_with_states_the_split_for_a_test():
    enc = _encounter(_carrying("kerendor", "heroes", _magic()), fighter("foe", side=Side.named("villains")))
    s = open_with(enc.sessions[0], "kerendor", "kmp", {"bolt": 60})
    assert pending_openings(s) == []
    assert s.combatants["kerendor"].state.slot_points["kmp"] == {
        "wind": 0, "bolt": 60, "wall": 0}
    with pytest.raises(Exception):
        open_with(enc.sessions[0], "kerendor", "kmp", {"bolt": 60, "wall": 45})


def test_run_encounter_opens_then_fights_and_counts_no_opening_as_a_phase():
    def fight():
        return _encounter(_carrying("kerendor", "heroes", _magic()),
                          fighter("foe", side=Side.named("villains")))

    seat = _States({("kerendor", "kmp"): "bolt@60"})
    out = run_encounter(fight(), seat, roller=_roller(), max_turns=1)
    kinds = [e.kind for e in out.encounter.sessions[0].event_log]
    assert kinds.index("SlotsAllocated") < kinds.index("ActingOrderResolved")
    assert len([s for s in seat.seen if s.opening]) == 1

    # the same fight opened by the test: the same Phases, none for the opening
    pre = fight()
    pre = Encounter(id=pre.id, turn=pre.turn, segment=pre.segment,
                    sessions=[open_with(pre.sessions[0], "kerendor", "kmp", {"bolt": 60})])
    same = run_encounter(pre, _States({}), roller=_roller(), max_turns=1)
    assert out.phases == same.phases
