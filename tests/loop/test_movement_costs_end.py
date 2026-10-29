"""Moving costs END (6E1 p.158).

Nothing in the loop charged it. Every move a fighter chose --- closing,
repositioning, the Half Move, the move before a strike, a Move By --- goes
through `placement.move_toward`, which recorded the move and took no END.
The only movement END the engine ever charged was a Push's extra (6E2 p.135).

THE RULE. 6E1 p.158: "all movement costs END at the rate of 1 END per 10
Active Points in the Movement Power ... (This includes movement the
character receives for 'free,' such as the standard Running 12m.) ... If a
character uses less than his full meters of movement, typically he only
pays END proportionately (for example, he pays half the power's full END
cost when making a Half Move)."

- A movement POWER's full END is the cost engine's own figure
  (`end_usage`, Hero Designer's END column: Reduced Endurance, Increased
  Endurance Cost and Charges already in it).
- RUNNING / LEAPING bought as characteristics have no END column in Hero
  Designer; the book's rule is applied to the template's rate (Running 1
  point per metre, Leaping 1 per 2m). The book's own sheets agree:
  "Running +2m (14m total)" costs 1 END, "Leaping +4m (8m forward)" 1 END
  (6E2 p.180).
- Climbing is a Skill, and Skills cost no END (RULING: no END is printed
  for it anywhere).
- Every cost rounds as 6E1 p.132 rounds END (a half rounds down) and is at
  least 1 when anything at all is owed.
- END is charged only where the campaign counts it (`manage_endurance`),
  exactly as an attack's is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from kirby_dice import FakeRoller
from kirby_world.scene import AmbientConditions, Position, Scene, SceneBounds, Surface

from kirby_combat.endurance import end_for_points, movement_end
from kirby_combat.enumeration import LegalAction
from kirby_combat.hero_view import _movement_capabilities
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_HEROIC, RAW_SUPERHEROIC

# ---------------------------------------------------------------------------
# What a full move costs
# ---------------------------------------------------------------------------


@dataclass
class _Char:
    xmlid: str
    level_cost: float
    level_value: float


@dataclass
class _Power:
    xmlid: str
    levels: int
    active_cost: float
    end_usage: int
    objects: list = field(default_factory=list)


@dataclass
class _Hero:
    values: dict
    powers: list

    @property
    def characteristics(self):
        return [_Char("RUNNING", 1.0, 1.0), _Char("LEAPING", 1.0, 2.0)]

    def characteristic_value(self, xmlid):
        return self.values.get(xmlid, 0)


def _modes(hero):
    return {c.mode: c.end_cost for c in _movement_capabilities(hero)}


def test_the_free_running_still_costs_end():
    """12m of Running, bought for nothing, is 12 points' worth: 1 END."""
    assert _modes(_Hero({"RUNNING": 12}, []))["running"] == 1


def test_the_books_own_sheets():
    """6E2 p.180: Running 14m is 1 END, Leaping 8m (4 points) is 1 END."""
    modes = _modes(_Hero({"RUNNING": 14, "LEAPING": 8}, []))
    assert (modes["running"], modes["leaping"]) == (1, 1)


def test_more_running_costs_more_and_leaping_costs_half_as_much():
    """Running 40m is 40 points (4 END); Leaping 40m is 20 points (2 END)."""
    modes = _modes(_Hero({"RUNNING": 40, "LEAPING": 40}, []))
    assert (modes["running"], modes["leaping"]) == (4, 2)


def test_a_movement_power_costs_what_the_cost_engine_says():
    """Flight's END is Hero Designer's figure, modifiers and all: a 0 END
    Flight costs nothing, a x2 END Teleportation costs double."""
    hero = _Hero({"RUNNING": 12}, [
        _Power("FLIGHT", 30, 45.0, 0),
        _Power("TELEPORTATION", 20, 20.0, 4),
    ])
    modes = _modes(hero)
    assert (modes["flight"], modes["teleportation"]) == (0, 4)


def test_climbing_costs_nothing():
    assert _modes(_Hero({"RUNNING": 12}, []))["climbing"] == 0


def test_end_rounds_as_the_book_rounds_it():
    """6E1 p.132: 15 Active Points pays 1 END, 46 pays 5; never under 1."""
    assert [end_for_points(p) for p in (15, 46, 2, 25, 26)] == [1, 5, 1, 2, 3]


# ---------------------------------------------------------------------------
# What part of a move costs
# ---------------------------------------------------------------------------

def test_a_part_move_pays_its_share():
    """6E1 p.158: "half the power's full END cost when making a Half
    Move". Flight 4 END a full 20m: 10m is 2, 5m is 1, 20m is 4."""
    assert [movement_end(4, used_m=m, combat_m=20) for m in (20, 10, 5)] == [4, 2, 1]


def test_any_move_at_all_costs_at_least_one():
    """Running 12m is 1 END; a 3m step is a quarter of it --- still 1."""
    assert movement_end(1, used_m=3, combat_m=12) == 1


def test_free_movement_and_no_movement_cost_nothing():
    assert movement_end(0, used_m=20, combat_m=20) == 0
    assert movement_end(4, used_m=0, combat_m=20) == 0


def test_a_pushed_move_pays_the_full_move_and_no_more_here():
    """Metres past his movement are a Push, and a Push is paid for by
    its own +END (6E2 p.135, `reposition_push`); the move itself costs
    its full END and not a share above it."""
    assert movement_end(4, used_m=28, combat_m=20) == 4


# ---------------------------------------------------------------------------
# The loop charges it
# ---------------------------------------------------------------------------

def _scene():
    return Scene(
        id="lot", name="A Lot", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(0, 0), (100, 0), (100, 100), (0, 100)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(gravity_scale=1.0),
        combatant_positions={"r": Position(10, 10, 0), "e": Position(60, 10, 0)},
    )


def _session(template, *, running=40):
    runner = synthetic_combatant(
        id="r", name="r", spd=4, dex=20, running=running, max_end=40,
        side=Side.named("a"))
    enemy = synthetic_combatant(id="e", name="e", spd=4, side=Side.named("b"))
    return CombatSession.create(
        id="s", combatants=[runner, enemy], scene=_scene(),
        template=template, dice_roller=FakeRoller([]),
    ).start()


def _move_at_e():
    return LegalAction(action_id="move:e", kind="move", target_id="e",
                       power_xmlid=None, power_name=None,
                       mode="running", summary="close on e")


def _end_rows(resolved):
    return [(e.end, e.reason) for e in resolved.events
            if e.kind == "VitalsChanged" and e.combatant_id == "r"]


def test_a_full_move_is_paid_for_in_the_log():
    """Running 40m, all of it toward a man 50m away: 4 END, recorded."""
    session = _session(RAW_HEROIC)
    out = resolve_chosen(session, session.combatants["r"], _move_at_e(),
                         template=RAW_HEROIC, roller=FakeRoller([]))
    assert _end_rows(out) == [(-4, "end_spent")]
    assert out.session.combatants["r"].state.current_end == 36


def test_a_campaign_that_does_not_count_end_charges_none():
    """`manage_endurance=False` --- the superheroic template's setting ---
    is honoured for movement exactly as it is for an attack."""
    session = _session(RAW_SUPERHEROIC)
    out = resolve_chosen(session, session.combatants["r"], _move_at_e(),
                         template=RAW_SUPERHEROIC, roller=FakeRoller([]))
    assert _end_rows(out) == []


def test_a_short_move_pays_a_share():
    """Running 40m, the enemy 50m off but only 10m of it walkable from a
    start 40m closer: 10 of 40 metres, a quarter of 4 END --- 1."""
    session = _session(RAW_HEROIC)
    session = replace(session, scene=replace(session.scene, combatant_positions={
        "r": Position(49, 10, 0), "e": Position(60, 10, 0)}))
    out = resolve_chosen(session, session.combatants["r"], _move_at_e(),
                         template=RAW_HEROIC, roller=FakeRoller([]))
    assert _end_rows(out) == [(-1, "end_spent")]
