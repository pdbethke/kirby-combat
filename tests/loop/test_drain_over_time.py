"""A Damage Over Time Drain drains on its clock, increment by increment.

6E1 p.330: Damage Over Time "is primarily intended for Instant attacks,
such as Blast, Drain, and RKA". p.331: "the first increment of damage
affects the target one time period after the character uses the attack";
p.331's options: "Target's defenses only apply once", and a Lock Out that
bars a second use on the same victim until the first has run (p.332).
p.332: the standard defense still applies, "such as Power Defense against a
Drain STUN".

FOUND 2026-11-10: every Damage Over Time Drain was refused as unbuilt
(`attack_shapes.offer_is_buildable`), so Plague's Acute Disease (Drain 1d6,
6 increments one every 2 Segments, defenses once, Lock Out) never reached a
menu even after its Variable Effect was built.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.attack_shapes import offers_the_engine_can_keep
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.lingering import LingeringEnd, active_lingering, fire_due_doses
from kirby_combat.loop.chooser import complete_choice, validate_choice
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")
HIT = [1, 1, 1]


def _adder(xmlid, option):
    return SimpleNamespace(xmlid=xmlid, option_id=option, _selected_option=None)


class _AcuteDisease:
    """Plague's Acute Disease (CV3), in the shape the loader gives."""

    def __init__(self, *, input="DEX", one_defense=True, lockout=True,
                 variable=False):
        self.xmlid = "DRAIN"
        self.name = self.alias = "Acute Disease"
        self.id = "src-disease"
        self.levels = 1
        self.level_value = 1.0
        self.input = input
        self.range = "Yes"
        self.range_value = 100
        self.active_cost = 40
        self.assigned_adders: list = []
        subs = []
        if one_defense:
            subs.append(SimpleNamespace(xmlid="ONEDEFENSE"))
        if lockout:
            subs.append(SimpleNamespace(xmlid="LOCKOUT"))
        dot = SimpleNamespace(
            xmlid="DAMAGEOVERTIME", levels=0,
            assigned_adders=[_adder("INCREMENTS", "6"), _adder("TIMEBETWEEN", "2SEGMENTS")],
            assigned_modifiers=subs)
        mods = [dot]
        if variable:
            mods += [SimpleNamespace(xmlid="VARIABLEEFFECT", levels=0),
                     SimpleNamespace(xmlid="EXPANDEDEFFECT", levels=2)]
        self.assigned_modifiers = mods
        self.sub_powers: list = []


def _plague(**kw):
    c = fighter("plague", side=VILLAINS)
    c.hero.powers.append(_AcuteDisease(**kw))
    return c


def _session(*cast) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(cast), scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


def _menu(session):
    actor = session.combatants["plague"]
    enemies = [c for c in session.combatants.values() if c.side != actor.side]
    return offers_the_engine_can_keep(session, "plague",
                                      enumerate_actions(actor, enemies, allies=[]))


def _drain(session):
    return next(a for a in _menu(session) if a.kind == "drain")


def _at(session, segment_offset: int) -> CombatSession:
    """The same fight ``segment_offset`` Segments after the use."""
    tl = session.timeline
    absolute = (tl.turn - 1) * 12 + tl.segment + segment_offset
    session.timeline = replace(tl, turn=(absolute - 1) // 12 + 1,
                               segment=(absolute - 1) % 12 + 1)
    return session


def _use(session, dice):
    return resolve_chosen(session, session.combatants["plague"], _drain(session),
                          template=TEMPLATE, roller=FakeRoller(dice)).session


def _dex(session, who="agent"):
    return session.combatants[who].combat_stats().dex


def test_a_damage_over_time_drain_is_offered() -> None:
    session = _session(_plague(), fighter("agent", side=HEROES))
    assert _drain(session).target_id == "agent"


def test_the_use_drains_nothing_yet() -> None:
    """p.331: the first increment lands one interval after the use."""
    session = _use(_session(_plague(), fighter("agent", side=HEROES, dex=20)), [HIT])
    assert _dex(session) == 20
    [effect] = active_lingering(session)
    assert effect.adjusts == ("DEX",) and effect.increments_remaining == 6


def test_each_increment_drains_on_its_clock_and_it_runs_its_course() -> None:
    """Six 1d6 increments of 4: DEX costs 2 a point (6E1 p.137), so each
    takes 2 DEX; nothing has returned inside 12 Segments (5 a Turn,
    p.141) beyond one Turn's 5 points."""
    session = _use(_session(_plague(one_defense=False),
                            fighter("agent", side=HEROES, dex=20)), [HIT])
    session = fire_due_doses(_at(session, 2), template=TEMPLATE, roller=FakeRoller([[4]]))
    assert _dex(session) == 18
    session = fire_due_doses(_at(session, 10), template=TEMPLATE,
                             roller=FakeRoller([[4]] * 5))
    ended = [e for e in session.event_log if e.kind == "LingeringAttackEnded"]
    assert [e.reason for e in ended] == [LingeringEnd.RAN_ITS_COURSE.value]
    doses = [e for e in session.event_log if e.kind == "ActionResolved"
             and (e.result_payload or {}).get("lingering_id")]
    assert len(doses) == 6
    assert all(d.result_payload["character_points"] == {"DEX": -4} for d in doses)


def test_power_defense_applies_to_each_increment() -> None:
    """p.332: Power Defense applies against a Drain's increments."""
    session = _session(_plague(one_defense=False), _agent_with_power_defense(3))
    session = _use(session, [HIT])
    session = fire_due_doses(_at(session, 4), template=TEMPLATE,
                             roller=FakeRoller([[5], [5]]))
    doses = _doses(session)
    assert [d["power_defense_absorbed"] for d in doses] == [3, 3]
    assert [d["character_points"]["DEX"] for d in doses] == [-2, -2]


def test_defenses_only_once_spends_power_defense_across_the_increments() -> None:
    """p.331, "Target's defenses only apply once": PD 3 against 2 then 5 is
    2 soaked, then the last 1, then nothing."""
    session = _session(_plague(one_defense=True), _agent_with_power_defense(3))
    session = _use(session, [HIT])
    session = fire_due_doses(_at(session, 6), template=TEMPLATE,
                             roller=FakeRoller([[2], [5], [4]]))
    doses = _doses(session)
    assert [d["power_defense_absorbed"] for d in doses] == [2, 1, 0]
    assert [d["character_points"]["DEX"] for d in doses] == [0, -4, -4]


def test_lock_out_bars_a_second_use_on_him_until_the_first_has_run() -> None:
    session = _use(_session(_plague(), fighter("agent", side=HEROES)), [HIT])
    assert not [a for a in _menu(session) if a.kind == "drain"]


def test_a_variable_effect_disease_drains_what_he_named_every_increment() -> None:
    """Plague's own power: the choice is made at the use (p.144) and every
    increment drains both."""
    session = _session(_plague(input="any two characteristics at once", variable=True,
                               one_defense=False),
                       fighter("agent", side=HEROES, dex=20))
    menu = _menu(session)
    offer = next(a for a in menu if a.kind == "drain")
    action = validate_choice(complete_choice(offer, ["DEX", "STR"]), menu)
    session = resolve_chosen(session, session.combatants["plague"], action,
                             template=TEMPLATE, roller=FakeRoller([HIT])).session
    session = fire_due_doses(_at(session, 2), template=TEMPLATE, roller=FakeRoller([[4]]))
    stats = session.combatants["agent"].combat_stats()
    assert (stats.dex, stats.str_) == (18, 15 - 4)


def _doses(session):
    return [e.result_payload for e in session.event_log if e.kind == "ActionResolved"
            and (e.result_payload or {}).get("lingering_id")]


def _agent_with_power_defense(pd: int, dex: int = 20):
    from fixtures.synthetic_hero import synthetic_combatant

    return synthetic_combatant(
        id="agent", name="agent", ocv=9, dcv=5, omcv=5, dmcv=5, spd=4, dex=dex,
        ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4, rpd=2, red=2, md=3,
        power_defense=pd, flash_defense=0, max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40, side=HEROES, attacks=[])
