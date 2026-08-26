"""Lightning Reflexes (6E1 p.116) tests.

Fixtures build the Talent to the OBSERVED shape from real character files
(project rule: characters come from the corpus, HDC is import-only -- so
this constructs a synthetic ``<TALENT>`` element rather than loading a raw
``.hdc``) and feed it through kirby-cost's real, oracle-validated
``LightningReflexesAll`` class -- not a hand-rolled stand-in -- so these
tests exercise the same accessors (`levels`, `option_alias()`) production
code reads off a real loaded character.
"""
from lxml import etree

from kirby_cost.engine.rolls import characteristic_roll
from kirby_cost.objects.talents.lightning_reflexes_all import LightningReflexesAll

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.session.tie_rule import TieRule, dex_roll_target
from kirby_combat.session.timeline import (
    ActionIntent,
    build_provisional_order_for_segment,
    resolve_acting_order,
)
from kirby_combat.talents.lightning_reflexes import (
    effective_dex,
    lightning_reflexes_bonus,
)


def _hero_with_talent(*, optionid: str, levels: int, option_alias: str = ""):
    """A hero stub carrying one real LightningReflexesAll Talent, built from
    the verbatim attribute shape HD writes (confirmed against 76 real
    instances -- see the module docstring in kirby_combat.talents.
    lightning_reflexes): OPTION and OPTIONID are always identical for this
    Talent, and both are set here for fidelity to the real document."""
    elem = etree.Element("TALENT")
    elem.set("XMLID", "LIGHTNING_REFLEXES_ALL")
    elem.set("LEVELS", str(levels))
    elem.set("ALIAS", "Lightning Reflexes")
    elem.set("OPTION", optionid)
    elem.set("OPTIONID", optionid)
    elem.set("OPTION_ALIAS", option_alias)
    talent = LightningReflexesAll(elem)

    class _Hero:
        talents = [talent]
        powers: list = []

    return _Hero()


def _c(id_: str, *, spd: int = 4, dex: int) -> "HeroCombatant":
    return synthetic_combatant(id=id_, name=id_, spd=spd, dex=dex)


def _c_with_hero(hero, *, dex: int) -> "HeroCombatant":
    c = synthetic_combatant(id="quick", name="quick", spd=4, dex=dex)
    # Graft the fixture's Lightning Reflexes talent onto the synthetic
    # hero already inside the combatant, rather than swapping `.hero`
    # wholesale, so combat_stats()/defenses keep working as normal.
    c.hero.talents = list(hero.talents)
    return c


def test_all_actions_bonus_applies_to_any_action():
    """6E1 p.116: bought for all Actions, a group, or a single Action.
    OPTIONID="ALL" is 52 of the 76 real instances."""
    hero = _hero_with_talent(optionid="ALL", levels=6,
                              option_alias="All Actions")
    assert lightning_reflexes_bonus(hero, "STRIKE") == 6


def test_single_action_bonus_applies_only_to_its_action():
    """20 of 76 real instances. NOTE the XMLID is still
    LIGHTNING_REFLEXES_ALL -- only OPTIONID says the scope is narrow."""
    hero = _hero_with_talent(optionid="SINGLE", levels=4,
                              option_alias="Spirit Travel")
    assert lightning_reflexes_bonus(hero, "Spirit Travel") == 4
    assert lightning_reflexes_bonus(hero, "STRIKE") == 0


def test_narrow_scope_is_not_read_off_the_xmlid():
    """The regression this task exists to prevent: every real instance --
    including all 20 SINGLE ones -- carries XMLID LIGHTNING_REFLEXES_ALL.
    Branching on the XMLID grants a universal bonus to 32% of characters
    who bought a narrow one."""
    hero = _hero_with_talent(optionid="SINGLE", levels=10,
                              option_alias="with Claws")
    assert hero.talents[0].xmlid == "LIGHTNING_REFLEXES_ALL"
    assert lightning_reflexes_bonus(hero, "STRIKE") == 0


def test_unknown_optionid_fails_closed():
    """An unrecognised scope returns 0, never the bonus."""
    hero = _hero_with_talent(optionid="SOMETHING_NEW", levels=8,
                              option_alias="?")
    assert lightning_reflexes_bonus(hero, "STRIKE") == 0


def test_largegroup_scope_matches_on_option_alias_like_single():
    """2 of 76 real instances. Group MEMBERSHIP isn't resolvable from the
    Talent alone (it names a Multipower, not its slots), so this matches
    the declared action against OPTION_ALIAS the same way SINGLE does."""
    hero = _hero_with_talent(optionid="LARGEGROUP", levels=6,
                              option_alias="Sonic Implants Multipower")
    assert lightning_reflexes_bonus(hero, "Sonic Implants Multipower") == 6
    assert lightning_reflexes_bonus(hero, "STRIKE") == 0


def test_allranged_scope_does_not_apply_to_hth():
    """2 of 76 real instances. No ranged/HtH signal reaches ActionIntent
    yet (see the KNOWN GAP note in lightning_reflexes.py), so this only
    checks the fail-closed side: a plainly-HtH action never gets the
    ALLRANGED bonus."""
    hero = _hero_with_talent(optionid="ALLRANGED", levels=5,
                              option_alias="All Ranged Attacks")
    assert lightning_reflexes_bonus(hero, "STRIKE") == 0


def test_bonus_applies_only_when_elected():
    """6E1 p.116(c): taking the bonus forfeits the rest of the Phase, so it
    is a choice, never applied silently."""
    hero = _hero_with_talent(optionid="ALL", levels=6)
    c = _c_with_hero(hero, dex=16)
    assert effective_dex(c, ActionIntent("STRIKE", elect_lightning_reflexes=False)) == 16
    assert effective_dex(c, ActionIntent("STRIKE", elect_lightning_reflexes=True)) == 22


def test_effective_dex_beats_higher_printed_dex():
    """6E1 p.116, verbatim example: "A character with a base DEX of 16 and
    +6 Lightning Reflexes (total effective DEX 16 + 6 = 22) would act
    before a character with a base DEX of 20"."""
    quick = _c_with_hero(_hero_with_talent(optionid="ALL", levels=6), dex=16)
    rival = _c("rival", spd=4, dex=20)
    prov = build_provisional_order_for_segment([quick, rival], segment=3)
    final = resolve_acting_order(prov, intents={
        quick.id: ActionIntent("STRIKE", elect_lightning_reflexes=True),
        "rival": ActionIntent("STRIKE"),
    })
    assert [s.combatant_id for s in final] == [quick.id, "rival"]


def test_effective_dex_does_not_reach_the_tie_roll():
    """6E1 p.116(a): "his Agility Skill Rolls remain 12-". A combatant who
    elects +6 still rolls its tie on printed DEX."""
    hero = _hero_with_talent(optionid="ALL", levels=6)
    c = _c_with_hero(hero, dex=16)
    assert dex_roll_target(c.combat_stats().dex) == characteristic_roll(16)  # not 22


def test_dex_roll_tie_break_uses_printed_dex_not_effective():
    """Integration guard for the same rule, run through the real ordering
    path instead of calling dex_roll_target directly: electing Lightning
    Reflexes can make two combatants' EFFECTIVE DEX tie (14+6 == 20) even
    though their printed DEX differs. 6E1 p.116(a) says the DEX Roll must
    still target printed DEX, so the tie-break margin must come out
    exactly as if no bonus had ever been added -- proving `resolve_acting_
    order` never lets `ordering_value`'s boosted number reach
    `dex_roll_target`."""
    hero = _hero_with_talent(optionid="ALL", levels=6)
    quick = _c_with_hero(hero, dex=14)   # effective DEX 14 + 6 = 20
    rival = _c("rival", dex=20)          # printed DEX 20 -- an ordering tie
    prov = build_provisional_order_for_segment([quick, rival], segment=3)
    intents = {
        quick.id: ActionIntent("STRIKE", elect_lightning_reflexes=True),
        "rival": ActionIntent("STRIKE"),
    }

    # Provisional order sorts on PRINTED DEX alone: rival (20) before
    # quick (14), so the roller is consumed rival-then-quick.
    rolls_a = iter([[3, 3, 3], [3, 3, 3]])  # identical rolls for both
    a = resolve_acting_order(prov, intents=intents, tie_rule=TieRule.DEX_ROLL,
                              roller=lambda: next(rolls_a))
    # Same identical-roll scenario computed by hand from PRINTED DEX only:
    # rival's margin = dex_roll_target(20) - 9; quick's = dex_roll_target(14) - 9.
    # dex_roll_target(20) > dex_roll_target(14), so rival wins the tie --
    # UNLESS quick's boosted ordering DEX (20) were smuggled into its own
    # roll target, which would tie the margins and fall through to the
    # combatant_id tiebreak ("quick" < "rival" alphabetically) instead.
    assert [s.combatant_id for s in a] == ["rival", "quick"]
