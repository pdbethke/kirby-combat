"""A Haymaker lands at the very end of the next Segment, +4 DC (6E2 p.70, p.73).

Before this, Haymaker was a declaration whose +4 DC and -5 DCV nothing read
(`modifiers_for_pending_attack` had no caller outside its tests): it cost a
Phase and did nothing. Every test here drives `run_phase`.

The fighters (`tests/loop/conftest.fighter`, unarmed): STR 15, so a Strike is
3d6; PD 4, DCV 5. With every die showing 1, a bare Strike is 3 STUN, all
stopped by PD 4; a Haymaker of it is 7d6, 7 STUN, 3 through.
"""
from __future__ import annotations

from conftest import encounter_of, fighter  # tests/loop/conftest.py
from kirby_dice import RandomRoller

from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS

X, Y = Side.named("x"), Side.named("y")


class Ones(RandomRoller):
    """Every die shows 1: every Attack Roll hits (6E2 p.37)."""

    def roll_dice(self, n, sides=6):
        return [1] * n


class Script:
    """(actor, segment) -> an action-id prefix on his Phase; (actor, segment)
    -> an Abort when attacked. Anything else: Set, Hold or Dodge, none of
    which touches the other man."""

    def __init__(self, own=None, react=None):
        self.own, self.react = own or {}, react or {}
        self.menus: dict[tuple[str, int], list] = {}

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, sit):
        who, seg = sit.actor.id, sit.session.timeline.segment
        oot = getattr(sit, "out_of_turn", None)
        if oot is not None:
            if oot.reason.value != "abort":
                return sit.menu[0].action_id           # a Held Action: let it go
            want = self.react.get((who, seg), "no_abort")
            return next(o.action_id for o in sit.menu if o.kind == want)
        self.menus[(who, seg)] = list(sit.menu)
        prefix = self.own.get((who, seg))
        if prefix is not None:
            return next(o.action_id for o in sit.menu if o.action_id.startswith(prefix))
        return next(o.action_id for o in sit.menu if o.kind in ("set", "hold"))


def _run(script, *, a_spd=6, until=(2, 4)):
    a = fighter("a", side=X, spd=a_spd, dex=30, armed=False)
    b = fighter("b", side=Y, spd=4, dex=10, armed=False)    # Phases 3, 6, 9, 12
    enc, events = encounter_of(a, b), []
    while (enc.turn, enc.segment) <= until:
        r = run_phase(enc, script, roller=Ones(seed=1), on_unresolvable="raise")
        events += r.events
        enc = r.encounter
    return events


def _segment_of(events):
    """Each event, with the Turn 2 Segment it fell in."""
    seg, out = None, []
    for e in events:
        if e.kind == "SegmentAdvanced" and e.to_turn == 2:
            seg = e.to_segment
        out.append((seg, e))
    return out


def _attacks_by_a(events):
    return [(seg, e) for seg, e in _segment_of(events)
            if e.kind == "ActionResolved" and e.result_payload.get("kind") == "attack"
            and e.result_payload.get("target_id") == "b"]


def _closed(events):
    return [e.result_payload for e in events if e.kind == "ActionResolved"
            and e.result_payload.get("kind") == "haymaker"]


def test_it_lands_at_the_end_of_the_next_segment_with_four_more_dc():
    events = _run(Script(own={("a", 2): "haymaker:strike:b"}))
    (seg, blow), = _attacks_by_a(events)
    assert seg == 3, "begun in Segment 2, it goes off at the end of Segment 3"
    # After everyone in Segment 3 has acted: b's Phase there comes first.
    order = [e for _, e in _segment_of(events)]
    b_in_3 = next(i for i, (s, e) in enumerate(_segment_of(events))
                  if s == 3 and e.kind == "PhaseSpent" and e.combatant_id == "b")
    assert b_in_3 < order.index(blow)
    assert blow.result_payload["stun_dealt"] == 7 - 4          # 7d6 of 1s, PD 4
    assert _closed(events) == [{"kind": "haymaker", "landed": True, "ruined": False,
                                "reason": "+4 DC", "combatant_id": "a",
                                "attack_action_id": "strike:b"}]


def test_the_same_strike_without_it_does_nothing_through_pd():
    events = _run(Script(own={("a", 2): "strike:b"}))
    (_, blow), = _attacks_by_a(events)
    assert blow.result_payload["stun_dealt"] == 0               # 3d6 of 1s, PD 4


def test_he_is_at_minus_five_dcv_while_he_winds_up():
    events = _run(Script(own={("a", 2): "haymaker:strike:b", ("b", 3): "strike:a"}))
    on_a = [e for e in events if e.kind == "ActionResolved"
            and e.result_payload.get("kind") == "attack"
            and e.result_payload.get("target_id") == "a"]
    assert on_a[0].result_payload["target_dcv"] == 5 - 5


def test_aborting_to_a_defence_ruins_it():
    """6E2 p.70: he may Abort in the Segment it goes off, "but doing so ruins
    the Haymaker"."""
    events = _run(Script(own={("a", 2): "haymaker:strike:b", ("b", 3): "strike:a"},
                         react={("a", 3): "dodge"}))
    assert not _attacks_by_a(events)
    (closed,) = _closed(events)
    assert closed["ruined"] and closed["reason"] == "he Aborted to a defensive Action"


def test_no_second_haymaker_while_one_is_in_the_air():
    """SPD 12: a Phase every Segment, so his next comes before it lands."""
    script = Script(own={("a", 2): "haymaker:strike:b"})
    _run(script, a_spd=12, until=(2, 3))
    assert any(o.kind == "haymaker" for o in script.menus[("a", 2)])
    assert not any(o.kind == "haymaker" for o in script.menus[("a", 3)])
