"""A power bought with an Activation Roll can fail to go off — 6E1 p.375.

Activation Roll is a Limitation: the power works only when its owner makes
a 3d6 roll against the number he bought (8- for -2, 11- for -1, 14- for
-1/2, 15- for -1/4). It is one of the commonest Limitations in any bestiary
and this engine did not model it at all --- `AttackPower` carried no field
for it, `hero_view` did not parse it, and nothing rolled it. So every
character who had taken points off a power for an Activation Roll fired it
at will, every Phase, and kept the discount.

NONE IS NOT ZERO. A power with no Activation Roll carries `None`, not 0:
"never fails" and "fails on anything above zero" must never be the same
answer, and a default of 0 would have made every attack in the engine
impossible to activate.

The failure is RECORDED, not swallowed. The payload says the power did not
go off and what it rolled against, because an attack that vanished with no
row on the log is indistinguishable from one that was never declared -- to
a reader, to a narrator, and to anything learning from the fight.
"""
from __future__ import annotations

from conftest import fighter, session_of            # tests/loop/conftest.py
from kirby_dice import FakeRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
DICE = 2
ACTIVATION = 11                       # the 11- option, a -1 Limitation


def _blast(activation: int | None) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=DICE,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="brute-eb", is_ranged=True,
        activation_roll=activation,
    )


def _fight():
    return session_of(
        fighter("brute", side=Side.named("villains"), dice=DICE),
        fighter("mark", side=Side.named("heroes"), dice=DICE),
    ).start()


def _fire(session, power, activation_dice, *, went_off=True):
    """The Activation Roll is drawn FIRST -- before the attack's own dice --
    because a power that does not go off is never rolled to hit."""
    pool = [activation_dice]
    if went_off:
        pool += [[4, 4, 4], [1] * DICE, [3, 3, 3], [1]]
    action = LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary="attack",
        _attack_view=power,
    )
    return resolve_chosen(
        session, session.combatants["brute"], action,
        template=TEMPLATE, roller=FakeRoller(pool),
    )


def _payload(resolved):
    for event in reversed(resolved.session.event_log):
        payload = getattr(event, "result_payload", None)
        if isinstance(payload, dict) and "hit" in payload:
            return payload
    raise AssertionError("no resolution event on the log")


def test_a_power_with_no_activation_roll_rolls_nothing():
    """Guards the guard, and guards the dice sequence: an engine that rolled
    an Activation for every power would shift every seeded fight."""
    session = _fight()
    action = LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid="ENERGYBLAST", power_name="Blast", summary="attack",
        _attack_view=_blast(None),
    )
    resolved = resolve_chosen(
        session, session.combatants["brute"], action, template=TEMPLATE,
        roller=FakeRoller([[4, 4, 4], [1] * DICE, [3, 3, 3], [1]]),
    )
    assert _payload(resolved)["hit"] is True


def test_a_made_activation_roll_lets_the_attack_through():
    """3d6 = 9 against an 11-: the power goes off and the attack is an
    ordinary attack from there on."""
    payload = _payload(_fire(_fight(), _blast(ACTIVATION), [3, 3, 3]))
    assert payload["activated"] is True
    assert payload["activation_roll"] == 9
    assert payload["activation_target"] == ACTIVATION
    assert payload["hit"] is True


def test_a_failed_activation_means_the_power_does_not_go_off():
    """3d6 = 15 against an 11-. No to-hit is rolled, nothing is damaged,
    and the log says why."""
    session = _fight()
    before = session.combatants["mark"].state.current_stun
    resolved = _fire(session, _blast(ACTIVATION), [5, 5, 5], went_off=False)
    payload = _payload(resolved)

    assert payload["activated"] is False
    assert payload["activation_roll"] == 15
    assert payload["activation_target"] == ACTIVATION
    assert payload["hit"] is False
    assert payload["stun_dealt"] == 0
    assert payload["body_dealt"] == 0
    assert resolved.session.combatants["mark"].state.current_stun == before


def test_the_roll_is_made_against_the_number_on_the_power():
    """Exactly the number: 6E1 p.375's options are "8-", "11-", "14-",
    "15-", so an 11 makes an 11- and fails a 10-."""
    made = _payload(_fire(_fight(), _blast(11), [5, 3, 3]))
    assert made["activated"] is True

    missed = _payload(_fire(_fight(), _blast(10), [5, 3, 3], went_off=False))
    assert missed["activated"] is False


def test_a_failed_activation_is_still_the_attack_kind():
    """`kind` is what every downstream filter and narrator reads. A
    resolution that dropped it would be invisible rather than reported."""
    resolved = _fire(_fight(), _blast(ACTIVATION), [6, 6, 6], went_off=False)
    payload = _payload(resolved)
    assert payload["kind"] == "attack"
    assert payload["target_id"] == "mark"
    assert payload["power_name"] == "Blast"
