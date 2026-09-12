"""A grabbed man had no way to struggle.

The escape ladder in `enumerate_actions` is keyed to `physical_entangle`,
so it answers 6E1 p.217's Entangle and nothing else. A man held by a
GRAB --- 6E2 p.64 --- was offered no escape at all, while
`Grab.escape(session, escaper_id=, escaper_str=, grabber_str=)` sat in
the package unused, complete with the tie rule ("grabber wins ties").

6E2 p.64 is explicit that the struggle is immediate:

    "To Grab an opponent, a character must make an Attack Roll with
     appropriate modifiers. If successful, he has Grabbed his opponent.
     (As described below under Escaping From Grabs, the victim
     immediately gets a Casual STR roll to break free, if desired.)"

TWO OFFERS, NOT THE ENTANGLE LADDER. An Entangle escape chews through
BODY and DEF; a Grab escape is STR against the grabber's STR. Reusing the
Entangle offers would put an Entangle's numbers in a Grab's summary and
route a STR contest through `str_escape_dice`. So this is its own pair,
and `escape:grab:*` ids keep the resolver's routing unambiguous.
"""
from __future__ import annotations

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat.enumeration import enumerate_actions


def _escapes(grabbed_by):
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4)
    actor = _combatant(id="frank", powers=[gun])
    enemy = _combatant(id="doc", powers=[gun])
    return [a for a in enumerate_actions(actor, [enemy], grabbed_by=grabbed_by,
                                         distances={"doc": 1.0})
            if a.kind == "escape_str"]


def test_a_free_man_is_offered_no_escape():
    assert _escapes(None) == []


def test_a_grabbed_man_may_struggle():
    assert _escapes("doc") != []


def test_both_the_casual_and_the_full_attempt_are_offered():
    """6E2 p.64 gives the victim a Casual STR roll immediately, and a
    full-STR attempt costs the Phase. They are different prices and the
    chooser must be able to pick either."""
    ids = {a.action_id for a in _escapes("doc")}
    assert "escape:grab:casual" in ids
    assert "escape:grab:full" in ids


def test_the_offer_names_the_grabber():
    """A STR contest is against a specific man, so the resolver has to
    know whose STR to beat."""
    assert all(a.target_id == "doc" for a in _escapes("doc"))


def test_the_summaries_do_not_talk_about_entangles():
    """Reusing the Entangle ladder would put an Entangle's BODY and DEF
    in a Grab's summary."""
    for a in _escapes("doc"):
        assert "Entangle" not in a.summary


def test_the_driver_asks_who_is_holding_the_actor():
    import inspect

    from kirby_combat.loop import run

    assert "grabbed_by=" in inspect.getsource(run), (
        "run.py must pass grabbed_by or a held man can never struggle"
    )


# ---- and it has to RESOLVE as a Grab, not as an Entangle ----

def _fight():
    """A session where doc has Grabbed frank."""
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.actions.grab import Grab
    from kirby_combat.session import CombatSession
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    def man(id_, str_):
        return synthetic_combatant(
            id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=18,
            ego=15, str_=str_, con=15, pre=15, rec=5, pd=5, ed=5, rpd=0,
            red=0, md=5, power_defense=0, flash_defense=0,
            max_stun=30, max_body=15, max_end=30,
            current_stun=30, current_body=15, current_end=30)

    s = CombatSession.create(
        id="s", combatants=[man("doc", 10), man("frank", 20)], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=3)).start()
    s, _ = Grab.declare_and_resolve(
        s, attacker_id="doc", target_id="frank",
        attacker_str=10, target_str=20, attacker_ocv=8, target_dcv=0,
        attack_roll=3)
    return s


def _struggle(session, action_id: str):
    import kirby_combat.loop.resolvers  # noqa: F401  (registers the kinds)
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    action = LegalAction(
        action_id=action_id, kind="escape_str", target_id="doc",
        power_xmlid=None, power_name=None, summary="Break free")
    return resolve_chosen(
        session, session.combatants["frank"], action,
        template=CombatTemplate.default_6e_superheroic(),
        roller=RandomRoller(seed=3))


def test_the_stronger_man_breaks_the_hold():
    """`Grab.escape`: the escaper wins iff his STR is greater --- the
    grabber wins ties. Frank at STR 20 beats Doc at STR 10."""
    from kirby_combat.actions.grab import Grab

    session = _fight()
    assert Grab.is_grabbed(session, "frank")[0] is True

    out = _struggle(session, "escape:grab:full")
    assert Grab.is_grabbed(out.session, "frank")[0] is False


def test_it_does_not_go_through_the_entangle_path():
    """Routing a STR contest through `str_escape_dice` would roll dice
    against an Entangle that does not exist. The resolver must pick the
    Grab branch off the action_id."""
    out = _struggle(_fight(), "escape:grab:casual")
    assert out.result is not None
