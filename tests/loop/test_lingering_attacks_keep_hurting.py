"""Constant and Damage Over Time attacks go on hurting after they land.

6E1 p.129, Constant: "From then on the target takes damage ... in every
Segment in which the attacker has a Phase (on the attacker's DEX) until the
attacker turns off the Power, stops maintaining it (i.e., stops paying END
for it), or loses LOS to the target."

6E1 p.331-332, Damage Over Time: "the first increment of damage affects the
target one time period after the character uses the attack ... it requires
no Actions ... If the caster is Stunned or Knocked Out, or loses Line Of
Sight on the target, the power continues to function as intended."

Neither did anything in the engine: a Constant Blast hit once, a Damage
Over Time power hit once at full damage. The deleted api driver fired both
at the start of the VICTIM's Phase as STUN only, and let the victim shake
either off with a CON Roll no page grants.

Both fighters are SPD 4 (Phases 3, 6, 9, 12); the attacker is the faster.
"""
from __future__ import annotations

from dataclasses import replace

from shaped import (                                    # tests/loop/shaped.py
    Dice, Picks, armed, encounter_on, payloads, scene_with, shaped_blast,
)
from kirby_combat.lingering import LingeringEnd, active_lingering
from kirby_combat.loop import run_phase
from kirby_combat.power_modifiers import DamageOverTimeSpec
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_engine
from kirby_combat.side import Side
from kirby_world.scene import Position, Wall

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _fight(power, *, walls=None):
    scene = scene_with({"a": (0, 0, 0), "b": (6, 0, 0)}, walls=walls)
    return encounter_on(scene,
                        armed("a", power, side=VILLAINS, dex=30),
                        armed("b", None, side=HEROES, dex=10))


def _attacks_once():
    """Attack b on the first Phase only, then Dodge."""
    fired = []

    def want(action, situation):
        if situation.actor.id == "a" and action.kind == "attack" and not fired:
            fired.append(action.action_id)
            return True
        return False
    return Picks(want)


def _phases(enc, chooser, n, dice):
    results = []
    for _ in range(n):
        r = run_phase(enc, chooser, roller=dice, on_unresolvable="raise")
        results.append(r)
        enc = r.encounter
    return enc, results


def _to_as_next_phase(enc, chooser, dice):
    """Step until a's next Phase has been run; return it and the fight. (b
    may Abort to a Dodge out of turn on the way, 6E2 p.24, which costs him
    his own next Phase --- so "the third Phase" is not a fixed index.)"""
    for _ in range(12):
        r = run_phase(enc, chooser, roller=dice, on_unresolvable="raise")
        enc = r.encounter
        if r.actor_id == "a":
            return enc, r
    raise AssertionError("a never acted again")


def _stun(enc, who):
    return enc.sessions[0].combatants[who].state.current_stun


# --- Constant ----------------------------------------------------------------

def test_a_constant_blast_hurts_him_again_on_the_attackers_next_phase():
    """Seam: Segment 12 a hits b (4d6 of 2s = 8 STUN, less ED 4 = 4). At
    the start of a's next Phase he pays and b takes it again --- no Attack
    Roll, no Action --- and a still chooses (a Dodge)."""
    enc = _fight(shaped_blast("a-beam", 4, constant=True))
    chooser = _attacks_once()
    enc, _ = _phases(enc, chooser, 1, Dice(face=2))
    enc, second = _to_as_next_phase(enc, chooser, Dice(face=2))
    assert second.kind == "dodge"
    # The free Post-Segment 12 Recovery (6E2 p.131) falls between the two.
    assert _stun(enc, "b") == 40 - 4 - 4 + _recovered(enc.sessions[0], "b")
    doses = payloads(enc.sessions[0], lingering_mode="constant")
    assert len(doses) == 1 and doses[0]["target_id"] == "b"
    assert doses[0]["power_source_id"] is None     # not a second firing


def test_it_stops_when_the_attacker_is_stunned():
    """6E1 p.347: a Constant power "turns off at the end of the Segment
    whenever the character is asleep, Stunned, or Knocked Out"."""
    enc = _fight(shaped_blast("a-beam", 4, constant=True))
    chooser = _attacks_once()
    enc, _ = _phases(enc, chooser, 1, Dice(face=2))
    s = enc.sessions[0]
    s = apply_event(s, ActionResolved(
        id="stun-a", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_engine(),
        declaration_event_id="",
        result_payload={"kind": "attack", "target_id": "a",
                        "status_changes": ["Stunned"]},
    ))
    enc = replace(enc, sessions=[s])
    enc, _ = _to_as_next_phase(enc, chooser, Dice(face=2))
    ended = [e for e in enc.sessions[0].event_log if e.kind == "LingeringAttackEnded"]
    assert [e.reason for e in ended] == [LingeringEnd.ATTACKER_STUNNED.value]
    assert payloads(enc.sessions[0], lingering_mode="constant") == []


def test_it_stops_when_he_loses_line_of_sight():
    """6E1 p.129: "or loses LOS to the target". A wall goes up between them."""
    enc = _fight(shaped_blast("a-beam", 4, constant=True))
    chooser = _attacks_once()
    enc, _ = _phases(enc, chooser, 1, Dice(face=2))
    s = enc.sessions[0]
    wall = Wall(id="w", name="w",
                segment=(Position(3.0, -5.0, 0.0), Position(3.0, 5.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4)
    s = replace(s, scene=replace(s.scene, walls=[wall]))
    enc = replace(enc, sessions=[s])
    enc, _ = _to_as_next_phase(enc, chooser, Dice(face=2))
    ended = [e.reason for e in enc.sessions[0].event_log
             if e.kind == "LingeringAttackEnded"]
    assert ended == [LingeringEnd.LOST_LINE_OF_SIGHT.value]


def test_a_constant_hit_is_recorded_and_survives_a_replay():
    """The running effect is in the LOG (`LingeringAttackApplied`), so a
    fight rebuilt from its rows still has it."""
    from kirby_combat.serialization import from_dict, to_dict

    enc = _fight(shaped_blast("a-beam", 4, constant=True))
    enc, _ = _phases(enc, _attacks_once(), 1, Dice(face=2))
    s = enc.sessions[0]
    rebuilt = [from_dict(to_dict(e)) for e in s.event_log]
    assert [e.kind for e in rebuilt].count("LingeringAttackApplied") == 1
    assert len(active_lingering(s)) == 1


# --- Damage Over Time --------------------------------------------------------

def _dot(increments=3, every=1, lockout=False, one_defense=False):
    return DamageOverTimeSpec(increments=increments, interval_segments=every,
                              lockout=lockout, one_defense=one_defense,
                              unbuilt=())


def test_damage_over_time_does_nothing_on_the_hit_and_then_doses_on_its_clock():
    """Seam: the hit in Segment 12 does no damage. One dose a Segment for
    three Segments (Turn 2's Segments 1, 2, 3), each 4d6 of 2s less ED 4 =
    4 STUN, then it has run its course."""
    enc = _fight(shaped_blast("a-venom", 4, damage_over_time=_dot()))
    chooser = _attacks_once()
    enc, results = _phases(enc, chooser, 1, Dice(face=2))
    assert payloads(enc.sessions[0], damage_over_time=True)[0]["hit"] is True
    assert _stun(enc, "b") == 40

    enc, _ = _phases(enc, chooser, 3, Dice(face=2))
    s = enc.sessions[0]
    doses = payloads(s, lingering_mode="damage_over_time")
    assert [d["increments_remaining"] for d in doses] == [2, 1, 0]
    assert _stun(enc, "b") == 40 - 3 * 4 + _recovered(s, "b")
    ended = [e.reason for e in s.event_log if e.kind == "LingeringAttackEnded"]
    assert ended == [LingeringEnd.RAN_ITS_COURSE.value]


def _recovered(session, who):
    """Post-Segment 12 Recovery handed back between the hit and the doses."""
    return sum(e.stun_recovered for e in session.event_log
               if e.kind == "RecoveryTaken" and e.combatant_id == who)


def test_lock_out_takes_the_offer_away_while_it_runs():
    """6E1 p.332: a Locked Out Damage Over Time cannot be used on that target
    again "until the first use stops affecting him"."""
    enc = _fight(shaped_blast("a-venom", 4,
                              damage_over_time=_dot(increments=8, every=12,
                                                    lockout=True)))
    chooser = _attacks_once()
    enc, _ = _phases(enc, chooser, 3, Dice(face=2))
    later = [m for m in chooser.menus[1:] if any(a.kind == "dodge" for a in m)]
    a_menus = [m for m in chooser.menus if any(
        getattr(x, "_attack_view", None) is not None
        and x._attack_view.source_id == "a-venom" for x in m)]
    # Offered on the first Phase, gone from a's menu once it is running.
    assert len(a_menus) == 1
    assert later


def test_a_defence_that_applies_once_is_spent_and_then_gone():
    """6E1 p.332's acid on Hemdring, as a Killing 1d6 against his rPD 2 (the
    fixture's): doses of 1, 3 and 2 BODY. The first is soaked (1 of the 2
    spent); the second takes the last point and lets 2 through; the third
    meets no defense and all 2 land."""
    venom = replace(shaped_blast("a-acid", 1,
                                 damage_over_time=_dot(one_defense=True)),
                    damage_type="killing", defense_type="pd")
    enc = _fight(venom)
    # Every single die is scripted, in order: the hit's damage die and STUN
    # multiplier (rolled and unused --- a Damage Over Time hit does no
    # damage), then each dose's damage die and STUN multiplier.
    dice = _SingleDice([1, 1, 1, 1, 3, 1, 2, 1])
    enc, _ = _phases(enc, _attacks_once(), 4, dice)
    doses = payloads(enc.sessions[0], lingering_mode="damage_over_time")
    assert [d["body_dealt"] for d in doses] == [0, 2, 2]
    assert [d["defense_absorbed_body"] for d in doses] == [1, 1, 0]


class _SingleDice(Dice):
    """Scripted single dice; every bigger roll shows 3s."""

    def __init__(self, singles):
        super().__init__(face=3)
        self.singles = list(singles)

    def roll_dice(self, count, sides=6):
        if count == 1:
            return [self.singles.pop(0)]
        return [3] * count


def test_a_second_use_is_a_second_maintained_attack():
    """6E1 p.129: "he could attack the same target a second time and affect
    him with the power twice ... Each use of the power costs END to activate
    and to maintain" --- Sapphire keeps two going at once. Batch C ended the
    first use when the power was used again; the page keeps both."""
    enc = _fight(shaped_blast("a-beam", 4, constant=True))
    fired = []

    def want(action, situation):
        if situation.actor.id == "a" and action.kind == "attack" and len(fired) < 2:
            fired.append(1)
            return True
        return False
    chooser = Picks(want)
    enc, _ = _phases(enc, chooser, 1, Dice(face=2))
    enc, _ = _to_as_next_phase(enc, chooser, Dice(face=2))
    s = enc.sessions[0]
    assert len(active_lingering(s, attacker_id="a")) == 2
    assert [e for e in s.event_log if e.kind == "LingeringAttackEnded"] == []
