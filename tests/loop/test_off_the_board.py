"""Knocked off the board: he comes back, at combat speed, by his best way.

Knockback (and a Throw, and a shove) can carry a man past the edge of the
map. Until this ruling that was the end of him: `Roster.has_left` read his
position as "outside the bounds, so gone", and `resolve_fall` found no
ground beyond the edge and dropped him to the bounds' floor (z=-5 on the
random maps). It happened in 4 of 6 demo seeds.

PETER'S RULING (2026-10-29): the map's edge is not the world's. A man
forced off it is coming back --- the question is how long it takes him and
how he travels. So:

- Beyond the edge the ground goes on at the height where he crossed it.
- He comes back to the point where he crossed, along the line he flew.
- At COMBAT speed (6E2 p.25-26: a Full Move is his combat movement; a move
  of half or less is a Half Phase Action). Noncombat speed was rejected:
  its 1/2 DCV, 0 OCV and the p.27 acceleration limit are state the engine
  does not carry.
- By the mode that gets him back in the FEWEST Phases, of running, leaping,
  flight and teleportation; a tie goes to the cheaper trip in END, then
  running, leaping, flight, teleportation in that order. A man in the air
  can only fly or teleport.
- His first Phase starts with the Half Phase it takes to get up, if he is
  on the ground (6E2 p.116: "must spend a Half Phase to get up").
- While he is off the board nobody can target him, he is not gone, and the
  loop spends his Phases moving him back --- he gets no menu, because every
  offer is worked out from a position on the board.
- If the move that brings him back uses half his movement or less, he has a
  Half Phase left and gets the menu from the edge (6E2 p.26).
- A man with no way back at all has left. Walking off is still leaving.
"""
from __future__ import annotations

from conftest import blast  # tests/loop/conftest.py
from kirby_dice import FakeRoller
from kirby_world.scene import (
    AmbientConditions,
    Position,
    Scene,
    SceneBounds,
    Surface,
)

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import Roster, run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import MovementCapability
from kirby_combat.off_board import way_back
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
HIT = [1, 1, 1]
LOCATION = [3, 3, 3]
STUN_X = [1]
#: 6E2 p.21's DEX Roll, made for every slot when the order is resolved.
TIE = [3, 3, 3]
#: 6d6 of sixes is 12 BODY; a Knockback roll of 2 sends him (12-2) x 2 = 20m.
KNOCKED_20M = [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5]


def _cap(mode, combat_m, end=1):
    return MovementCapability(mode=mode, combat_m=float(combat_m),
                              noncombat_m=float(combat_m) * 2, end_cost=end)


# ---------------------------------------------------------------------------
# Which way back, and how many Phases
# ---------------------------------------------------------------------------

def test_the_mode_that_gets_him_back_soonest_is_the_one_he_takes():
    """30m back: Running 12 needs three Phases on his feet, Flight 30 one."""
    back = way_back([_cap("running", 12), _cap("flight", 30)],
                    distance_m=30.0, prone=False, airborne=False)
    assert (back.mode, back.combat_m, back.phases) == ("flight", 30.0, 1)


def test_getting_up_costs_him_half_of_his_first_phase():
    """7m back on Running 12: on his feet it is one Phase. Prone, he spends
    a Half Phase getting up and covers 6m, so it is two."""
    caps = [_cap("running", 12)]
    assert way_back(caps, distance_m=7.0, prone=False, airborne=False).phases == 1
    assert way_back(caps, distance_m=7.0, prone=True, airborne=False).phases == 2
    assert way_back(caps, distance_m=6.0, prone=True, airborne=False).phases == 1


def test_a_tie_goes_to_the_cheaper_mode_then_to_the_fixed_order():
    """10m back, one Phase either way. Teleportation 20m at 4 END a full
    move costs 2 for the trip, Running 12m at 1 END costs 1 (6E1 p.158), so
    he runs. Flight and running cost the same, so the order decides."""
    tp = way_back([_cap("teleportation", 20, end=4), _cap("running", 12)],
                  distance_m=10.0, prone=False, airborne=False)
    assert tp.mode == "running"
    fl = way_back([_cap("flight", 20), _cap("running", 12)],
                  distance_m=10.0, prone=False, airborne=False)
    assert fl.mode == "running"


def test_a_man_in_the_air_can_only_fly_or_teleport_back():
    back = way_back([_cap("running", 40), _cap("flight", 10)],
                    distance_m=10.0, prone=False, airborne=True)
    assert back.mode == "flight"
    assert way_back([_cap("running", 40)], distance_m=10.0,
                    prone=False, airborne=True) is None


def test_swimming_and_tunneling_do_not_bring_him_back_over_open_ground():
    assert way_back([_cap("swimming", 20), _cap("tunneling", 20)],
                    distance_m=5.0, prone=False, airborne=False) is None


# ---------------------------------------------------------------------------
# Knocked past the edge
# ---------------------------------------------------------------------------

def _ground_inside() -> Surface:
    """Ground only inside the map: nothing is authored beyond the edge."""
    return Surface(id="ground", name="ground",
                   polygon_xy=[(0, 0), (25, 0), (25, 100), (0, 100)],
                   elevation_m=0.0, surface_type="ground", cover_level=0,
                   is_supporting=True)


def _scene() -> Scene:
    """The map ends at x=25; its floor is 5m below the ground, the way the
    random maps author it."""
    return Scene(
        id="lot", name="A Lot", bounds=SceneBounds(0, 0, -5, 25, 100, 50),
        surfaces=[_ground_inside()], walls=[], hazards=[],
        ambient=AmbientConditions(gravity_scale=1.0),
        combatant_positions={"a": Position(10, 10, 0), "t": Position(12, 10, 0)},
    )


def _session(*, running=12, rolls=()) -> CombatSession:
    attacker = synthetic_combatant(
        id="a", name="a", ocv=9, dcv=5, spd=4, dex=20, str_=15, con=20,
        pd=4, ed=4, max_stun=40, max_body=12, max_end=40,
        side=Side.named("heroes"), attacks=[blast("a-eb", dice=6)],
    )
    target = synthetic_combatant(
        id="t", name="t", ocv=9, dcv=5, spd=4, dex=10, str_=15, con=35,
        pd=4, ed=4, max_stun=60, max_body=15, max_end=40, running=running,
        side=Side.named("villains"), attacks=[blast("t-eb", dice=6)],
    )
    return CombatSession.create(
        id="s", combatants=[attacker, target], scene=_scene(),
        template=TEMPLATE, dice_roller=FakeRoller(list(rolls)),
    ).start()


def _blast_at_t() -> LegalAction:
    power = blast("a-eb", dice=6)
    return LegalAction(action_id="attack:t:a-eb", kind="attack", target_id="t",
                       power_xmlid=power.xmlid, power_name=power.name,
                       summary="Blast t", _attack_view=power)


def _where(session, cid="t"):
    p = session.scene.combatant_positions[cid]
    return (round(p.x, 6), round(p.y, 6), round(p.z, 6))


def test_beyond_the_edge_the_ground_goes_on():
    """He flies from x=12 to x=32, past the edge at x=25. He lands on the
    ground there, at the height he crossed at --- not 5m down on the map's
    floor --- and takes the open-ground 1d6 per 4m (6E2 p.118)."""
    session = _session()
    out = resolve_chosen(session, session.combatants["a"], _blast_at_t(),
                         template=TEMPLATE, roller=FakeRoller(list(KNOCKED_20M)))
    assert _where(out.session) == (32.0, 10.0, 0.0)
    moves = [e.move_type for e in out.events
             if e.kind == "MovementResolved" and e.combatant_id == "t"]
    assert moves == ["knockback"], "no phantom fall"
    reasons = [e.reason for e in out.events
               if e.kind == "VitalsChanged" and e.combatant_id == "t"]
    assert reasons == ["damage", "knockback"]


def test_off_the_board_he_is_no_target_but_he_has_not_left():
    session = _session()
    s = resolve_chosen(session, session.combatants["a"], _blast_at_t(),
                       template=TEMPLATE, roller=FakeRoller(list(KNOCKED_20M))).session
    roster = Roster(s)
    assert not roster.has_left("t")
    assert roster.is_off_board("t")
    assert [e.id for e in roster.enemies_of(s.combatants["a"])] == []
    assert "t" in [cid for ids in roster.standing.values() for cid in ids], (
        "his side is not beaten while he is on his way back")
    assert not roster.decide()


def test_a_man_with_no_way_back_has_left():
    session = _session(running=0)
    s = resolve_chosen(session, session.combatants["a"], _blast_at_t(),
                       template=TEMPLATE, roller=FakeRoller(list(KNOCKED_20M))).session
    assert Roster(s).has_left("t")


class _BlastHim:
    """`a` blasts `t`; nobody else is ever asked in these tests."""

    def choose(self, situation):
        no_abort = [x for x in situation.menu if x.kind == "no_abort"]
        if no_abort:
            # Asked whether to Abort against the blast (6E2 p.24), while he
            # is still on the board: he takes it.
            return no_abort[0].action_id
        assert situation.actor.id == "a", (
            f"{situation.actor.id} was handed a menu off the board")
        return next(x.action_id for x in situation.menu
                    if x.kind == "attack" and x.target_id == "t")


class _ThenAnything:
    def choose(self, situation):
        return situation.menu[0].action_id


def _knocked_off_in_segment_12():
    enc = Encounter(id="e", turn=1, segment=12, sessions=[_session()])
    roller = FakeRoller([TIE, TIE] + list(KNOCKED_20M))
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))
    phase = run_phase(enc, _BlastHim(), roller=roller, on_unresolvable="raise")
    assert phase.actor_id == "a"
    return phase


def test_the_engine_says_how_long_he_will_be_gone_and_how_he_is_coming_back():
    """7m back on Running 12, prone: 6m after getting up in his Segment 12
    Phase, the last 1m in Segment 3 of Turn 2."""
    phase = _knocked_off_in_segment_12()
    rows = [e for e in phase.events if e.kind == "ForcedOffTheBoard"]
    assert len(rows) == 1
    row = rows[0]
    assert row.combatant_id == "t"
    assert row.cause == "knockback"
    assert row.exit_point == {"x": 25.0, "y": 10.0, "z": 0.0}
    assert row.distance_m == 7.0
    assert (row.mode, row.metres_per_phase, row.phases) == ("running", 12.0, 2)
    assert (row.returns_turn, row.returns_segment) == (2, 3)


def test_his_phases_bring_him_back_and_then_he_fights():
    phase = _knocked_off_in_segment_12()
    roller = FakeRoller([TIE] * 8)

    # Segment 12: he gets up (a Half Phase) and runs the other half, 6m.
    phase = run_phase(phase.encounter, _BlastHim(), roller=roller)
    assert phase.actor_id == "t"
    s = phase.session
    assert PRONE not in statuses_for(s, "t")
    assert _where(s) == (26.0, 10.0, 0.0)
    assert Roster(s).is_off_board("t")
    assert any(e.kind == "PhaseSpent" and e.combatant_id == "t" for e in phase.events)

    # Turn 2, Segment 3: `a` acts first (DEX 20) and has nobody to shoot,
    # then `t` runs the last metre --- a Half Move --- and is back.
    while phase.actor_id != "t" or Roster(phase.session).is_off_board("t"):
        phase = run_phase(phase.encounter, _ThenAnything(), roller=roller)
    s = phase.session
    assert (s.timeline.turn, s.timeline.segment) == (2, 3)
    assert _where(s) == (25.0, 10.0, 0.0)
    assert not any(e.kind == "PhaseSpent" and e.combatant_id == "t"
                   for e in phase.events), "the Half Phase left is still his"

    # And the rest of that Phase is his to use, from the edge: the Half
    # Phase Actions, and `a` back on his list of targets.
    class _SeeTheMenu:
        menu: list = []

        def choose(self, situation):
            _SeeTheMenu.menu = situation.menu
            return next(x.action_id for x in situation.menu if x.kind == "dodge")

    phase = run_phase(phase.encounter, _SeeTheMenu(), roller=roller)
    assert phase.actor_id == "t"
    assert any(x.kind == "attack" and x.target_id == "a" for x in _SeeTheMenu.menu)


def test_the_trip_back_costs_end():
    """Moving costs END (6E1 p.158), and the trip back is a move. Running
    12m is 1 END a full move: 6m after getting up is half of it, the last
    1m a twelfth --- each at least 1 (6E1 p.132)."""
    phase = _knocked_off_in_segment_12()
    roller = FakeRoller([TIE] * 8)
    spent = []
    while True:
        phase = run_phase(phase.encounter, _ThenAnything(), roller=roller)
        if phase.actor_id == "t":
            spent += [(e.end, e.reason) for e in phase.events
                      if e.kind == "VitalsChanged" and e.combatant_id == "t"
                      and e.end]
            if not Roster(phase.session).is_off_board("t"):
                break
    assert spent == [(-1, "end_spent"), (-1, "end_spent")]


def test_somebody_standing_where_he_crossed_does_not_get_him_on_top_of_him():
    """He can see the board from off it (Peter, 2026-10-31), so he comes
    back to the nearest spot nobody stands in, inside the map, rather than
    onto the man at the edge; and the engine says he is back."""
    from dataclasses import replace

    from kirby_world.geometry import distance_3d

    from kirby_combat.placement import PERSONAL_SPACE_M

    phase = _knocked_off_in_segment_12()
    s = phase.session
    # `a` walks to the very point `t` crossed at, x=25.
    s = replace(s, scene=replace(s.scene, combatant_positions={
        **s.scene.combatant_positions, "a": Position(25.0, 10.0, 0.0)}))
    phase = replace(phase, encounter=replace(phase.encounter, sessions=[s]))
    class _AStandsStill:
        def choose(self, situation):
            if situation.actor.id == "a":
                still = [x for x in situation.menu
                         if x.kind in ("dodge", "hold", "recover", "no_abort")]
                assert still, [x.kind for x in situation.menu]
                return still[0].action_id
            return situation.menu[0].action_id

    roller = FakeRoller([TIE] * 8)
    while True:
        phase = run_phase(phase.encounter, _AStandsStill(), roller=roller)
        if phase.actor_id == "t" and not Roster(phase.session).is_off_board("t"):
            break
    s = phase.session
    assert s.scene.combatant_positions["a"] == Position(25.0, 10.0, 0.0), "a stayed put"
    here = s.scene.combatant_positions["t"]
    assert here.x <= 25.0 + 1e-9, "inside the map"
    assert distance_3d(here, s.scene.combatant_positions["a"]) >= PERSONAL_SPACE_M - 1e-6
    (back,) = [e for e in s.event_log if e.kind == "ReturnedToTheBoard"]
    assert back.combatant_id == "t"
    assert (back.at["x"], back.at["y"]) == (here.x, here.y)
