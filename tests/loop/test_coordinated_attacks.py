"""A coordinated strike is made WITH an attack (6E2 p.46-47, p.51).

"To Coordinate attacks, the characters must attack on the same DEX on the
same Phase (the attacks are considered to occur simultaneously)." The join
was an Attack Action, which ends the Phase (6E2 p.20), so a man who joined
never made the attack he joined with: the pool `coordination.pooled_stun`
sums was always empty, and the offer was a Teamwork roll for nothing. On
prod the model seat never chose it (fight a7efcb02, 2026-10-31: 0 of 71).

RULING, stated: the Teamwork roll is a Skill Roll, and "making most ... Skill
Rolls" is a Half Phase Action (6E2 p.20), so joining leaves him the attack.

THE MULTIPLE ATTACKER BONUS (6E2 p.51, optional, a template switch): "If the
attackers successfully Coordinate, the defender suffers a -1 DCV for every
attacker after the first, down to a minimum of 1/2 DCV ... The DCV penalty
applies only against those opponents who Coordinate their attacks."
Defense Maneuver II "eliminates Multiple Attacker Bonuses as to attackers
the character can perceive", III to all of them (6E1 p.76).

RULING, stated: the book's attacks are simultaneous and this loop's are
not, so the bonus counts the attackers who have joined SO FAR this Segment.
The first to swing gets nothing from the men who join after him; a horde's
fifth man swings at -4.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.action_time import ActionTime, time_of
from kirby_combat.coordination import multiple_attacker_dcv_delta
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import (
    CINEMATIC_SUPERHEROIC, RAW_HEROIC, RAW_SUPERHEROIC, CombatTemplate,
)
from kirby_dice import FakeRoller, RandomRoller

GANG = CombatTemplate.by_name("6e-superheroic-cinematic-gang")


class _Skill:
    def __init__(self, xmlid: str, option_id: str = "") -> None:
        self.xmlid = xmlid
        self.option_id = option_id


def _session(template=GANG, *, horde=4, defense_maneuver: str | None = None):
    mark = fighter("mark", side=Side.named("villains"), dex=10)
    mark.hero.skills = ([_Skill("DEFENSE_MANEUVER", defense_maneuver)]
                        if defense_maneuver else [])
    men = [fighter(f"m{i}", side=Side.named("horde"), dex=20 - i)
           for i in range(horde)]
    return CombatSession.create(
        id="s", scene=None, template=template, dice_roller=RandomRoller(seed=2),
        combatants=[*men, mark],
    ).start()


def _join(session, who: str):
    action = LegalAction(action_id="coordinate:mark", kind="coordinate",
                         target_id="mark", power_xmlid=None, power_name=None,
                         summary="coordinate")
    return resolve_chosen(session, session.combatants[who], action,
                          template=session.template,
                          roller=FakeRoller([[1, 1, 1]])).session


def _joined(session, *who):
    for w in who:
        session = _join(session, w)
    return session


# -- the join leaves him his attack -----------------------------------------


def test_joining_is_a_half_phase_skill_roll():
    join = LegalAction(action_id="coordinate:mark", kind="coordinate",
                       target_id="mark", power_xmlid=None, power_name=None,
                       summary="coordinate")
    assert time_of(join) is ActionTime.HALF


class JoinsThenShoots:
    def __init__(self):
        self.steps = []

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None) is not None:
            return situation.menu[0].action_id
        kinds = {a.kind: a.action_id for a in situation.menu}
        self.steps.append(sorted(kinds))
        for a in situation.menu:
            if a.kind == "coordinate" and a.target_id == "mark":
                return a.action_id
        for a in situation.menu:
            if a.kind == "attack" and a.target_id == "mark":
                return a.action_id
        return situation.menu[0].action_id


def test_a_man_who_joins_makes_the_attack_he_joined_with():
    session = _session(horde=2)
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    seat = JoinsThenShoots()
    first = run_phase(enc, seat, roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert first.kind == "coordinate"
    assert not [e for e in first.events if e.kind == "PhaseSpent"]

    again = Encounter(id="e", turn=first.session.timeline.turn,
                      segment=first.session.timeline.segment,
                      sessions=[first.session])
    second = run_phase(again, seat, roller=RandomRoller(seed=4), on_unresolvable="raise")
    assert second.actor_id == first.actor_id
    assert second.kind == "attack"
    # And he is not asked to join twice for one strike.
    assert "coordinate" not in seat.steps[1]


# -- the Multiple Attacker Bonus --------------------------------------------


def test_each_attacker_after_the_first_is_minus_one_dcv():
    session = _joined(_session(), "m0", "m1", "m2")
    assert multiple_attacker_dcv_delta(session, "m0", "mark", dcv=8) == -2
    assert multiple_attacker_dcv_delta(session, "m2", "mark", dcv=8) == -2


def test_one_man_alone_has_no_bonus():
    session = _joined(_session(), "m0")
    assert multiple_attacker_dcv_delta(session, "m0", "mark", dcv=8) == 0


def test_only_against_those_who_coordinate():
    session = _joined(_session(), "m0", "m1", "m2")
    assert multiple_attacker_dcv_delta(session, "m3", "mark", dcv=8) == 0


def test_never_below_half_dcv():
    """"down to a minimum of 1/2 DCV": four men, DCV 5, half is 3 (6E1
    p.14 rounds in the defender's favour), so -2 and not -3."""
    session = _joined(_session(), "m0", "m1", "m2", "m3")
    assert multiple_attacker_dcv_delta(session, "m3", "mark", dcv=5) == -2


def test_it_is_an_optional_rule():
    for template in (RAW_SUPERHEROIC, RAW_HEROIC, CINEMATIC_SUPERHEROIC):
        assert template.use_multiple_attacker_bonus is False
        session = _joined(_session(template), "m0", "m1", "m2")
        assert multiple_attacker_dcv_delta(session, "m2", "mark", dcv=8) == 0


def test_the_gang_templates_are_cinematic_plus_the_bonus():
    for gang, cinematic in (("6e-superheroic-cinematic-gang", "6e-superheroic-cinematic"),
                            ("6e-heroic-cinematic-gang", "6e-heroic-cinematic")):
        g, c = CombatTemplate.by_name(gang), CombatTemplate.by_name(cinematic)
        assert g.use_multiple_attacker_bonus is True
        assert replace(g, name=c.name, use_multiple_attacker_bonus=False) == c


def test_defense_maneuver_two_spares_him():
    session = _joined(_session(defense_maneuver="TWO"), "m0", "m1", "m2")
    assert multiple_attacker_dcv_delta(session, "m2", "mark", dcv=8) == 0


def test_defense_maneuver_one_does_not():
    """Level I only stops attacks "from behind"."""
    session = _joined(_session(defense_maneuver="ONE"), "m0", "m1", "m2")
    assert multiple_attacker_dcv_delta(session, "m2", "mark", dcv=8) == -2


def test_the_bonus_reaches_the_attack_roll():
    """The one door every attack takes, `_fold_session_cvs`."""
    from kirby_combat.actions.recording import _fold_session_cvs
    from kirby_combat.models import AttackInput, DiceValues

    session = _joined(_session(), "m0", "m1", "m2")
    m2, mark = session.combatants["m2"], session.combatants["mark"]
    power = m2.attacks[0]
    attack = AttackInput(attacker=m2, target=mark, power=power, distance_m=None,
                         aim=None, dice=DiceValues(to_hit=[3, 3, 3]))
    plain = _fold_session_cvs(_joined(_session(RAW_SUPERHEROIC), "m0", "m1", "m2"),
                              replace(attack))
    ganged = _fold_session_cvs(session, attack)
    assert ganged.dcv_modifier == plain.dcv_modifier - 2
