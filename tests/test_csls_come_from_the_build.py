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


# ---------------------------------------------------------------------------
# A REAL build, through the real loader
# ---------------------------------------------------------------------------
#
# THE SYNTHETIC FIXTURE ALONE PROVED NOTHING, and this section exists
# because it did not. The first cut of this wiring read the named attacks
# from `skill.input` and walked `hero.skills`; the fixture was handed an
# INPUT because the code asked for one, and lived in `skills` because the
# code looked there, so eight tests passed over a reader that could not
# have worked on any character anyone has built. Hero Designer writes the
# words to NAME or OPTION_ALIAS and never to INPUT, and it lets a player
# buy Combat Skill Levels in the POWERS section -- which PowerLad did.

def test_a_real_build_has_its_combat_levels_found_at_all():
    """PowerLad buys his Combat Skill Levels in the POWERS section, which
    HERO Designer permits. A reader that walked `hero.skills` alone did not
    merely fail to match them -- it never found them, and reported `[]`."""
    from kirby_combat.hero_view import HeroCombatant
    from corpus import require_authored, require_template

    require_template()

    lad = HeroCombatant.from_build(require_authored("PowerLad"), id="lad")
    levels = lad.csls
    assert levels, "PowerLad's Combat Skill Levels were not found on the build"
    assert [c.levels for c in levels] == [1]
    # The BREADTH is deliberately not asserted here. `build_json` does carry
    # OPTIONID, so a doc written today reads "tight" -- but the committed
    # fixture this test loads predates that and reads "single". Pinning
    # either would pin the fixture's age rather than the engine's
    # behaviour. What the product path actually costs a narrow level is
    # asserted in `test_the_build_doc_cannot_name_a_framework` below.


def test_a_real_build_names_its_attacks_where_hd_actually_writes_them():
    """PowerLad's level carries NAME="+1 With Punch, Haymaker, and Throw"
    and an empty INPUT. The named text has to come off NAME; the
    OPTION_ALIAS beside it is the template's own "with a small group of
    attacks" boilerplate and names nothing."""
    from kirby_combat.hero_view import HeroCombatant
    from corpus import require_authored, require_template

    require_template()

    lad = HeroCombatant.from_build(require_authored("PowerLad"), id="lad")
    named = lad.csls[0].named_attacks.lower()
    assert "punch" in named and "haymaker" in named and "throw" in named
    assert "small group of attacks" not in named


def test_the_build_doc_cannot_name_a_framework():
    """JUDGEMENT + the kirby-cost gap, named so it is greppable.

    A narrow (single / tight / broad) Combat Skill Level says WHICH attacks
    it covers in one of two places, and only one of them survives the
    product path. HD writes NAME ("+1 With Punch, Haymaker, and Throw",
    PowerLad) and OPTION_ALIAS ("with Power Over Light And Heat
    Multipower", HELIOS-CV1). `kirby_cost.io.build_json` maps `alias` to
    the skill's own ALIAS ("Combat Skill Levels") and has NO field for
    OPTION_ALIAS at all.

    So through `tests/corpus.py` -- build docs, which is what this engine
    reads and what the product rests on -- a level can only ever name what
    is in its NAME. A BROAD level bought across a framework names the
    framework in OPTION_ALIAS and nothing else, so it arrives naming
    nothing and reaches nothing. **No real build's single/tight/broad CSL
    reaches a roll through the product path today.**

    The engine's behaviour is correct and deliberately narrow: a level that
    names nothing reaches nothing, so a build loses points rather than
    gaining reach it did not pay for. Carrying OPTION_ALIAS through
    `build_json` is a KIRBY-COST change, not an A3 one.

    Asserted on the raw document so it fails the day kirby-cost carries the
    field -- at which point `_csl_named_attacks` already reads it and this
    test is the notice that the gap closed."""
    from corpus import require_authored_doc

    doc = require_authored_doc("PowerLad")

    def find(node):
        if isinstance(node, dict):
            if str(node.get("xmlid", "")).upper() == "COMBAT_LEVELS":
                return node
            for value in node.values():
                found = find(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = find(value)
                if found is not None:
                    return found
        return None

    csl = find(doc)
    assert csl is not None, "PowerLad's COMBAT_LEVELS is not in the build doc"
    assert "option_alias" not in csl, (
        "build_json now carries OPTION_ALIAS — the product-path gap this "
        "test records has closed; `_csl_named_attacks` already reads it, so "
        "rewrite this test to assert the framework match instead."
    )


def test_a_real_builds_level_reaches_only_what_it_names():
    """THE HONEST BEHAVIOUR, asserted rather than wished away. PowerLad's
    level names Punch, Haymaker and Throw -- MANEUVERS -- and his only
    listed attack power is an HKA called "Rending and Tearing". So the
    level does not reach that power, and should not.

    JUDGEMENT, and a known limit: a level that names a MANEUVER cannot
    reach one today. (The other product-path limit -- a level that names a
    FRAMEWORK, which is how BROAD levels are written -- is
    `test_the_build_doc_cannot_name_a_framework` above.) The engine resolves a Haymaker or a Throw through a
    maneuver resolver that carries an attack POWER as its damage handle,
    so there is no "Haymaker" name for `_csl_reaches` to match against. A
    maneuver-aware match is a follow-on; inventing one here by matching the
    level against whatever power the maneuver happened to hold would hand
    out the levels on every attack he makes, which is the over-generous
    reading this whole reader is built to refuse."""
    from kirby_combat.hero_view import HeroCombatant
    from kirby_combat.resolution.to_hit import _csl_reaches
    from corpus import require_authored, require_template

    require_template()

    lad = HeroCombatant.from_build(require_authored("PowerLad"), id="lad")
    level = lad.csls[0]
    assert [ap.name for ap in lad.attacks] == ["Rending and Tearing"]
    assert not _csl_reaches(level, lad.attacks[0])


def test_a_broad_level_bought_across_a_framework_reaches_its_slots():
    """The HELIOS-CV1 / ARTHON-CV1 shape, which is how BROAD levels are
    actually written: HD puts the group's name in OPTION_ALIAS ("with
    Power Over Light And Heat Multipower") and every slot in that
    Multipower is called something else entirely ("Light Blast", "Laser
    Blast"). Matching the power's own name found nothing for either
    character; the FRAMEWORK's name is what the level names.

    Stated synthetically because kirby-combat commits no character data --
    verified against both real builds through the real loader on
    2026-09-17, 4 levels reaching all five of HELIOS's slots and 2 reaching
    all three of ARTHON's."""
    power = _blast()
    power.framework_name = "Power Over Light And Heat"
    level = CombatSkillLevel(
        levels=LEVELS, applies_to="ocv", breadth="broad",
        named_attacks="with Power Over Light And Heat Multipower",
    )
    man = _man(csls=[level])
    assert _roll(man, power).effective_ocv == OCV + LEVELS
    # A slot in a DIFFERENT framework is not reached.
    other = _blast()
    other.framework_name = "Brick Tricks"
    assert _roll(man, other).effective_ocv == OCV


def test_the_templates_own_boilerplate_names_no_attack():
    """PowerLad's OPTION_ALIAS is "with a small group of attacks" -- the
    template's DISPLAY string for TIGHT, copied in by HD. Treating it as a
    list of attacks would make a power called "Attack" match and everything
    else miss, on a coincidence of wording."""
    man = _man(csls=[CombatSkillLevel(
        levels=LEVELS, applies_to="ocv", breadth="tight",
        named_attacks="",          # what `_csl_named_attacks` returns for it
    )])
    assert _roll(man, _blast()).effective_ocv == OCV


def test_a_level_after_an_already_seen_purchase_is_still_found():
    """`_csl_skills` de-duplicates by object identity, because a framework
    slot is reachable twice -- directly in `powers` and again through its
    framework's own `powers`. It read `return` on the duplicate rather than
    `continue`, which abandoned the whole remaining list: a hero whose
    purchases ran [framework, slot, csl] yielded NO levels at all.

    Latent, because the corpus characters happen to list their levels
    before their frameworks. A test rather than a comment, because "the
    order happens to be kind to us" is not a property."""
    from kirby_combat.hero_view import _csl_skills

    class _Obj:
        def __init__(self, xmlid, powers=()):
            self.xmlid = xmlid
            self.powers = list(powers)
            self.levels = 2
            self.name = "+2 with the Flamethrower"
            self.input = ""

    slot = _Obj("ENERGYBLAST")
    framework = _Obj("GENERIC_OBJECT", powers=[slot])
    csl = _Obj("COMBAT_LEVELS")

    class _Hero:
        skills: list = []
        powers = [framework, slot, csl]      # the slot arrives twice

    assert [o.xmlid for o in _csl_skills(_Hero())] == ["COMBAT_LEVELS"]
