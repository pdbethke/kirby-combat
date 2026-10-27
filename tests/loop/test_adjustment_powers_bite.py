"""Aid, Drain and Healing change the stat they are bought against.

WHAT ORIGIN/MAIN DID. `_resolve_aid` / `_resolve_drain` recorded every
Adjustment as ``stat="STUN"`` (resolvers.py hard-coded it) and divided the
roll by 5; nothing reads a STUN Adjustment, so a Drain DEX drained nothing,
an Aid STR hit no harder and a Drain SPD left the man his Phases. Aid was
offered with no target and applied to the man using it. Healing recorded its
roll and healed nobody. A Drain made no Attack Roll.

Every test here goes through `resolve_chosen` or `run_phase`, with offers
taken from `enumerate_actions`, and reads the result where a FIGHT reads it
--- `combat_stats()`, the vitals, the attacks --- not the fold.

The numbers are the book's own where it has them:
6E1 p.137: "Drain DEX ... rolls 15 points of effect. Chiron loses 15/2 = 7
points of DEX"; p.143: half effect against CON, BODY, STUN and the other
defences; p.169: an Aid's maximum effect is the most its dice can roll;
p.234: "Healing BODY 2d6 spell (maximum effect 12 points, or 6 BODY)".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import VitalsChanged, make_author_engine
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


class _Power:
    """An Adjustment Power in the shape the loader gives enumeration: its
    INPUT names the stat; `range` / `range_value` are the cost engine's."""

    def __init__(self, xmlid: str, levels: int, input: str, *, ranged: bool,
                 mods: tuple[str, ...] = ()):
        self.xmlid = xmlid
        self.name = self.alias = f"{xmlid.title()} {input}"
        self.id = f"src-{xmlid}-{input}".replace(" ", "")
        self.levels = levels
        self.level_value = 1.0
        self.input = input
        self.range = "Yes" if ranged else "No"
        self.range_value = 10 * levels * 10 if ranged else 0
        self.active_cost = levels * 10
        self.assigned_adders: list = []
        self.assigned_modifiers = [SimpleNamespace(xmlid=m) for m in mods]
        self.sub_powers: list = []


def _with(c, *powers):
    c.hero.powers.extend(powers)
    return c


def _session(*cast) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(cast), scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


def _offer(session, actor_id: str, kind: str, target_id: str):
    actor = session.combatants[actor_id]
    others = [c for c in session.combatants.values() if c.id != actor_id]
    enemies = [c for c in others if c.side != actor.side]
    allies = [c for c in others if c.side == actor.side]
    menu = enumerate_actions(actor, enemies, allies=allies)
    offers = [a for a in menu if a.kind == kind and a.target_id == target_id]
    assert offers, f"no {kind} offer on {target_id}: {[a.action_id for a in menu]}"
    return offers[0]


def _use(session, actor_id, kind, target_id, dice):
    action = _offer(session, actor_id, kind, target_id)
    return resolve_chosen(session, session.combatants[actor_id], action,
                          template=TEMPLATE, roller=FakeRoller(dice))


HIT = [1, 1, 1]          # 3 on 3d6: always hits (6E2 p.37)
MISS = [6, 6, 6]         # 18: always misses


# ── Drain ────────────────────────────────────────────────────────────────────

def _drainer(stat: str, levels: int = 3, **kw):
    return _with(fighter("leech", side=VILLAINS),
                 _Power("DRAIN", levels, stat, ranged=True, **kw))


def test_a_drain_dex_drains_dex_by_its_cost_per_point():
    """p.137's own example: 15 points of effect is 7 DEX."""
    session = _session(_drainer("DEX"), fighter("chiron", side=HEROES, dex=20))
    after = _use(session, "leech", "drain", "chiron", [HIT, [5, 5, 5]]).session
    assert after.combatants["chiron"].combat_stats().dex == 13


def test_a_drain_spd_costs_him_a_speed():
    """SPD is 10 points a point (6E1 p.140: "To Drain a point of SPD requires
    that 10 Character Points be Drained")."""
    session = _session(_drainer("SPD"), fighter("chiron", side=HEROES, spd=4))
    after = _use(session, "leech", "drain", "chiron", [HIT, [6, 6, 2]]).session
    assert after.combatants["chiron"].combat_stats().spd == 3
    nine = _use(session, "leech", "drain", "chiron", [HIT, [3, 3, 3]]).session
    assert nine.combatants["chiron"].combat_stats().spd == 4, "9 points buy no SPD"


def test_a_drain_con_is_half_effect_and_makes_the_next_blow_stun():
    """6E1 p.143 halves it against CON; 6E2 p.106 Stuns on STUN over CON."""
    from kirby_combat.enumeration import LegalAction
    from conftest import blast

    session = _session(_drainer("CON"), fighter("chiron", side=HEROES))
    after = _use(session, "leech", "drain", "chiron", [HIT, [6, 6, 6]]).session
    assert after.combatants["chiron"].combat_stats().con == 18 - 9

    power = blast("leech-eb", dice=3)
    shot = LegalAction(action_id="attack:chiron", kind="attack", target_id="chiron",
                       power_xmlid=power.xmlid, power_name=power.name,
                       summary="attack", _attack_view=power, )
    hit = resolve_chosen(after, after.combatants["leech"], shot, template=TEMPLATE,
                         roller=FakeRoller([HIT, [6, 6, 6], [3, 3, 3], [1], [6, 6]]))
    # 18 STUN less ED 4 = 14 through: over a Drained CON of 9, not over 18.
    assert "Stunned" in hit.result.status_changes


def test_a_drain_that_misses_drains_nothing():
    session = _session(_drainer("DEX"), fighter("chiron", side=HEROES, dex=20))
    after = _use(session, "leech", "drain", "chiron", [MISS]).session
    assert after.combatants["chiron"].combat_stats().dex == 20


def test_power_defense_comes_off_the_drain():
    """6E1 p.197: "subtracts the target's Power Defense"."""
    from fixtures.synthetic_hero import synthetic_combatant

    shielded = synthetic_combatant(
        id="chiron", name="chiron", ocv=6, dcv=3, omcv=3, dmcv=3, spd=3, dex=20,
        ego=10, str_=10, con=10, pre=10, rec=4, pd=3, ed=3, power_defense=5,
        max_stun=30, max_body=10, max_end=30, side=HEROES,
    )
    session = _session(_drainer("DEX"), shielded)
    after = _use(session, "leech", "drain", "chiron", [HIT, [5, 5, 5]]).session
    assert after.combatants["chiron"].combat_stats().dex == 20 - 5     # (15-5)/2


def test_a_drain_stun_takes_current_stun_too_and_gives_it_back():
    """6E1 p.138: a Drain on an expendable "affects both the current total
    of that Characteristic and the maximum", and the returning points
    "increase both"."""
    session = _session(_drainer("STUN"), fighter("chiron", side=HEROES, stun=40))
    after = _use(session, "leech", "drain", "chiron", [HIT, [4, 4, 4]]).session
    chiron = after.combatants["chiron"]
    # 12 points, half effect: 6 Character Points of STUN = 12 STUN.
    assert chiron.combat_stats().max_stun == 40 - 12
    assert chiron.state.current_stun == 40 - 12

    enc = Encounter(id="e", turn=1, segment=12, sessions=[after]).advance_segment()
    back = enc.sessions[0].combatants["chiron"]
    # 5 Character Points returned at Post-Segment 12 are 10 STUN.
    assert back.combat_stats().max_stun == 40 - 2
    assert back.state.current_stun >= 40 - 2


def test_a_drain_on_a_power_takes_its_dice():
    """6E1 p.139: it takes the power's own Active Points per die to remove
    one --- 15 for a plain HKA."""
    hka = AttackPower(
        xmlid="HKA", name="Claws", damage_dice=2, half_die=False, plus_one=False,
        damage_type="killing", defense_type="pd", range_m=0.0, uses_str=True,
        str_min=0, armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="claws", active_points=30,
    )
    wolf = fighter("wolf", side=HEROES, armed=False)
    wolf.attacks.append(hka)
    session = _session(_drainer("HKA"), wolf)
    after = _use(session, "leech", "drain", "wolf", [HIT, [6, 6, 4]]).session
    (claws,) = [a for a in after.combatants["wolf"].attacks if a.source_id == "claws"]
    assert claws.damage_dice == 1


def test_a_drain_naming_a_special_effect_group_is_not_offered():
    """"Fire Powers" names no power this engine can identify."""
    session = _session(_drainer("FIRE POWERS"), fighter("chiron", side=HEROES))
    actor = session.combatants["leech"]
    menu = enumerate_actions(actor, [session.combatants["chiron"]])
    assert not [a for a in menu if a.kind == "drain"]


# ── Aid ──────────────────────────────────────────────────────────────────────

def _aider(stat: str, levels: int = 3):
    return _with(fighter("medic", side=HEROES), _Power("AID", levels, stat, ranged=False))


def test_an_aid_str_hits_harder():
    """STR 15 + 12 is 27: the bare-handed Strike's dice come off it (6E2
    p.99), and every reader of STR sees the Aid."""
    session = _session(_aider("STR"), fighter("brick", side=HEROES),
                       fighter("foe", side=VILLAINS))
    before = session.combatants["brick"].str_strike_view().damage_dice
    after = _use(session, "medic", "aid", "brick", [[4, 4, 4]]).session
    brick = after.combatants["brick"]
    assert brick.combat_stats().str_ == 27
    assert brick.str_strike_view().damage_dice > before


def test_an_aid_is_offered_on_an_ally_by_name_and_on_yourself():
    """origin/main offered it with `target_id=None` and applied it to the
    man using it."""
    session = _session(_aider("STR"), fighter("brick", side=HEROES),
                       fighter("foe", side=VILLAINS))
    medic = session.combatants["medic"]
    menu = enumerate_actions(medic, [session.combatants["foe"]],
                             allies=[session.combatants["brick"]])
    assert {a.target_id for a in menu if a.kind == "aid"} == {"medic", "brick"}


def test_an_aid_stops_at_its_maximum_effect():
    """6E1 p.169: "the maximum that could be rolled on the dice". 3d6 is 18
    points of STR however many times it is used."""
    session = _session(_aider("STR"), fighter("brick", side=HEROES),
                       fighter("foe", side=VILLAINS))
    once = _use(session, "medic", "aid", "brick", [[6, 6, 4]]).session
    twice = _use(once, "medic", "aid", "brick", [[6, 6, 6]]).session
    assert twice.combatants["brick"].combat_stats().str_ == 15 + 18


def test_an_aid_needs_no_attack_roll_on_a_willing_target():
    """6E1 p.169: the roll "succeeds automatically" --- so no 3d6 is drawn."""
    session = _session(_aider("STR"), fighter("brick", side=HEROES),
                       fighter("foe", side=VILLAINS))
    resolved = _use(session, "medic", "aid", "brick", [[1, 1, 1]])
    assert resolved.result["hit"] is True


# ── Healing ──────────────────────────────────────────────────────────────────

def _healer(input: str = "BODY", levels: int = 4):
    return _with(fighter("doc", side=HEROES), _Power("HEALING", levels, input, ranged=False))


def _hurt(session, who: str, *, body: int = 0, stun: int = 0):
    return apply_event(session, VitalsChanged(
        id="hurt", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=session.created_at, author=make_author_engine(),
        combatant_id=who, body=-body, stun=-stun, reason="damage",
    ))


def test_healing_body_heals_half_its_roll_and_stops_at_full():
    """6E1 p.234's example: Healing BODY 2d6 is "maximum effect 12 points,
    or 6 BODY" --- half effect (p.143)."""
    session = _hurt(_session(_healer(), fighter("patient", side=HEROES),
                             fighter("foe", side=VILLAINS)), "patient", body=8)
    after = _use(session, "doc", "heal", "patient", [[3, 3, 3, 3]]).session
    assert after.combatants["patient"].state.current_body == 12 - 8 + 6


def test_healing_again_heals_only_what_beats_the_last_roll():
    """6E1 p.234: Willem "has to roll more than 4 ... and can only Heal him to
    the extent his roll exceeds 4"."""
    session = _hurt(_session(_healer(), fighter("patient", side=HEROES),
                             fighter("foe", side=VILLAINS)), "patient", body=10)
    once = _use(session, "doc", "heal", "patient", [[2, 2, 2, 2]]).session   # 8 -> 4 BODY
    twice = _use(once, "doc", "heal", "patient", [[3, 3, 2, 2]]).session     # 10: 2 over -> 1
    assert once.combatants["patient"].state.current_body == 2 + 4
    assert twice.combatants["patient"].state.current_body == 2 + 4 + 1


def test_simplified_healing_heals_the_total_as_stun_and_the_body_it_counts():
    """6E1 p.236: "rolls 20 on the dice ... Heals 20 STUN and 6 BODY"."""
    session = _hurt(_session(_healer("SIMPLIFIED"), fighter("patient", side=HEROES),
                             fighter("foe", side=VILLAINS)),
                    "patient", body=6, stun=30)
    after = _use(session, "doc", "heal", "patient", [[6, 6, 5, 3]]).session
    patient = after.combatants["patient"]
    assert patient.state.current_stun == 10 + 20
    assert patient.state.current_body == 6 + 6     # 2 + 2 + 1 + 1 counted BODY


def test_healing_is_not_offered_on_a_man_who_has_lost_nothing():
    """6E1 p.234: "only use Healing to restore Characteristics or Powers that
    have been lost or reduced"."""
    session = _session(_healer(), fighter("patient", side=HEROES),
                       fighter("foe", side=VILLAINS))
    doc = session.combatants["doc"]
    menu = enumerate_actions(doc, [session.combatants["foe"]],
                             allies=[session.combatants["patient"]])
    assert not [a for a in menu if a.kind == "heal"]


def test_healing_body_stops_bleeding():
    """6E1 p.234: "Any successful use of a Healing BODY stops Bleeding"."""
    from kirby_combat.encounter import _is_stabilized

    session = _hurt(_session(_healer(), fighter("patient", side=HEROES),
                             fighter("foe", side=VILLAINS)), "patient", body=14)
    after = _use(session, "doc", "heal", "patient", [[1, 1, 1, 1]]).session
    assert _is_stabilized(after, "patient")


# ── The loop ─────────────────────────────────────────────────────────────────

class _Picks:
    def __init__(self, kind: str):
        self.kind = kind

    def choose(self, situation):
        return next(a for a in situation.menu if a.kind == self.kind).action_id


def test_run_phase_resolves_a_drain_and_the_next_phase_feels_it():
    """The whole path: offered, chosen, resolved, recorded, folded."""
    leech = fighter("leech", side=VILLAINS, dex=30)
    leech.hero.powers.append(_Power("DRAIN", 6, "DEX", ranged=True))
    session = _session(leech, fighter("chiron", side=HEROES, dex=20))
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    result = run_phase(enc, _Picks("drain"), roller=RandomRoller(seed=5),
                       on_unresolvable="raise")
    assert result.actor_id == "leech" and result.kind == "drain"
    after = result.encounter.sessions[0].combatants["chiron"]
    payload = result.result
    # Signed on the payload: a Drain records what it took away.
    expected = 20 - (-payload["character_points"]["DEX"] // 2) if payload["hit"] else 20
    assert after.combat_stats().dex == expected
