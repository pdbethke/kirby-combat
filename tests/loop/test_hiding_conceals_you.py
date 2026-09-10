"""A successful Hide has to make you harder to see.

`_resolve_hide` runs the real contest --- Stealth against every watcher's
PER, per observer, because being unseen is not a property of the hider ---
and writes the losers into the event payload as ``unseen_by``. NOTHING
has ever read that list back. The only references to it in the whole
engine are the three lines that build it.

So hiding was a Phase spent to produce a log entry. The enumeration
perception gate takes a ``concealment`` map and `loop/run.py` never
passed one; `is_surprised` takes ``attacker_hidden`` and no caller
supplied it. The information existed, was correct, and reached nobody ---
which also meant 6E2 p.52's Surprised could never fire from the one
manoeuvre in the game designed to cause it.

Invisibility is read off the BUILD (`perception.invisibility_groups`) and
so has always been visible to `perceive`; Hide is a fact about the FIGHT
and only the log knows it.
"""
from __future__ import annotations

import pytest

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.concealment import concealment_for
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _session(watchers=("mark", "other")):
    return CombatSession.create(
        id="h", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=5),
        combatants=[fighter("sneak", side=Side.named("a"), dex=30)]
        + [fighter(w, side=Side.named("b"), dex=8) for w in watchers],
    ).start()


@pytest.fixture
def plain_session():
    return _session()


@pytest.fixture
def hidden_session():
    """One Hide, resolved, with a DEX 30 sneak against two dull watchers.

    Returns the session plus who ended up unable to see him and who did.
    Seeded, so which watchers lose him is fixed -- but the test reads the
    answer off the log rather than asserting a particular pair, because
    the contest is the engine's and not this fixture's to predict.
    """
    session = _session()
    resolved = resolve_chosen(
        session, session.combatants["sneak"],
        LegalAction(action_id="hide", kind="hide", target_id=None,
                    power_xmlid=None, power_name=None, summary="hide"),
        template=TEMPLATE, roller=RandomRoller(seed=5),
    )
    unseen = set(resolved.session.event_log[-1].result_payload["unseen_by"])
    watchers = {"mark", "other"}
    blind = next(iter(unseen), None)
    seeing = next(iter(watchers - unseen), None)
    if blind is None:
        pytest.skip("this seed hid from nobody; the contest is not under test")
    return resolved.session, "sneak", blind, seeing


def test_a_hider_is_concealed_from_whoever_lost_him(hidden_session):
    session, hider_id, blind_id, seeing_id = hidden_session
    seen_by_the_blind = concealment_for(session, observer_id=blind_id)
    assert seen_by_the_blind.get(hider_id, (False, False))[1] is True


def test_a_hider_is_not_concealed_from_whoever_still_sees_him(hidden_session):
    """Pairwise, not global. One enemy losing you does not blind the rest,
    which is the whole reason `_resolve_hide` contests per observer."""
    session, hider_id, blind_id, seeing_id = hidden_session
    if seeing_id is None:
        return                      # this seed hid from everyone; nothing to assert
    seen_by_the_watcher = concealment_for(session, observer_id=seeing_id)
    assert seen_by_the_watcher.get(hider_id, (False, False))[1] is False


def test_nobody_is_concealed_in_a_fight_with_no_hiding(plain_session):
    assert concealment_for(plain_session, observer_id="mark") == {}


def test_the_driver_tells_enumeration_who_cannot_be_seen(hidden_session):
    """`enumerate_actions` has always taken a `concealment` map and
    `loop/run.py` never passed one, so the perception gate ran blind to
    hiding: a man who had just vanished stayed on everybody's list of
    things to shoot, which is exactly the metagaming the perception line
    was built to stop. A Phase spent Hiding bought a log entry and
    nothing else.

    Spying on the call is the honest test of THAT claim -- what
    enumeration then does with the map is its own tested behaviour."""
    session, hider_id, blind_id, _seeing = hidden_session
    import kirby_combat.loop.run as run

    passed: dict = {}
    original = run.enumerate_actions

    def spy(actor, enemies, **kwargs):
        if getattr(actor, "id", None) == blind_id:
            passed.update(kwargs.get("concealment") or {})
        return original(actor, enemies, **kwargs)

    # Give the Segment an acting order. The fixture resolved its Hide
    # through `resolve_chosen` directly, so no order has been built and
    # `run_phase` would report "no unspent slot in this Segment".
    from kirby_combat.encounter import Encounter

    _ties = RandomRoller(seed=11)
    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session],
                          template=TEMPLATE).run_segment(
        roller=lambda: _ties.roll_dice(3))
    session = encounter.sessions[0]

    run.enumerate_actions = spy
    try:
        # The watcher is not first in the order, so spend Phases until he
        # comes up. `actor_id is None` means the Segment is exhausted.
        for _ in range(8):
            result = run.run_phase(session, _First(), template=TEMPLATE,
                                   roller=RandomRoller(seed=5),
                                   on_unresolvable="skip")
            session = result.session
            if result.actor_id in (None, blind_id):
                break
    finally:
        run.enumerate_actions = original

    assert passed or result.actor_id == blind_id, (
        "the watcher never got a Phase, so nothing was proved")

    assert passed.get(hider_id, (False, False))[1] is True, (
        f"{blind_id} lost track of {hider_id}, and enumeration was told "
        f"{passed or 'nothing at all'}"
    )


class _First:
    """Takes whatever is offered first; this test is about the menu, not
    the choice."""

    def choose(self, situation):
        return situation.menu[0].action_id
