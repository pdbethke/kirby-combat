"""A reallocation the reserve can actually pay for.

Power Lad chose `reallocate_slots` 152 times in one fight and the engine
refused it 152 times. `decided: False, winner: None, phases: 289` --- the
O.K. Corral ran to `max_turns` and never resolved, because the menu kept
offering an action the resolver kept rejecting and nothing on either side
learned.

The offer named EVERY slot of the framework at once:

    reallocate_slots:{framework}:{slot,slot,slot,slot,slot}

Power Lad's Brick Tricks reserve is 45 Active Points and each of its five
slots draws 44-45, so that set draws 224 against 45. `validate_split`
raises `ReserveExceeded`, correctly --- 6E1 p.404 makes the reserve the
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

from dataclasses import replace

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import split_of_action, validate_split
from kirby_combat.side import Side


def _on(offer) -> set[str]:
    """The slots a whole-set offer switches on: its id is a completed split
    (``reallocate_slots:<fw>:split=<sid>@<AP>+...``)."""
    fw, tail = split_of_action(offer.action_id, "reallocate_slots")
    assert fw, offer.action_id
    return {t.split("@")[0] for t in tail.split("+") if t and int(t.split("@")[1]) > 0}


def _opened(c, framework, active=()):
    """The framework opened with ``active`` on at full AP, the rest off: a
    re-split is offered only once the fight has stated a split."""
    return replace(c, state=replace(c.state, slot_points={framework.framework_id: {
        sl.slot_id: (sl.active_points if sl.slot_id in active else 0)
        for sl in framework.slots}}))


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


def _actor(framework, active=()):
    c = _opened(fighter("lad", side=Side.named("x")), framework, active)
    c.framework_view = lambda: [framework]                  # type: ignore[method-assign]
    return c


def _offers(framework):
    menu = enumerate_actions(_actor(framework), [fighter("foe", side=Side.named("y"))])
    return [a for a in menu if a.kind == "reallocate"]


def test_it_does_not_offer_a_set_the_reserve_cannot_pay_for():
    """Five 45-point slots against a 45-point reserve is 224 of 45."""
    offers = _offers(_framework(45, [45, 45, 45, 44, 45]))
    for offer in offers:
        slot_ids = _on(offer)
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
        assert "s1" not in _on(offer)


def test_a_framework_whose_slots_all_fit_is_offered_them_together():
    """The other ordinary case: a generous reserve, and no reason to make
    a fighter switch one at a time."""
    offers = _offers(_framework(100, [20, 30]))
    assert any(_on(o) == {"s1", "s2"} for o in offers)


def test_every_offer_the_menu_makes_would_be_accepted():
    """The guard that matters, and the one this engine keeps needing: ask
    the resolver's own validator, so the two cannot disagree."""
    framework = _framework(45, [45, 45, 45, 44, 45])
    for offer in _offers(framework):
        slot_ids = _on(offer)
        # An offered set, each slot at its full Active Points, must be a
        # legal split.
        validate_split(framework, {
            sl.slot_id: sl.active_points for sl in framework.slots
            if sl.slot_id in slot_ids})      # must not raise


# ---- and it must CHANGE something ----

def _offers_with_active(framework, active):
    """What is already on is the split folded onto him."""
    actor = _actor(framework, active)
    menu = enumerate_actions(actor, [fighter("foe", side=Side.named("y"))])
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
        assert _on(offer) != {"s1"}, (
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
    actor = _opened(actor, framework)
    actor.framework_view = lambda: [framework]              # type: ignore[method-assign]
    assert not actor.attacks, "this fighter has nothing to hit with"
    offers = [a for a in enumerate_actions(
        actor, [fighter("foe", side=Side.named("y"))]) if a.kind == "reallocate"]
    assert "claws" in _on(offers[0]), (
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
    actor = _opened(actor, framework, {"claws"})
    actor.framework_view = lambda: [framework]          # type: ignore[method-assign]
    menu = enumerate_actions(actor, [fighter("foe", side=Side.named("y"))])
    offers = [a for a in menu if a.kind == "reallocate"]
    assert any("legs" in _on(o) for o in offers), (
        "he cannot reach anybody and must be allowed to pick up his legs"
    )


def test_the_offer_names_its_slots_and_what_it_switches_off():
    """A chooser returns an id from the menu; the words beside it are all it
    reads. "make active: s2(45pts)" asked it to look an id up. A whole-set
    offer (every slot fixed: a variable one gets the re-split offer
    instead) names each slot, what it draws, and which slots go off."""
    from kirby_combat.models import FrameworkView, SlotView

    fw = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Wind Magic",
        kind="multipower", reserve_or_pool=60,
        slots=[SlotView(slot_id="s1", name="Lightning Bolt", active_points=60,
                        variable=False, kind="attack"),
               SlotView(slot_id="s2", name="Wall Of Wind", active_points=45,
                        variable=False, kind="other")],
    )
    # His Wall is up and he switches to the Bolt (a switch AWAY from his
    # only attack slot is withheld from an armed man: the O.K. Corral guard).
    actor = _actor(fw, {"s2"})
    menu = enumerate_actions(actor, [fighter("foe", side=Side.named("y"))])
    words = [a.summary for a in menu if a.kind == "reallocate"]
    assert any("Lightning Bolt (fixed, 60 pts)" in w
               and "switches off Wall Of Wind" in w for w in words), words


def test_a_switch_that_ends_a_kept_up_field_says_so():
    """6E1 p.402: the Constant power on a slot that loses the reserve stops."""
    from kirby_combat.enumeration import _reallocate_summary

    text = _reallocate_summary(
        "Shadows", 60, 60, ["blast"], ["dark"],
        names={"blast": "Shadow Bolt", "dark": "Pall"},
        kinds={"blast": "variable", "dark": "fixed"},
        points={"blast": 60, "dark": 40},
        kept_on={"dark": ["a Darkness field"]},
    )
    assert "switches off Pall" in text
    assert "ends a Darkness field (Pall)" in text and "6E1 p.402" in text


def test_the_brief_shows_the_reserve_in_use_and_what_fixed_means():
    """The juggling is the chooser's: it must see what is drawn and what is
    free, and what a fixed and a variable slot are (6E1 p.404-405)."""
    import uuid
    from datetime import UTC, datetime

    from conftest import session_of
    from kirby_combat.brief_detail import framework_lines
    from kirby_combat.loop.chooser import PhaseSituation
    from kirby_combat.hero_view import SlotEffect, SlotStep
    from kirby_combat.models import FrameworkView, PricedSlotView, SlotView
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import SlotsAllocated, make_author_engine

    fw = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Wind Magic",
        kind="multipower", reserve_or_pool=60,
        slots=[SlotView(slot_id="s1", name="Wind Riding", active_points=60,
                        variable=True, kind="other"),
               SlotView(slot_id="s3", name="Wall Of Wind", active_points=45,
                        variable=False, kind="other")],
    )
    actor = _actor(fw)
    s = session_of(actor, fighter("foe", side=Side.named("y")))
    s = apply_event(s, SlotsAllocated(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        combatant_id="lad", framework_id="fw1",
        slot_points={"s1": 0, "s3": 45}, opening=True,
    ))
    # The fold replaces the combatant, so the (synthetic) view is attached
    # after; the brief reads each slot's current effect off the priced one.
    priced = FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Wind Magic",
        kind="multipower", reserve_or_pool=60,
        slots=[PricedSlotView(slot_id=sl.slot_id, name=sl.name,
                              active_points=sl.active_points,
                              variable=sl.variable, kind=sl.kind,
                              steps=(SlotStep(0, "", SlotEffect.nothing()),
                                     SlotStep(sl.active_points, f"{sl.name} up",
                                              SlotEffect.nothing())))
               for sl in fw.slots],
    )
    s.combatants["lad"].framework_view = lambda: [fw]       # type: ignore[method-assign]
    s.combatants["lad"].priced_framework_view = lambda: [priced]  # type: ignore[method-assign]
    lines = framework_lines(PhaseSituation(actor=s.combatants["lad"], menu=[], session=s))
    assert "  45 of 60 points in use, 15 free" in lines
    assert any("fixed slot draws its full Active Points" in ln and "6E1 p.404-405" in ln
               for ln in lines)
    assert "  Wall Of Wind: 45 AP, fixed, now Wall Of Wind up (45 pts)" in lines
