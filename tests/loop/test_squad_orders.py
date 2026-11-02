"""A squad leader's orders (squad tactics spec, section 4, "Orders").

At the top of his own Phase the leader's seat is asked `give_orders(page)`;
the engine validates what comes back, records it as `SquadOrdersGiven`, and
every member reads his team's order off the log. `order_fit` says whether
an offer carries it out. The order is a fact for him, never a cut of his
menu, and giving it takes no time (a Zero Phase RULING on 6E2 p.25).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from kirby_dice import RandomRoller
from shaped import armed, encounter_on, scene_with, shaped_blast

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.run import _situation_for
from kirby_combat.scene.scene import Position, Wall
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import VitalsChanged, make_author_engine
from kirby_combat.session.involvement import events_involving
from kirby_combat.side import Side
from kirby_combat.squads import (
    KEEP_ORDERS, FireTeam, InvalidOrders, OrdersPage, Squad, SquadOrders,
    TeamTask, leader_of, name_leaders, order_fit, orders_for, orders_page,
    record_orders, validate_orders,
)

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _bolt():
    return shaped_blast("bolt", 4, name="Bolt", range_m=100, is_ranged=True)


def _encounter(positions, *, squad="alpha", walls=(), villains=("her",)):
    """``l`` (seated first, so he leads on the last tie), ``b`` and ``c`` of
    squad alpha against ``villains``. ``l`` has the best DEX and acts first."""
    people = [armed(v, _bolt(), side=VILLAINS, dex=10) for v in villains]
    for i, m in enumerate(m for m in positions if m not in villains):
        people.append(armed(m, _bolt(), side=HEROES, dex=30 - i, squad=squad))
    return encounter_on(scene_with(positions, walls=walls), *people)


_PLACES = {"her": (0, 0, 0), "l": (20, 0, 0), "b": (20, 6, 0), "c": (20, -6, 0)}


def _session(positions=_PLACES, **kw):
    return name_leaders(_encounter(positions, **kw).sessions[0])


def _team(members, task, *, target_id=None, radius_m=None, position=None):
    return FireTeam(member_ids=tuple(members), task=task, target_id=target_id,
                    radius_m=radius_m, position=position)


def _orders(*teams):
    return SquadOrders(teams=tuple(teams))


def _alpha(session):
    return Squad(name="alpha", side="heroes", member_ids=("l", "b", "c"))


def _page(session, leader="l"):
    return orders_page(session, _alpha(session), leader, situation_for=_situation_for)


def _knock_out(session, cid):
    stun = session.combatants[cid].state.current_stun
    return apply_event(session, VitalsChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_engine(), combatant_id=cid, stun=-stun, body=0, end=0))


class _Leader:
    """Answers `give_orders` with ``orders`` (a SquadOrders, KEEP_ORDERS, or a
    function of the page) and shoots ``her``; records the order of calls."""

    def __init__(self, orders):
        self.orders = orders
        self.calls: list[tuple[str, str]] = []
        self.pages: list[OrdersPage] = []

    def give_orders(self, page):
        self.calls.append(("give_orders", page.leader_id))
        self.pages.append(page)
        return self.orders(page) if callable(self.orders) else self.orders

    def choose(self, situation):
        self.calls.append(("choose", situation.actor.id))
        for a in situation.menu:
            if a.kind == "no_abort":
                return a.action_id
        for a in situation.menu:
            if a.kind == "attack" and a.target_id == "her":
                return a.action_id
        return situation.menu[0].action_id


class _NoOrders:
    """A seat that only picks: no `give_orders`."""

    def choose(self, situation):
        for a in situation.menu:
            if a.kind == "no_abort":
                return a.action_id
        return situation.menu[0].action_id


def _given(session):
    return [e for e in session.event_log if e.kind == "SquadOrdersGiven"]


def _all_focus(page):
    return _orders(_team(page.standing, TeamTask.FOCUS_FIRE, target_id="her"))


# ── Asked at the top of his own Phase ──────────────────────────────────────


def test_leader_is_asked_before_his_pick():
    seat = _Leader(_all_focus)
    phase = run_phase(_encounter(_PLACES), seat, roller=RandomRoller(seed=3))
    assert phase.actor_id == "l"
    assert seat.calls[:2] == [("give_orders", "l"), ("choose", "l")]
    page = seat.pages[0]
    assert page.squad.name == "alpha" and page.leader_id == "l"
    assert page.standing == ("l", "b", "c")
    assert page.current is None
    assert set(page.pictures) == {"l", "b", "c"}
    assert page.targets == ("her",)


def test_orders_cost_no_time():
    phase = run_phase(_encounter(_PLACES), _Leader(_all_focus),
                      roller=RandomRoller(seed=3))
    kinds = [e.kind for e in phase.events]
    # He still acts in that same Phase: the order comes first, then his shot.
    assert phase.actor_id == "l" and phase.kind == "attack"
    assert kinds.index("SquadOrdersGiven") < kinds.index("ActionResolved")
    (given,) = _given(phase.session)
    assert given.leader_id == "l" and given.squad == "alpha" and given.side == "heroes"
    assert given.teams == [{"member_ids": ["l", "b", "c"], "task": "focus_fire",
                            "target_id": "her", "radius_m": None, "position": None}]
    # The attack, not the order, spent his Phase: the next Phase is not his.
    assert run_phase(phase.encounter, _Leader(KEEP_ORDERS),
                     roller=RandomRoller(seed=3)).actor_id != "l"


def test_keep_orders_records_nothing():
    phase = run_phase(_encounter(_PLACES), _Leader(KEEP_ORDERS),
                      roller=RandomRoller(seed=3))
    assert phase.actor_id == "l" and phase.kind == "attack"
    assert _given(phase.session) == []
    assert orders_for(phase.session, "b") is None


def test_the_next_page_shows_the_orders_standing():
    s = _session()
    s = record_orders(s, _alpha(s), "l", _orders(
        _team(["l", "b", "c"], TeamTask.HOLD)))
    current = _page(s).current
    assert current == _orders(_team(["l", "b", "c"], TeamTask.HOLD))


def test_chooser_without_give_orders_raises_naming_the_protocol():
    with pytest.raises(TypeError, match="OrdersChooser"):
        run_phase(_encounter(_PLACES), _NoOrders(), roller=RandomRoller(seed=3))


def test_a_squadless_fight_never_asks_for_orders():
    phase = run_phase(_encounter(_PLACES, squad=None), _NoOrders(),
                      roller=RandomRoller(seed=3))
    assert phase.actor_id == "l"


def test_a_follower_is_not_asked():
    places = {"her": (0, 0, 0), "b": (20, 6, 0), "l": (20, 0, 0)}
    s = _encounter(places)
    # b is seated first (DEX 30) and leads on the last tie; l (DEX 29) acts
    # after him and is never asked.
    seat = _Leader(_all_focus)
    phase = run_phase(s, seat, roller=RandomRoller(seed=3))
    assert phase.actor_id == "b"            # DEX 30, seated first, leads
    assert seat.calls[0] == ("give_orders", "b")
    phase = run_phase(phase.encounter, seat, roller=RandomRoller(seed=3))
    assert phase.actor_id == "l"
    assert ("give_orders", "l") not in seat.calls


# ── Validation ─────────────────────────────────────────────────────────────


def test_member_twice_is_invalid():
    page = _page(_session())
    with pytest.raises(InvalidOrders, match="'b'.*more than one|more than one.*'b'"):
        validate_orders(page, _orders(_team(["l", "b"], TeamTask.HOLD),
                                      _team(["b", "c"], TeamTask.WITHDRAW)))


def test_member_missing_is_invalid():
    page = _page(_session())
    with pytest.raises(InvalidOrders, match="'c'"):
        validate_orders(page, _orders(_team(["l", "b"], TeamTask.HOLD)))


def test_an_unknown_id_is_invalid():
    page = _page(_session())
    with pytest.raises(InvalidOrders, match="'zed'"):
        validate_orders(page, _orders(_team(["l", "b", "c", "zed"], TeamTask.HOLD)))


def test_a_fallen_member_must_not_be_ordered():
    s = name_leaders(_knock_out(_session(), "c"))
    page = _page(s)
    assert page.standing == ("l", "b")
    with pytest.raises(InvalidOrders, match="'c'.*down"):
        validate_orders(page, _orders(_team(["l", "b", "c"], TeamTask.HOLD)))
    validate_orders(page, _orders(_team(["l", "b"], TeamTask.HOLD)))


def test_unperceived_target_is_invalid():
    # "ghost" stands behind a tall wall: the leader cannot see him, so he is
    # not on the page's targets, and an order to shoot him is refused.
    wall = Wall(id="w", name="w", segment=(Position(-40, 20, 0), Position(40, 20, 0)),
                height_m=6.0, blocks_los=True, cover_level=4)
    places = {"her": (0, 0, 0), "ghost": (0, 30, 0), **{
        k: v for k, v in _PLACES.items() if k != "her"}}
    s = _session(places, walls=[wall], villains=("her", "ghost"))
    page = _page(s)
    assert page.targets == ("her",)
    with pytest.raises(InvalidOrders, match="'ghost'"):
        validate_orders(page, _orders(
            _team(["l", "b", "c"], TeamTask.FOCUS_FIRE, target_id="ghost")))


@pytest.mark.parametrize("team, problem", [
    (_team(["l", "b", "c"], TeamTask.FOCUS_FIRE), "target_id"),
    (_team(["l", "b", "c"], TeamTask.CLOSE), "target_id"),
    (_team(["l", "b", "c"], TeamTask.SPREAD_OUT), "radius_m"),
    (_team(["l", "b", "c"], TeamTask.SPREAD_OUT, radius_m=0.0), "radius_m"),
    (_team(["l", "b", "c"], TeamTask.FLANK), "position"),
    # Set but unused is refused too, so an order says one thing.
    (_team(["l", "b", "c"], TeamTask.HOLD, target_id="her"), "target_id"),
    (_team(["l", "b", "c"], TeamTask.FOCUS_FIRE, target_id="her", radius_m=4.0),
     "radius_m"),
])
def test_a_task_needs_its_own_fields_and_no_others(team, problem):
    with pytest.raises(InvalidOrders, match=problem):
        validate_orders(_page(_session()), _orders(team))


def test_a_task_must_be_a_team_task():
    with pytest.raises(InvalidOrders, match="TeamTask"):
        validate_orders(_page(_session()), _orders(_team(["l", "b", "c"], "hold")))


def test_keep_orders_is_always_valid():
    assert validate_orders(_page(_session()), KEEP_ORDERS) is KEEP_ORDERS
    assert KEEP_ORDERS != _orders()


def test_invalid_orders_from_the_loop_raise():
    bad = _Leader(_orders(_team(["l"], TeamTask.HOLD)))
    with pytest.raises(InvalidOrders):
        run_phase(_encounter(_PLACES), bad, roller=RandomRoller(seed=3))


# ── Reading them ───────────────────────────────────────────────────────────


def _ordered(s, *teams):
    return record_orders(s, _alpha(s), "l", _orders(*teams))


def test_every_member_reads_his_own_team():
    s = _ordered(_session(), _team(["l", "b"], TeamTask.FOCUS_FIRE, target_id="her"),
                 _team(["c"], TeamTask.FLANK, position=Position(5, 5, 0)))
    assert orders_for(s, "b").task is TeamTask.FOCUS_FIRE
    flank = orders_for(s, "c")
    assert flank.task is TeamTask.FLANK and flank.position == Position(5, 5, 0)
    assert orders_for(s, "her") is None
    assert _situation_for(s, "c").squad_order == flank


def test_the_latest_orders_win():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.HOLD))
    s = _ordered(s, _team(["l", "b", "c"], TeamTask.WITHDRAW))
    assert orders_for(s, "b").task is TeamTask.WITHDRAW


def test_orders_stand_after_the_leader_falls():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.TAKE_COVER))
    s = name_leaders(_knock_out(s, "l"))
    assert leader_of(s, "alpha", "heroes") == "b"
    assert orders_for(s, "c").task is TeamTask.TAKE_COVER


def test_a_man_down_when_the_orders_were_given_has_none():
    s = name_leaders(_knock_out(_session(), "c"))
    s = _ordered(s, _team(["l", "b"], TeamTask.HOLD))
    assert orders_for(s, "c") is None


def test_the_order_is_in_the_record_of_every_man_it_names():
    s = _ordered(_session(), _team(["l", "b"], TeamTask.HOLD),
                 _team(["c"], TeamTask.WITHDRAW))
    for man in ("l", "b", "c"):
        assert any(e.kind == "SquadOrdersGiven" for e in events_involving(s, man)), man


def test_the_order_never_cuts_his_menu():
    s = _session()
    before = [a.action_id for a in _situation_for(s, "b").menu]
    s = _ordered(s, _team(["l", "b", "c"], TeamTask.HOLD))
    assert [a.action_id for a in _situation_for(s, "b").menu] == before


def test_the_page_renders_in_judged_words():
    s = _session()
    text = _page(s).render()
    assert "alpha" in text and "l, b, c" in text
    assert "her" in text
    assert "DCV" not in text and "OCV" not in text


# ── order_fit ──────────────────────────────────────────────────────────────


def _offer(kind, *, target_id=None, dest=None):
    return LegalAction(action_id=f"{kind}:{target_id}:{dest}", kind=kind,
                       target_id=target_id, power_xmlid=None, power_name=None,
                       summary="", reposition_dest=dest)


def _fit(s, who, offer):
    return order_fit(_situation_for(s, who), offer)


def test_order_fit_focus_fire():
    s = _session({**_PLACES, "him": (0, 10, 0)}, villains=("her", "him"))
    s = _ordered(s, _team(["l", "b", "c"], TeamTask.FOCUS_FIRE, target_id="her"))
    menu = _situation_for(s, "b").menu
    at_her = next(a for a in menu if a.kind == "attack" and a.target_id == "her")
    at_him = next(a for a in menu if a.kind == "attack" and a.target_id == "him")
    assert _fit(s, "b", at_her) is True
    assert _fit(s, "b", at_him) is False
    assert _fit(s, "b", _offer("coordinate", target_id="her")) is True
    assert _fit(s, "b", _offer("coordinate", target_id="him")) is False
    assert _fit(s, "b", _offer("move", target_id="her")) is False


def test_order_fit_close():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.CLOSE, target_id="her"))
    menu = _situation_for(s, "b").menu
    toward = next(a for a in menu if a.kind == "move" and a.target_id == "her")
    assert _fit(s, "b", toward) is True
    assert _fit(s, "b", _offer("reposition", dest=(30, 6, 0))) is False
    assert _fit(s, "b", _offer("reposition", dest=(12, 6, 0))) is True
    assert _fit(s, "b", next(a for a in menu if a.kind == "attack")) is False


def test_order_fit_take_cover():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.TAKE_COVER))
    at_her = next(a for a in _situation_for(s, "b").menu if a.kind == "attack")
    assert _fit(s, "b", _offer("move_to_cover", dest=(25, 6, 0))) is True
    assert _fit(s, "b", at_her) is False            # in the open
    # A low wall between him and her: he is in cover, so shooting from it fits.
    low = Wall(id="low", name="low", segment=(Position(18, 3, 0), Position(18, 9, 0)),
               height_m=1.0, blocks_los=False, cover_level=2)
    s = _ordered(_session(walls=[low]), _team(["l", "b", "c"], TeamTask.TAKE_COVER))
    at_her = next(a for a in _situation_for(s, "b").menu if a.kind == "attack")
    assert _fit(s, "b", at_her) is True


def test_order_fit_spread_out():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.SPREAD_OUT, radius_m=8.0))
    # l at (20,0), c at (20,-6): a spot 8 m from both fits, one by c does not.
    assert _fit(s, "b", _offer("reposition", dest=(20, 12, 0))) is True
    assert _fit(s, "b", _offer("reposition", dest=(22, -4, 0))) is False
    assert _fit(s, "b", _offer("hold")) is False


def test_order_fit_flank():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.FLANK,
                                   position=Position(0, 30, 0)))
    assert _fit(s, "b", _offer("reposition", dest=(14, 14, 0))) is True
    assert _fit(s, "b", _offer("reposition", dest=(26, 0, 0))) is False


def test_order_fit_hold():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.HOLD))
    menu = _situation_for(s, "b").menu
    assert _fit(s, "b", next(a for a in menu if a.kind == "hold")) is True
    assert _fit(s, "b", next(a for a in menu if a.kind == "attack")) is False


def test_order_fit_withdraw():
    s = _ordered(_session(), _team(["l", "b", "c"], TeamTask.WITHDRAW))
    assert _fit(s, "b", _offer("disengage", dest=(40, 6, 0))) is True
    assert _fit(s, "b", _offer("reposition", dest=(10, 6, 0))) is False
    menu = _situation_for(s, "b").menu
    assert _fit(s, "b", next(a for a in menu if a.kind == "move")) is False


def test_a_man_with_no_order_fits_nothing():
    s = _session()
    for offer in _situation_for(s, "b").menu:
        assert _fit(s, "b", offer) is False


@pytest.mark.parametrize("team", [
    _team(["l", "b", "c"], TeamTask.FOCUS_FIRE, target_id="her"),
    _team(["l", "b", "c"], TeamTask.CLOSE, target_id="her"),
    _team(["l", "b", "c"], TeamTask.TAKE_COVER),
    _team(["l", "b", "c"], TeamTask.SPREAD_OUT, radius_m=8.0),
    _team(["l", "b", "c"], TeamTask.FLANK, position=Position(0, 30, 0)),
    _team(["l", "b", "c"], TeamTask.HOLD),
    _team(["l", "b", "c"], TeamTask.WITHDRAW),
], ids=lambda t: t.task.value)
def test_every_offer_on_a_real_menu_gets_an_answer(team):
    """No kind on his own menu leaves `order_fit` without a rule."""
    s = _ordered(_session(), team)
    situation = _situation_for(s, "b")
    assert {order_fit(situation, a) for a in situation.menu} <= {True, False}
    # And each task is one his menu can carry out, save cover on an open
    # field, where there is none to take and nothing to shoot from.
    if team.task is not TeamTask.TAKE_COVER:
        assert any(order_fit(situation, a) for a in situation.menu), team.task
