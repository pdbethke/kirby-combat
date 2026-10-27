"""What a defender is told about the attack he is asked to Abort against.

A seat answering "he is attacking you --- do you Abort?" out of a STANDING
ORDER ("Dodge when a Killing attack comes at me", "Block his punches") has
to know two things about the incoming attack that are rules, not display:
whether it is hand-to-hand (6E2 p.59: Block is a hand-to-hand defence) and
whether it does Killing Damage (6E1 p.98). `reaction_menu` already decides
the first (`_is_hth`) and the attack's power or maneuver carries the second.
`OutOfTurn.attack` hands both over, so no seat above the engine re-derives
either from a summary string or a private handle.

Every test here drives `run_phase`, the live path.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import blast, encounter_of, fighter  # tests/loop/conftest.py
from kirby_combat.loop import run_phase
from kirby_combat.loop.chooser import OutOfTurnReason
from kirby_combat.loop.reactions import IncomingAttack
from kirby_combat.side import Side
from kirby_dice import RandomRoller

HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


class Recorder:
    """The attacker attacks ``d``; everybody asked out of turn declines.
    Keeps every out-of-turn situation it was shown."""

    def __init__(self, kind: str = "attack"):
        self.kind = kind
        self.out_of_turn = []

    def choose(self, situation):
        oot = situation.out_of_turn
        if oot is not None:
            self.out_of_turn.append(oot)
            return situation.menu[0].action_id
        for offer in situation.menu:
            if offer.kind == self.kind and offer.target_id == "d":
                return offer.action_id
        return situation.menu[0].action_id


def _asked(attack_power, *, kind="attack"):
    a = fighter("a", side=HEROES, dex=30)
    a.attacks[:] = [attack_power]
    d = fighter("d", side=VILLAINS, dex=10)
    chooser = Recorder(kind)
    run_phase(encounter_of(a, d), chooser, roller=RandomRoller(seed=3),
              on_unresolvable="raise")
    aborts = [o for o in chooser.out_of_turn if o.reason is OutOfTurnReason.ABORT]
    assert aborts, "the defender was never asked whether he Aborts"
    return aborts[0]


def test_a_ranged_normal_attack_is_described_as_such():
    oot = _asked(blast("a-eb", dice=8, range_m=100))
    attack = oot.attack
    assert isinstance(attack, IncomingAttack)
    assert attack.attacker_id == "a"
    assert attack.action_id == oot.incoming.action_id
    assert attack.kind == "attack"
    assert attack.hand_to_hand is False
    assert attack.killing is False
    assert attack.summary == oot.incoming.summary


def test_a_killing_attack_says_it_is_killing():
    rka = replace(blast("a-rka", dice=2, range_m=100), damage_type="killing")
    attack = _asked(rka).attack
    assert attack.killing is True
    assert attack.hand_to_hand is False


def test_a_hand_to_hand_attack_says_so_and_is_the_one_block_is_offered_against():
    """`hand_to_hand` is `reaction_menu`'s own test, so it agrees with
    whether Block was put on the menu (6E2 p.59)."""
    fist = blast("a-fist", dice=6, range_m=0)
    a = fighter("a", side=HEROES, dex=30)
    a.attacks[:] = [fist]
    d = fighter("d", side=VILLAINS, dex=10)

    shown = []

    class Watch(Recorder):
        def choose(self, situation):
            if situation.out_of_turn is not None:
                shown.append(situation)
            return super().choose(situation)

    run_phase(encounter_of(a, d), Watch(), roller=RandomRoller(seed=3),
              on_unresolvable="raise")
    abort = next(s for s in shown
                 if s.out_of_turn.reason is OutOfTurnReason.ABORT)
    assert abort.out_of_turn.attack.hand_to_hand is True
    assert "block" in abort.action_ids


def test_a_held_action_question_carries_no_attack():
    """The HELD_ACTION question is asked before the man whose Phase it is
    has chosen anything, so there is no attack to describe: None, the same
    answer ``incoming`` gives."""
    from test_reactions_and_concealment import Ones, _holding_encounter

    seen = []

    class Watch:
        def choose(self, situation):
            if situation.out_of_turn is not None:
                seen.append(situation.out_of_turn)
            return situation.menu[0].action_id

    run_phase(_holding_encounter(), Watch(), roller=Ones(seed=1),
              on_unresolvable="raise")
    held = [o for o in seen if o.reason is OutOfTurnReason.HELD_ACTION]
    assert held, "nobody was asked about a Held Action"
    assert all(o.attack is None and o.incoming is None for o in held)


def test_the_abort_offers_name_the_attacker_not_his_id():
    """The offers are read by a person when the defender is a player
    (kirby-api shows them as the question). They named the attacker by his
    combatant id --- a uuid in a real fight --- where the Brief beside them
    names him. Same name the menu uses everywhere else (`_friendly`)."""
    a = fighter("a-id", side=HEROES, dex=30)
    a.attacks[:] = [blast("a-fist", dice=6, range_m=0)]
    a.hero.name = "Grond"
    d = fighter("d", side=VILLAINS, dex=10)
    shown = []

    class Watch(Recorder):
        def choose(self, situation):
            if situation.out_of_turn is not None:
                shown.append(situation)
            return super().choose(situation)

    run_phase(encounter_of(a, d), Watch(), roller=RandomRoller(seed=3),
              on_unresolvable="raise")
    abort = next(s for s in shown if s.out_of_turn.reason is OutOfTurnReason.ABORT)
    summaries = {o.kind: o.summary for o in abort.menu}
    assert "Grond" in summaries["no_abort"] and "a-id" not in summaries["no_abort"]
    assert "Grond" in summaries["block"] and "a-id" not in summaries["block"]
