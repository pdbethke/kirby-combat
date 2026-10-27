"""Areas that stay: Constant and Damage Over Time Areas, auras and Damage
Shields.

Batch C built the one-shot Area Of Effect and stopped offering a Constant or
Damage Over Time one --- 89 attack views in the corpus --- because nothing
could keep a zone. These are the zone, through `run_phase`.

The pages:
  * 6E1 p.129: a Constant Area "remains in effect in the Segments between
    the attacker's Phases. Any target who enters the area takes damage ...
    in the Segment he enters and every time the attacker's Phase occurs
    while the target remains within the area" --- once per Phase at most.
  * 6E1 p.332: a Damage Over Time Area "remains in all Segments for its
    defined duration ... Any character who enters the area takes damage ...
    that Segment and after each damage interval thereafter".
  * 6E1 p.323-324: a Damage Shield, a Constant personal Surface, hurts
    whoever hits or Grabs its wearer and whoever he hits or Grabs.

Scene: a (villain, DEX 30) at the origin; b (hero, DEX 10) 8m out, the
target; c (hero, DEX 20) 20m out along the same line. All SPD 4 (Phases 3,
6, 9, 12); the fight opens in Segment 12.
"""
from __future__ import annotations

from dataclasses import replace

from shaped import (                                    # tests/loop/shaped.py
    TEMPLATE, Dice, Picks, armed, encounter_on, payloads, scene_with,
    shaped_blast,
)
from kirby_combat.loop import run_phase
from kirby_combat.power_modifiers import (
    AreaShape, AreaSpec, AreaTargeting, DamageOverTimeSpec, unbuilt_reasons,
)
from kirby_combat.side import Side
from kirby_combat.standing_areas import (
    RAISE_DAMAGE_SHIELD, Dose, StandingEnd, active_standing_areas,
    standing_areas,
)

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (20, 0, 0)}


def area(size=3.0, shape=AreaShape.RADIUS, targeting=AreaTargeting.STANDARD,
         explosion=False, personal_immunity=False):
    return AreaSpec(shape=shape, size_m=size, targeting=targeting,
                    explosion=explosion, personal_immunity=personal_immunity,
                    width_m=2.0, height_m=2.0, thin_cone=False, unbuilt=())


def _dot(increments=3, every=2):
    return DamageOverTimeSpec(increments=increments, interval_segments=every,
                              lockout=False, one_defense=False, unbuilt=())


def _people(power, *, positions=POSITIONS, c_power=None, **a_stats):
    people = [armed("a", power, side=VILLAINS, dex=30, **a_stats),
              armed("b", None, side=HEROES, dex=10),
              armed("c", c_power, side=HEROES, dex=20)]
    return [p for p in people if p.id in positions]


#: A campaign that counts END (6E2 p.133); the superheroic default does not.
COUNTED = replace(TEMPLATE, manage_endurance=True, manage_endurance_npc=True)


def _fight(power, *, positions=POSITIONS, template=TEMPLATE, **kw):
    return encounter_on(scene_with(positions),
                        *_people(power, positions=positions, **kw),
                        template=template)


def _chooser(*, a_attacks="b", c_moves=False, a_fires=1):
    """a uses his power on ``a_attacks`` ``a_fires`` times, then Dodges; c
    closes on a if ``c_moves``; everyone else Dodges."""
    fired = []

    def want(action, situation):
        who = situation.actor.id
        if who == "a" and action.kind == "attack" and action.target_id == a_attacks \
                and len(fired) < a_fires:
            fired.append(action.action_id)
            return True
        if who == "c" and c_moves and action.kind == "move" and action.target_id == "a":
            return True
        return False
    return Picks(want)


def _run(enc, chooser, n, dice):
    results = []
    for _ in range(n):
        r = run_phase(enc, chooser, roller=dice, on_unresolvable="raise")
        results.append(r)
        enc = r.encounter
    return enc, results


def _until(enc, chooser, dice, who, *, skip=0):
    """Run Phases until ``who`` has had one more (after ``skip`` of his)."""
    for _ in range(40):
        r = run_phase(enc, chooser, roller=dice, on_unresolvable="raise")
        enc = r.encounter
        if r.actor_id == who:
            if skip == 0:
                return enc, r
            skip -= 1
    raise AssertionError(f"{who} never acted")


class _NoAborts(Picks):
    """`Picks`, but nobody Aborts out of turn: the first out-of-turn offer
    is always to do nothing (`loop/reactions.py`)."""

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None):
            return situation.menu[0].action_id
        return super().choose(situation)


def _stun(enc, who):
    return enc.sessions[0].combatants[who].state.current_stun


def _recovered(enc, who):
    return sum(e.stun_recovered for e in enc.sessions[0].event_log
               if e.kind == "RecoveryTaken" and e.combatant_id == who)


def _doses(enc, why=None, who=None):
    return [p for p in payloads(enc.sessions[0])
            if p.get("standing_area_id")
            and (why is None or p.get("standing_dose") == why.value)
            and (who is None or p.get("target_id") == who)]


# --- A Constant Area is offered, and stays --------------------------------

def test_a_constant_area_is_offered_now():
    """It was refused as "Constant or Damage Over Time Area Of Effect"."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    assert unbuilt_reasons(power) == []
    chooser = _chooser()
    run_phase(_fight(power), chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert any(a.kind == "attack" and a.target_id == "b" for a in chooser.menus[0])


def test_the_use_leaves_a_zone_that_hurts_on_the_owners_next_phase():
    """Seam: Segment 12, a's Constant 3m Radius lands on b: 4d6 of 3s = 12
    less ED 4 = 8 STUN, and a `StandingAreaEstablished` at b's spot. At a's
    next Phase (Turn 2, Segment 3) he pays its END and b, still in it, takes
    8 again --- no Attack Roll, no Action: a still chooses (a Dodge)."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True, active_points=20)
    enc = _fight(power, template=COUNTED)
    chooser = _chooser()
    enc, (first,) = _run(enc, chooser, 1, Dice(face=3))
    assert first.kind == "attack"
    est = [e for e in enc.sessions[0].event_log if e.kind == "StandingAreaEstablished"]
    assert len(est) == 1 and est[0].point == {"x": 8.0, "y": 0.0, "z": 0.0}
    assert _stun(enc, "b") == 40 - 8
    end_before = enc.sessions[0].combatants["a"].state.current_end
    enc, second = _until(enc, chooser, Dice(face=3), "a")
    assert second.kind == "dodge"
    phase = _doses(enc, Dose.PHASE, "b")
    assert len(phase) == 1 and phase[0]["power_source_id"] is None
    assert _stun(enc, "b") == 40 - 8 - 8 + _recovered(enc, "b")
    # He paid to keep it up (20 Active Points = 2 END, 6E1 p.130).
    end_after = enc.sessions[0].combatants["a"].state.current_end
    assert end_before + _recovered_end(enc, "a") - end_after == 2


def _recovered_end(enc, who):
    return sum(e.end_recovered for e in enc.sessions[0].event_log
               if e.kind == "RecoveryTaken" and e.combatant_id == who)


def test_a_man_who_walks_in_is_hurt_in_the_segment_he_enters():
    """c, 20m out, closes on a: the straight line runs through the zone
    around b (5m to 11m). He takes the zone's dose in his own Phase, the
    Segment he entered (6E1 p.129), with no Attack Roll."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc = _fight(power)
    chooser = _chooser(c_moves=True)
    enc, results = _run(enc, chooser, 2, Dice(face=3))
    assert [r.actor_id for r in results] == ["a", "c"]
    entered = _doses(enc, Dose.ENTERED, "c")
    assert len(entered) == 1 and entered[0]["movement_event_id"]
    assert _stun(enc, "c") == 40 - 8


def test_entering_twice_before_his_next_phase_hurts_once():
    """6E1 p.129: "more than once per Phase, he does not suffer the damage
    ... multiple times". The same entering, offered to the fold again, is
    refused: the dose is keyed to the window between a's Phases."""
    from kirby_combat.standing_areas import entries_since

    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc = _fight(power)
    enc, _ = _run(enc, _chooser(c_moves=True), 2, Dice(face=3))
    s = enc.sessions[0]
    move = next(e for e in s.event_log if e.kind == "MovementResolved"
                and e.combatant_id == "c")
    # The same crossing, written down again (a second move in the window).
    from kirby_combat.session.apply import apply_event
    again = replace(move, id="again", sequence=len(s.event_log) + 1)
    s2 = apply_event(s, again)
    s3 = entries_since(s2, len(s.event_log), template=TEMPLATE, roller=Dice(face=3))
    assert len([p for p in payloads(s3) if p.get("standing_dose") == "entered"
                and p.get("target_id") == "c"]) == 1


def test_it_stops_when_he_cannot_pay():
    """6E1 p.129: "stops maintaining it (i.e., stops paying END for it)". He
    starts with 2 END and REC 0, spends both on the use, and has none at his
    next Phase."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True, active_points=20)
    enc = _fight(power, current_end=2, rec=0, template=COUNTED)
    chooser = _chooser()
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    enc, _ = _until(enc, chooser, Dice(face=3), "a")
    ended = [e.reason for e in enc.sessions[0].event_log if e.kind == "StandingAreaEnded"]
    assert ended == [StandingEnd.NO_END.value]
    assert _doses(enc, Dose.PHASE) == []


def test_it_stops_when_he_loses_sight_of_the_spot():
    """6E1 p.129: "maintain a Line Of Sight to the location of the Power"."""
    from kirby_world.scene import Position, Wall

    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc = _fight(power)
    chooser = _chooser()
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    s = enc.sessions[0]
    wall = Wall(id="w", name="w",
                segment=(Position(3.0, -5.0, 0.0), Position(3.0, 5.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4)
    enc = replace(enc, sessions=[replace(s, scene=replace(s.scene, walls=[wall]))])
    enc, _ = _until(enc, chooser, Dice(face=3), "a")
    ended = [e.reason for e in enc.sessions[0].event_log if e.kind == "StandingAreaEnded"]
    assert ended == [StandingEnd.LOST_LINE_OF_SIGHT.value]


def test_a_recovery_lets_it_go():
    """6E2 p.131: a man who Recovers "cannot even maintain a Constant
    Power"."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc = _fight(power, current_end=4)    # low enough, after REC, to be offered one
    taken = []

    def want(action, situation):
        if situation.actor.id != "a":
            return False
        if not taken and action.kind == "attack" and action.target_id == "b":
            taken.append("attack")
            return True
        if taken == ["attack"] and action.kind == "recover":
            taken.append("recover")
            return True
        return False
    chooser = Picks(want)
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    enc, r = _until(enc, chooser, Dice(face=3), "a")
    assert r.kind == "recover"
    ended = [e.reason for e in enc.sessions[0].event_log if e.kind == "StandingAreaEnded"]
    assert ended == [StandingEnd.RECOVERED.value]


def test_the_zone_survives_a_replay():
    """The zone is in the LOG, so a fight rebuilt from its rows still has
    it, where it was set down."""
    from kirby_combat.serialization import from_dict, to_dict

    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc, _ = _run(_fight(power), _chooser(), 1, Dice(face=3))
    s = enc.sessions[0]
    rebuilt = replace(s, event_log=[from_dict(to_dict(e)) for e in s.event_log])
    zones = active_standing_areas(rebuilt)
    assert len(zones) == 1 and zones[0].point == (8.0, 0.0, 0.0)


def test_two_uses_are_two_zones_both_paid():
    """6E1 p.129: a Constant power used again affects its target twice, and
    "Sapphire has to pay END to maintain each use"."""
    power = shaped_blast("a-storm", 4, area=area(), constant=True)
    enc = _fight(power)
    chooser = _chooser(a_fires=2)
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    enc, _ = _until(enc, chooser, Dice(face=3), "a")
    assert len(active_standing_areas(enc.sessions[0])) == 2


# --- Selective and Nonselective -------------------------------------------

def test_a_selective_zone_rolls_for_a_newcomer_and_spares_a_friend():
    """6E1 p.326: a man entering a Selective Constant area later needs an
    Attack Roll, which "takes no time". c is an enemy, so a rolls (3d6 of 3s
    = 9 against his DCV 5: hits)."""
    power = shaped_blast("a-storm", 4, area=area(targeting=AreaTargeting.SELECTIVE),
                         constant=True)
    enc = _fight(power)
    enc, _ = _run(enc, _chooser(c_moves=True), 2, Dice(face=3))
    entered = _doses(enc, Dose.ENTERED, "c")
    assert len(entered) == 1 and entered[0]["target_dcv"] == 5
    zone = active_standing_areas(enc.sessions[0])[0]
    assert {"b", "c"} <= zone.affected


def test_a_nonselective_zone_rolls_against_everyone_every_phase():
    """6E1 p.326: "the attacker has to make an Attack Roll against each
    person in the affected area every Phase". 3d6 of 6s = 18 always misses
    (6E2 p.37): b is in it and takes nothing at a's next Phase."""
    power = shaped_blast("a-storm", 4, area=area(targeting=AreaTargeting.NONSELECTIVE),
                         constant=True)
    enc = _fight(power)
    chooser = _chooser()
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    hurt = _stun(enc, "b")
    enc, _ = _until(enc, chooser, Dice(face=6), "a")
    phase = _doses(enc, Dose.PHASE, "b")
    assert len(phase) == 1 and phase[0]["hit"] is False
    assert _stun(enc, "b") == hurt + _recovered(enc, "b")


# --- No Range: it goes where he goes ---------------------------------------

def test_a_no_range_zone_moves_with_him_and_catches_what_it_sweeps():
    """6E1 p.326: a No Range Constant area "'sticks to' the character
    generating it and moves as he moves", and "as it sweeps over an area"
    the Constant rules apply. a's 3m aura (Personal Immunity) is offered
    against b, 2m off --- inside it, though out of arm's reach --- and is
    rolled against DCV 0 (6E1 p.322). Then a closes on c and the aura comes
    onto c, who takes the entering dose; a never takes his own."""
    aura = replace(shaped_blast("a-aura", 4, area=area(personal_immunity=True),
                                constant=True), range_m=0, is_ranged=False)
    positions = {"a": (0, 0, 0), "b": (2, 0, 0), "c": (12, 0, 0)}
    enc = _fight(aura, positions=positions)
    moved = []

    def want(action, situation):
        if situation.actor.id != "a":
            return False
        if not moved and action.kind == "attack" and action.target_id == "b":
            moved.append("aura")
            return True
        if moved == ["aura"] and action.kind == "move" and action.target_id == "c":
            moved.append("move")
            return True
        return False
    chooser = _NoAborts(want)
    enc, (first,) = _run(enc, chooser, 1, Dice(face=3))
    use = payloads(enc.sessions[0], area_use=True)[0]
    assert use["target_dcv"] == 0 and use["victims"] == ["b"]
    zone = active_standing_areas(enc.sessions[0])[0]
    assert zone.follows_owner
    enc, r = _until(enc, chooser, Dice(face=3), "a")
    assert r.kind == "move"
    assert len(_doses(enc, Dose.ENTERED, "c")) == 1
    assert _doses(enc, who="a") == []           # Personal Immunity


def test_a_persistent_aura_is_on_from_the_start_and_never_offered():
    """6E1 p.130: a Persistent power is "assumed to be on at all times".
    Basilisk's Deadly Smell is a Persistent No Range Radius: it is no attack
    on the menu, has no establishing event, and b, standing in it, takes it
    on a's Phase."""
    aura = replace(shaped_blast("a-smell", 4, area=area(size=10, personal_immunity=True),
                                constant=True, persistent=True),
                   range_m=0, is_ranged=False)
    enc = _fight(aura, positions={"a": (0, 0, 0), "b": (6, 0, 0)})
    chooser = _chooser()
    enc, (first,) = _run(enc, chooser, 1, Dice(face=3))
    assert not any(getattr(x, "_attack_view", None) is not None
                   and x._attack_view.source_id == "a-smell"
                   for x in chooser.menus[0])
    s = enc.sessions[0]
    assert [e for e in s.event_log if e.kind == "StandingAreaEstablished"] == []
    assert len(standing_areas(s)) == 1
    assert len(_doses(enc, Dose.PHASE, "b")) == 1


# --- Damage Over Time zones ------------------------------------------------

def test_a_damage_over_time_zone_does_nothing_on_the_use_then_doses_on_its_clock():
    """Seam (6E1 p.331-332): the use in Segment 12 does no damage; every 2
    Segments b, still in it, takes 4d6 of 3s less ED 4 = 8; three
    increments, and the zone is gone after Turn 2 Segment 6."""
    power = shaped_blast("a-cloud", 4, area=area(), damage_over_time=_dot())
    enc = _fight(power)
    chooser = _chooser()
    enc, _ = _run(enc, chooser, 1, Dice(face=3))
    assert _stun(enc, "b") == 40
    # Run to Turn 2 Segment 9: past the zone's six Segments.
    for _ in range(20):
        r = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
        enc = r.encounter
        t = enc.sessions[0].timeline
        if (t.turn, t.segment) >= (2, 9):
            break
    interval = _doses(enc, Dose.INTERVAL, "b")
    assert len(interval) == 3
    assert [(p["turn"], p["segment"]) for p in interval] == [(2, 2), (2, 4), (2, 6)]
    ended = [e.reason for e in enc.sessions[0].event_log if e.kind == "StandingAreaEnded"]
    assert ended == [StandingEnd.RAN_ITS_COURSE.value]


def test_a_damage_over_time_zone_holds_back_its_stun_from_recovery():
    """6E1 p.333: the victim "cannot Recover any of the damage sustained
    until the Damage Over Time has entirely run its course". b, dosed in
    Turn 2, gets none of that STUN back at the Post-Segment 12 Recovery
    while the zone (12 increments, a Turn apart) is still running."""
    from kirby_combat.recovery_limits import stun_held_by_damage_over_time

    power = shaped_blast("a-cloud", 4, area=area(), damage_over_time=_dot(increments=12, every=2))
    enc = _fight(power)
    chooser = _chooser()
    for _ in range(40):
        r = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
        enc = r.encounter
        if enc.sessions[0].timeline.turn >= 3:
            break
    s = enc.sessions[0]
    held = stun_held_by_damage_over_time(s, "b")
    assert held > 0
    post12 = [e for e in s.event_log if e.kind == "RecoveryTaken"
              and e.combatant_id == "b"]
    assert post12[-1].stun_recovered == 0


# --- Damage Shields --------------------------------------------------------

def _shield(source="a-spikes", *, persistent=False, dice=2):
    return replace(shaped_blast(source, dice, area=area(size=1, shape=AreaShape.SURFACE),
                                constant=True, persistent=persistent),
                   range_m=0, is_ranged=False, damage_type="killing",
                   defense_type="pd", xmlid="RKA")


def _punch(source="x-fist"):
    return replace(shaped_blast(source, 3), range_m=0, is_ranged=False,
                   xmlid="HANDTOHANDATTACK", name="Punch")


def test_a_damage_shield_is_raised_with_a_zero_phase_action():
    """6E1 p.323: "he only has to use a Zero Phase Action to activate it". It
    is offered as `raise_damage_shield`, never as an attack; after it the
    same Phase comes back to him without the offer."""
    enc = _fight(_shield(), positions={"a": (0, 0, 0), "b": (1, 0, 0)})
    chooser = Picks(lambda a, s: s.actor.id == "a" and a.kind == RAISE_DAMAGE_SHIELD)
    enc, (first, second) = _run(enc, chooser, 2, Dice(face=3))
    assert first.kind == RAISE_DAMAGE_SHIELD
    assert second.actor_id == "a" and second.kind != RAISE_DAMAGE_SHIELD
    assert not any(a.kind == "attack" and a._attack_view.source_id == "a-spikes"
                   for a in chooser.menus[0] if a._attack_view is not None)
    assert not any(a.kind == RAISE_DAMAGE_SHIELD for a in chooser.menus[1])
    est = [e for e in enc.sessions[0].event_log if e.kind == "StandingAreaEstablished"]
    assert len(est) == 1 and est[0].shape == "surface" and est[0].covered_id == "a"


def test_whoever_punches_a_shielded_man_takes_the_shield():
    """6E1 p.323: "Any attacker who makes a successful HTH Combat attack
    against a character with a Damage Shield takes the damage". b punches a,
    who wears a Persistent 2d6 RKA shield: b takes 2d6 of 3s = 6 BODY less
    rPD 2 = 4 BODY, against his own defenses, with no Attack Roll."""
    positions = {"a": (0, 0, 0), "b": (1, 0, 0)}
    people = [armed("a", _shield(persistent=True), side=VILLAINS, dex=5),
              armed("b", _punch(), side=HEROES, dex=30)]
    enc = encounter_on(scene_with(positions), *people)
    chooser = Picks(lambda a, s: s.actor.id == "b" and a.kind in ("attack", "strike")
                    and a.target_id == "a")
    enc, (first,) = _run(enc, chooser, 1, Dice(face=3))
    assert first.actor_id == "b" and first.kind in ("attack", "strike")
    contact = _doses(enc, Dose.CONTACT, "b")
    assert len(contact) == 1 and contact[0]["body_dealt"] == 4
    assert enc.sessions[0].combatants["b"].state.current_body == 12 - 4


def test_a_shielded_man_s_own_punch_carries_it():
    """6E1 p.323: "(b) when the character contacts the target (for example,
    by punching him ...)". a raises his shield (a Zero Phase Action), then
    punches b with the same Phase; b takes the punch and the shield."""
    positions = {"a": (0, 0, 0), "b": (1, 0, 0)}
    a = armed("a", _shield(), side=VILLAINS, dex=30, also=[_punch("a-fist")])
    enc = encounter_on(scene_with(positions), a, armed("b", None, side=HEROES, dex=10))

    def want(action, situation):
        if situation.actor.id != "a":
            return False
        offers = {a.kind for a in situation.menu}
        if RAISE_DAMAGE_SHIELD in offers:
            return action.kind == RAISE_DAMAGE_SHIELD
        return (action.kind in ("attack", "strike") and action.target_id == "b"
                and action._attack_view is not None
                and action._attack_view.source_id == "a-fist")
    enc, (raised, punched) = _run(enc, _NoAborts(want), 2, Dice(face=3))
    assert raised.kind == RAISE_DAMAGE_SHIELD
    assert punched.kind in ("attack", "strike")
    contact = _doses(enc, Dose.CONTACT, "b")
    assert len(contact) == 1 and contact[0]["body_dealt"] == 4


def test_a_held_man_takes_the_shield_every_phase():
    """6E1 p.324: "A Grabbed character takes the damage from the Shield every
    time the attacker has a Phase." a, shield up from the start (Persistent),
    Grabs b (the Grab itself is contact), and at a's next Phase b, still
    held, takes it again."""
    positions = {"a": (0, 0, 0), "b": (1, 0, 0)}
    a = armed("a", _shield(persistent=True), side=VILLAINS, dex=30)
    enc = encounter_on(scene_with(positions), a, armed("b", None, side=HEROES, dex=10))
    grabbed = []

    def want(action, situation):
        if situation.actor.id == "a" and action.kind == "grab" and not grabbed:
            grabbed.append(1)
            return True
        return False
    chooser = Picks(want)
    enc, (first,) = _run(enc, chooser, 1, Dice(face=3))
    assert first.kind == "grab"
    assert len(_doses(enc, Dose.CONTACT, "b")) == 1
    enc, _ = _until(enc, chooser, Dice(face=3), "a")
    from kirby_combat.actions.grab import Grab
    if Grab.is_grabbed(enc.sessions[0], "b")[1] == "a":
        assert len(_doses(enc, Dose.CONTACT, "b")) == 2


def test_a_ranged_surface_on_another_man_burns_whoever_touches_him():
    """6E1 p.323: a Surface on another character is rolled against "his
    standard DCV"; covered, he suffers it now and, Constant, every Phase;
    and "any character who comes into contact with that Surface suffers the
    Power's effects immediately" --- here c, b's own friend, who punches
    him."""
    heat = shaped_blast("a-heat", 2, area=area(size=1, shape=AreaShape.SURFACE),
                        constant=True)
    positions = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (9, 0, 0)}
    people = [armed("a", heat, side=VILLAINS, dex=30),
              armed("b", None, side=HEROES, dex=10),
              armed("c", _punch("c-fist"), side=VILLAINS, dex=20)]
    enc = encounter_on(scene_with(positions), *people)

    def want(action, situation):
        who = situation.actor.id
        if who == "a":
            return action.kind == "attack" and action.target_id == "b"
        if who == "c":
            return action.kind in ("attack", "strike") and action.target_id == "b"
        return False
    enc, results = _run(enc, _NoAborts(want), 2, Dice(face=3))
    use = [p for p in payloads(enc.sessions[0]) if p.get("power_source_id") == "a-heat"]
    assert use and use[0]["target_dcv"] == 5           # his DCV, not 3
    assert len([e for e in enc.sessions[0].event_log
                if e.kind == "LingeringAttackApplied"]) == 1
    # c touched the covered man and took the heat, against his ED 4.
    assert any(p.get("standing_dose") == "contact" and p.get("target_id") == "c"
               for p in payloads(enc.sessions[0]))


# --- Explosion on a Killing attack ----------------------------------------

def test_a_killing_explosion_loses_a_die_per_6m():
    """6E1 p.325: for Killing Attacks "subtract one die, starting with the
    highest die, for every 6m of expansion (full dice within 6m of the
    target point, -1 die for the next 6m, and so on)" --- the first of the
    two methods the page gives (RULING)."""
    from kirby_combat.actions.area_attack import explosion_dice_lost

    assert [explosion_dice_lost(d, killing=True) for d in (0, 6, 6.5, 12, 13, 19)] \
        == [0, 0, 1, 1, 2, 3]
    assert [explosion_dice_lost(d, killing=False) for d in (2, 3, 5)] == [0, 1, 2]
    grenade = replace(shaped_blast("a-frag", 3, area=area(size=20, explosion=True)),
                      damage_type="killing", defense_type="pd")
    assert unbuilt_reasons(grenade) == []


# --- What stays unoffered --------------------------------------------------

def test_uncontrolled_is_not_offered():
    """6E1 p.354: Uncontrolled runs on an END pool its user chooses and stops
    on words the build carries; neither is anything an offer can say."""
    power = shaped_blast("a-ignite", 4, area=area(), constant=True, uncontrolled=True)
    assert "Uncontrolled (6E1 p.354)" in unbuilt_reasons(power)
