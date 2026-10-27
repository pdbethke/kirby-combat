"""Who last made an attack on a man --- read off the record.

A player's Held Action order can name its target as "whoever attacks Lady
Blue". The engine is the one reader of the record (`threat.harm_witnessed`
joins `ActionDeclared` to `ActionResolved` the same way), so the answer is
here: the last combatant whose attack roll was made against her.
"""
from __future__ import annotations

from conftest import encounter_of, fighter  # tests/loop/conftest.py
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.threat import last_attacker_of
from kirby_dice import RandomRoller

HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


class ShootAt:
    """Each man on his own Phase shoots the named target; nobody Aborts."""

    def __init__(self, targets):
        self.targets = targets

    def choose(self, situation):
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        want = self.targets.get(situation.actor.id)
        for offer in situation.menu:
            if offer.kind == "attack" and offer.target_id == want:
                return offer.action_id
        return situation.menu[0].action_id


def test_nobody_has_attacked_her_yet():
    enc = encounter_of(fighter("blue", side=HEROES), fighter("ogre", side=VILLAINS))
    assert last_attacker_of(enc.sessions[0], "blue") is None


def test_the_man_who_shot_her_is_named():
    enc = encounter_of(fighter("ogre", side=VILLAINS, dex=30),
                       fighter("blue", side=HEROES, dex=10))
    result = run_phase(enc, ShootAt({"ogre": "blue"}), roller=RandomRoller(seed=3),
                       on_unresolvable="raise")
    assert result.actor_id == "ogre"
    assert last_attacker_of(result.session, "blue") == "ogre"
    # She attacked nobody, so nobody is named for him.
    assert last_attacker_of(result.session, "ogre") is None


def test_the_latest_attacker_is_named():
    enc = encounter_of(fighter("ogre", side=VILLAINS, dex=30),
                       fighter("viper", side=VILLAINS, dex=20),
                       fighter("blue", side=HEROES, dex=10))
    chooser = ShootAt({"ogre": "blue", "viper": "blue"})
    first = run_phase(enc, chooser, roller=RandomRoller(seed=3), on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=RandomRoller(seed=4),
                       on_unresolvable="raise")
    assert [first.actor_id, second.actor_id] == ["ogre", "viper"]
    assert last_attacker_of(second.session, "blue") == "viper"
