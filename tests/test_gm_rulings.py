"""GM rulings: what the table has ruled about a body, and the routes an
attack travels by.

A ruling only takes away what cannot happen; it never grants anything. A
body fact (``NO_LUNGS``, ``NO_SKIN``, ``NO_ORGANS``) closes one delivery
route (breath, skin, ingestion). A ruling about a power names the routes it
travels by. An attack whose every route is closed on a target is not
offered against him, and the page says why.

Life Support's Self-Contained Breathing closes breath too (6E1 p.247;
paraphrased, this project ships no rules text), read off the build in play,
so Ravel's, bought Only In Hero ID, does nothing for Teddy.

Ravel and Bokor are PeterB's own characters.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_dice import RandomRoller

from kirby_combat.brief import Brief
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.run import _situation_for
from kirby_combat.rulings import (
    CLOSES,
    BodyFact,
    DeliveryRoute,
    Ruling,
    Withheld,
    closed_routes,
    routes_of,
    rulings_for,
    state_rulings,
)
from kirby_combat.serialization import from_dict, to_dict
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from tests.corpus import require_authored

BOKOR_MULTIPOWER = "1674532452187"   # "Vodou Powers - gris gris bag powders"
SCORPION = "1674684810701"           # Scorpion Pepper powder, Flash, 37
DIGITALIS = "1674701239535"          # Digitalis dust, RKA, 37
NETTLE = "1686189167441"             # Stinging Nettle Powder, Drain, 41
MOJO_HAND = "1674562160366"          # Mojo Hand, HA, not in the Multipower

RAVEL = "Ravel, The Unmade Man"     # his name on the build
STRING = "He's string: no skin, no lungs, no organs."
POWDERS = "Bokor's powders go in by breath, through the skin or swallowed."


def _bokor(slot: str, points: int) -> HeroCombatant:
    hero = replace(HeroCombatant.from_build(require_authored("Bokor"), id="bokor"),
                   side=Side.named("bokor"))
    split = {s.slot_id: 0 for f in hero.framework_view()
             if f.framework_id == BOKOR_MULTIPOWER for s in f.slots}
    split[slot] = points
    return replace(hero, state=replace(hero.state,
                                       slot_points={BOKOR_MULTIPOWER: split}))


def _ravel(*, in_hero_id: bool = True) -> HeroCombatant:
    hero = replace(HeroCombatant.from_build(require_authored("Ravel"), id="ravel"),
                   side=Side.named("ravel"))
    return replace(hero, state=replace(hero.state, in_hero_id=in_hero_id))


def _session(*, slot: str = SCORPION, points: int = 37, in_hero_id: bool = True):
    template = CombatTemplate.default_6e_superheroic()
    return CombatSession.create(
        id="s", scene=None, template=template, dice_roller=RandomRoller(seed=3),
        combatants=[_ravel(in_hero_id=in_hero_id), _bokor(slot, points)],
    ).start()


def _body(*facts: BodyFact) -> list[Ruling]:
    return [Ruling(power_id=None, fact=f.value, sentence=STRING) for f in facts]


def _routes(*routes: DeliveryRoute, power_id: str = BOKOR_MULTIPOWER) -> list[Ruling]:
    return [Ruling(power_id=power_id, fact=r.value, sentence=POWDERS) for r in routes]


def _ruled(session, *, ravel=(), bokor=()):
    if ravel:
        session = state_rulings(session, "ravel", ravel)
    if bokor:
        session = state_rulings(session, "bokor", bokor)
    return session


def _at_ravel(session):
    return [a for a in _situation_for(session, "bokor").menu if a.target_id == "ravel"]


ALL_THREE = (BodyFact.NO_SKIN, BodyFact.NO_LUNGS, BodyFact.NO_ORGANS)
EVERY_ROUTE = (DeliveryRoute.BREATH, DeliveryRoute.SKIN, DeliveryRoute.INGESTION)


def test_the_vocabulary_closes_one_route_per_fact():
    assert CLOSES == {BodyFact.NO_LUNGS: DeliveryRoute.BREATH,
                      BodyFact.NO_SKIN: DeliveryRoute.SKIN,
                      BodyFact.NO_ORGANS: DeliveryRoute.INGESTION}


def test_bokors_powders_are_withheld_from_a_man_with_no_skin_lungs_or_organs():
    plain = _session()
    assert any(a.kind == "flash" for a in _at_ravel(plain)), \
        "the fixture must offer the Flash before any ruling"

    s = _ruled(plain, ravel=_body(*ALL_THREE), bokor=_routes(*EVERY_ROUTE))
    situation = _situation_for(s, "bokor")
    at_ravel = [a for a in situation.menu if a.target_id == "ravel"]
    assert not [a for a in at_ravel if a.kind == "flash"]
    assert not [a for a in at_ravel if routes_of(s, "bokor", a)]

    assert situation.withheld
    ids = {w.action_id for w in situation.withheld}
    assert f"flash:ravel:{SCORPION}" in ids
    for w in situation.withheld:
        assert isinstance(w, Withheld)
        assert "no skin" in w.reason
        assert "GM ruling" in w.reason
        assert w.reason.startswith(f"Not offered against {RAVEL}: ")
    (flash,) = [w for w in situation.withheld if w.action_id == f"flash:ravel:{SCORPION}"]
    assert flash.reason == (
        f"Not offered against {RAVEL}: Scorpion Pepper powder needs breath, "
        f"skin or ingestion; {RAVEL} has none of them (GM ruling: \"{STRING}\"; "
        "Self-Contained Breathing)")


def test_one_open_route_keeps_the_offer():
    """No skin, but Teddy breathes: one open route and it is offered as
    today."""
    s = _ruled(_session(in_hero_id=False), ravel=_body(BodyFact.NO_SKIN),
               bokor=_routes(DeliveryRoute.SKIN, DeliveryRoute.BREATH))
    situation = _situation_for(s, "bokor")
    assert f"flash:ravel:{SCORPION}" in {a.action_id for a in situation.menu}
    assert situation.withheld == []


def test_self_contained_breathing_closes_breath_in_hero_id_only():
    """Ravel's Life Support is bought Only In Hero ID (6E1 p.247 for the
    Adder; the identity rule is `identity.build_in_play`)."""
    flash = f"flash:ravel:{SCORPION}"

    costumed = _ruled(_session(), bokor=_routes(DeliveryRoute.BREATH))
    assert closed_routes(costumed, "ravel") == frozenset({DeliveryRoute.BREATH})
    situation = _situation_for(costumed, "bokor")
    assert flash not in {a.action_id for a in situation.menu}
    (withheld,) = [w for w in situation.withheld if w.action_id == flash]
    assert withheld.reason.endswith("(Self-Contained Breathing)")
    assert "GM ruling" not in withheld.reason

    teddy = _ruled(_session(in_hero_id=False), bokor=_routes(DeliveryRoute.BREATH))
    assert closed_routes(teddy, "ravel") == frozenset()
    assert flash in {a.action_id for a in _situation_for(teddy, "bokor").menu}


def test_an_attack_with_no_route_ruling_is_untouched():
    s = _ruled(_session(), ravel=_body(*ALL_THREE), bokor=_routes(*EVERY_ROUTE))
    situation = _situation_for(s, "bokor")
    mojo = f"attack:ravel:{MOJO_HAND}"
    (offer,) = [a for a in situation.menu if a.action_id == mojo]
    assert routes_of(s, "bokor", offer) == frozenset()
    assert mojo not in {w.action_id for w in situation.withheld}


@pytest.mark.parametrize("slot, points, kind", [
    (DIGITALIS, 37, "attack"), (NETTLE, 41, "drain"),
])
def test_a_ruling_on_the_multipower_covers_its_slots(slot, points, kind):
    """The ruling names the Multipower; each slot is offered from its own
    id, and the gate reads up to the framework (`parent_id`)."""
    plain = _session(slot=slot, points=points)
    offered = f"{kind}:ravel:{slot}"
    (offer,) = [a for a in _at_ravel(plain) if a.action_id == offered]

    s = _ruled(plain, ravel=_body(*ALL_THREE), bokor=_routes(*EVERY_ROUTE))
    assert routes_of(s, "bokor", offer) == frozenset(EVERY_ROUTE)
    situation = _situation_for(s, "bokor")
    assert offered not in {a.action_id for a in situation.menu}
    assert offered in {w.action_id for w in situation.withheld}


def test_a_ruling_on_the_slot_itself_is_read_before_the_framework():
    s = _ruled(_session(), bokor=[*_routes(DeliveryRoute.SKIN),
                                  *_routes(DeliveryRoute.INGESTION, power_id=SCORPION)])
    (offer,) = [a for a in _at_ravel(s) if a.kind == "flash"]
    assert routes_of(s, "bokor", offer) == frozenset({DeliveryRoute.INGESTION})


def test_rulings_survive_a_replay():
    """What a consumer that persisted the rows as JSON rebuilds."""
    s = _ruled(_session(), ravel=_body(*ALL_THREE), bokor=_routes(*EVERY_ROUTE))
    rebuilt = CombatSession.create(
        id=s.id, combatants=list(s.initial_combatants.values()), scene=None,
        template=s.template, dice_roller=s.dice_roller)
    for event in s.event_log:
        rebuilt = apply_event(rebuilt, from_dict(to_dict(event)))

    for who in ("ravel", "bokor"):
        assert rulings_for(rebuilt, who) == rulings_for(s, who)
        assert rulings_for(rebuilt, who)
    assert ([w.action_id for w in _situation_for(rebuilt, "bokor").withheld]
            == [w.action_id for w in _situation_for(s, "bokor").withheld])


def test_nothing_stated_is_nothing_ruled():
    s = _session()
    assert rulings_for(s, "ravel") == ()
    assert _situation_for(s, "bokor").withheld == []


def test_rulings_are_stated_once_per_fighter():
    s = _ruled(_session(), ravel=_body(BodyFact.NO_SKIN))
    with pytest.raises(ValueError, match="already"):
        state_rulings(s, "ravel", _body(BodyFact.NO_LUNGS))


def test_rulings_are_fixed_once_the_fight_has_moved():
    """Spec §7a: an edit mid-fight applies from the next fight. Any row
    other than SessionStarted / RulingsStated closes the window; here the
    first Phase's own rows, from the loop."""
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import FirstLegalChooser, run_phase

    s = _session()
    ravel = s.combatants["ravel"]
    # Ravel's frameworks split ahead (all off), so first-legal is not asked
    # for an opening split it will not choose (6E1 p.404-406).
    split = {f.framework_id: {sl.slot_id: 0 for sl in f.slots}
             for f in ravel.framework_view()}
    s = replace(s, combatants={**s.combatants, "ravel": replace(
        ravel, state=replace(ravel.state, slot_points=split))})
    s = _ruled(s, ravel=_body(BodyFact.NO_SKIN))
    moved = run_phase(Encounter(id="e", turn=1, segment=12, sessions=[s]), FirstLegalChooser(),
                      roller=RandomRoller(seed=1)).session
    late = [e.kind for e in moved.event_log
            if e.kind not in ("SessionStarted", "RulingsStated")]
    assert late, "the Phase must have put rows on the log"
    with pytest.raises(ValueError, match=f"after a {late[0]} row"):
        state_rulings(moved, "bokor", _routes(DeliveryRoute.SKIN))

    # A valid log, rulings first and then the fight, still replays.
    rebuilt = CombatSession.create(
        id=moved.id, combatants=list(moved.initial_combatants.values()),
        scene=None, template=moved.template, dice_roller=moved.dice_roller)
    for event in moved.event_log:
        rebuilt = apply_event(rebuilt, from_dict(to_dict(event)))
    assert rulings_for(rebuilt, "ravel") == rulings_for(moved, "ravel")
    assert len(rebuilt.event_log) == len(moved.event_log)


def test_rulings_name_a_fighter_in_the_fight():
    with pytest.raises(KeyError, match="nobody"):
        state_rulings(_session(), "nobody", _body(BodyFact.NO_SKIN))


def test_a_power_ruling_names_a_power_he_has():
    with pytest.raises(ValueError, match="1234"):
        state_rulings(_session(), "bokor", _routes(DeliveryRoute.SKIN, power_id="1234"))


def test_a_fact_must_be_in_the_vocabulary():
    with pytest.raises(ValueError, match="no_blood"):
        Ruling(power_id=None, fact="no_blood", sentence="x")
    with pytest.raises(ValueError):
        Ruling(power_id=BOKOR_MULTIPOWER, fact=BodyFact.NO_SKIN.value, sentence="x")
    with pytest.raises(ValueError):
        Ruling(power_id=None, fact=DeliveryRoute.SKIN.value, sentence="x")
    with pytest.raises(ValueError, match="sentence"):
        Ruling(power_id=None, fact=BodyFact.NO_SKIN.value, sentence="  ")


def test_the_brief_shows_rulings_and_what_was_withheld():
    s = _ruled(_session(), ravel=_body(*ALL_THREE), bokor=_routes(*EVERY_ROUTE))
    page = Brief(_situation_for(s, "bokor")).render()
    assert f'GM ruling: "{STRING}"' in page
    assert f'GM ruling: "{POWDERS}"' in page
    assert f"Not offered against {RAVEL}: Scorpion Pepper powder needs" in page

    plain = Brief(_situation_for(_session(), "bokor")).render()
    assert "GM ruling" not in plain
    assert "Not offered" not in plain
