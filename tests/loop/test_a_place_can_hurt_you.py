"""A burning room burns, and deep water drowns, Segment by Segment.

`construct_effects.resolve_construct_effect` decided whether a zone touches
its occupant and nothing in the engine called it (it was the parked api
driver's). Now `run_phase` fires every ``every_segment`` zone at the top of
each Segment.

Drowning follows 6E2 p.132-133, not the old flat "1 BODY per Segment": 1
END per Phase at SPD 2 or better, then STUN as END (1d6 per 2 END, no
defense), then -1 BODY a Phase.
"""
from __future__ import annotations

from shaped import Dice, Picks, armed, encounter_on, scene_with  # tests/loop/shaped.py
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_world.construct import Construct, ConstructEffect

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
SQUARE = [(4.0, -2.0), (8.0, -2.0), (8.0, 2.0), (4.0, 2.0)]


def _zone(kind, **fields):
    return Construct(
        obj_id=f"{kind}-zone", kind="hazard_zone", polygon_xy=list(SQUARE),
        elevation_range_m=(0.0, 3.0), permeability="porous",
        effect=ConstructEffect(kind=kind, trigger="every_segment", **fields),
    )


def _fight(zone, *, end=40, stun=40):
    # c keeps the heroes' side standing, so a knocked-out b does not end
    # the fight before the water has finished with him.
    scene = scene_with({"a": (0, 0, 0), "b": (6, 0, 0), "c": (0, 10, 0)},
                       constructs=[zone])
    return encounter_on(scene,
                        armed("a", None, side=VILLAINS, dex=30),
                        armed("b", None, side=HEROES, dex=10,
                              current_end=end, stun=stun),
                        armed("c", None, side=HEROES, dex=5))


def _step(enc, n, dice):
    chooser = Picks(lambda a, _s: False)
    for _ in range(n):
        enc = run_phase(enc, chooser, roller=dice, on_unresolvable="raise").encounter
    return enc


def _triggered(enc):
    return [e for e in enc.sessions[0].event_log if e.kind == "EnvironmentalTriggered"]


def test_a_fire_zone_burns_whoever_stands_in_it_every_segment():
    """Seam: b stands in a 3d6 Normal fire. Every Segment --- the fight's
    opening Segment 12, then Turn 2's 1, 2 and 3 --- 3d6 of 4s = 12 STUN less
    his ED 4 (fire is an Energy attack) = 8. a, outside it, is untouched."""
    enc = _fight(_zone("damage", damage_dice=3, damage_type="fire",
                       gating="physical_def"))
    enc = _step(enc, 4, Dice(face=4))       # Seg 12 a, b, c; then Turn 2's Seg 3
    fires = _triggered(enc)
    assert {tuple(e.affected_combatants) for e in fires} == {("b",)}
    assert [e.effect["stun"] for e in fires] == [8, 8, 8, 8]
    assert enc.sessions[0].combatants["a"].state.current_stun == 40


def test_a_man_who_cannot_swim_spends_his_breath_in_his_phases():
    """6E2 p.132: "expends a minimum of 1 END per Phase" --- SPD 4, so in
    Segment 12 and then Segment 3, and not in Segments 1 or 2."""
    zone = _zone("suffocation", gating="breathing_swimming")
    enc = _fight(zone)
    s = enc.sessions[0]
    s.combatants["b"].state.statuses.add("cannot_swim")
    enc = _step(enc, 4, Dice(face=4))
    drowning = [e.effect for e in _triggered(enc)]
    assert drowning == [{"kind": "suffocation", "end": 1, "stun": 0, "body": 0}] * 2
    reached = [e.to_segment for e in enc.sessions[0].event_log
               if e.kind == "SegmentAdvanced"]
    assert reached[:3] == [1, 2, 3]        # it passed Segments 1 and 2 dry


def test_out_of_breath_he_burns_stun_and_then_body():
    """6E2 p.132-133: no END left, 1d6 STUN as END with no defense; no STUN
    left either, -1 BODY."""
    zone = _zone("suffocation", gating="breathing_swimming")
    enc = _fight(zone, end=0)
    enc.sessions[0].combatants["b"].state.statuses.add("cannot_swim")
    enc = _step(enc, 3, Dice(face=4))
    assert _triggered(enc)[0].effect == {
        "kind": "suffocation", "end": 0, "stun": 4, "body": 0}

    enc = _fight(zone, end=0, stun=0)
    enc.sessions[0].combatants["b"].state.statuses.add("cannot_swim")
    enc = _step(enc, 3, Dice(face=4))
    assert _triggered(enc)[0].effect["body"] == 1
