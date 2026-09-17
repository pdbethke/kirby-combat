"""A Drained CV reaches the Attack Roll — 6E1 p.139.

`adjustments.py` closed the Adjustment chain for exactly two consumers and
said so in its own docstring: "The CV path (`effective_ocv_for` and
friends) and the Stunning check are wired below because they are what
decides a fight." Only one of those two was ever read by a fight.
`adjusted_con` has a live caller in `actions/recording.py`;
`effective_ocv_for` and `effective_dcv_for` have none anywhere in the
package. So a Drain that took four points off a man's OCV changed his
Stunning threshold and nothing else, and he shot as straight as ever.

The attack path asks `net_adjustment` directly, which is the seam
`recording.py` already uses for CON: the base comes from the build and the
session supplies the modifier. It rides in on the `ocv_modifier` /
`dcv_modifier` channel that already exists rather than a new field.

DEX IS NOT A CV IN 6E, and no test here pretends otherwise. `adjustments.py`
names the four CV characteristics explicitly -- "OCV and DCV are their own
characteristics in 6E and not abbreviations of something else" -- so a DEX
Drain moves initiative and leaves the Attack Roll alone. The kirby-api
driver carried a `_dex_drain_cv_penalty` on both sides of every attack; it
is 5E's DEX/3, has no 6E page, and is not carried here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from conftest import blast, fighter, session_of      # tests/loop/conftest.py
from kirby_dice import FakeRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import AdjustmentApplied, make_author_engine
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
DICE = 2


def _fight():
    return session_of(
        fighter("brute", side=Side.named("villains"), dice=DICE),
        fighter("mark", side=Side.named("heroes"), dice=DICE),
    ).start()


def _adjust(session, target: str, stat: str, delta: int):
    return apply_event(session, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id=target, stat=stat, delta=delta, fade_rate_per_turn=5,
    ))


def _shoot(session):
    power = blast("brute-eb", dice=DICE)
    action = LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary="attack",
        _attack_view=power,
    )
    roller = FakeRoller([[4, 4, 4], [1] * DICE, [3, 3, 3], [1]])
    resolved = resolve_chosen(
        session, session.combatants["brute"], action,
        template=TEMPLATE, roller=roller,
    )
    for event in reversed(resolved.session.event_log):
        payload = getattr(event, "result_payload", None)
        if isinstance(payload, dict) and "hit" in payload:
            return payload
    raise AssertionError("no resolution event on the log")


def test_an_undrained_fight_is_unchanged():
    """Guards the guard."""
    session = _fight()
    payload = _shoot(session)
    assert payload["effective_ocv"] == int(session.combatants["brute"].ocv)
    assert payload["target_dcv"] == int(session.combatants["mark"].dcv)


def test_draining_the_attackers_ocv_lowers_what_he_rolls_with():
    """The defect: the Drain was folded, faded and recorded, and the
    Attack Roll never read it."""
    session = _fight()
    base = int(session.combatants["brute"].ocv)
    session = _adjust(session, "brute", "OCV", -4)
    assert _shoot(session)["effective_ocv"] == base - 4


def test_aiding_the_attackers_ocv_raises_it():
    """The same seam, signed the other way -- an Aid is not a special case
    (6E1 p.133)."""
    session = _fight()
    base = int(session.combatants["brute"].ocv)
    session = _adjust(session, "brute", "OCV", +3)
    assert _shoot(session)["effective_ocv"] == base + 3


def test_draining_the_targets_dcv_makes_him_easier_to_hit():
    session = _fight()
    base = int(session.combatants["mark"].dcv)
    session = _adjust(session, "mark", "DCV", -3)
    assert _shoot(session)["target_dcv"] == base - 3


def test_a_drained_dex_does_not_touch_either_cv():
    """6E made OCV and DCV characteristics in their own right. A DEX Drain
    is felt in the order of Phases, not in the Attack Roll, and the driver
    that charged it to both sides' CV was applying a 5E rule."""
    session = _fight()
    base_ocv = int(session.combatants["brute"].ocv)
    base_dcv = int(session.combatants["mark"].dcv)
    session = _adjust(_adjust(session, "brute", "DEX", -9), "mark", "DEX", -9)
    payload = _shoot(session)
    assert payload["effective_ocv"] == base_ocv
    assert payload["target_dcv"] == base_dcv


def test_a_drain_cannot_take_a_cv_below_zero():
    """6E1 p.139: a characteristic does not go negative, and a negative CV
    would poison every number derived from it. `effective_characteristic`
    owns that floor; the attack path does not grow a second one."""
    session = _fight()
    session = _adjust(session, "brute", "OCV", -50)
    assert _shoot(session)["effective_ocv"] == 0


def test_a_drain_is_applied_exactly_once():
    """ONE FOLD. For a week there were two: `cv_modifiers.effective_ocv_for`
    (which applies the Adjustment to the BASE, before any factor, per 6E1
    p.133/p.139) and a second `resolvers._adjustment_cv_delta` added on top.
    Only one of them was ever called, so the double never fired -- but two
    folds for one rule is how it fires later. `_adjustment_cv_delta` is
    deleted and the attack path reads `effective_*_for`.

    Asserted as a NUMBER, not a direction: a -4 Drain that lands twice
    still lowers the OCV, and a test asserting only "it went down" would
    have passed either way."""
    session = _fight()
    base = int(session.combatants["brute"].ocv)
    session = _adjust(session, "brute", "OCV", -4)
    rolled = _shoot(session)["effective_ocv"]
    assert rolled == base - 4
    assert rolled != base - 8


def test_the_second_fold_is_gone():
    """Names the deleted helper, so re-adding one has to delete this line
    too rather than quietly restoring a second home for the rule."""
    from kirby_combat.loop import resolvers

    assert not hasattr(resolvers, "_adjustment_cv_delta")
