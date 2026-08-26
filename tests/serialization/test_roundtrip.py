"""Round-trip parity tests — to_dict -> from_dict invariant."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from hypothesis import given, strategies as st, settings

from kirby_combat.serialization import to_dict, from_dict
from kirby_combat.models import StatBlockCombatant
from kirby_combat.vehicles import Vehicle, Passenger
from kirby_combat.masscombat import Unit, UnitMorale
from kirby_combat.scene import (
    Scene, SceneBounds, Position, AmbientConditions,
    Surface, Wall, Hazard, HazardEffect,
)
from kirby_combat.session.events import (
    SessionStarted, SegmentAdvanced, ActionDeclared, ActionResolved,
    RecoveryTaken, MovementResolved, StatusChanged, AbortDeclared,
    HeldActionDeclared, HeldActionReleased,
    AdjustmentApplied, AdjustmentFaded, EntangleApplied, EntangleEscape,
    FlashApplied, FlashRecovered, EnvironmentalTriggered, GMOverride,
    SessionEnded, EventAuthor, make_author_engine, make_author_gm,
)


def _ts() -> datetime:
    return datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


# NOT synthetic: exercises full-field dataclass equality after
# to_dict/from_dict, which only holds for the flat StatBlockCombatant shape.
def _ct(id_: str = "alice") -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_full_session_roundtrip_preserves_state():
    """Build a session-like collection of events, round-trip individually."""
    events = [
        SessionStarted(
            id="evt-1", session_id="s1", sequence=1,
            timestamp=_ts(), author=make_author_engine(),
            scene_id="sc", combatant_ids=["alice", "bob"],
        ),
        SegmentAdvanced(
            id="evt-2", session_id="s1", sequence=2,
            timestamp=_ts(), author=make_author_engine(),
            from_segment=12, to_segment=1, to_turn=2,
        ),
        ActionDeclared(
            id="evt-3", session_id="s1", sequence=3,
            timestamp=_ts(), author=EventAuthor(type="combatant", id="alice"),
            combatant_id="alice", action_type="attack", targets=["bob"],
            parameters={"power": "blast"},
        ),
        SessionEnded(
            id="evt-4", session_id="s1", sequence=4,
            timestamp=_ts(), author=make_author_engine(),
            reason="all done",
        ),
    ]
    for ev in events:
        restored = from_dict(to_dict(ev))
        assert type(restored) is type(ev)
        assert restored.id == ev.id
        assert restored.sequence == ev.sequence


def test_every_event_type_roundtrips():
    """One instance per CombatEvent subclass survives round-trip."""
    base_kwargs = dict(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=_ts(), author=make_author_engine(),
    )
    instances = [
        SessionStarted(**base_kwargs, scene_id="sc", combatant_ids=["a"]),
        SegmentAdvanced(**base_kwargs, from_segment=0, to_segment=1, to_turn=1),
        ActionDeclared(**base_kwargs, combatant_id="a", action_type="attack", targets=["b"]),
        ActionResolved(**base_kwargs, declaration_event_id="evt-prev", result_payload={"x": 1}),
        RecoveryTaken(**base_kwargs, combatant_id="a", stun_recovered=4, end_recovered=2),
        MovementResolved(**base_kwargs, combatant_id="a", from_pos={"x": 0.0}, to_pos={"x": 1.0},
                         velocity_mps=5.0, move_type="run"),
        StatusChanged(**base_kwargs, combatant_id="a", from_status="ok", to_status="stunned",
                      reason="big hit"),
        AbortDeclared(**base_kwargs, combatant_id="a", to_action="dodge"),
        HeldActionDeclared(**base_kwargs, combatant_id="a", trigger_condition="see attacker",
                           for_action="block"),
        HeldActionReleased(**base_kwargs, held_event_id="evt-h", trigger_observed="hit"),
        AdjustmentApplied(**base_kwargs, target_id="a", stat="dex", delta=-3,
                          fade_rate_per_turn=5, source_event_id="evt-src"),
        AdjustmentFaded(**base_kwargs, target_id="a", stat="dex", remaining_delta=0),
        EntangleApplied(**base_kwargs, target_id="a", entangle_body=10, entangle_pd=4, entangle_ed=4),
        EntangleEscape(**base_kwargs, target_id="a", method="full_str",
                       damage_to_entangle_body=12, escaped=True),
        FlashApplied(**base_kwargs, target_id="a", sense_group="sight", segments=4),
        FlashRecovered(**base_kwargs, target_id="a", sense_group="sight", segments_remaining=0),
        EnvironmentalTriggered(**base_kwargs, hazard_id="lava1",
                               affected_combatants=["a"], effect={"dmg": 4}),
        GMOverride(
            id="evt-x", session_id="s1", sequence=1, timestamp=_ts(),
            author=make_author_gm("gm-pete"),
            tier=1, target_event_id=None, patch={"op": "set"}, justification="",
        ),
        SessionEnded(**base_kwargs, reason="end"),
    ]
    for inst in instances:
        restored = from_dict(to_dict(inst))
        assert type(restored) is type(inst)
        assert restored.id == inst.id


@given(
    id_=st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
    spd=st.integers(min_value=0, max_value=12),
    dex=st.integers(min_value=1, max_value=40),
    stun=st.integers(min_value=1, max_value=100),
    body=st.integers(min_value=1, max_value=30),
)
@settings(max_examples=50, deadline=None)
def test_hypothesis_random_combatant_roundtrip(id_, spd, dex, stun, body):
    c = StatBlockCombatant(
        id=id_, name=id_, ocv=5, dcv=5, omcv=3, dmcv=3,
        spd=spd, dex=dex, ego=10, int_=10, str_=10, con=10, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=stun, max_body=body, max_end=stun,
        current_stun=stun, current_body=body, current_end=stun,
    )
    assert from_dict(to_dict(c)) == c


def test_scene_with_complex_terrain_roundtrips():
    s = Scene(
        id="sc", name="Warehouse",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[
            Surface(id="floor1", name="Main floor",
                    polygon_xy=[(0, 0), (50, 0), (50, 50), (0, 50)],
                    elevation_m=0.0, surface_type="ground", cover_level=0,
                    is_supporting=True),
        ],
        walls=[
            Wall(id="w1", name="Wall",
                 segment=(Position(10, 0, 0), Position(10, 50, 0)),
                 height_m=4.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=8),
        ],
        hazards=[
            Hazard(id="lava1", name="Lava",
                   polygon_xy=[(20, 20), (30, 20), (30, 30), (20, 30)],
                   elevation_range_m=(0.0, 0.5),
                   trigger="on_enter",
                   effect=HazardEffect(damage_dice=4, damage_type="killing")),
        ],
        ambient=AmbientConditions(light_level=2, gravity_scale=1.0, weather="fog"),
        combatant_positions={"alice": Position(5, 5, 0)},
    )
    restored = from_dict(to_dict(s))
    assert restored.id == "sc"
    assert restored.surfaces[0].id == "floor1"
    assert restored.walls[0].id == "w1"
    assert restored.hazards[0].effect.damage_type == "killing"
    assert restored.combatant_positions["alice"] == Position(5, 5, 0)


def test_vehicle_with_passengers_roundtrips():
    v = Vehicle.make(
        id="v1", name="Bus",
        size=5, body=15, def_=6, pd=6, ed=6,
        speed=3, dex=11, str_=40,
        max_stun=30, max_end=0,
        movement_inches={"ground": 14},
        passengers=[
            Passenger("alice", "driver", False),
            Passenger("bob", "shotgun", True),
        ],
    )
    restored = from_dict(to_dict(v))
    assert isinstance(restored, Vehicle)
    assert len(restored.passengers) == 2
    assert restored.passengers[1].is_firing_port is True


def test_unit_with_morale_enum_roundtrips():
    u = Unit.from_archetype(
        id="u1", name="Goons", archetype_combatant_id="thug",
        count=20, morale=UnitMorale.SHAKEN,
    )
    restored = from_dict(to_dict(u))
    assert isinstance(restored, Unit)
    assert restored.morale == UnitMorale.SHAKEN
    assert restored.count == 20
