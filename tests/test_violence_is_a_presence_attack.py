"""Tearing a man in half is a Presence Attack --- 6E2 p.138.

Power Lad killed seven men in the O.K. Corral while seven more shot him
for nothing, Phase after Phase, and not one of them flinched. They were
brave in a way nobody is brave. PeterB: *"if powerlad literally ripped
someone in half, thats a major PRE attack"*.

It is not a house rule. 6E2 p.138's Presence Attack Modifiers Table
prices exactly this:

    Violent action              +1d6
    Extremely violent action    +2d6
    Incredibly violent action   +3d6
    Exhibiting a Power or superior technology   +1d6
    Target is in partial retreat                +2d6
    Target is in full retreat / has been captured   +4d6

And the engine already owns the receiving half: `resolve_presence_attack`
takes `bonus_dice_from_situation`, and `PresenceEffects` already spends
the tiers' 0 DCV and cannot-act. What was missing is that a violent ACT
generates one. Only a declared `presence_attack` action ever did.

WHICH BLOWS QUALIFY IS A JUDGEMENT and the table says so --- the book
gives three named rungs and no numbers. Ours reads the damage against the
man who took it, because that is what the onlookers saw: a blow that took
somebody from standing to dying is a different thing from a graze, and
"how bad did that look" is proportional to what it did to him. Recorded
as judgement, not as RAW, and quotable in the audit trail.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.pre_attacks.violence import (
    INCREDIBLY_VIOLENT, EXTREMELY_VIOLENT, VIOLENT, presence_from_violence,
    violence_bonus_dice,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


class _MaxRoller:
    """Every die a six, so the tier is decided by the rule under test and
    not by luck."""

    def roll_dice(self, n: int) -> list[int]:
        return [6] * n


def _man(id_, *, pre=15, side="law"):
    return synthetic_combatant(
        id=id_, name=id_, ocv=5, dcv=4, omcv=3, dmcv=3, spd=3, dex=13,
        ego=10, str_=13, con=13, pre=pre, rec=5, pd=2, ed=2, rpd=0, red=0,
        md=0, power_defense=0, flash_defense=0,
        max_stun=26, max_body=10, max_end=26,
        current_stun=26, current_body=10, current_end=26,
        side=Side.named(side), attacks=[],
    )


def _lot():
    """A monster, the man he is about to kill, and two who watch."""
    monster = _man("power_lad", pre=40, side="solo")
    people = [monster, _man("virgil"), _man("wyatt"), _man("morgan")]
    session = CombatSession.create(
        id="lot", combatants=people, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=3),
    ).start()
    return session, monster


def test_a_killing_blow_is_incredibly_violent():
    """The case that started it: a man goes down and does not get up."""
    assert violence_bonus_dice(body_dealt=19, target_max_body=10,
                               target_body_after=-9) == INCREDIBLY_VIOLENT


def test_a_maiming_blow_is_extremely_violent():
    """Still standing, and visibly ruined -- half his BODY in one hit."""
    assert violence_bonus_dice(body_dealt=6, target_max_body=10,
                               target_body_after=4) == EXTREMELY_VIOLENT


def test_drawing_blood_is_violent():
    assert violence_bonus_dice(body_dealt=2, target_max_body=10,
                               target_body_after=8) == VIOLENT


def test_a_blow_that_does_no_body_impresses_nobody():
    """Seven revolvers on Power Lad's hide, all night. Loud, and not
    frightening --- which is the whole point of grading this by what the
    onlookers actually saw happen to somebody."""
    assert violence_bonus_dice(body_dealt=0, target_max_body=10,
                               target_body_after=10) == 0


def test_a_miss_is_not_violence():
    assert violence_bonus_dice(body_dealt=0, target_max_body=10,
                               target_body_after=10) == 0


def test_the_rungs_are_the_books_three_and_no_more():
    """6E2 p.138 names three. Inventing a fourth would be inventing a
    rule, and this is judgement sitting under a table that is not."""
    assert (VIOLENT, EXTREMELY_VIOLENT, INCREDIBLY_VIOLENT) == (1, 2, 3)


def test_a_target_with_no_body_at_all_does_not_divide_by_zero():
    """Constructs and oddities: no BODY to measure against, so fall back
    to 'something bled' rather than raising in the middle of a fight."""
    assert violence_bonus_dice(body_dealt=5, target_max_body=0,
                               target_body_after=-5) == INCREDIBLY_VIOLENT


# ---- The onlookers ----

def test_a_kill_frightens_the_men_who_watched_it():
    """The whole point. Power Lad tears somebody apart; the lot reacts."""
    session, monster = _lot()
    after = presence_from_violence(
        session, attacker=monster, target_id="virgil",
        body_dealt=19, target_max_body=10, target_body_after=-9,
        roller=_MaxRoller(),
    )
    from kirby_combat.session.effects import presence_state

    assert presence_state(after, "wyatt").is_active, (
        "a man who watched that should not be unmoved"
    )


def test_the_victim_is_not_also_an_onlooker():
    """He is not watching it happen to somebody else; it is happening to
    him, and he is dying. A separate rule from this one."""
    session, monster = _lot()
    after = presence_from_violence(
        session, attacker=monster, target_id="virgil",
        body_dealt=19, target_max_body=10, target_body_after=-9,
        roller=_MaxRoller(),
    )
    from kirby_combat.session.effects import presence_state

    assert not presence_state(after, "virgil").is_active


def test_the_attacker_does_not_frighten_himself():
    session, monster = _lot()
    after = presence_from_violence(
        session, attacker=monster, target_id="virgil",
        body_dealt=19, target_max_body=10, target_body_after=-9,
        roller=_MaxRoller(),
    )
    from kirby_combat.session.effects import presence_state

    assert not presence_state(after, "power_lad").is_active


def test_bullets_that_do_nothing_frighten_nobody():
    """Seven revolvers on a hide they cannot break. Loud, and not
    frightening -- and the fight should read that way."""
    session, monster = _lot()
    after = presence_from_violence(
        session, attacker=monster, target_id="virgil",
        body_dealt=0, target_max_body=10, target_body_after=10,
        roller=_MaxRoller(),
    )
    assert after is session, "no violence, no Presence Attack, no new events"


def test_onlookers_take_it_one_level_lighter_than_the_victim_would():
    """6E2 p.137: 'the effects of a Presence Attack are reduced by one
    level when applied to anyone against whom the attack isn't
    specifically directed.' Nobody swung at the onlookers."""
    from kirby_combat.pre_attacks.violence import one_level_lighter

    assert one_level_lighter("overwhelmed") == "cowed"
    assert one_level_lighter("cowed") == "awed"
    assert one_level_lighter("awed") == "very_impressed"
    assert one_level_lighter("impressed") == "no_effect"
    assert one_level_lighter("no_effect") == "no_effect"
