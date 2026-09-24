"""A resolver does what its offer said --- no more targets, no other OCV.

THE DEFECT THIS GUARDS. Enumeration and resolution each answer "who does
this hit, and at what": enumeration when it writes the menu, the resolver
when it rolls. Each was tested alone and the two drifted apart. A Sweep
offered against "the 2 of 3 enemies in reach" rebuilt its target list from
the whole roster, so it also struck a man 64 metres away and took every
shot at the three-target penalty instead of the two-target OCV it quoted.
A Multiple Attack rolled with no distance, so it paid no Range Modifier a
single shot at the same man pays (6E2 p.73 charges the multi-shot penalty
ON TOP of the usual modifiers, not instead of them).

Each test here takes the offer from the real `enumerate_actions`, fed the
way `run_phase` feeds it, resolves it through `resolve_chosen`, and reads
back every `AttackInput` that reached the pure resolver. The assertion is
on what was rolled, not on what the resolver meant to roll.

Found by Codex's review of 2026-09-23 (`docs/review-2026-09-23.md`),
not by this suite.
"""
from __future__ import annotations

import re
from dataclasses import replace

import pytest
from conftest import blast  # tests/loop/conftest.py
from kirby_dice import RandomRoller

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from kirby_combat.actions import recording
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import distances_from
from kirby_combat.roster import Roster
from kirby_combat.scene.scene import (
    AmbientConditions,
    Position,
    Scene,
    SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

ACTOR_AT = Position(10.0, 10.0, 0.0)


class _AlwaysLow(RandomRoller):
    """Every die shows 1, so every to-hit roll is a 3 and hits.

    A Multiple Attack or Sweep stops at its first miss (6E2 p.73), so a
    random miss on shot one would hide a target the resolver should never
    have been aiming at. Low damage also keeps the fight from ending
    mid-sequence.
    """

    def roll_dice(self, n):
        return [1] * n


def _fighter(id_: str, side: str, *, attack=None):
    return synthetic_combatant(
        id=id_, name=id_, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        side=Side.named(side), attacks=[attack] if attack else [],
    )


def _session(actor, positions: dict[str, Position], *enemies):
    scene = Scene(
        id="field", name="Field", bounds=SceneBounds(0, 0, 0, 200, 200, 20),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={actor.id: ACTOR_AT, **positions},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[actor, *enemies],
    ).start()


def _menu(session, actor_id: str):
    """The menu exactly as `run_phase` asks for it: same enemies, same
    measured distances, same scene."""
    actor = session.combatants[actor_id]
    enemies = Roster(session).enemies_of(actor)
    return enumerate_actions(
        actor, enemies, has_scene=True, scene=session.scene,
        distances=distances_from(session.scene, actor, enemies),
    )


def _offer(menu, kind: str, target_id: str | None = None):
    matches = [a for a in menu if a.kind == kind
               and (target_id is None or a.target_id == target_id)]
    assert matches, f"no {kind!r} offer on the menu: {[a.kind for a in menu]}"
    return matches[0]


def _quoted_ocv(offer) -> int:
    m = re.search(r"EVERY shot at OCV (-?\d+)", offer.summary)
    assert m, f"offer does not quote its OCV: {offer.summary!r}"
    return int(m.group(1))


@pytest.fixture
def rolled(monkeypatch):
    """Every `AttackInput` that reaches the pure resolver, in order."""
    seen: list = []
    original = recording.resolve_attack

    def spy(attack, template):
        seen.append(attack)
        return original(attack, template)

    monkeypatch.setattr(recording, "resolve_attack", spy)
    return seen


# --- Sweep: the enemies in Reach, and only them -------------------------

def _sweep_fight():
    """Two men within a metre of the actor, a third 64 metres away."""
    fist = replace(blast("brawler-fist", dice=2, range_m=0), name="Fist")
    actor = _fighter("brawler", "a", attack=fist)
    near1, near2, far = (_fighter(i, "b") for i in ("near1", "near2", "far"))
    session = _session(actor, {
        "near1": Position(11.0, 10.0, 0.0),
        "near2": Position(10.0, 11.0, 0.0),
        "far": Position(74.0, 10.0, 0.0),
    }, near1, near2, far)
    return session, _offer(_menu(session, "brawler"), "sweep")


def test_the_sweep_offer_names_only_the_enemies_in_reach():
    """The premise the other Sweep tests rest on: enumeration already
    narrows the offer. If this fails, the fixture is wrong, not the
    resolver."""
    _, offer = _sweep_fight()
    assert "the 2 of 3 enemies in reach" in offer.summary


def test_a_sweep_strikes_only_the_enemies_it_offered(rolled):
    """6E2 p.56: every blow of a Sweep is hand-to-hand, so it cannot reach
    the man 64 metres off, and the offer did not name him."""
    session, offer = _sweep_fight()
    resolve_chosen(session, session.combatants["brawler"], offer,
                   template=TEMPLATE, roller=_AlwaysLow(seed=1))
    struck = {attack.target.id for attack in rolled}
    assert "far" not in struck
    assert struck == {"near1", "near2"}


def test_a_sweep_rolls_at_the_ocv_it_quoted(rolled):
    """The offer quoted one OCV for every blow. The penalty is set by the
    number of targets, so a resolver that counts a different set of
    targets rolls at a different OCV than the chooser was shown."""
    session, offer = _sweep_fight()
    actor = session.combatants["brawler"]
    resolve_chosen(session, actor, offer,
                   template=TEMPLATE, roller=_AlwaysLow(seed=1))
    base = int(actor.combat_stats().ocv)
    assert rolled, "the Sweep rolled nothing"
    assert {base + a.ocv_modifier for a in rolled} == {_quoted_ocv(offer)}


# --- Multiple Attack: the Range Modifier still applies -------------------

def _gunfight():
    """Two men 64 metres away, well inside the blast's 100 m range."""
    actor = _fighter("gunman", "a", attack=blast("gunman-eb", dice=2))
    far1, far2 = _fighter("far1", "b"), _fighter("far2", "b")
    session = _session(actor, {
        "far1": Position(74.0, 10.0, 0.0),
        "far2": Position(10.0, 74.0, 0.0),
    }, far1, far2)
    return session, _menu(session, "gunman")


def test_a_multiple_attack_rolls_at_the_distance_a_single_shot_would(rolled):
    """A single shot at far1 is rolled at its measured distance, so it
    pays the Range Modifier. A Multiple Attack shot at the same man must
    carry the same distance, or the maneuver's own -2 is cheaper than a
    single shot at long range, which is the reverse of the book."""
    session, menu = _gunfight()
    actor = session.combatants["gunman"]

    resolve_chosen(session, actor, _offer(menu, "attack", "far1"),
                   template=TEMPLATE, roller=_AlwaysLow(seed=1))
    single = [a.distance_m for a in rolled if a.target.id == "far1"]
    assert single and single[0] is not None, (
        "premise: a single shot is rolled at a distance")
    rolled.clear()

    resolve_chosen(session, actor, _offer(menu, "multiple_attack"),
                   template=TEMPLATE, roller=_AlwaysLow(seed=1))
    multi = [a.distance_m for a in rolled if a.target.id == "far1"]
    assert multi == single


def test_a_multiple_attack_rolls_at_the_ocv_it_quoted(rolled):
    """The same contract as the Sweep: the OCV on the menu is the OCV
    each shot is rolled at. Range is a separate modifier and stays out of
    `ocv_modifier`, so this holds at any distance."""
    session, menu = _gunfight()
    actor = session.combatants["gunman"]
    offer = _offer(menu, "multiple_attack")
    resolve_chosen(session, actor, offer,
                   template=TEMPLATE, roller=_AlwaysLow(seed=1))
    base = int(actor.combat_stats().ocv)
    assert rolled, "the Multiple Attack rolled nothing"
    assert {base + a.ocv_modifier for a in rolled} == {_quoted_ocv(offer)}
