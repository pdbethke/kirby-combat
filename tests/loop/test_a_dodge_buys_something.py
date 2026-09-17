"""A declared Dodge is worth +3 DCV to the man who declared it — 6E2 p.55.

`Dodge.dcv_bonus` has been correct since the reactive line shipped and had
NO production caller: a grep for it outside `actions/reactive/dodge.py`
found its own unit test and nothing else. So a fighter could spend his
Phase aborting to a Dodge -- giving up his next action for it, which is
what an Abort costs -- and the next man to shoot at him rolled against his
untouched DCV. The tactic catalogue has a whole entry (`dodge_under_fire`)
recommending a move that bought nothing.

The same shape this engine keeps paying for: a rule written at one door
(`Dodge.dcv_bonus`) and read at none of the others.

WHAT THIS IS NOT. It is not the reactive consult -- nothing here asks a
defender "do you want to Abort?" when an attack is declared at him. The
defender declares his Dodge on his own Phase, off the menu, through the
engine's existing abort machinery, and this is the attack path reading
that declaration back. See the A3 report for why the consult itself is a
harness question.
"""
from __future__ import annotations

from conftest import blast, fighter, session_of      # tests/loop/conftest.py
from kirby_dice import FakeRoller

from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

DODGE_DCV_BONUS = 3                 # 6E2 p.55
DICE = 2


def _fight():
    return session_of(
        fighter("brute", side=Side.named("villains"), dice=DICE),
        fighter("mark", side=Side.named("heroes"), dice=DICE),
    ).start()


def _attack():
    power = blast("brute-eb", dice=DICE)
    return LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary="attack",
        _attack_view=power,
    )


def _shoot(session):
    """`_attack_dice` draws to-hit 3d6, damage, Hit Location 3d6, STUN mult."""
    roller = FakeRoller([[4, 4, 4], [1] * DICE, [3, 3, 3], [1]])
    return resolve_chosen(
        session, session.combatants["brute"], _attack(),
        template=TEMPLATE, roller=roller,
    )


def _payload(resolved):
    for event in reversed(resolved.session.event_log):
        payload = getattr(event, "result_payload", None)
        if isinstance(payload, dict) and "hit" in payload:
            return payload
    raise AssertionError("no resolution event on the log")


def test_a_man_who_has_not_dodged_defends_at_his_own_dcv():
    """Guards the guard: the ordinary case must not move."""
    session = _fight()
    assert _payload(_shoot(session))["target_dcv"] == \
        int(session.combatants["mark"].dcv)


def test_a_declared_dodge_reaches_the_attack_roll():
    """The defect. The bonus was computed by a function nothing called."""
    session = _fight()
    base_dcv = int(session.combatants["mark"].dcv)
    session, _ = Dodge.declare(session, "mark")

    assert _payload(_shoot(session))["target_dcv"] == base_dcv + DODGE_DCV_BONUS


def test_a_dodge_helps_only_the_man_who_declared_it():
    """The bonus is read per combatant off the log, so the ATTACKER
    dodging does nothing for his target."""
    session = _fight()
    base_dcv = int(session.combatants["mark"].dcv)
    session, _ = Dodge.declare(session, "brute")

    assert _payload(_shoot(session))["target_dcv"] == base_dcv


def test_an_abort_to_something_other_than_a_dodge_buys_no_dcv():
    """`Dodge.dcv_bonus` reads the abort's `to_action`, so a Block is not a
    Dodge -- the +3 belongs to one maneuver and not to aborting as such."""
    from kirby_combat.actions.reactive.block import Block

    session = _fight()
    base_dcv = int(session.combatants["mark"].dcv)
    session, _ = Block.declare(session, "mark")

    assert _payload(_shoot(session))["target_dcv"] == base_dcv


def test_a_maneuver_meets_the_dodge_too():
    """6E2 p.55 says "all attacks", so a Trip at a dodging man meets the
    same +3. Read through the SAME helper the attack path uses -- a second
    copy at the maneuver door is how this engine grows a rule it enforces
    in one place and not the next."""
    session = _fight()
    base_dcv = int(session.combatants["mark"].dcv)
    session, _ = Dodge.declare(session, "mark")

    trip = LegalAction(
        action_id="trip:mark", kind="trip", target_id="mark",
        power_xmlid=None, power_name=None, summary="trip",
        _attack_view=blast("brute-eb", dice=DICE),
    )
    # A Trip does no damage, so only the to-hit, location and STUN-mult
    # dice are drawn; nobody here has ACROBATICS, so no save is rolled.
    resolved = resolve_chosen(
        session, session.combatants["brute"], trip,
        template=TEMPLATE, roller=FakeRoller([[4, 4, 4], [3, 3, 3], [1]]),
    )
    assert _payload(resolved)["target_dcv"] == base_dcv + DODGE_DCV_BONUS
