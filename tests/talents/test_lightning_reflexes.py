"""Lightning Reflexes (6E1 p.116) tests.

Fixtures build the Talent to the OBSERVED shape from real character files
(project rule: characters come from the corpus, HDC is import-only -- so
this constructs a synthetic ``<TALENT>`` element rather than loading a raw
``.hdc``) and feed it through kirby-cost's real, oracle-validated
``LightningReflexesAll`` class -- not a hand-rolled stand-in -- so these
tests exercise the same accessors (`levels`, `option_alias()`) production
code reads off a real loaded character.
"""
import dataclasses

from lxml import etree

from kirby_cost.objects.talents.lightning_reflexes_all import LightningReflexesAll

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.session.timeline import (
    ActionIntent,
    build_provisional_order_for_segment,
    ordering_value,
    resolve_acting_order,
)
from kirby_combat.session.timeline import ActingSlot
from kirby_combat.talents.lightning_reflexes import (
    LightningReflexesGrant,
    lightning_reflexes_bonus,
    phase_restricted_to,
    restriction_for_slot,
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
    is a choice, never applied silently. Exercised through
    `timeline.ordering_value` -- the function production actually calls to
    decide acting order -- rather than a since-deleted stand-in
    (`effective_dex`) that had already diverged from it (no `is_mental`
    branch) despite being unreachable from any real ordering path."""
    hero = _hero_with_talent(optionid="ALL", levels=6)
    c = _c_with_hero(hero, dex=16)
    slot = build_provisional_order_for_segment([c], segment=3)[0]
    not_elected = dataclasses.replace(
        slot, intent=ActionIntent("STRIKE", elect_lightning_reflexes=False))
    elected = dataclasses.replace(
        slot, intent=ActionIntent("STRIKE", elect_lightning_reflexes=True))
    assert ordering_value(not_elected) == 16
    assert ordering_value(elected) == 22


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


def test_dex_roll_tie_break_uses_printed_dex_not_effective():
    """THE guard for 6E1 p.116(a): "his Agility Skill Rolls remain 12-" --
    a combatant who elects Lightning Reflexes still rolls its DEX-tie roll
    on PRINTED DEX, never the boosted effective DEX. Run through the real
    ordering path (not by calling `dex_roll_target` directly, which would
    only restate the contract, not exercise it): electing Lightning
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


def test_electing_lightning_reflexes_forbids_other_actions():
    """6E1 p.116: "no movement, acrobatics, or other Actions" in a Phase
    where the character uses the bonus."""
    intent = ActionIntent("Shuriken", elect_lightning_reflexes=True)
    assert phase_restricted_to(intent) == "Shuriken"


def test_not_electing_leaves_the_phase_free():
    assert phase_restricted_to(ActionIntent("Shuriken")) is None


def _slot(*, intent, grants=()) -> ActingSlot:
    return ActingSlot(
        combatant_id="c", segment=3, dex_at_phase=16, int_tiebreak=10,
        pre_tiebreak=10, ego=10, intent=intent, lightning_reflexes_grants=grants,
    )


def test_restriction_for_slot_matches_phase_restricted_to_for_single_scope():
    """A SINGLE-scoped elector really is narrowed to the one Action."""
    grant = LightningReflexesGrant(levels=4, option_id="SINGLE",
                                    option_alias="Shuriken")
    slot = _slot(
        intent=ActionIntent("Shuriken", elect_lightning_reflexes=True),
        grants=(grant,),
    )
    assert restriction_for_slot(slot) == "Shuriken"


def test_restriction_for_slot_does_not_narrow_an_all_scope_elector():
    """An ALL-scope grant covers every Action -- electing it forfeits
    nothing extra, so the Phase is not restricted (6E1 p.116(c))."""
    grant = LightningReflexesGrant(levels=6, option_id="ALL",
                                    option_alias="All Actions")
    slot = _slot(
        intent=ActionIntent("Shuriken", elect_lightning_reflexes=True),
        grants=(grant,),
    )
    assert restriction_for_slot(slot) is None


def test_restriction_for_slot_is_none_when_no_grant_actually_applies():
    """Electing produces no bonus when the build's grant doesn't cover the
    declared action -- nothing was "used", so nothing is forfeited."""
    grant = LightningReflexesGrant(levels=4, option_id="SINGLE",
                                    option_alias="Spirit Travel")
    slot = _slot(
        intent=ActionIntent("Shuriken", elect_lightning_reflexes=True),
        grants=(grant,),
    )
    assert restriction_for_slot(slot) is None


def test_restriction_for_slot_is_none_when_not_electing():
    slot = _slot(intent=ActionIntent("Shuriken"))
    assert restriction_for_slot(slot) is None


def test_restriction_for_slot_is_none_for_a_mental_intent():
    """6E1 p.116(c) forfeits the Phase for a character who "uses Lightning
    Reflexes to increase his effective DEX". A mental intent orders on EGO
    (APG p.50, timeline.ordering_value) and never applies the bonus, even
    when a covering SINGLE grant exists and the intent elects it -- so
    nothing was increased, and nothing should be forfeited. Reproduces the
    telepath DEX 10 / EGO 30 scenario: `ordering_value` returns 30 (bonus
    never applied) while a scope-only check would still see the grant
    covers "Mind Blast" and wrongly restrict the Phase."""
    grant = LightningReflexesGrant(levels=6, option_id="SINGLE",
                                    option_alias="Mind Blast")
    slot = _slot(
        intent=ActionIntent("Mind Blast", is_mental=True,
                             elect_lightning_reflexes=True),
        grants=(grant,),
    )
    assert restriction_for_slot(slot) is None
