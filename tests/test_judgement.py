"""What a fighter can JUDGE of one enemy: how hurt he looks, what he has been
seen to use, how the hits on him visibly landed --- and none of his sheet."""
import uuid
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from types import SimpleNamespace

from kirby_dice import RandomRoller
from kirby_combat.judgement import EnemyJudgement, judge_enemy, render_judgement
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import (
    CINEMATIC_SUPERHEROIC, RAW_SUPERHEROIC,
)


def _c(ident, side, **kw):
    return synthetic_combatant(id=ident, name=ident.capitalize(), side=side, **kw)


def _session(*combatants, template=RAW_SUPERHEROIC):
    return CombatSession.create(
        id="s", combatants=list(combatants), scene=None, template=template,
        dice_roller=RandomRoller(seed=1),
    ).start()


def _resolved(session, author, **payload):
    base = {"kind": "attack", "hit": False, "stun_dealt": 0, "body_dealt": 0,
            "status_changes": []}
    base.update(payload)
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(author),
        declaration_event_id="", result_payload=base,
    ))


def _situation(session, actor_id="hero", foe_id="vex", distance=34.0):
    return PhaseSituation(
        actor=session.combatants[actor_id], menu=[],
        enemies=[session.combatants[foe_id]], allies=[],
        distances_m={foe_id: distance}, session=session,
    )


def _fight(**foe_kw):
    return _session(_c("hero", "heroes"), _c("vex", "villains", **foe_kw))


def test_no_sheet_numbers_on_a_judged_enemy():
    s = _fight()
    s = _resolved(s, "vex", power_name="Energy Disk", target_id="hero")
    s = _resolved(s, "hero", power_name="Strike", target_id="vex", hit=True,
                  stun_dealt=9, body_dealt=3, status_changes=["Stunned"])
    lines = "\n".join(render_judgement(
        judge_enemy(_situation(s), s.combatants["vex"])))
    assert "Vex" in lines
    for hidden in ("STUN", "BODY", "PD", "ED", "OCV", "DCV", "SPD", "EGO"):
        assert hidden not in lines


def test_a_power_he_used_is_seen_and_one_he_has_not_is_not():
    s = _fight()
    s = _resolved(s, "vex", power_name="Energy Disk", target_id="hero")
    s = _resolved(s, "vex", power_name="Strike", target_id="hero")
    s = _resolved(s, "vex", power_name="Energy Disk", target_id="hero")
    # Someone ELSE using Hellfire is not Vex using it.
    s = _resolved(s, "hero", power_name="Hellfire", target_id="vex")
    j = judge_enemy(_situation(s), s.combatants["vex"])
    assert j.seen == ("Energy Disk", "Strike")
    assert "Hellfire" not in j.seen
    assert j.acted is True
    assert "seen: Energy Disk, Strike" in "\n".join(render_judgement(j))


def test_a_hit_he_took_says_what_visibly_followed():
    s = _fight()
    s = _resolved(s, "hero", power_name="Hellfire", target_id="vex", hit=True,
                  stun_dealt=12, body_dealt=4, status_changes=["Stunned"])
    s = _resolved(s, "hero", power_name="Strike", target_id="vex", hit=True)
    s = _resolved(s, "hero", power_name="Blast", target_id="vex", hit=False)
    j = judge_enemy(_situation(s), s.combatants["vex"])
    assert j.how_hits_landed == (
        "Hellfire hit him; he staggered (Stunned)",
        "Strike hit him; he kept fighting",
    )


def test_an_unperceived_enemy_reveals_nothing(monkeypatch):
    from kirby_combat import judgement
    from kirby_combat.brief_detail import Sighting

    s = _fight()
    s = _resolved(s, "vex", power_name="Energy Disk", target_id="hero")
    s = _resolved(s, "hero", power_name="Strike", target_id="vex", hit=True)
    monkeypatch.setattr(judgement, "sightings", lambda sit: {
        "vex": Sighting(enemy_id="vex", physical=False, mental=False,
                        through_lock=False)})
    j = judge_enemy(_situation(s), s.combatants["vex"])
    assert j.perceived is False
    assert (j.name, j.side) == ("Vex", "villains")
    assert j.seen == () and j.how_hits_landed == () and j.features == ()
    assert j.looks == "" and j.distance_m is None and j.acted is False
    text = "\n".join(render_judgement(j))
    assert "Energy Disk" not in text and "Strike" not in text


def test_turn_one_reads_has_not_acted_yet():
    s = _fight()
    j = judge_enemy(_situation(s), s.combatants["vex"])
    assert j.acted is False and j.seen == ()
    assert "has not acted yet" in "\n".join(render_judgement(j))
    s = _resolved(s, "vex", power_name="Strike", target_id="hero")
    assert "has not acted yet" not in "\n".join(render_judgement(
        judge_enemy(_situation(s), s.combatants["vex"])))


def test_a_declared_action_counts_as_having_acted():
    s = _fight()
    s = apply_event(s, ActionDeclared(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("vex"), combatant_id="vex",
        action_type="attack"))
    assert judge_enemy(_situation(s), s.combatants["vex"]).acted is True


def test_a_mook_reads_as_one_only_under_the_mook_rules():
    for template, expected in ((RAW_SUPERHEROIC, False),
                               (CINEMATIC_SUPERHEROIC, True)):
        s = _session(_c("hero", "heroes"), _c("vex", "villains", minor_hits=1),
                     template=template)
        j = judge_enemy(_situation(s), s.combatants["vex"])
        assert ("a mook" in j.features) is expected, template.name
    # Cinematic rules but a man with no minor_hits is no mook.
    s = _session(_c("hero", "heroes"), _c("vex", "villains"),
                 template=CINEMATIC_SUPERHEROIC)
    assert "a mook" not in judge_enemy(_situation(s), s.combatants["vex"]).features


def test_an_automaton_reads_as_a_machine():
    foe = _c("vex", "villains")
    foe.hero.powers.append(SimpleNamespace(xmlid="AUTOMATON", name="Robot"))
    s = _session(_c("hero", "heroes"), foe)
    j = judge_enemy(_situation(s), s.combatants["vex"])
    assert "a machine" in j.features
    plain = _fight()
    assert "a machine" not in judge_enemy(
        _situation(plain), plain.combatants["vex"]).features


def test_looks_and_distance_and_down():
    s = _fight(max_stun=40, current_stun=8)
    j = judge_enemy(_situation(s, distance=34.0), s.combatants["vex"])
    assert j.looks == "critical"
    assert j.distance_m == 34.0
    assert "34m away" in "\n".join(render_judgement(j))
    s = _fight(max_stun=40, current_stun=0)
    assert "down" in judge_enemy(_situation(s), s.combatants["vex"]).features
