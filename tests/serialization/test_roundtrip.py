"""Round-trip parity tests — to_dict -> from_dict invariant."""
from __future__ import annotations

import dataclasses
from typing import get_args

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
from kirby_combat.session.apply import apply_event
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.session.events import (
    EVENT_CLASSES, VitalsChanged,
    SessionStarted, SegmentAdvanced, ActionDeclared, StatusEffectsChanged,
    SessionEnded, EventAuthor, make_author_engine,
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


def _an_instance(cls):
    """One of these, built from the base fields alone.

    Every concrete event gives all of its own fields a default, so this is
    a total constructor over the union -- no per-class table, which is the
    thing that went stale.
    """
    return cls(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=_ts(), author=make_author_engine(),
    )


def test_the_gate_could_actually_fail():
    """The negative control, FIRST. An event class that is not registered
    must not round-trip -- otherwise the parametrised test below passes
    whether or not registration happened.

    `_Unregistered` is a real event-shaped dataclass that is deliberately
    NOT a member of the `CombatEvent` union, so it is absent from
    `EVENT_CLASSES` and therefore from the registry `from_dict` builds.
    This is exactly the state `VitalsChanged` was in.
    """
    from dataclasses import dataclass, field
    from typing import Literal

    from kirby_combat.session.events import _BaseEvent

    @dataclass
    class _Unregistered(_BaseEvent):
        kind: Literal["_Unregistered"] = field(
            default="_Unregistered", init=False)

    assert _Unregistered not in EVENT_CLASSES

    payload = to_dict(_an_instance(_Unregistered))
    with pytest.raises(TypeError, match="_Unregistered"):
        from_dict(payload)


def test_the_union_is_the_only_list_of_events():
    """`EVENT_CLASSES` is `get_args(CombatEvent)`, not a copy of it.

    The registry and the gate below both read this. A second hand-written
    list is how six of twenty-eight events came to be unreadable off the
    wire while a test called "every event type roundtrips" stayed green.
    """
    from kirby_combat.session.events import CombatEvent

    assert set(EVENT_CLASSES) == set(get_args(CombatEvent))
    assert len(EVENT_CLASSES) >= 28


@pytest.mark.parametrize(
    "cls", EVENT_CLASSES, ids=lambda c: c.__name__,
)
def test_every_event_in_the_union_roundtrips(cls):
    """THE PROPERTY, over the union rather than over a list somebody kept.

    Field-by-field, not just the type: a class can be registered and still
    lose a field to a coercion that does not know its shape.
    """
    original = _an_instance(cls)

    restored = from_dict(to_dict(original))

    assert type(restored) is type(original)
    for f in dataclasses.fields(original):
        if f.name == "timestamp":
            # Pre-existing: `to_dict` writes an ISO string and `from_dict`
            # leaves it as one for a `datetime`-annotated field. Out of
            # scope here; asserted as the shape it really is so this gate
            # is not quietly asserting something false.
            assert restored.timestamp == original.timestamp.isoformat()
            continue
        assert getattr(restored, f.name) == getattr(original, f.name), f.name


def test_a_populated_vitals_row_survives_the_wire():
    """The row the harness actually persists, with real numbers on it.

    The scenario: a consumer writes the rows as JSON, reloads them to
    rehydrate, and replays. Before this, the first damage row raised
    `TypeError: unknown type 'VitalsChanged'` and the fight could not be
    rebuilt at all.
    """
    import json

    original = VitalsChanged(
        id="evt-9", session_id="s1", sequence=9, timestamp=_ts(),
        author=make_author_engine(),
        combatant_id="villain", stun=-14, body=-3, end=-5, reason="damage",
    )

    restored = from_dict(json.loads(json.dumps(to_dict(original))))

    assert (restored.combatant_id, restored.stun, restored.body,
            restored.end, restored.reason) == (
        "villain", -14, -3, -5, "damage")


def _a_short_fight():
    """A real fight, run through the loop, so the rows are the rows the
    engine actually emits rather than ones this test made up."""
    from fixtures.synthetic_hero import synthetic_combatant

    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import FirstLegalChooser, run_encounter
    from kirby_combat.models import AttackPower
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    def _f(id_: str, side: str, dex: int):
        blast = AttackPower(
            xmlid="ENERGYBLAST", name="Blast", damage_dice=8, half_die=False,
            plus_one=False, damage_type="normal", defense_type="ed",
            range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
            penetrating=0, increased_stun_mult=0, source_id=f"{id_}-eb",
            is_ranged=True,
        )
        return synthetic_combatant(
            id=id_, name=id_, ocv=9, dcv=5, spd=4, dex=dex, rec=6,
            pd=4, ed=4, con=18,
            max_stun=40, max_body=12, max_end=40,
            current_stun=40, current_body=12, current_end=40,
            side=Side.named(side), attacks=[blast],
        )

    template = CombatTemplate.default_6e_superheroic()
    session = CombatSession.create(
        id="s", combatants=[_f("a", "x", 25), _f("b", "y", 10)],
        scene=None, template=template, dice_roller=RandomRoller(seed=7),
    ).start()
    result = run_encounter(
        Encounter(id="e", turn=1, segment=12, sessions=[session]),
        FirstLegalChooser(), roller=RandomRoller(seed=5),
        on_unresolvable="skip", max_turns=8,
    )
    return result.encounter.sessions[0]


def test_a_fight_replayed_from_json_rows_lands_on_the_same_vitals():
    """End to end, the way the harness does it: persist every row as JSON,
    read them back, replay them into a fresh session.

    This is the test the engine-side replay test could not be: that one
    never leaves Python objects, so six unregistered event classes were
    invisible to it.
    """
    import json

    live = _a_short_fight()
    rows = [json.loads(json.dumps(to_dict(e))) for e in live.event_log]
    assert any(r["__type__"] == "VitalsChanged" for r in rows), (
        "the fight must actually have hurt somebody")

    rebuilt = rewind_to_sequence(live, 0)
    for row in rows:
        rebuilt = apply_event(rebuilt, from_dict(row))

    assert {cid: (c.state.current_stun, c.state.current_body,
                  c.state.current_end)
            for cid, c in rebuilt.combatants.items()} == \
        {cid: (c.state.current_stun, c.state.current_body,
               c.state.current_end)
         for cid, c in live.combatants.items()}


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


def test_status_effects_changed_wire_shape_is_sorted_lists():
    """`added`/`removed` are frozenset[str] in Python — not JSON. The wire
    representation is a sorted list (same precedent as the HeroCombatant
    snapshot's `"statuses": sorted(obj.state.statuses)` in to_dict.py),
    which is both valid JSON and stable/diffable in a recorded stream."""
    ev = StatusEffectsChanged(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=_ts(), author=make_author_engine(),
        combatant_id="a",
        added=frozenset({"stunned", "prone"}),
        removed=frozenset({"entangled", "flash_sight"}),
    )
    wire = to_dict(ev)
    assert wire["added"] == ["prone", "stunned"]
    assert wire["removed"] == ["entangled", "flash_sight"]


def test_status_effects_changed_roundtrips_with_both_added_and_removed():
    ev = StatusEffectsChanged(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=_ts(), author=make_author_engine(),
        combatant_id="a",
        added=frozenset({"stunned", "prone"}),
        removed=frozenset({"entangled", "flash_sight"}),
    )
    restored = from_dict(to_dict(ev))
    assert type(restored) is type(ev)
    assert restored.combatant_id == ev.combatant_id
    assert restored.added == frozenset({"stunned", "prone"})
    assert restored.removed == frozenset({"entangled", "flash_sight"})
    assert isinstance(restored.added, frozenset)
    assert isinstance(restored.removed, frozenset)


def test_status_effects_changed_unregistered_type_fails_to_replay():
    """Proves the from_dict registry wiring actually matters: if
    StatusEffectsChanged were missing from the `_TYPE_REGISTRY` (the
    import + class-list step in from_dict.py's `_ensure_registry`), a
    recorded event of this kind could not replay. Simulate that by
    deleting it from the (already-populated) registry and confirming
    from_dict then raises rather than silently succeeding."""
    import sys
    import kirby_combat.serialization.from_dict  # noqa: F401 — ensures it's imported
    from_dict_module = sys.modules["kirby_combat.serialization.from_dict"]

    ev = StatusEffectsChanged(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=_ts(), author=make_author_engine(),
        combatant_id="a",
        added=frozenset({"stunned"}),
        removed=frozenset({"entangled"}),
    )
    wire = to_dict(ev)

    from_dict_module._ensure_registry()  # populate if not already
    saved = from_dict_module._TYPE_REGISTRY.pop("StatusEffectsChanged")
    try:
        with pytest.raises(TypeError):
            from_dict(wire)
    finally:
        from_dict_module._TYPE_REGISTRY["StatusEffectsChanged"] = saved
