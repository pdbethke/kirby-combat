"""Attacks cost END, and END is a thing you can run out of.

NOBODY IN THIS ENGINE HAS EVER SPENT END ON AN ATTACK. `AttackResult
.end_spent` is computed in `actions/base.py` and returned, and no caller
subtracts it: a fighter throws an 8d6 Blast and finishes the Phase at the
END he started with. Measured on the O.K. Corral, where all nine men end a
41-Phase gunfight at 25/25 -- though the corral is the WRONG place to
notice it, because those Colts run on Charges and a charged weapon
genuinely costs 0 END. It shows on a plain Blast.

The engine implements Recovery, Post-Segment 12 Recovery and a REC
characteristic, and there has never been anything to recover from.

Found by sweeping every dataclass field in the engine for reads.
`hero_view` line 1933 says the quiet part out loud:

    reduced_end = _has_modifier(power, "REDUCEDEND")  # noqa: F841 (END calc TBD)

THE RULE, 6E1 p.132: "Every Phase such a Power is turned on, it costs the
character 1 END for every 10 Active Points of Power used ... The minimum
END cost for a power that costs END is 1 END per Phase, regardless of how
few Active Points of the Power a character uses." And: "The standard
rounding rules apply to END cost calculations. A character using a 15
Active Point ability pays 1 END; a character using a 46 Active Point
ability pays 5 END."

Those two numbers are the test. 15 -> 1 is round-half-in-the-character's-
favour (1.5 down, because this is a cost); 46 -> 5 is ordinary rounding
up from 4.6.

WHAT WAS THERE BEFORE was `end_spent = max(1, power.damage_dice)`, which
reads Active Points off the dice count and gets roughly double: an 8d6
Blast is 40 Active Points and costs 4 END, not 8.
"""
from __future__ import annotations

import pytest

from kirby_combat.endurance import end_cost
from kirby_combat.models import AttackPower


def _power(active_points, *, dice=8, charges=None, reduced_end=False):
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=dice, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id="eb", active_points=active_points,
        charges=charges, reduced_end=reduced_end,
    )


# ---- The book's own two examples ----

@pytest.mark.parametrize("active_points,expected", [
    (15, 1),    # 6E1 p.132, quoted: "a 15 Active Point ability pays 1 END"
    (46, 5),    # 6E1 p.132, quoted: "a 46 Active Point ability pays 5 END"
])
def test_the_books_worked_examples(active_points, expected):
    assert end_cost(_power(active_points)) == expected


def test_one_end_per_ten_active_points():
    assert end_cost(_power(40)) == 4
    assert end_cost(_power(60)) == 6


def test_the_minimum_is_one():
    """"The minimum END cost for a power that costs END is 1 END per
    Phase, regardless of how few Active Points ... a character uses." """
    assert end_cost(_power(5)) == 1
    assert end_cost(_power(1)) == 1


def test_half_rounds_in_the_characters_favour():
    """15 -> 1.5 -> 1, which is the book's own first example: a cost
    rounds DOWN at the half, because rounding favours the character."""
    assert end_cost(_power(15)) == 1
    assert end_cost(_power(25)) == 2


# ---- What is free ----

def test_a_charged_weapon_costs_no_end():
    """A Colt Peacemaker runs on Charges. This is why the O.K. Corral was
    the wrong place to notice the bug: those men were right to end the
    fight at full END."""
    assert end_cost(_power(40, charges=6)) == 0


def test_reduced_endurance_zero_end_costs_no_end():
    """The modifier `hero_view` has been parsing and discarding."""
    assert end_cost(_power(40, reduced_end=True)) == 0


def test_no_active_points_recorded_still_costs_the_minimum():
    """A hand-built power with no cost-engine figure is not free; it is
    the minimum. Returning 0 would make every synthetic fixture in the
    suite a perpetual-motion machine."""
    assert end_cost(_power(0)) == 1


# ---- And it comes out of the fighter ----

def test_the_resolver_prices_the_attack_from_active_points():
    """`actions/base.py` had `end_spent = max(1, power.damage_dice)`."""
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.template import CombatTemplate
    from fixtures.synthetic_hero import synthetic_combatant

    def _guy():
        return synthetic_combatant(
            id="a", name="A", ocv=9, dcv=5, omcv=5, dmcv=5, spd=4, dex=20,
            ego=10, str_=15, con=15, pre=10, rec=5, pd=2, ed=2, rpd=0, red=0,
            md=0, power_defense=0, flash_defense=0, max_stun=30, max_body=10,
            max_end=30, current_stun=30, current_body=10, current_end=30)

    out = resolve_attack(
        AttackInput(attacker=_guy(), target=_guy(), power=_power(40),
                    distance_m=5.0, aim=None,
                    dice=DiceValues(to_hit=[1, 1, 1], damage=[3] * 8)),
        CombatTemplate.default_6e_superheroic(),
    )
    assert out.end_spent == 4, "40 Active Points is 4 END, not 8 dice"


def test_a_fight_actually_drains_the_pool():
    """THE DEFECT. Nothing subtracted `end_spent`, so a fighter threw an
    8d6 Blast and finished the Phase at the END he started with.

    Run under `RAW_HEROIC`, because whether END is counted at all is the
    campaign's call and `RAW_SUPERHEROIC` says not to -- see
    `test_a_superheroic_campaign_does_not`.
    """
    import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    def _guy(cid, side, attacks=()):
        return synthetic_combatant(
            id=cid, name=cid, ocv=9, dcv=5, omcv=5, dmcv=5, spd=4, dex=20,
            ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4, rpd=0, red=0,
            md=3, power_defense=0, flash_defense=0, max_stun=40, max_body=12,
            max_end=40, current_stun=40, current_body=12, current_end=40,
            side=side, attacks=list(attacks))

    from kirby_combat.template import RAW_HEROIC

    session = CombatSession.create(
        id="s", scene=None, template=RAW_HEROIC,
        dice_roller=RandomRoller(seed=2),
        combatants=[_guy("a", Side.named("x"), [_power(40)]),
                    _guy("b", Side.named("y"))],
    ).start()
    menu = enumerate_actions(session.combatants["a"], [session.combatants["b"]])
    attack = next(m for m in menu if m.kind == "attack")

    before = session.combatants["a"].state.current_end
    out = resolve_chosen(session, session.combatants["a"], attack,
                         template=RAW_HEROIC, roller=RandomRoller(seed=2))
    after = out.session.combatants["a"].state.current_end
    assert after < before, "an attack that costs END must cost END"


# ---- Whether END is tracked at all is the campaign's call ----

def _tracked_fight(template):
    """One attack under `template`; returns (END before, END after)."""
    import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_dice import RandomRoller

    def _guy(cid, side, attacks=()):
        return synthetic_combatant(
            id=cid, name=cid, ocv=9, dcv=5, omcv=5, dmcv=5, spd=4, dex=20,
            ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4, rpd=0, red=0,
            md=3, power_defense=0, flash_defense=0, max_stun=40, max_body=12,
            max_end=40, current_stun=40, current_body=12, current_end=40,
            side=side, attacks=list(attacks))

    session = CombatSession.create(
        id="s", scene=None, template=template,
        dice_roller=RandomRoller(seed=2),
        combatants=[_guy("a", Side.named("x"), [_power(40)]),
                    _guy("b", Side.named("y"))],
    ).start()
    menu = enumerate_actions(session.combatants["a"], [session.combatants["b"]])
    attack = next(m for m in menu if m.kind == "attack")
    before = session.combatants["a"].state.current_end
    out = resolve_chosen(session, session.combatants["a"], attack,
                         template=template, roller=RandomRoller(seed=2))
    return before, out.session.combatants["a"].state.current_end


def test_a_heroic_campaign_tracks_endurance():
    """`RAW Heroic` ships `manage_endurance=True`. Gritty games count it."""
    from kirby_combat.template import CombatTemplate

    from kirby_combat.template import RAW_HEROIC

    before, after = _tracked_fight(RAW_HEROIC)
    assert after < before


def test_a_superheroic_campaign_does_not():
    """`RAW Superheroic` ships `manage_endurance=False`, and it always has.

    THIS CAUGHT A DEFECT IN THE COMMIT BEFORE IT. Spending END was made
    unconditional, which quietly overrode a policy the templates had
    stated since they were written -- superheroic games hand-wave END,
    heroic ones count it, and that split is exactly what these two flags
    are for. They were read by nothing, so the contradiction was silent.
    """
    from kirby_combat.template import CombatTemplate

    before, after = _tracked_fight(CombatTemplate.default_6e_superheroic())
    assert after == before
