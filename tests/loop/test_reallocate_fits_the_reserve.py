"""A reallocation the reserve can actually pay for.

Power Lad chose `reallocate_slots` 152 times in one fight and the engine
refused it 152 times. `decided: False, winner: None, phases: 289` --- the
O.K. Corral ran to `max_turns` and never resolved, because the menu kept
offering an action the resolver kept rejecting and nothing on either side
learned.

The offer named EVERY slot of the framework at once:

    reallocate_slots:{framework}:{slot,slot,slot,slot,slot}

Power Lad's Brick Tricks reserve is 45 Active Points and each of its five
slots draws 44-45, so that set draws 224 against 45. `validate_allocation`
raises `ReserveExceeded`, correctly --- 6E1 p.204 makes the reserve the
total a Multipower's slots may draw AT ONCE, and it is the whole reason a
framework costs less than buying the powers outright.

The resolver's own comment says "`enumerate_actions` gates which slots it
OFFERS, but an offer is not a permission slip". The gate was not there.
And the summary said "choose which slots are active this phase", which a
chooser cannot do: it returns an action_id from the menu, so an id naming
all five slots offers no choice at all.

Fixed by asking the same function the resolver asks. The menu and the
engine must not hold separate opinions about what the reserve can pay
for --- the recurring lesson of this whole engine.
"""
from __future__ import annotations

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import parse_reallocation, validate_allocation
from kirby_combat.side import Side


def _framework(reserve, slot_points):
    """A Multipower whose slots cannot all be up at once --- the ordinary
    case, and the whole point of a reserve.

    The engine's own `FrameworkView` and `SlotView` rather than a double,
    so this test cannot pass against a shape enumeration does not see.
    """
    from kirby_combat.models import FrameworkView, SlotView

    return FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Brick Tricks",
        kind="multipower", reserve_or_pool=reserve,
        slots=[SlotView(slot_id=f"s{i}", name=f"s{i}", active_points=p,
                        variable=False, kind="attack")
               for i, p in enumerate(slot_points, 1)],
    )


def _actor(framework):
    c = fighter("lad", side=Side.named("x"))
    c.framework_view = lambda: [framework]                  # type: ignore[method-assign]
    return c


def _offers(framework):
    menu = enumerate_actions(_actor(framework), [fighter("foe", side=Side.named("y"))])
    return [a for a in menu if a.kind == "reallocate"]


def test_it_does_not_offer_a_set_the_reserve_cannot_pay_for():
    """Five 45-point slots against a 45-point reserve is 224 of 45."""
    offers = _offers(_framework(45, [45, 45, 45, 44, 45]))
    for offer in offers:
        _, slot_ids = parse_reallocation(offer.action_id)
        drawn = sum(45 if s != "s4" else 44 for s in slot_ids)
        assert drawn <= 45, f"{offer.action_id} draws {drawn} against a reserve of 45"


def test_it_still_offers_something_when_only_one_slot_fits():
    """A fighter whose Multipower can run exactly one power at a time must
    still be able to change WHICH one --- that is what a Multipower is."""
    offers = _offers(_framework(45, [45, 45, 45, 44, 45]))
    assert len(offers) == 5, "one per slot he can actually switch to"


def test_a_slot_bigger_than_the_whole_reserve_is_never_offered():
    """Buildable, and it can never be turned on."""
    offers = _offers(_framework(30, [60, 20]))
    for offer in offers:
        _, slot_ids = parse_reallocation(offer.action_id)
        assert "s1" not in slot_ids


def test_a_framework_whose_slots_all_fit_is_offered_them_together():
    """The other ordinary case: a generous reserve, and no reason to make
    a fighter switch one at a time."""
    offers = _offers(_framework(100, [20, 30]))
    assert any(set(parse_reallocation(o.action_id)[1]) == {"s1", "s2"}
               for o in offers)


def test_every_offer_the_menu_makes_would_be_accepted():
    """The guard that matters, and the one this engine keeps needing: ask
    the resolver's own validator, so the two cannot disagree."""
    framework = _framework(45, [45, 45, 45, 44, 45])
    actor = _actor(framework)
    for offer in _offers(framework):
        framework_id, slot_ids = parse_reallocation(offer.action_id)
        validate_allocation(actor, framework_id, slot_ids)      # must not raise


# ---- and it must CHANGE something ----

def _offers_with_active(framework, active):
    """As the loop calls it: `slot_allocation` carries what is already on."""
    actor = _actor(framework)
    points = {sl.slot_id: sl.active_points for sl in framework.slots}
    menu = enumerate_actions(
        actor, [fighter("foe", side=Side.named("y"))],
        slot_allocation={framework.framework_id: (
            framework.reserve_or_pool,
            sum(points[s] for s in active),
            set(active),
            points,
        )},
    )
    return [a for a in menu if a.kind == "reallocate"]


def test_it_does_not_offer_the_allocation_already_in_force():
    """The second half of the same livelock. Once the offer FIT the
    reserve it stopped being refused and started succeeding --- and Power
    Lad reallocated to the slot he already had, 152 times, for 289
    Phases. An action that changes nothing, chosen for ever, is the cover
    trap one more time.
    """
    framework = _framework(45, [45, 45, 45, 44, 45])
    offers = _offers_with_active(framework, ["s1"])
    for offer in offers:
        _, slot_ids = parse_reallocation(offer.action_id)
        assert set(slot_ids) != {"s1"}, (
            f"{offer.action_id} switches to what is already switched on"
        )


def test_the_other_slots_are_still_offered():
    """Guards the guard: he must still be able to change weapon."""
    framework = _framework(45, [45, 45, 45, 44, 45])
    assert len(_offers_with_active(framework, ["s1"])) == 4


def test_a_fighter_with_no_attack_is_offered_his_weapon_first():
    """Why the O.K. Corral livelocked, once the other two causes were out.

    NO TACTIC EMITS `reallocate` --- a grep of the catalogue finds none.
    It was the FALLBACK choosing it: Power Lad's claws live in a
    Multipower slot, the slot was not active, so he had no attack offers,
    so no tactic's first step matched the menu, so `TacticChooser` fell
    through to `FirstLegalChooser`, which takes menu[0]. That was a
    reallocation to an arbitrary slot --- and next Phase, the same.

    A fighter holding nothing has one thing worth doing: pick up
    something that fights. `SlotView` already knows which slots are
    attacks, so the menu can put those first instead of leaving a
    superhuman to shuffle his own powers for two hundred Phases.
    """
    from kirby_combat.models import FrameworkView, SlotView

    framework = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Brick Tricks",
        kind="multipower", reserve_or_pool=45,
        slots=[
            SlotView(slot_id="legs", name="Leaping", active_points=44,
                     variable=False, kind="movement"),
            SlotView(slot_id="claws", name="Rending", active_points=45,
                     variable=False, kind="attack"),
        ],
    )
    from fixtures.synthetic_hero import synthetic_combatant

    # STR 1 deliberately: enumeration builds a bare-STR strike for anyone
    # with STR >= 5, and that synthetic view carries no source id, so
    # enumerating it raises. A fighter whose only weapon is a slot is the
    # case under test, and this is the way to construct one.
    actor = synthetic_combatant(
        id="lad", name="lad", ocv=8, dcv=6, omcv=5, dmcv=5, spd=4, dex=20,
        ego=10, str_=1, con=15, pre=10, rec=5, pd=2, ed=2, rpd=0, red=0,
        md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=10, max_end=40,
        current_stun=40, current_body=10, current_end=40,
        side=Side.named("x"), attacks=[],
    )
    actor.framework_view = lambda: [framework]              # type: ignore[method-assign]
    assert not actor.attacks, "this fighter has nothing to hit with"
    offers = [a for a in enumerate_actions(
        actor, [fighter("foe", side=Side.named("y"))]) if a.kind == "reallocate"]
    first_ids = parse_reallocation(offers[0].action_id)[1]
    assert "claws" in first_ids, (
        "a man with no attack should be shown the slot that gives him one"
    )


def test_it_does_not_offer_to_disarm_a_fighter_mid_fight():
    """The mechanism behind the O.K. Corral livelock, finally.

    Power Lad's claws are a Multipower slot. With the slot ON he has
    attacks, tactics match, and he fights. The no-op filter then removes
    CLAWS from his reallocate offers --- correctly, he already has it ---
    leaving only switches that take his weapon away. On a Phase where no
    tactic matched, the fallback chooser took the first thing on the menu
    and disarmed him. Next Phase he switched back. 289 Phases, 152
    reallocations, `decided: False`.

    No tactic emits `reallocate`, so this offer is ONLY ever taken by the
    fallback --- which is exactly the chooser least able to judge whether
    throwing your only weapon away mid-fight is a good idea.

    A man with enemies in front of him is not offered the chance to put
    his weapon down. Where every option disarms him, the offer is
    withheld entirely rather than reordered: last on the menu is still
    reachable, and the fallback reaches everything eventually.
    """
    from kirby_combat.models import FrameworkView, SlotView

    framework = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Brick Tricks",
        kind="multipower", reserve_or_pool=45,
        slots=[
            SlotView(slot_id="claws", name="Rending", active_points=45,
                     variable=False, kind="attack"),
            SlotView(slot_id="legs", name="Leaping", active_points=44,
                     variable=False, kind="movement"),
            SlotView(slot_id="skin", name="Armour", active_points=45,
                     variable=False, kind="defense"),
        ],
    )
    # Claws are ON, and they are the only thing he can hit with.
    offers = _offers_with_active(framework, ["claws"])
    assert offers == [], (
        "every remaining switch would disarm him while enemies are up"
    )


def test_he_may_trade_his_weapon_for_the_legs_to_reach_anybody():
    """The superleap trade, and the case the disarm guard got wrong.

    PeterB: "powerlad can also superleap". His claws and his 69-point
    Leaping are BOTH Brick Tricks slots, 44-45 points each against a
    45-point reserve --- so he can have the weapon or the legs and never
    both. Crossing a gap MEANS disarming, and that is not a mistake, it is
    what a Multipower is for.

    The guard added earlier today forbade any switch that leaves a man
    weaponless with enemies up. Right when he can already reach somebody;
    wrong when standing still is the alternative --- which is exactly the
    7.8m standoff that stalled the benchmark.

    So the guard now asks whether he can hit ANYBODY on this menu. If he
    can, putting the weapon down is a bad idea and is not offered. If he
    cannot, every switch is on the table, including the one that trades
    claws for the legs to close the distance.
    """
    from kirby_combat.models import FrameworkView, SlotView

    framework = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Brick Tricks",
        kind="multipower", reserve_or_pool=45,
        slots=[
            SlotView(slot_id="claws", name="Rending", active_points=45,
                     variable=False, kind="attack"),
            SlotView(slot_id="legs", name="Iron Grasshopper",
                     active_points=44, variable=False, kind="movement"),
        ],
    )
    from fixtures.synthetic_hero import synthetic_combatant

    # Claws are ON but he has no attack he can actually make --- nobody in
    # reach. `attacks` is empty, which is what "nothing on this menu can
    # hit" looks like from the inside.
    actor = synthetic_combatant(
        id="lad", name="lad", ocv=8, dcv=6, omcv=5, dmcv=5, spd=4, dex=20,
        ego=10, str_=1, con=15, pre=10, rec=5, pd=2, ed=2, rpd=0, red=0,
        md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=10, max_end=40,
        current_stun=40, current_body=10, current_end=40,
        side=Side.named("x"), attacks=[],
    )
    actor.framework_view = lambda: [framework]          # type: ignore[method-assign]
    points = {sl.slot_id: sl.active_points for sl in framework.slots}
    menu = enumerate_actions(
        actor, [fighter("foe", side=Side.named("y"))],
        slot_allocation={"fw1": (45, 45, {"claws"}, points)},
    )
    offers = [a for a in menu if a.kind == "reallocate"]
    assert any("legs" in parse_reallocation(o.action_id)[1] for o in offers), (
        "he cannot reach anybody and must be allowed to pick up his legs"
    )
