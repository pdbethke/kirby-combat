"""Mental combat that does something (spec 2026-10-26-mental-combat-design).

WHAT A PROD FIGHT SHOWED (session 33bf8bee, 2026-10-26). Brainchild, OMCV 8,
used Mental Blast nine times and Mind Control once in a five-way fight:

* every mental power hit --- there was no MCV Attack Roll (6E1 p.150);
* his Mind Control landed, was recorded as a degree, and changed nothing:
  no order, no Breakout Roll, his victim fought on exactly as before;
* he had line of sight to NOBODY and was offered mental attacks on all
  four enemies, because owning Mind Scan counted as perceiving every mind.

Each test below drives the engine's own doors --- `resolve_chosen`,
`run_phase`, `enumerate_actions` --- because calling the pure resolvers
directly is exactly the standard under which all of this sat unreached
behind a green suite.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import LegalAction, enumerate_actions
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.mental.attack_roll import mental_attack_roll, mind_scan_omcv_modifier
from kirby_combat.mental.continuing import (
    WITHDRAW_KINDS, breakout_due, effects_on, mind_control_orders, mind_scan_locks,
)
from kirby_combat.models import AttackPower
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionResolved, BreakoutRolled, make_author_engine
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


# ── the cast ────────────────────────────────────────────────────────────────

class _Power:
    """A hero power in the shape the loader gives enumeration."""

    def __init__(self, xmlid: str, levels: int, *, mods: tuple[str, ...] = ()):
        self.xmlid = xmlid
        self.name = xmlid.title()
        self.alias = xmlid.title()
        self.levels = levels
        self.id = f"src-{xmlid}"
        self.assigned_adders: list = []
        self.assigned_modifiers = [SimpleNamespace(xmlid=m) for m in mods]
        self.sub_powers: list = []


def _mental_blast(levels: int = 6) -> AttackPower:
    return AttackPower(
        xmlid="MENTALBLAST", name="Mind Blast", damage_dice=levels,
        half_die=False, plus_one=False, damage_type="normal", defense_type="md",
        range_m=None, uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, source_id="src-MENTALBLAST", is_ranged=False,
    )


def _person(id_: str, side: str, *, dex: int, mentalist: bool = False,
            dmcv: int = 5, md: int = 0, ego: int = 10):
    c = synthetic_combatant(
        id=id_, name=id_, ocv=6, dcv=5, omcv=8 if mentalist else 3, dmcv=dmcv,
        spd=4, dex=dex, ego=ego, str_=15, con=18, pre=10, rec=6,
        pd=5, ed=5, md=md, max_stun=40, max_body=12, max_end=40,
        side=Side.named(side), is_mentalist=mentalist,
        attacks=[_mental_blast()] if mentalist else [AttackPower(
            xmlid="ENERGYBLAST", name="Blast", damage_dice=6, half_die=False,
            plus_one=False, damage_type="normal", defense_type="ed", range_m=100,
            uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
            increased_stun_mult=0, source_id=f"{id_}-eb", is_ranged=True)],
    )
    return c


def _brainchild(*, telepathic: bool = False):
    psi = _person("psi", "psi", dex=10, mentalist=True)
    psi.hero.powers.extend([
        _Power("MINDCONTROL", 12, mods=("TELEPATHIC",) if telepathic else ()),
        _Power("MINDSCAN", 12),
    ])
    return psi


def _scene(*, wall: bool, **positions) -> Scene:
    walls = [Wall(id="w", name="Brick", segment=(Position(10, 0, 0), Position(10, 30, 0)),
                  height_m=6.0, blocks_los=True, blocks_movement=True,
                  cover_level=4, body=6)] if wall else []
    return Scene(
        id="lot", name="lot", bounds=SceneBounds(-5, -5, 0, 40, 40, 20),
        surfaces=[Surface(id="g", name="g", polygon_xy=[(-5, -5), (40, -5), (40, 40), (-5, 40)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=walls, hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _fight(*cast, scene=None) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(cast), scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


class _Dice(RandomRoller):
    """3d6 rolls come off a script, in order; every other roll is honest."""

    def __init__(self, *three_d6: tuple[int, int, int], effect: int | None = None):
        super().__init__(seed=11)
        self._three = [list(t) for t in three_d6]
        self._effect = effect

    def roll_dice(self, count, sides=6):
        if count == 3 and self._three:
            return self._three.pop(0)
        if self._effect is not None and count != 3:
            return [self._effect] * count
        return super().roll_dice(count, sides)


def _offer(kind: str, target: str, power, *, order: str | None = None) -> LegalAction:
    return LegalAction(action_id=f"{kind}:{target}:{order}", kind=kind, target_id=target,
                       power_xmlid=power.xmlid, power_name=power.name, summary=kind,
                       _attack_view=power, order=order)


def _controlled(order: str, *, extra=()):
    """psi has just Mind Controlled mark with ``order``; nobody has broken out."""
    psi = _brainchild()
    mark = _person("mark", "gang", dex=30)
    session = _fight(psi, mark, *extra)
    mc = next(p for p in psi.hero.powers if p.xmlid == "MINDCONTROL")
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mind_control", "mark", mc, order=order),
                              template=TEMPLATE, roller=_Dice((1, 1, 1), effect=6))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["established"] is True, payload
    return resolved.session


class _Records:
    """A chooser that takes the first offer and keeps the menu it was shown
    on the actor's OWN Phase.

    The loop now also asks a man out of turn --- whether he Aborts when he is
    attacked, whether he uses a Held Action (`loop/reactions.py`) --- and those
    menus are not the Phase menu these tests read, so they are not kept.
    """

    def __init__(self):
        self.menu: list[LegalAction] = []

    def choose(self, situation):
        if situation.out_of_turn is None:
            self.menu = list(situation.menu)
        return situation.menu[0].action_id


def _marks_phase(session, roll: tuple[int, int, int]):
    """Mark's Breakout Roll comes up ``roll``, then his Phase runs (DEX 30:
    he acts first in Segment 12).

    The roll is made through `roll_breakouts` --- the very function
    `run_phase` calls --- because a Phase draws a DEX tie-break per acting
    slot before it, and scripting dice through that is scripting the
    tie-break. `test_run_phase_makes_the_breakout_roll_itself` proves the
    loop makes the call.
    """
    from kirby_combat.mental.continuing import roll_breakouts

    session = roll_breakouts(session, "mark", _Dice(roll))
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    chooser = _Records()
    result = run_phase(enc, chooser, roller=RandomRoller(seed=21))
    assert result.actor_id == "mark"
    return result, chooser.menu


def _targets(menu) -> set[str]:
    return {a.target_id for a in menu if a.target_id}


# ── §1 the MCV Attack Roll ──────────────────────────────────────────────────

def test_a_mental_blast_that_misses_does_nothing_and_rolls_no_effect():
    """6E1 p.151: the Effect Roll follows "a successful MCV Attack Roll".
    An 18 misses 11 + 8 - 5 = 14; the target keeps every point of STUN."""
    psi, mark = _brainchild(), _person("mark", "gang", dex=30)
    session = _fight(psi, mark)
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mental_blast", "mark", _mental_blast()),
                              template=TEMPLATE, roller=_Dice((6, 6, 6)))
    payload = resolved.session.event_log[-1].result_payload
    assert (payload["hit"], payload["roll"], payload["target_number"]) == (False, 18, 14)
    assert "stun_dealt" not in payload
    assert resolved.session.combatants["mark"].state.current_stun == 40


def test_a_mental_blast_that_hits_says_so():
    psi, mark = _brainchild(), _person("mark", "gang", dex=30)
    session = _fight(psi, mark)
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mental_blast", "mark", _mental_blast()),
                              template=TEMPLATE, roller=_Dice((2, 2, 2), effect=4))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["hit"] is True and payload["stun_dealt"] == 24


def test_a_stunned_mind_is_easier_to_hit():
    """6E2 p.106: "A Stunned character's DCV and DMCV instantly drop to 1/2".
    DMCV 5 halves to 3 (6E2 p.39 rounds in the character's favour), so the
    target number goes from 14 to 16."""
    psi, mark = _brainchild(), _person("mark", "gang", dex=30)
    session = _fight(psi, mark)
    assert mental_attack_roll(session, psi, mark, _Dice((3, 3, 3))).target_number == 14
    stunned = apply_event(session, ActionResolved(
        id="hit", session_id="s", sequence=len(session.event_log) + 1,
        timestamp=session.event_log[-1].timestamp, author=make_author_engine(),
        declaration_event_id="", result_payload={
            "kind": "attack", "target_id": "mark", "status_changes": ["Stunned"]},
    ))
    assert mental_attack_roll(stunned, psi, mark, _Dice((3, 3, 3))).target_number == 16


# ── §3 Mind Control: the order, the Breakout Roll, obedience ────────────────

def test_an_order_is_in_force_but_not_obeyed_before_the_first_breakout_roll():
    """6E1 p.258: "he doesn't take any Actions under Mind Control until he
    attempts and fails his first Breakout Roll"."""
    session = _controlled("spare", extra=[_person("rando", "solo", dex=20)])
    assert [e.order for e in effects_on(session, "mark")] == ["spare"]
    assert mind_control_orders(session, "mark") == []


def test_he_breaks_out_on_his_first_phase_and_acts_freely():
    """The Darkmind example (6E1 p.152): the Breakout Roll succeeds and
    "he has his full Phase in which to act" --- psi is a target again."""
    session = _controlled("spare", extra=[_person("rando", "solo", dex=20)])
    result, menu = _marks_phase(session, (1, 1, 1))
    rolled = [e for e in result.session.event_log if e.kind == "BreakoutRolled"]
    assert len(rolled) == 1 and rolled[0].broke_free is True
    assert "psi" in _targets(menu)
    assert effects_on(result.session, "mark") == []


def test_a_failed_breakout_roll_and_spare_leaves_the_controller_alone():
    session = _controlled("spare", extra=[_person("rando", "solo", dex=20)])
    result, menu = _marks_phase(session, (6, 6, 6))
    assert [e.broke_free for e in result.session.event_log
            if e.kind == "BreakoutRolled"] == [False]
    assert "psi" not in _targets(menu)
    assert "rando" in _targets(menu)


def test_run_phase_makes_the_breakout_roll_itself():
    """At the top of his first Phase, before he acts, at +0 --- and only one."""
    session = _controlled("withdraw")
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    result = run_phase(enc, _Records(), roller=RandomRoller(seed=21))
    rolled = [e for e in result.events if e.kind == "BreakoutRolled"]
    assert result.actor_id == "mark"
    assert [(e.target_id, e.bonus) for e in rolled] == [("mark", 0)]
    assert result.events.index(rolled[0]) < next(
        i for i, e in enumerate(result.events) if e.kind == "PhaseSpent")


def test_turn_sends_him_at_his_own_side():
    """6E1 p.256: beyond EGO+20, "attack one of his allies/teammates"."""
    session = _controlled("turn", extra=[_person("pal", "gang", dex=20)])
    _, menu = _marks_phase(session, (6, 6, 6))
    assert _targets(menu) == {"pal"}


def test_withdraw_leaves_him_no_attack_on_anybody():
    """6E1 p.256: EGO+20 "could be forced to flee from the combat"."""
    session = _controlled("withdraw")
    _, menu = _marks_phase(session, (6, 6, 6))
    assert menu and {a.kind for a in menu} <= WITHDRAW_KINDS


def test_spare_is_not_offered_when_the_controller_is_his_only_enemy():
    """With nobody else to fight, "leave me alone" means "stop fighting",
    which 6E1 p.256 puts beyond EGO+10 --- so `spare` is not on the menu,
    and `turn` is not either: he has no friends here to turn on."""
    psi, mark = _brainchild(), _person("mark", "gang", dex=30)
    menu = enumerate_actions(psi, [mark])
    orders = {a.order for a in menu if a.kind == "mind_control"}
    assert orders == {"withdraw"}


def test_the_breakout_roll_follows_the_time_chart_not_every_phase():
    """6E1 p.152: after the first, "+1 after 1 Turn has passed, +2 after 1
    Minute has passed ... (The victim does not get to make a Breakout Roll
    on each of his Phases --- only when specified by the Time Chart.)\""""
    session = _controlled("withdraw")
    result, _ = _marks_phase(session, (6, 6, 6))
    session = result.session
    effect = effects_on(session, "mark")[0]
    at = lambda turn, seg: replace(session, timeline=replace(session.timeline, turn=turn, segment=seg))  # noqa: E731
    first = effect.attempts[0]
    assert breakout_due(at(first.turn, first.segment + 3), effect) is None
    assert breakout_due(at(first.turn + 1, first.segment), effect) == 1
    assert breakout_due(at(first.turn + 5, first.segment), effect) == 2


def test_an_order_given_with_room_to_spare_is_harder_to_break():
    """6E1 p.152: -1 to the Breakout Roll per 5 points over the minimum.
    12d6 of sixes is 72 against withdraw's 10 + 20 = 30: 42 over, -8."""
    session = _controlled("withdraw")
    assert effects_on(session, "mark")[0].breakout_modifier == -8
    result, _ = _marks_phase(session, (1, 1, 2))
    rolled = next(e for e in result.session.event_log if e.kind == "BreakoutRolled")
    assert rolled.target_number == 11 - 8 and rolled.broke_free is False


# ── §4 Mind Scan ────────────────────────────────────────────────────────────

def _behind_the_wall(*, telepathic: bool = False):
    psi = _brainchild(telepathic=telepathic)
    mark = _person("mark", "gang", dex=30)
    scene = _scene(wall=True, psi=(0.0, 5.0), mark=(20.0, 5.0))
    return psi, mark, _fight(psi, mark, scene=scene), scene


def test_a_mentalist_who_sees_nobody_is_offered_a_scan_not_an_attack():
    """The prod defect itself: no line of sight, and Mental Blast / Mind
    Control offered anyway."""
    psi, mark, session, scene = _behind_the_wall()
    menu = enumerate_actions(psi, [mark], has_scene=True, scene=scene)
    kinds = {a.kind for a in menu if a.target_id == "mark"}
    assert "mind_scan" in kinds
    assert not kinds & {"mental_blast", "mind_control", "telepathy"}


def test_nobody_scans_a_mind_he_can_already_see():
    psi, mark = _brainchild(), _person("mark", "gang", dex=30)
    scene = _scene(wall=False, psi=(0.0, 5.0), mark=(20.0, 5.0))
    menu = enumerate_actions(psi, [mark], has_scene=True, scene=scene)
    assert "mind_scan" not in {a.kind for a in menu}
    assert "mental_blast" in {a.kind for a in menu}


def _lock(session, psi):
    scan = next(p for p in psi.hero.powers if p.xmlid == "MINDSCAN")
    return resolve_chosen(session, session.combatants["psi"], _offer("mind_scan", "mark", scan),
                          template=TEMPLATE, roller=_Dice((1, 1, 1), effect=6)).session


def test_a_lock_lets_mental_powers_through_the_wall_and_runs_both_ways():
    psi, mark, session, scene = _behind_the_wall()
    session = _lock(session, psi)
    payload = session.event_log[-1].result_payload
    assert payload["established"] is True and payload["reached"] == "all_attacks"
    assert mind_scan_locks(session, "psi") == {"mark"}
    assert mind_scan_locks(session, "mark") == {"psi"}     # 6E1 p.265's two-way circuit
    menu = enumerate_actions(psi, [mark], has_scene=True, scene=scene,
                             mind_scan_locks=mind_scan_locks(session, "psi"))
    kinds = {a.kind for a in menu if a.target_id == "mark"}
    assert "mental_blast" in kinds and "mind_scan" not in kinds
    # An order he cannot hear is not given (6E1 p.266): no TELEPATHIC, no
    # Mind Control through the lock.
    assert "mind_control" not in kinds


def test_telepathic_mind_control_goes_through_a_lock():
    psi, mark, session, scene = _behind_the_wall(telepathic=True)
    session = _lock(session, psi)
    menu = enumerate_actions(psi, [mark], has_scene=True, scene=scene,
                             mind_scan_locks=mind_scan_locks(session, "psi"))
    assert "mind_control" in {a.kind for a in menu}


def test_breaking_out_of_a_scan_ends_the_lock():
    psi, mark, session, scene = _behind_the_wall()
    session = _lock(session, psi)
    effect = effects_on(session, "mark")[0]
    session = apply_event(session, BreakoutRolled(
        id="b", session_id="s", sequence=len(session.event_log) + 1,
        timestamp=session.event_log[-1].timestamp, author=make_author_engine(),
        target_id="mark", effect_id=effect.effect_id, roll=3, target_number=11,
        bonus=0, broke_free=True, turn=1, segment=12,
    ))
    assert mind_scan_locks(session, "psi") == frozenset()


def test_a_knocked_out_scanner_loses_his_lock():
    """Mind Scan is a Constant Power (6E1 p.263); it does not stay on in an
    unconscious man."""
    psi, mark, session, scene = _behind_the_wall()
    session = _lock(session, psi)
    out = session.combatants["psi"]
    session = replace(session, combatants={
        **session.combatants, "psi": replace(out, state=replace(out.state, current_stun=0))})
    assert mind_scan_locks(session, "mark") == frozenset()


@pytest.mark.parametrize("minds,penalty", [(1, 0), (2, -2), (10, -2), (11, -4), (100, -4), (101, -6)])
def test_the_mind_scan_table_reads_its_rows_as_upper_bounds(minds, penalty):
    """6E1 p.263: 1 mind 0, 10 minds -2, 100 minds -4, "and so forth"."""
    assert mind_scan_omcv_modifier(minds) == penalty
