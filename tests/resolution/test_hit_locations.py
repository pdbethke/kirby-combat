"""Aiming at the head does something.

THE TABLE WAS ALWAYS HERE AND ONE COLUMN OF IT WAS READ.
`tables.HIT_LOCATIONS` carries `stunX`, `nStunX`, `bodyX` and `ocvMod` for
every body part; `tables.HIT_LOCATION_ROLL` maps 3d6 to a location.
`resolution/to_hit.py` reads `ocvMod` and applies the aiming penalty.
NOTHING read the other three columns, and NOTHING ever rolled on the
table.

So a fighter could aim at the head, pay -8 OCV for it, hit, and do exactly
the damage he would have done swinging at nothing in particular:
`compute_damage` took a `hit_location`, passed it through to the result
untouched, and hardcoded `body_multiplier=1.0`. Aiming was strictly worse
than not aiming, in every fight this engine has run -- a penalty charged
with the benefit never delivered.

Found by sweeping every dataclass field for reads: `DiceValues
.hit_location`, `DamageResult.hit_location`, `DamageResult
.body_multiplier`, `CombatTemplate.allowed_hit_locations` and
`CombatTemplate.auto_roll_hit_location_npc` were all written and never
read.

THE BOOK'S WORKED EXAMPLE IS THE FIRST TEST (6E2 p.110): "Arkelos hits a
goblin (ED 5, PD 3, BODY 15) with his Fire Blast spell (RKA 3d6). He rolls
3d6 to determine Hit Location and gets an 8 - the Arms. He rolls another
3d6 to determine the BODY damage for his spell and gets a 13. Consulting
the STUNx column, he finds that the STUN Multiplier for the Arms is x2, so
he does 26 STUN to the target. The goblin takes 18 of this after
subtracting his defenses. Then the GM subtracts the goblin's 3 PD from the
BODY, leaving 10, which is multiplied by the x1/2 BODYx for the Arms, so
the goblin takes 5 BODY."

Eighteen and five, and this module must produce both.
"""
from __future__ import annotations

import pytest

from kirby_combat.resolution.hit_location import (
    effect_for, killing_damage, location_for_roll, normal_damage,
    uses_hit_locations,
)


# ---- The book's example ----

def test_the_goblins_arm():
    """6E2 p.110, quoted above: 18 STUN and 5 BODY."""
    stun, body = killing_damage(
        13, total_defense=8, resistant_defense=3, effect=effect_for("Arm"),
    )
    assert (stun, body) == (18, 5)


def test_the_roll_that_found_the_arm():
    """"He rolls 3d6 to determine Hit Location and gets an 8 - the Arms." """
    assert location_for_roll(8) == "Arm"


# ---- The asymmetry, which is the whole point ----

def test_killing_stun_multiplies_BEFORE_defenses():
    """6E2 p.110: "Multiply the BODY rolled by the STUNx ... The result is
    the amount of STUN done to the target BEFORE his defenses are applied."

    Head is STUNx 5. Ten BODY against 10 defense: 50 - 10 = 40, not
    (10 - 10) x 5 = 0. Getting this backwards makes a head shot harmless.
    """
    stun, _ = killing_damage(
        10, total_defense=10, resistant_defense=0, effect=effect_for("Head"),
    )
    assert stun == 40


def test_normal_stun_multiplies_AFTER_defenses():
    """6E2 p.111: "Multiply the amount of damage the target takes AFTER
    applying his defenses by the modifier ... in the N STUN column."

    Head is N STUN x2. Thirty STUN against 10 defense: (30 - 10) x 2 = 40,
    not (30 x 2) - 10 = 50.
    """
    stun, _ = normal_damage(
        30, 6, total_defense=10, effect=effect_for("Head"),
    )
    assert stun == 40


def test_body_always_multiplies_after_defenses():
    """Both paths agree here, and the book says so twice."""
    _, killing_body = killing_damage(
        13, total_defense=0, resistant_defense=3, effect=effect_for("Arm"))
    _, normal_body = normal_damage(
        0, 13, total_defense=3, effect=effect_for("Arm"))
    assert killing_body == normal_body == 5


# ---- A limb is not a head ----

@pytest.mark.parametrize("location,stun_x,body_x", [
    ("Head", 5, 2.0),
    ("Vitals", 4, 1.5),
    ("Chest", 3, 1.0),
    ("Hand", 1, 0.5),
    ("Foot", 1, 0.5),
])
def test_the_table_is_the_books(location, stun_x, body_x):
    e = effect_for(location)
    assert (e.stun_x, e.body_x) == (stun_x, body_x)


def test_an_unknown_location_is_no_location():
    """Most attacks are not aimed. None means "resolve it the way this
    engine always has"."""
    assert effect_for(None) is None
    assert effect_for("Elbow") is None


# ---- Whether the campaign uses them at all ----

class _NPC:
    is_npc = True


class _PC:
    is_npc = False


def test_superheroic_does_not_use_hit_locations():
    from kirby_combat.template import RAW_SUPERHEROIC

    assert uses_hit_locations(RAW_SUPERHEROIC, _PC()) is False


def test_heroic_does():
    from kirby_combat.template import RAW_HEROIC

    assert uses_hit_locations(RAW_HEROIC, _PC()) is True


def test_npcs_can_be_rolled_for_even_when_the_flag_is_off():
    """`auto_roll_hit_location_npc` -- "auto-roll for NPCs even if flag is
    off", the field's own comment, and read by nothing until now."""
    from dataclasses import replace

    from kirby_combat.template import RAW_SUPERHEROIC

    t = replace(RAW_SUPERHEROIC, auto_roll_hit_location_npc=True)
    assert uses_hit_locations(t, _NPC()) is True
    assert uses_hit_locations(t, _PC()) is False


# ---- And the resolver uses it ----

def _guy(side=None, attacks=(), **kw):
    from fixtures.synthetic_hero import synthetic_combatant

    base = dict(side=side, attacks=list(attacks),
        id="c", name="C", ocv=9, dcv=5, omcv=5, dmcv=5, spd=4, dex=20,
        ego=10, str_=15, con=18, pre=10, rec=5, pd=0, ed=0, rpd=0, red=0,
        md=0, power_defense=0, flash_defense=0, max_stun=60, max_body=20,
        max_end=40, current_stun=60, current_body=20, current_end=40)
    base.update(kw)
    return synthetic_combatant(**base)


def _rka(dice=3):
    from kirby_combat.models import AttackPower

    return AttackPower(
        xmlid="RKA", name="Fire Blast", damage_dice=dice, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, source_id="rka")


def _shoot(aim, template, damage=(5, 5, 3)):
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues

    return resolve_attack(
        AttackInput(attacker=_guy(id="a"), target=_guy(id="t"), power=_rka(),
                    distance_m=5.0, aim=aim,
                    dice=DiceValues(to_hit=[1, 1, 1], damage=list(damage),
                                    stun_multiplier=[3])),
        template,
    )


def test_a_head_shot_hurts_more_than_a_body_shot():
    """THE DEFECT. Both cost OCV; only one used to be worth it."""
    from kirby_combat.template import RAW_HEROIC

    head = _shoot("Head", RAW_HEROIC)
    chest = _shoot("Chest", RAW_HEROIC)
    assert head.stun_dealt > chest.stun_dealt
    assert head.body_dealt > chest.body_dealt


def test_a_hand_shot_hurts_less():
    """BODYx 1/2 cuts a limb wound down, which is why anyone aims at one."""
    from kirby_combat.template import RAW_HEROIC

    assert _shoot("Hand", RAW_HEROIC).body_dealt < _shoot("Chest", RAW_HEROIC).body_dealt


def test_a_superheroic_campaign_ignores_the_location_entirely():
    """`use_hit_locations=False` means the aim is flavour: no OCV penalty
    (`to_hit` already checks the flag) and no damage change either."""
    from kirby_combat.template import RAW_SUPERHEROIC

    head = _shoot("Head", RAW_SUPERHEROIC)
    chest = _shoot("Chest", RAW_SUPERHEROIC)
    assert (head.stun_dealt, head.body_dealt) == (chest.stun_dealt, chest.body_dealt)


# ---- Rolling for a location when nobody aimed ----

def test_an_unaimed_shot_rolls_for_a_location():
    """6E2 p.110 step 1: "Roll 3d6 and consult the first two columns of
    the Hit Location Table to find out where the attack struck."

    `DiceValues.hit_location` exists for exactly this and was written by
    nothing and read by nothing. Without it a heroic campaign got hit
    locations only on deliberately aimed shots, which is not the rule --
    the table is rolled on every hit.
    """
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.template import RAW_HEROIC

    # 3d6 = 3 is the Head; 3d6 = 6 is the Hand. Same damage, same defenses.
    def _at(loc_dice):
        return resolve_attack(
            AttackInput(attacker=_guy(id="a"), target=_guy(id="t"),
                        power=_rka(), distance_m=5.0, aim=None,
                        dice=DiceValues(to_hit=[1, 1, 1], damage=[5, 5, 3],
                                        hit_location=loc_dice,
                                        stun_multiplier=[3])),
            RAW_HEROIC,
        )

    head = _at([1, 1, 1])     # 3 -> Head
    hand = _at([2, 2, 2])     # 6 -> Hand
    assert head.stun_dealt > hand.stun_dealt
    assert head.body_dealt > hand.body_dealt


def test_an_aimed_shot_beats_the_roll():
    """6E2 p.111's Placed Shot: the character chose, so the dice do not.
    Aiming at the Hand and rolling a 3 (Head) must hit the Hand."""
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.template import RAW_HEROIC

    out = resolve_attack(
        AttackInput(attacker=_guy(id="a"), target=_guy(id="t"), power=_rka(),
                    distance_m=5.0, aim="Hand",
                    dice=DiceValues(to_hit=[1, 1, 1], damage=[5, 5, 3],
                                    hit_location=[1, 1, 1], stun_multiplier=[3])),
        RAW_HEROIC,
    )
    assert "Hand" in " ".join(out.audit_trail)


def test_the_loop_rolls_one():
    """The wiring: a live attack in a heroic fight must arrive with a
    location roll, or the table only ever fires on aimed shots."""
    import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import RAW_HEROIC
    from kirby_dice import RandomRoller

    a = _guy(id="a", side=Side.named("x"), attacks=[_rka()])
    t = _guy(id="t", side=Side.named("y"))
    session = CombatSession.create(
        id="s", scene=None, template=RAW_HEROIC,
        dice_roller=RandomRoller(seed=5), combatants=[a, t],
    ).start()
    attack = next(m for m in enumerate_actions(session.combatants["a"],
                                               [session.combatants["t"]])
                  if m.kind == "attack")
    out = resolve_chosen(session, session.combatants["a"], attack,
                         template=RAW_HEROIC, roller=RandomRoller(seed=5))
    assert out.result is not None
    assert any("Hit Location" in line for line in out.result.audit_trail), (
        "a heroic fight must roll a hit location; audit was "
        f"{out.result.audit_trail}"
    )


# ---- A campaign that only uses some locations ----

def test_a_campaign_can_restrict_which_locations_are_in_play():
    """`CombatTemplate.allowed_hit_locations` -- "empty = all", its own
    comment -- was written by nothing and read by nothing, so a GM who
    listed the locations their table uses was ignored.

    A location outside the list resolves as no location at all: the
    campaign has taken it out of play, so the multipliers do not apply and
    damage falls through to the ordinary path.
    """
    from dataclasses import replace

    from kirby_combat.template import RAW_HEROIC

    only_torso = replace(RAW_HEROIC, allowed_hit_locations=["Chest", "Stomach"])
    assert effect_for("Head", template=only_torso) is None
    assert effect_for("Chest", template=only_torso) is not None


def test_an_empty_list_means_every_location():
    from kirby_combat.template import RAW_HEROIC

    assert RAW_HEROIC.allowed_hit_locations == []
    assert effect_for("Head", template=RAW_HEROIC) is not None


def test_no_template_restricts_nothing():
    assert effect_for("Head") is not None
