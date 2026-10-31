"""Minor NPCs: the book's three rules for making them fall like extras.

6E2 p.121-122, optional rules "to make a game a little more like novels
and movies", which "should only apply to minor or trivial NPCs; major
enemies and villains should function in combat just like PCs do":

1. "Once a minor enemy hits 0 BODY, he falls over dead."
2. "any time a minor NPC becomes Stunned by a Normal Damage or Killing
   Damage attack, he's not Stunned - he's dead."
3. Counting hits: the GM "simply decide[s] how many hits it takes to kill
   him. The weakest are one-hit wonders: a single successful Attack Roll
   against them kills them ... a two-hit foe takes two successful Attack
   Rolls to kill, or only a single Attack Roll that's made by 2 or more".

Who is a minor NPC is the GM's call per combatant (`minor_hits`: how many
hits kill him; None for everybody else). Which rules a table plays is the
campaign's (three `CombatTemplate` switches, off in both RAW templates).
These replace the One-Hit Wonder fields, which nothing read and which
described a STUN threshold the book does not have.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from kirby_combat.enumeration import is_down
from kirby_combat.mooks import check_mooks
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_engine
from kirby_combat.side import Side
from kirby_combat.statuses import DEAD, statuses_for
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_HEROIC, RAW_SUPERHEROIC, CombatTemplate

COUNTING = dataclasses.replace(RAW_SUPERHEROIC, minor_hit_counting=True)
STUNNED_IS_DEAD = dataclasses.replace(RAW_SUPERHEROIC, minor_stunned_is_dead=True)
ZERO_BODY = dataclasses.replace(RAW_SUPERHEROIC, minor_dead_at_zero_body=True)


def _fight(template, *, minor_hits=1, body=10):
    hero = synthetic_combatant(id="h", name="h", spd=4, side=Side.named("a"))
    mook = synthetic_combatant(id="m", name="m", spd=3, max_body=10, current_body=body,
                               side=Side.named("b"), minor_hits=minor_hits)
    return CombatSession.create(id="s", combatants=[hero, mook], scene=None,
                                template=template, dice_roller=None).start()


def _shot(session, *, hit=True, margin=0, damage_type="normal", status=()):
    from kirby_combat.session.apply import apply_event

    base = lambda: dict(id=str(uuid.uuid4()), session_id=session.id,  # noqa: E731
                        sequence=len(session.event_log) + 1,
                        timestamp=datetime.now(timezone.utc), author=make_author_engine())
    d = ActionDeclared(**base(), combatant_id="h", action_type="attack", targets=["m"])
    session = apply_event(session, d)
    return apply_event(session, ActionResolved(
        **base(), declaration_event_id=d.id,
        result_payload={"kind": "attack", "target_id": "m", "hit": hit, "margin": margin,
                        "damage_type": damage_type, "status_changes": list(status)}))


def _dead(session):
    return DEAD in statuses_for(session, "m") and is_down(session.combatants["m"])


def test_the_switches_replace_one_hit_wonder_and_are_off_by_the_book():
    names = {f.name for f in dataclasses.fields(CombatTemplate)}
    assert {"minor_dead_at_zero_body", "minor_stunned_is_dead", "minor_hit_counting"} <= names
    assert not {"one_hit_wonder_enabled", "one_hit_wonder_pct"} & names
    for t in (RAW_SUPERHEROIC, RAW_HEROIC):
        assert not (t.minor_dead_at_zero_body or t.minor_stunned_is_dead or t.minor_hit_counting)


def test_a_one_hit_wonder_dies_to_one_successful_attack_roll():
    s = check_mooks(_shot(_fight(COUNTING, minor_hits=1)))
    assert _dead(s)
    (row,) = [e for e in s.event_log if e.kind == "MinorFoeKilled"]
    assert (row.combatant_id, row.rule) == ("m", "hits")


def test_a_miss_does_not_count():
    assert not _dead(check_mooks(_shot(_fight(COUNTING), hit=False)))


def test_a_two_hit_foe_takes_two_hits_or_one_made_by_two():
    s = check_mooks(_shot(_fight(COUNTING, minor_hits=2), margin=1))
    assert not _dead(s)
    assert _dead(check_mooks(_shot(s, margin=0)))
    assert _dead(check_mooks(_shot(_fight(COUNTING, minor_hits=2), margin=2)))


def test_stunned_by_a_normal_or_killing_attack_is_dead():
    assert _dead(check_mooks(_shot(_fight(STUNNED_IS_DEAD), status=("Stunned",))))
    assert _dead(check_mooks(_shot(_fight(STUNNED_IS_DEAD), damage_type="killing",
                                   status=("Stunned",))))
    assert not _dead(check_mooks(_shot(_fight(STUNNED_IS_DEAD), damage_type="mental",
                                       status=("Stunned",))))


def test_at_zero_body_he_falls_over_dead():
    assert _dead(check_mooks(_fight(ZERO_BODY, body=0)))
    assert not _dead(check_mooks(_fight(ZERO_BODY, body=1)))


def test_nobody_but_a_minor_npc_and_no_rule_the_table_does_not_play():
    assert not _dead(check_mooks(_shot(_fight(COUNTING, minor_hits=None))))
    assert not _dead(check_mooks(_shot(_fight(RAW_SUPERHEROIC, minor_hits=1),
                                       status=("Stunned",))))


def test_a_dead_mook_is_killed_once():
    s = check_mooks(check_mooks(_shot(_fight(COUNTING))))
    assert len([e for e in s.event_log if e.kind == "MinorFoeKilled"]) == 1


def test_minor_hits_is_at_least_one():
    with pytest.raises(ValueError, match="minor_hits"):
        _fight(COUNTING, minor_hits=0)


def test_through_the_loop_a_one_hit_wonder_falls_and_stays_down():
    """On the live path: `run_phase` resolves the blast, writes the
    `MinorFoeKilled` and the DEAD status, and the mook acts no more."""
    from conftest import blast  # tests/loop/conftest.py
    from kirby_dice import RandomRoller

    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import Roster, run_phase

    hero = synthetic_combatant(id="h", name="h", ocv=12, spd=4, dex=30, side=Side.named("a"),
                               attacks=[blast("h-eb", dice=1)])
    mook = synthetic_combatant(id="m", name="m", dcv=1, spd=2, dex=5, max_stun=60, max_body=20,
                               side=Side.named("b"), minor_hits=1)
    session = CombatSession.create(id="s", combatants=[hero, mook], scene=None,
                                   template=COUNTING, dice_roller=RandomRoller(seed=3)).start()

    class _Shoot:
        def choose(self, situation):
            for x in situation.menu:
                if x.kind == "no_abort":
                    return x.action_id
            return next(x.action_id for x in situation.menu
                        if x.kind == "attack" and x.target_id == "m")

    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    r = RandomRoller(seed=3)
    phase = run_phase(enc.run_segment(roller=lambda: r.roll_dice(3)), _Shoot(),
                      roller=RandomRoller(seed=3), on_unresolvable="raise")
    s = phase.session
    hit = [e for e in s.event_log if e.kind == "ActionResolved"
           and (e.result_payload or {}).get("hit") is True]
    assert hit, "the test needs the 1d6 blast to land; OCV 12 against DCV 1"
    assert any(e.kind == "MinorFoeKilled" for e in s.event_log)
    assert any(e.kind == "StatusEffectsChanged" and e.combatant_id == "m"
               and DEAD in e.added for e in s.event_log)
    assert s.combatants["m"].state.current_stun > 0, "a 1d6 blast cannot KO 60 STUN"
    assert Roster(s).decide() is not None, "his side is beaten"


def test_the_cinematic_templates_are_the_raw_ones_with_the_mook_rules_on():
    """Peter, 2026-10-31: a table turns the minor-NPC rules on by naming a
    cinematic template (6E2 p.121: rules "to make a game a little more like
    novels and movies")."""
    for name, raw in (("6e-superheroic-cinematic", RAW_SUPERHEROIC),
                      ("6e-heroic-cinematic", RAW_HEROIC)):
        t = CombatTemplate.by_name(name)
        assert t.minor_dead_at_zero_body and t.minor_stunned_is_dead and t.minor_hit_counting
        assert dataclasses.replace(t, name=raw.name, minor_dead_at_zero_body=False,
                                   minor_stunned_is_dead=False, minor_hit_counting=False) == raw
