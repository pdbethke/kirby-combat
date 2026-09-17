"""Combat Skill Levels reach the Attack Roll from the build — 6E1 p.72.

`resolution/to_hit.py` has summed `attack.attacker.csls` since to-hit
resolution was written. `HeroCombatant.csls` returned `[]` --- the property
body was a comment, "empty until the relational rows are wired through
hero_view (future step)" --- so for every character this engine has ever
resolved from a BUILD, the sum was over an empty list. A gunfighter with
+3 CSLs with Ranged Combat shot exactly as well as one with none, and the
only CSLs that ever reached a roll were the ones a test handed in by hand.

THE BREADTH IS PART OF THE RULE. 6E1 p.72 prices a level by how much it
covers: with a single attack, with a small or large group, with HTH
Combat, with Ranged Combat, or with All Attacks --- eight points for the
Ranged one against two for the single. A model that carried only the
COUNT would let a level bought for one pistol sharpen a punch, which is
both wrong and the cheap end of the price list applied at the dear end.
So `CombatSkillLevel` carries its breadth, and the roll asks whether this
level reaches THIS attack.

THE ALLOCATION IS A JUDGEMENT, and is labelled one. p.72: "a character can
only use a CSL for one thing at a time... he can change the assignment of
his CSLs as a Zero-Phase Action." Which of OCV, DCV or damage a level is
assigned to is therefore a choice made each Phase, and this engine has no
seat to ask. Build-derived levels default to OCV --- the assignment the
attack path can act on --- and a caller that knows better passes its own
`CombatSkillLevel` list, which still wins.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.models import (
    AttackInput, AttackPower, CombatSkillLevel, DiceValues,
)
from kirby_combat.resolution.to_hit import resolve_to_hit
from kirby_combat.template import RAW_SUPERHEROIC

OCV = 8
DCV = 5
LEVELS = 3


def _blast() -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="w1", is_ranged=True,
    )


def _fist() -> AttackPower:
    return AttackPower(
        xmlid="HANDTOHANDATTACK", name="Fist", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=0,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="w2", is_ranged=False, reach_m=2.0,
    )


def _man(**kwargs):
    return synthetic_combatant(
        id="a", name="A", ocv=OCV, dcv=DCV, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40, **kwargs,
    )


def _target():
    return synthetic_combatant(
        id="b", name="B", ocv=OCV, dcv=DCV, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40,
    )


def _roll(attacker, power):
    """Distance 0 so no Range Modifier can move the number under test."""
    return resolve_to_hit(
        AttackInput(
            attacker=attacker, target=_target(), power=power,
            distance_m=None, aim=None,
            dice=DiceValues(to_hit=[4, 4, 4]),
        ),
        RAW_SUPERHEROIC,
    )


# ---------------------------------------------------------------------------
# From the build at all
# ---------------------------------------------------------------------------

def test_levels_bought_with_all_attacks_reach_the_roll():
    """The defect: `HeroCombatant.csls` was a stub returning `[]`, so a
    build's levels reached nothing."""
    man = _man(combat_levels=[(LEVELS, "ALL", "")])
    assert _roll(man, _blast()).effective_ocv == OCV + LEVELS


def test_a_man_with_no_levels_is_unchanged():
    """Guards the guard."""
    assert _roll(_man(), _blast()).effective_ocv == OCV


# ---------------------------------------------------------------------------
# The breadth decides which attacks the level reaches
# ---------------------------------------------------------------------------

def test_ranged_levels_do_not_sharpen_a_punch():
    """8 points buys "with Ranged Combat" (6E1 p.72). It does not buy a
    better fist, and a model that counted levels without their breadth
    would have spent the cheap price at the dear end."""
    man = _man(combat_levels=[(LEVELS, "RANGED", "")])
    assert _roll(man, _blast()).effective_ocv == OCV + LEVELS
    assert _roll(man, _fist()).effective_ocv == OCV


def test_hth_levels_do_not_steady_a_shot():
    """The mirror of the row above."""
    man = _man(combat_levels=[(LEVELS, "HTH", "")])
    assert _roll(man, _fist()).effective_ocv == OCV + LEVELS
    assert _roll(man, _blast()).effective_ocv == OCV


def test_a_level_bought_with_one_attack_reaches_only_that_attack():
    """SINGLE / TIGHT / BROAD name their attacks in the build's INPUT
    field, which is the only thing that says WHICH attacks 2, 3 or 5
    points bought. Matched by name; a level whose INPUT names nothing this
    character is swinging reaches nothing, because guessing would hand out
    the dearest breadth at the cheapest price."""
    man = _man(combat_levels=[(LEVELS, "SINGLE", "Blast")])
    assert _roll(man, _blast()).effective_ocv == OCV + LEVELS
    assert _roll(man, _fist()).effective_ocv == OCV


def test_a_level_that_names_no_attack_reaches_none():
    man = _man(combat_levels=[(LEVELS, "SINGLE", "")])
    assert _roll(man, _blast()).effective_ocv == OCV


# ---------------------------------------------------------------------------
# The allocation
# ---------------------------------------------------------------------------

def test_levels_assigned_elsewhere_do_not_reach_the_ocv():
    """A caller that has made p.72's Zero-Phase assignment itself wins:
    the explicit list is used and the build is not re-read."""
    man = _man(csls=[CombatSkillLevel(levels=LEVELS, applies_to="dcv")])
    assert _roll(man, _blast()).effective_ocv == OCV


def test_a_hand_built_level_still_reaches_every_attack():
    """Backwards compatibility, stated as a test: a `CombatSkillLevel`
    constructed without a breadth covers everything, exactly as every such
    level did before breadth existed."""
    man = _man(csls=[CombatSkillLevel(levels=LEVELS, applies_to="ocv")])
    assert _roll(man, _fist()).effective_ocv == OCV + LEVELS
    assert _roll(man, _blast()).effective_ocv == OCV + LEVELS
