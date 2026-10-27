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


# ── perception governs it ────────────────────────────────────────────────────
#
# Peter's standing requirement: perception GOVERNS combat, and a fighter may
# not act on what he could not perceive (anti-metagaming). "Whoever attacks
# Lady Blue" is therefore the last attacker of Lady Blue THAT HE CAN
# PERCEIVE, judged with the engine's own door (`concealment.perceives`,
# with the menu's Mind Scan locks) from where he stands. If the man who
# last attacked her is imperceptible to him, the answer is None --- never
# an earlier attacker he happened to see.

from kirby_combat.scene.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.encounter import Encounter
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_combat.threat import last_attacker_perceived


class _Invisibility:
    xmlid = "INVISIBILITY"
    name = alias = "Invisibility"
    id = "inv"
    option_id = None
    assigned_adders: list = []
    assigned_modifiers: list = []
    sub_powers: list = []
    levels = 0


def _field(*people):
    spots = {"blue": (0, 0, 0), "h": (6, 0, 0), "ogre": (20, 0, 0), "viper": (20, 10, 0)}
    scene = Scene(
        id="field", name="field", bounds=SceneBounds(-50, -50, 0, 80, 80, 20),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={p.id: Position(*spots[p.id]) for p in people},
    )
    session = CombatSession.create(
        id="s", combatants=list(people), scene=scene,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=3),
    ).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


def _slow_ogre():
    """The Invisible Ogre at DEX 20, so a DEX 30 man acts before him."""
    ogre = fighter("ogre", side=VILLAINS, dex=20)
    ogre.hero.powers.append(_Invisibility())
    return ogre


def _ogre(invisible):
    ogre = fighter("ogre", side=VILLAINS, dex=30)
    if invisible:
        ogre.hero.powers.append(_Invisibility())
    return ogre


def test_a_visible_attacker_is_named_for_the_man_who_sees_him():
    enc = _field(_ogre(False), fighter("blue", side=HEROES, dex=10),
                 fighter("h", side=HEROES, dex=5))
    result = run_phase(enc, ShootAt({"ogre": "blue"}), roller=RandomRoller(seed=3),
                       on_unresolvable="raise")
    assert last_attacker_perceived(result.session, "blue", observer_id="h",
                                   roller=RandomRoller(seed=1)) == "ogre"


def test_an_invisible_attacker_is_named_for_nobody_who_cannot_see_him():
    enc = _field(_ogre(True), fighter("blue", side=HEROES, dex=10),
                 fighter("h", side=HEROES, dex=5))
    result = run_phase(enc, ShootAt({"ogre": "blue"}), roller=RandomRoller(seed=3),
                       on_unresolvable="raise")
    # The record knows who it was ...
    assert last_attacker_of(result.session, "blue") == "ogre"
    # ... and h, who cannot perceive him, is told nobody.
    assert last_attacker_perceived(result.session, "blue", observer_id="h",
                                   roller=RandomRoller(seed=1)) is None


def test_no_fallback_to_an_earlier_attacker_he_did_see():
    """Viper (visible, DEX 30) shoots Lady Blue, then the Invisible Ogre
    (DEX 20). The last attacker is Ogre, whom h cannot perceive: the answer
    is None, not Viper."""
    viper = fighter("viper", side=VILLAINS, dex=30)
    enc = _field(viper, _slow_ogre(), fighter("blue", side=HEROES, dex=10),
                 fighter("h", side=HEROES, dex=5))
    chooser = ShootAt({"ogre": "blue", "viper": "blue"})
    first = run_phase(enc, chooser, roller=RandomRoller(seed=3), on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=RandomRoller(seed=4),
                       on_unresolvable="raise")
    assert [first.actor_id, second.actor_id] == ["viper", "ogre"]
    assert last_attacker_of(second.session, "blue") == "ogre"
    assert last_attacker_perceived(second.session, "blue", observer_id="h",
                                   roller=RandomRoller(seed=1)) is None
