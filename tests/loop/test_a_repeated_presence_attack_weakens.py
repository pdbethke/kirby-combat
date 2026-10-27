"""Shouting at the same man again is worth less each time --- 6E2 p.140.

"Don't overuse Presence Attacks - repeated ones against the same targets
are less effective. Each time a character repeats a Presence Attack, he
gets -1d6 of effect (-1d6 on the second attack, -2d6 on the third attack,
and so forth)."

Found in kirby-app's 0.22.0 demo recording: GORGON (PRE 25) made a Presence
Attack at Drago in all eight of his Phases, and every one rolled 4d6 (PRE/5
= 5, -1d6 in combat). The eighth should have rolled none. Each roll fell
short of Drago's PRE 20, so "no effect" was right each time; the dice were
what was wrong.

And when the dice are gone the shout is gone from the menu: a 0d6 Presence
Attack can do nothing to anybody (6E2 p.139 needs a total of at least the
target's PRE), so offering it is a free action that buys nothing, which a
chooser can take every Phase for ever.
"""
from __future__ import annotations

from conftest import blast  # tests/loop/conftest.py
from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.loop.run import run_phase
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate


class Ones:
    def roll_dice(self, n: int) -> list[int]:
        return [1] * n


def _man(id: str, side: str, *, pre: int, dex: int = 20):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=6, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=18, pre=pre, rec=6,
        pd=40, ed=40, rpd=40, red=40, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        side=Side.named(side), attacks=[blast(f"{id}-eb", dice=1)],
    )


def _encounter(*men) -> Encounter:
    session = CombatSession.create(
        id="s", combatants=list(men), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


class Shouts:
    """Takes a Presence Attack whenever one is offered --- the single kind
    if ``group`` is False --- and otherwise attacks. Records each Phase menu."""

    def __init__(self, *, group: bool = False) -> None:
        self.kind = "presence_attack_group" if group else "presence_attack"
        self.menus: list[tuple[str, list[str]]] = []

    def choose(self, situation) -> str:
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.menus.append((situation.actor.id,
                           [a.action_id for a in situation.menu]))
        for wanted in (self.kind, "attack"):
            for offer in situation.menu:
                if offer.kind == wanted:
                    return offer.action_id
        return situation.ordered_menu[0].action_id


def _presence_results(encounter, actor_id="tom"):
    return [e.result_payload for e in encounter.sessions[0].event_log
            if e.kind == "ActionResolved"
            and e.author.id == actor_id
            and (e.result_payload or {}).get("kind", "").startswith("presence_attack")]


def _run(enc, chooser, phases):
    for _ in range(phases):
        enc = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise").encounter
    return enc


def test_each_repeat_at_the_same_man_rolls_a_die_fewer():
    """PRE 30: 6d6, -1d6 in combat = 5d6; then 4d6, then 3d6 (6E2 p.140)."""
    enc = _encounter(_man("tom", "a", pre=30, dex=30), _man("virgil", "b", pre=15))
    enc = _run(enc, Shouts(), 12)
    dice = [p["dice"] for p in _presence_results(enc)]
    assert dice[:3] == [5, 4, 3], dice


def test_the_repeat_is_counted_per_target():
    """A shout at a man he has not shouted at yet is not a repeat. One
    group roll is judged on each target's own dice: Virgil heard the
    single shout, Wyatt did not."""
    enc = _encounter(_man("tom", "a", pre=30, dex=30),
                     _man("virgil", "b", pre=15), _man("wyatt", "b", pre=15))
    enc = run_phase(enc, Shouts(), roller=Ones(), on_unresolvable="raise").encounter
    first = _presence_results(enc)
    assert len(first) == 1 and first[0]["dice"] == 5
    enc = _run(enc, Shouts(), 1)                     # spends the Phase
    enc = _run(enc, Shouts(group=True), 6)
    group = next(p for p in _presence_results(enc)
                 if p["kind"] == "presence_attack_group")
    shouted_at = first[0]["target_id"]
    other = "wyatt" if shouted_at == "virgil" else "virgil"
    assert group["targets"][shouted_at]["dice"] == 4
    assert group["targets"][other]["dice"] == 5


def test_a_shout_with_no_dice_left_is_not_offered():
    """PRE 10: 2d6 -1d6 = 1d6, then nothing. The second Phase's menu holds
    no Presence Attack at all, so he must act."""
    enc = _encounter(_man("tom", "a", pre=10, dex=30), _man("virgil", "b", pre=15))
    chooser = Shouts()
    enc = _run(enc, chooser, 12)
    dice = [p["dice"] for p in _presence_results(enc)]
    assert dice == [1], dice
    tom_menus = [m for who, m in chooser.menus if who == "tom"]
    assert any(a.startswith("presence_attack") for a in tom_menus[0])
    later = [m for m in tom_menus[2:]]
    assert later and not any(a.startswith("presence_attack")
                             for m in later for a in m)


def test_shouting_never_takes_the_whole_phase():
    """6E2 p.25: a Presence Attack takes No Time, and is IN ADDITION to his
    action. A chooser that shouts whenever it may still spends every Phase
    on something else: one Presence Attack, then a real action, every
    Phase, until the shout runs out of dice."""
    enc = _encounter(_man("tom", "a", pre=30, dex=30), _man("virgil", "b", pre=15))
    enc = _run(enc, Shouts(), 16)
    log = enc.sessions[0].event_log
    spent = [e for e in log if e.kind == "PhaseSpent" and e.combatant_id == "tom"]
    declared = [e.action_type for e in log
                if e.kind == "ActionDeclared" and e.combatant_id == "tom"]
    assert spent, "he spent Phases"
    real = [k for k in declared if not k.startswith("presence_attack")]
    assert len(real) == len(spent), (declared, len(spent))
