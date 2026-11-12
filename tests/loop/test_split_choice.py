"""A split is stated in points and checked against the book (6E1 p.404-406).

Kerendor's Multipower: reserve 60, `wind` variable 60, `bolt` variable 60,
`wall` fixed 45. The seat answers an offer's id plus
``=<slot>@<points>+...``; every rule break is refused both where the answer
is validated (`validate_choice`) and where it is resolved, because an offer
is not a permission slip.
"""
from __future__ import annotations

import pytest

from conftest import fighter, session_of            # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.framework import (
    SplitChoice, SlotTerms, ReserveExceeded, reallocated_this_phase,
    split_choice_of, validate_split,
)
from kirby_combat.loop.chooser import InvalidChoice, validate_choice
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.models import FrameworkView, SlotView
from kirby_combat.side import Side

OFFER = "reallocate_slots:kmp:split"


def _view():
    return FrameworkView(
        framework_id="kmp", xmlid="MULTIPOWER", name="Kerendor's Magic",
        kind="multipower", reserve_or_pool=60,
        slots=[SlotView("wind", "Wind", 60, True, "other"),
               SlotView("bolt", "Bolt", 60, True, "attack"),
               SlotView("wall", "Wall", 45, False, "other")])


def _choice(current=None):
    return split_choice_of(_view(), current or {})


def _offer(current=None):
    return LegalAction(action_id=OFFER, kind="reallocate", summary="split", target_id=None,
                       power_xmlid="", power_name="", choice=_choice(current))


def _world():
    actor = fighter("kerendor", side=Side.named("x"))
    actor.framework_view = lambda: [_view()]            # type: ignore[method-assign]
    s = session_of(actor, fighter("foe", side=Side.named("y")))
    s.combatants["kerendor"].framework_view = lambda: [_view()]  # type: ignore[method-assign]
    return s, s.combatants["kerendor"]


def _resolve(s, actor, action_id, kind="reallocate"):
    from kirby_dice import RandomRoller
    act = LegalAction(action_id=action_id, kind=kind, summary="x", target_id=None,
                    power_xmlid="", power_name="")
    return resolve_chosen(s, actor, act, template=s.template, roller=RandomRoller(seed=1))


BREAKS = ["wall@30", "bolt@61", "bolt@-5", "ghost@10", "wall@45+bolt@20", "bolt@x",
          "bolt@10+bolt@20",
          "bolt@ 40", "bolt@4_0", "bolt@10++wind@5", "bolt@\u0664\u0660"]


def test_answer_and_parse_round_trip():
    c = _choice()
    tail = c.answer({"bolt": 40, "wind": 20})
    assert tail == "=bolt@40+wind@20"
    assert c.parse(tail[1:]) == {"wind": 20, "bolt": 40, "wall": 0}


def test_validate_choice_completes_a_legal_split():
    done = validate_choice(OFFER + "=bolt@40+wind@20", [_offer()])
    assert done.action_id == OFFER + "=bolt@40+wind@20"


def test_the_bare_offer_is_not_an_answer():
    with pytest.raises(InvalidChoice):
        validate_choice(OFFER, [_offer()])


@pytest.mark.parametrize("tail", BREAKS)
def test_rule_breaks_are_refused_at_validate_choice(tail):
    with pytest.raises(InvalidChoice):
        validate_choice(f"{OFFER}={tail}", [_offer()])


@pytest.mark.parametrize("tail", BREAKS)
def test_rule_breaks_are_refused_at_the_resolver(tail):
    s, actor = _world()
    s = _open(s, actor)
    with pytest.raises(UnresolvableAction):
        _resolve(s, actor, f"{OFFER}={tail}")


def _open(s, actor, tail="wall@45"):
    return _resolve(s, actor, f"opening_split:kmp:split={tail}", "opening_split").session


def test_off_step_points_are_legal():
    assert _choice().parse("bolt@9+wind@51") == {"wind": 51, "bolt": 9, "wall": 0}
    assert validate_split(_view(), {"bolt": 9, "wind": 51}) == 60


def test_validate_split_raises_the_named_errors():
    with pytest.raises(ReserveExceeded):
        validate_split(_view(), {"wall": 45, "bolt": 20})
    with pytest.raises(KeyError):
        validate_split(_view(), {"ghost": 1})
    with pytest.raises(ValueError):
        validate_split(_view(), {"wall": 30})


def test_the_split_already_in_force_is_refused():
    with pytest.raises(ValueError):
        _choice({"wall": 45}).parse("wall@45")
    with pytest.raises(InvalidChoice):
        validate_choice(f"{OFFER}=wall@45", [_offer({"wall": 45})])
    s, actor = _world()
    s = _open(s, actor)
    with pytest.raises(UnresolvableAction):
        _resolve(s, actor, f"{OFFER}=wall@45")


def test_resolving_emits_slots_allocated_and_folds_it():
    s, actor = _world()
    s = _open(s, actor)
    r = _resolve(s, actor, f"{OFFER}=bolt@40+wind@20")
    evt = [e for e in r.events if e.kind == "SlotsAllocated"]
    assert len(evt) == 1
    assert evt[0].slot_points == {"bolt": 40, "wind": 20, "wall": 0}
    assert evt[0].opening is False
    assert r.session.combatants["kerendor"].state.slot_points["kmp"] == {
        "bolt": 40, "wind": 20, "wall": 0}
    resolved = [e for e in r.events if e.kind == "ActionResolved"][0]
    assert resolved.result_payload["active_points_drawn"] == 60


def test_an_opening_is_not_a_resplit():
    s, actor = _world()
    r = _resolve(s, actor, "opening_split:kmp:split=wall@45", "opening_split")
    evt = [e for e in r.events if e.kind == "SlotsAllocated"][0]
    assert evt.opening is True
    assert not reallocated_this_phase(r.session, "kerendor")
    # a second opening, and a re-split before any opening, are both refused
    with pytest.raises(UnresolvableAction):
        _resolve(r.session, actor, "opening_split:kmp:split=bolt@10", "opening_split")
    s2, a2 = _world()
    with pytest.raises(UnresolvableAction):
        _resolve(s2, a2, f"{OFFER}=bolt@10")
    r2 = _resolve(r.session, actor, f"{OFFER}=bolt@10")
    assert reallocated_this_phase(r2.session, "kerendor")


def test_the_legacy_slot_list_id_is_refused():
    s, actor = _world()
    s = _open(s, actor)
    with pytest.raises(UnresolvableAction):
        _resolve(s, actor, "reallocate_slots:kmp:bolt,wind")


def test_an_empty_whole_tail_means_every_slot_off():
    assert _choice({"wall": 45}).parse("") == {"wind": 0, "bolt": 0, "wall": 0}


def test_an_actor_not_in_the_session_is_refused():
    s, actor = _world()
    stranger = fighter("stranger", side=Side.named("x"))
    stranger.framework_view = lambda: [_view()]         # type: ignore[method-assign]
    with pytest.raises(UnresolvableAction):
        _resolve(s, stranger, "opening_split:kmp:split=wall@45", "opening_split")
