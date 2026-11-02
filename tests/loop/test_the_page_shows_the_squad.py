"""The fighter's page shows what can hurt him, where to take cover and, in a
squad, his orders (squad tactics spec, sections 2, 4 and 6); an offer that
carries the order out says so through `Brief.offer_summary`."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from shaped import armed, encounter_on, scene_with, shaped_blast
from test_threat_picture import area

from kirby_combat.brief import Brief
from kirby_combat.loop.run import _situation_for
from kirby_combat.scene.scene import Position, Wall
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.side import Side
from kirby_combat.squads import FireTeam, Squad, SquadOrders, TeamTask, name_leaders, record_orders
from kirby_combat.template import PageKnowledge

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
SUFFIX = " (carries out your orders)"


def _use(session, who, name):
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_combatant(who), declaration_event_id="",
        result_payload={"kind": "attack", "hit": False, "power_name": name,
                        "target_id": "l", "stun_dealt": 0, "body_dealt": 0,
                        "status_changes": []}))


_PLACES = {"Talisman": (0, 0, 0), "l": (40, 0, 0), "b": (44, 0, 0), "c": (40, 8, 0)}


def _fight(*, squad="alpha", radius=18.0, walls=(), template=None):
    storm = shaped_blast("storm", 4, area=area(radius), name="Storm",
                         range_m=100, is_ranged=True)
    people = [armed("Talisman", storm, side=VILLAINS, dex=10)]
    bolt = shaped_blast("bolt", 4, name="Bolt", range_m=100, is_ranged=True)
    people += [armed(m, bolt, side=HEROES, dex=30 - i, squad=squad)
               for i, m in enumerate(("l", "b", "c"))]
    e = encounter_on(scene_with(_PLACES, walls=walls), *people)
    s = name_leaders(e.sessions[0])
    if template is not None:
        s = replace(s, template=template)
    return _use(s, "Talisman", "Storm")


def _page(s, who="l"):
    return Brief(_situation_for(s, who)).render()


def _section(page, heading):
    lines = page.split("\n")
    start = lines.index(heading)
    out = []
    for line in lines[start + 1:]:
        if not line.startswith("  "):
            break
        out.append(line.strip())
    return out


def _cover_wall():
    return Wall(id="crates", name="Packing crates",
                segment=(Position(30, -4, 0), Position(30, 4, 0)),
                height_m=1.0, blocks_los=False, cover_level=3)


def _alpha():
    return Squad(name="alpha", side="heroes", member_ids=("l", "b", "c"))


def _orders(s, task, **kw):
    team = FireTeam(member_ids=("l", "b", "c"), task=task, target_id=kw.get("target_id"),
                    radius_m=kw.get("radius_m"), position=kw.get("position"))
    return record_orders(s, _alpha(), "l", SquadOrders(teams=(team,)))


# ── What can hurt you ──────────────────────────────────────────────────────


def test_an_area_is_told_in_words_with_what_answers_it():
    rows = _section(_page(_fight()), "What can hurt you:")
    assert rows[0].startswith(
        "Talisman has shown Storm, an area with a radius of 18 m; 2 of your squad stand inside "
        "one. It reaches you now. Dodge won't help; diving clear, ")
    assert "spacing out" in rows[0] and rows[0].endswith(" will.")
    assert rows[1] == "Talisman can reach 3 of your side."


def test_a_single_target_power_is_dodgeable_and_has_no_squad_clause():
    bolt = shaped_blast("bolt", 4, name="Bolt", range_m=100, is_ranged=True)
    e = encounter_on(scene_with({"Talisman": (0, 0, 0), "l": (10, 0, 0)}),
                     armed("Talisman", bolt, side=VILLAINS),
                     armed("l", None, side=HEROES, squad="alpha"))
    s = _use(name_leaders(e.sessions[0]), "Talisman", "Bolt")
    (row, *_) = _section(_page(s), "What can hurt you:")
    assert row.startswith("Talisman has shown Bolt. It reaches you now. Dodging")
    assert "stand inside" not in row and "won't help" not in row


def test_nothing_shown_means_no_section():
    e = encounter_on(scene_with(_PLACES),
                     armed("Talisman", shaped_blast("s", 4, name="Storm"), side=VILLAINS),
                     armed("l", None, side=HEROES))
    assert "What can hurt you" not in _page(e.sessions[0])


# ── Cover ──────────────────────────────────────────────────────────────────


def test_cover_names_the_spot_its_distance_reach_and_who_it_hides_from():
    rows = _section(_page(_fight(walls=[_cover_wall()])), "Cover:")
    assert len(rows) <= 3
    assert rows[0] == "Packing crates: you can reach it this Phase, hides you from Talisman."
    assert "m away" not in rows[0]       # the one distance is in "What is around you"
    around = _section(_page(_fight(walls=[_cover_wall()])), "What is around you:")
    assert any(r.startswith("Packing crates: ") for r in around)


def test_cover_says_when_a_spot_is_out_of_reach():
    far = Wall(id="rock", name="Rock", segment=(Position(5, -4, 0), Position(5, 4, 0)),
               height_m=1.0, blocks_los=False, cover_level=3)
    rows = _section(_page(_fight(walls=[far])), "Cover:")
    assert "cannot reach it this Phase" in rows[0]


def test_no_cover_means_no_section():
    assert "Cover:" not in _page(_fight())


# ── Your orders ────────────────────────────────────────────────────────────


def test_a_squad_member_reads_his_task_and_teammates():
    s = _orders(_fight(), TeamTask.FOCUS_FIRE, target_id="Talisman")
    rows = _section(_page(s, "b"), "Your orders:")
    assert rows == ["Squad alpha: focus fire on Talisman.", "With you: l, c."]


def test_the_other_tasks_read_in_words():
    said = {
        TeamTask.TAKE_COVER: "take cover and fire from there",
        TeamTask.HOLD: "hold your action",
        TeamTask.WITHDRAW: "fall back",
    }
    for task, words in said.items():
        rows = _section(_page(_orders(_fight(), task), "b"), "Your orders:")
        assert rows[0] == f"Squad alpha: {words}."
    rows = _section(_page(_orders(_fight(), TeamTask.SPREAD_OUT, radius_m=20.0), "b"),
                    "Your orders:")
    assert rows[0] == "Squad alpha: keep 20 m apart."


def test_no_orders_yet_names_the_leader():
    rows = _section(_page(_fight(), "b"), "Your orders:")
    assert rows == ["Your leader, l, has given no orders yet."]


def test_no_squad_no_orders_section():
    assert "Your orders" not in _page(_fight(squad=None))


# ── The suffix ─────────────────────────────────────────────────────────────


def test_an_offer_that_carries_out_the_order_says_so_through_offer_summary():
    s = _orders(_fight(), TeamTask.FOCUS_FIRE, target_id="Talisman")
    situation = _situation_for(s, "b")
    brief = Brief(situation)
    at = next(a for a in brief.menu if a.kind == "attack" and a.target_id == "Talisman")
    other = next(a for a in brief.menu if a.kind == "move")
    assert brief.offer_summary(at).endswith(SUFFIX)
    assert not brief.offer_summary(other).endswith(SUFFIX)
    page = brief.render()
    assert f"[{at.action_id}] " in page
    assert [ln for ln in page.split("\n") if ln.strip().startswith(f"[{at.action_id}]")][0] \
        .endswith(SUFFIX)


def test_no_order_no_suffix():
    brief = Brief(_situation_for(_fight(), "b"))
    assert not any(brief.offer_summary(a).endswith(SUFFIX) for a in brief.menu)


def test_the_suffix_shows_on_a_sheet_page_too():
    from tests.templates import PLAIN
    s = _orders(_fight(template=replace(PLAIN, page_knowledge=PageKnowledge.SHEET)),
                TeamTask.FOCUS_FIRE, target_id="Talisman")
    brief = Brief(_situation_for(s, "b"))
    at = next(a for a in brief.menu if a.kind == "attack" and a.target_id == "Talisman")
    assert brief.offer_summary(at).endswith(SUFFIX)
    page = brief.render()
    assert "What can hurt you:" in page and "Your orders:" in page


def test_the_perceived_set_is_computed_once_per_page(monkeypatch):
    from kirby_combat import brief_detail
    calls = []
    real = brief_detail.sightings
    monkeypatch.setattr(brief_detail, "sightings",
                        lambda sit: calls.append(1) or real(sit))
    s = _orders(_fight(), TeamTask.WITHDRAW)     # every move asks who he perceives
    brief = Brief(_situation_for(s, "b"))
    calls.clear()
    moves = [a for a in brief.menu if a.kind in ("move", "half_move", "reposition_strike")]
    assert len(moves) > 1
    for a in brief.menu:
        brief.offer_summary(a)
    assert len(calls) == 1


# ── Fix round 1 ────────────────────────────────────────────────────────────


def _sheet_fight(**kw):
    from tests.templates import PLAIN
    return _fight(template=replace(PLAIN, page_knowledge=PageKnowledge.SHEET), **kw)


def test_a_sheet_page_with_walls_shows_cover():
    page = _page(_sheet_fight(walls=[_cover_wall()]))
    assert _section(page, "Cover:")[0].startswith("Packing crates: ")


def test_an_area_he_has_not_used_is_not_on_the_page():
    storm = shaped_blast("storm", 4, area=area(18.0), name="Storm",
                         range_m=100, is_ranged=True)
    e = encounter_on(scene_with(_PLACES),
                     armed("Talisman", storm, side=VILLAINS, dex=10),
                     armed("l", None, side=HEROES, squad="alpha"))
    for page in (_page(e.sessions[0]), _page(replace(
            e.sessions[0], template=_sheet_fight().template))):
        assert "What can hurt you" not in page
        assert "Storm, an area" not in page
    used = _use(e.sessions[0], "Talisman", "Storm")        # positive control
    assert "Storm, an area" in _page(used)


def test_an_enemy_with_nothing_shown_gets_no_reach_line():
    page = _page(_fight())
    assert page.count("Talisman can reach") == 1  # he showed Storm
    quiet = encounter_on(scene_with(_PLACES),
                         armed("Talisman", None, side=VILLAINS),
                         armed("l", None, side=HEROES))
    assert "Talisman can reach" not in _page(quiet.sessions[0])


def test_orders_that_did_not_name_him_say_so():
    s = _fight()
    team = FireTeam(member_ids=("l", "c"), task=TeamTask.HOLD, target_id=None,
                    radius_m=None, position=None)
    s = record_orders(s, _alpha(), "l", SquadOrders(teams=(team,)))
    assert _section(_page(s, "b"), "Your orders:") == ["Your leader's orders did not name you."]


def test_a_cover_spot_the_scene_does_not_hold_is_an_error():
    import pytest
    from dataclasses import replace as rep
    from kirby_combat.brief_detail import cover_lines
    from kirby_combat.loop.run import _situation_for
    from kirby_combat.threat_picture import threat_picture
    s = _fight(walls=[_cover_wall()])
    sit = _situation_for(s, "l")
    pic = threat_picture(sit)
    ghost = rep(pic.cover[0], feature_id="ghost")
    with pytest.raises(KeyError, match="ghost"):
        cover_lines(sit, rep(pic, cover=(ghost,)))
