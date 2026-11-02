"""The threat picture: what each perceived enemy has SHOWN he can do, whether
it reaches the fighter now, which defences answer it, and how many of his own
squad an area would catch (squad tactics spec, section 2)."""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime

from shaped import armed, encounter_on, scene_with, shaped_blast

from kirby_combat.defences import Defence
from kirby_combat.judgement import MAX_SEEN, judge_enemy, powers_seen
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.side import Side
from kirby_combat.threat_picture import threat_picture

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def area(size: float) -> AreaSpec:
    return AreaSpec(shape=AreaShape.RADIUS, size_m=size,
                    targeting=AreaTargeting.STANDARD, explosion=False,
                    personal_immunity=False, width_m=2.0, height_m=2.0,
                    thin_cone=False, unbuilt=())


def _use(session, who, name, *, kind="attack"):
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC),
        author=make_author_combatant(who),
        declaration_event_id="",
        result_payload={"kind": kind, "hit": False, "power_name": name,
                        "target_id": "me", "stun_dealt": 0, "body_dealt": 0,
                        "status_changes": []}))


def _situation(session, me="me"):
    actor = session.combatants[me]
    return PhaseSituation(
        actor=actor, menu=[],
        enemies=[c for c in session.combatants.values() if c.side != actor.side],
        allies=[c for c in session.combatants.values()
                if c.side == actor.side and c.id != me],
        distances_m={}, session=session)


def _fight(positions, *, radius=12.0, range_m=100, squads=None, villains=("her",)):
    squads = squads or {}
    storm = shaped_blast("storm", 4, area=area(radius), name="Storm",
                         range_m=range_m, is_ranged=range_m > 0)
    people = [armed(v, storm, side=VILLAINS, dex=30) for v in villains]
    people += [armed(m, None, side=HEROES, dex=20 - i, squad=squads.get(m))
               for i, m in enumerate(m for m in positions if m not in villains)]
    return encounter_on(scene_with(positions), *people).sessions[0]


def test_an_unseen_power_is_not_a_threat():
    s = _fight({"her": (0, 0, 0), "me": (10, 0, 0)})
    pic = threat_picture(_situation(s))
    assert pic.lines == ()
    assert pic.enemies_who_can_reach_me == 0


def test_a_used_area_counts_the_bunched_squadmates():
    pos = {"her": (0, 0, 0), "me": (40, 0, 0), "b": (44, 0, 0),
           "c": (40, 8, 0), "far": (40, 30, 0), "other": (41, 0, 0)}
    s = _fight(pos, squads={"me": "alpha", "b": "alpha", "c": "alpha",
                            "far": "alpha", "other": "beta"})
    s = _use(s, "her", "Storm")
    (line,) = threat_picture(_situation(s)).lines
    assert line.enemy_id == "her" and line.power_name == "Storm"
    assert line.kind == "attack"
    assert line.area_radius_m == 12
    assert line.squadmates_it_would_catch == 2     # b and c; not far, other, himself
    assert Defence.DODGE not in line.answered_by
    assert Defence.DIVE_FOR_COVER in line.answered_by


def test_a_downed_squadmate_is_not_counted():
    pos = {"her": (0, 0, 0), "me": (40, 0, 0), "b": (44, 0, 0)}
    s = _fight(pos, squads={"me": "alpha", "b": "alpha"})
    s = _use(s, "her", "Storm")
    from dataclasses import replace
    b = s.combatants["b"]
    s.combatants["b"] = replace(b, state=replace(b.state, current_stun=0))
    (line,) = threat_picture(_situation(s)).lines
    assert line.squadmates_it_would_catch == 0


def test_no_squad_means_none():
    s = _fight({"her": (0, 0, 0), "me": (40, 0, 0), "b": (44, 0, 0)})
    s = _use(s, "her", "Storm")
    (line,) = threat_picture(_situation(s)).lines
    assert line.squadmates_it_would_catch is None


def test_a_single_target_power_has_no_radius_or_squad_count():
    storm = shaped_blast("bolt", 4, name="Bolt")
    s = encounter_on(scene_with({"her": (0, 0, 0), "me": (10, 0, 0)}),
                     armed("her", storm, side=VILLAINS),
                     armed("me", None, side=HEROES, squad="alpha")).sessions[0]
    s = _use(s, "her", "Bolt")
    (line,) = threat_picture(_situation(s)).lines
    assert line.area_radius_m is None
    assert line.squadmates_it_would_catch is None
    assert Defence.DODGE in line.answered_by


def test_out_of_range_cannot_reach():
    s = _fight({"her": (0, 0, 0), "me": (60, 0, 0)}, range_m=30)
    s = _use(s, "her", "Storm")
    pic = threat_picture(_situation(s))
    assert pic.lines[0].can_reach_me is False
    assert pic.enemies_who_can_reach_me == 0
    near = _fight({"her": (0, 0, 0), "me": (20, 0, 0)}, range_m=30)
    near = _use(near, "her", "Storm")
    pic = threat_picture(_situation(near))
    assert pic.lines[0].can_reach_me is True
    assert pic.enemies_who_can_reach_me == 1


def _all_seen(monkeypatch, *ids):
    """Perceived whatever the walls say (a sense that sees through them)."""
    # The module, by name: `kirby_combat.threat_picture` the attribute is the
    # exported function, which shadows the module of the same name.
    tp = sys.modules["kirby_combat.threat_picture"]
    from kirby_combat.brief_detail import Sighting
    monkeypatch.setattr(tp, "sightings", lambda sit: {
        i: Sighting(enemy_id=i, physical=True, mental=False, through_lock=False)
        for i in ids})


def test_a_wall_in_the_line_stops_a_ranged_power(monkeypatch):
    from kirby_combat.scene.scene import Position, Wall
    wall = Wall(id="w", name="w", segment=(Position(10, -10, 0), Position(10, 10, 0)),
                height_m=4.0, blocks_los=True, cover_level=3)
    storm = shaped_blast("storm", 4, area=area(4.0), name="Storm")
    s = encounter_on(scene_with({"her": (0, 0, 0), "me": (20, 0, 0)}, walls=[wall]),
                     armed("her", storm, side=VILLAINS),
                     armed("me", None, side=HEROES)).sessions[0]
    s = _use(s, "her", "Storm")
    _all_seen(monkeypatch, "her")
    assert threat_picture(_situation(s)).lines[0].can_reach_me is False


def test_men_she_can_reach_counts_his_side():
    pos = {"her": (0, 0, 0), "me": (20, 0, 0), "b": (25, 0, 0), "far": (500, 0, 0)}
    s = _fight(pos, range_m=30)
    s = _use(s, "her", "Storm")
    pic = threat_picture(_situation(s))
    assert pic.men_she_can_reach["her"] == 2        # me and b, not far


def test_an_enemy_he_cannot_perceive_is_not_in_the_picture(monkeypatch):
    s = _fight({"her": (0, 0, 0), "me": (10, 0, 0)})
    s = _use(s, "her", "Storm")
    # The module, by name: `kirby_combat.threat_picture` the attribute is the
    # exported function, which shadows the module of the same name.
    tp = sys.modules["kirby_combat.threat_picture"]
    from kirby_combat.brief_detail import Sighting
    monkeypatch.setattr(tp, "sightings", lambda sit: {
        "her": Sighting(enemy_id="her", physical=False, mental=False,
                        through_lock=False)})
    pic = threat_picture(_situation(s))
    assert pic.lines == () and pic.men_she_can_reach == {}


def test_a_non_threat_use_gets_no_line():
    s = _fight({"her": (0, 0, 0), "me": (10, 0, 0)})
    s = _use(s, "her", "Sprint", kind="move")
    assert threat_picture(_situation(s)).lines == ()


def test_a_maneuver_takes_its_kind_from_the_row():
    s = _fight({"her": (0, 0, 0), "me": (1, 0, 0)})
    s = _use(s, "her", "Haymaker", kind="haymaker")
    (line,) = threat_picture(_situation(s)).lines
    assert line.kind == "haymaker"
    assert line.can_reach_me is True               # within her reach
    assert Defence.BLOCK in line.answered_by
    far = _fight({"her": (0, 0, 0), "me": (30, 0, 0)})
    far = _use(far, "her", "Haymaker", kind="haymaker")
    assert threat_picture(_situation(far)).lines[0].can_reach_me is False


def test_cover_is_the_best_three_and_empty_with_no_map(monkeypatch):
    from kirby_combat.scene.scene import Position, Wall

    def wall(i, x):
        return Wall(id=f"w{i}", name=f"w{i}",
                    segment=(Position(x, -3, 0), Position(x, 3, 0)),
                    height_m=3.0, blocks_los=True, cover_level=3)
    walls = [wall(i, 28 + 2 * i) for i in range(5)]
    storm = shaped_blast("storm", 4, area=area(4.0), name="Storm")
    s = encounter_on(scene_with({"her": (0, 0, 0), "me": (30, 0, 0)}, walls=walls),
                     armed("her", storm, side=VILLAINS),
                     armed("me", None, side=HEROES, running=12)).sessions[0]
    s = _use(s, "her", "Storm")
    _all_seen(monkeypatch, "her")
    pic = threat_picture(_situation(s))
    assert len(pic.cover) == 3
    assert pic.reach_m == 12.0                       # his Running this Phase
    bare = _fight({"her": (0, 0, 0), "me": (10, 0, 0)})
    bare = _use(bare, "her", "Storm")
    assert threat_picture(_situation(bare)).cover == ()


def test_without_a_map_cover_is_empty_and_reach_is_unknown_so_open():
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.synthetic import synthetic_combatant
    storm = shaped_blast("storm", 4, area=area(6.0), name="Storm")
    s = CombatSession.create(
        id="s", scene=None, template=None, dice_roller=None,
        combatants=[synthetic_combatant(id="her", name="her", side=VILLAINS,
                                        attacks=[storm]),
                    synthetic_combatant(id="me", name="me", side=HEROES,
                                        squad="a"),
                    synthetic_combatant(id="b", name="b", side=HEROES,
                                        squad="a")]).start()
    s = _use(s, "her", "Storm")
    pic = threat_picture(_situation(s))
    assert pic.cover == ()
    assert pic.lines[0].can_reach_me is True          # an unplaced man is not gated
    assert pic.lines[0].squadmates_it_would_catch == 0  # nobody can be shown beside him


def test_powers_seen_is_uncapped_and_judge_enemy_caps_it():
    s = _fight({"her": (0, 0, 0), "me": (10, 0, 0)})
    for i in range(MAX_SEEN + 3):
        s = _use(s, "her", f"P{i}")
    assert len(powers_seen(s, "her")) == MAX_SEEN + 3
    assert powers_seen(s, "her")[:2] == ("P0", "P1")
    j = judge_enemy(_situation(s), s.combatants["her"])
    assert len(j.seen) == MAX_SEEN and j.seen_more == 3
