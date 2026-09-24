"""The template and roller the caller passes are the ones every action uses.

THE DEFECT THIS GUARDS. A fight carries its rules template and its dice
twice: once on the `CombatSession`, and once as the arguments the caller
hands `resolve_chosen`. Every fixture in this suite set the two to the same
objects, so a resolver reading the session's copy instead of the one it
was given still passed. Codex's review of 2026-09-23 found both:

- Sweep, Multiple Attack, Rapid Fire, move-and-strike and the hand-to-hand
  maneuvers resolved with `session.template`, so a campaign's rules
  override applied to a plain attack and not to them. With a killing STUN
  multiplier of 5 passed in, a plain attack did 28 STUN and the first
  Multiple Attack shot did 4.
- The Presence Attack a violent blow provokes (6E2 p.138) rolled with
  `session.dice_roller`, so a seeded fight stopped being seeded, and a
  session with no roller raised.

The cure for "the two copies always match" is a test where they do not.
Here the session holds a DIFFERENT template and a roller that fails the
test if anything rolls it, and every kind the menu offers is resolved
against it.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import blast  # tests/loop/conftest.py
from kirby_dice import RandomRoller
from test_resolution_keeps_the_offer import (
    TEMPLATE,
    _fighter,
    _menu,
    _session,
)

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from kirby_combat.actions import recording
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.scene import Position


class _Hits(RandomRoller):
    """Every die shows 5. A to-hit total of 15 hits this OCV 20 brute
    against DCV 5 even at a Multiple Attack's penalty, and twelve dice of
    5s (Blast, Fist, or STR 60) put BODY through PD 4, which is what
    provokes the witnesses' Presence reaction."""

    def roll_dice(self, n):
        return [5] * n


class _NotThisOne(RandomRoller):
    """The session's roller. Anything that rolls it has ignored the roller
    the caller passed."""

    def roll_dice(self, n):
        raise AssertionError(
            f"rolled {n} dice on session.dice_roller instead of the "
            f"roller passed to resolve_chosen")


#: Every kind the menu below offers, so a kind that stops being offered
#: fails loudly rather than dropping out of the check.
KINDS = [
    "attack", "block", "disarm", "disengage", "dodge", "grab", "haymaker",
    "hold", "move", "move_by", "move_strike", "move_through",
    "multiple_attack", "presence_attack", "presence_attack_group", "push",
    "rapid_fire", "set", "strike", "sweep", "trip",
]


def _fight(*, session_template, session_roller):
    """A brute with a Blast and a Fist, two enemies in Reach, and a
    witness close enough to see the blow land."""
    eb = blast("brute-eb", dice=12)
    fist = replace(blast("brute-fist", dice=12, range_m=0), name="Fist")
    actor = _fighter("brute", "a", attack=eb, ocv=20, str_=60)
    actor.attacks.append(fist)
    session = _session(
        actor,
        {"mark": Position(11.0, 10.0, 0.0),
         "mark2": Position(10.0, 11.0, 0.0),
         "witness": Position(15.0, 10.0, 0.0)},
        _fighter("mark", "b"), _fighter("mark2", "b"),
        _fighter("witness", "c"),
    )
    return replace(session, template=session_template,
                   dice_roller=session_roller)


def _first_offer(session, kind):
    offers = [a for a in _menu(session, "brute") if a.kind == kind]
    assert offers, f"premise: the menu no longer offers {kind!r}"
    return offers[0]


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_rolls_with_the_callers_roller(kind):
    session = _fight(session_template=TEMPLATE,
                     session_roller=_NotThisOne(seed=1))
    resolve_chosen(session, session.combatants["brute"],
                   _first_offer(session, kind),
                   template=TEMPLATE, roller=_Hits(seed=1))


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_resolves_under_the_callers_template(kind, monkeypatch):
    """Every attack that reaches the pure resolver carries the template
    the caller passed, never the session's own."""
    passed = replace(TEMPLATE)
    session = _fight(session_template=TEMPLATE,
                     session_roller=RandomRoller(seed=1))
    assert passed is not session.template

    used: list = []
    original = recording.resolve_attack

    def spy(attack, template):
        used.append(template)
        return original(attack, template)

    monkeypatch.setattr(recording, "resolve_attack", spy)
    resolve_chosen(session, session.combatants["brute"],
                   _first_offer(session, kind),
                   template=passed, roller=_Hits(seed=1))
    assert all(t is passed for t in used), (
        f"{kind} resolved {sum(t is not passed for t in used)} of "
        f"{len(used)} attacks under the session's template")
