"""Follow-up J: the martial maneuvers PR #5 stopped offering, built, and weapons.

PR #5 (`fix/maneuvers-resolve`) made every OFFERED maneuver resolve and stopped
offering the ones with no faithful rule. The engine has since gained real Move
By / Move Through, Blocks that stop blows, throws and prone, and Grab escapes,
so most of them are buildable: each test here takes the offer from the menu
`run_phase` builds (`loop.run._situation_for`), resolves it through
`run_phase(on_unresolvable="raise")` or `resolve_chosen`, and asserts the rule
it carries, with the page:

* WEAPONS (`kirby_combat.weapons`): an Accessible Focus (6E1 p.379) is a thing
  in a hand; a Disarm knocks it 1d6+1m after a STR contest (6E2 p.62), a
  Takeaway wrenches it away (6E2 p.69), and anybody can pick it up (6E2 p.25,
  p.62). Every move is a `WeaponMoved` row, so a replay keeps it.
* Must Follow Block (Counterstrike): only after a Block of THAT attacker
  succeeded, in his next Phase (6E2 p.59-60).
* Must Follow Grab: Crush is a later-Phase Squeeze and Grappling Throw a
  Throw of the man he holds (6E2 p.64).
* FMove: the charge of a Move By / Move Through (6E2 p.72) with the maneuver's
  own blow and velocity DCs (6E2 p.101).
* Shove (6E2 p.81), Martial Flash (6E1 p.228), a Grab with its free Squeeze
  (6E2 p.64), Choke Hold's Life Support defence (6E2 p.86), Martial Escape
  (6E2 p.94).

The corpus martial artist is Ravel; the armed man is Bokor, whose Mojo Hand is
an Obvious Accessible Focus. Maneuvers she has not bought are added to her
build doc and costed through kirby-cost, in Main6E.hdt's own shapes.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from kirby_dice import RandomRoller

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from kirby_combat import weapons as W
from kirby_combat.actions import recording
from kirby_combat.actions.grab import Grab
from kirby_combat.actions.maneuver_effects import (
    UnbuildableManeuver, decode_effect, damage_family,
)
from kirby_combat.encounter import Encounter
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.loop.run import _situation_for
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Wall,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

from tests.corpus import require_authored, require_authored_doc

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _AlwaysLow(RandomRoller):
    """Every die shows 1: every Attack Roll is a 3 and hits (6E2 p.37)."""

    def roll_dice(self, n):
        return [1] * n


class _AlwaysHigh(RandomRoller):
    """Every die shows 6: every Attack Roll is an 18 and misses (6E2 p.37)."""

    def roll_dice(self, n):
        return [6] * n


class _Faces(RandomRoller):
    """1s for every roll of THREE dice (Attack Rolls, which hit, and hit
    locations), and ``other`` for every other count --- so a STR contest or
    a Flash's dice can be made to come up high while the blow still lands."""

    def __init__(self, other: int):
        super().__init__(seed=1)
        self.other = other

    def roll_dice(self, n):
        return [1 if n == 3 else self.other] * n


def _maneuver(id_: str, display: str, effect: str, *, ocv: str, dcv: str,
              dc: int, add_str: bool, damage_type: int = 0, **extra) -> dict:
    """One bought maneuver in the build-doc shape HD writes (Main6E.hdt's
    definitions; a "Custom Maneuver" is HD's custom shape, as in the corpus)."""
    out = {
        "id": id_, "xmlid": "MANEUVER", "base_cost": 4.0, "alias": display,
        "maneuver": True, "category": "Hand To Hand", "display": display,
        "ocv": ocv, "dcv": dcv, "dc": dc, "phase": "1/2", "effect": effect,
        "add_str": add_str, "maneuver_active_cost": 0,
        "damage_type": damage_type, "max_str": 0, "str_multiplier": 1,
        "use_weapon": False,
    }
    out.update(extra)
    return out


#: The maneuvers PR #5 refused that this engine now builds (Main6E.hdt).
NEWLY_BUILT = [
    _maneuver("c-counter", "Counterstrike", "[NORMALDC] Strike, Must Follow Block",
              ocv="+2", dcv="+2", dc=2, add_str=True),
    _maneuver("c-crush", "Crush", "[NORMALDC] Crush, Must Follow Grab",
              ocv="+0", dcv="+0", dc=4, add_str=True),
    _maneuver("c-gthrow", "Grappling Throw",
              "[NORMALDC] Strike; Target Falls; Must Follow Grab",
              ocv="+0", dcv="+2", dc=2, add_str=True),
    _maneuver("c-takeaway", "Takeaway", "Grab Weapon, [STRDC] to take weapon away",
              ocv="+0", dcv="+0", dc=2, add_str=True),
    _maneuver("c-dthrow", "Disarming Throw",
              "Grab Weapon, [STRDC] to take weapon away; Target Falls",
              ocv="+0", dcv="+0", dc=1, add_str=True),
    _maneuver("c-shove", "Shove", "[STRDC] to Shove",
              ocv="+0", dcv="+0", dc=3, add_str=True),
    _maneuver("c-flash", "Martial Flash", "[FLASHDC]",
              ocv="-1", dcv="-1", dc=4, add_str=False, input="Sight"),
    _maneuver("c-passing", "Passing Strike", "[NORMALDC] +v/10; FMove",
              ocv="+1", dcv="+0", dc=0, add_str=True),
    _maneuver("c-tackle", "Flying Tackle",
              "[NORMALDC] +v/10 Strike; You Fall, Target Falls; FMove",
              ocv="+0", dcv="-1", dc=0, add_str=True),
    _maneuver("c-fgrab", "Flying Grab", "Grab Two Limbs, [STRDC] for holding on; FMove",
              ocv="-2", dcv="-1", dc=2, add_str=True),
    _maneuver("c-pdisarm", "Passing Disarm", "Disarm, [STRDC] to Disarm; FMove",
              ocv="-1", dcv="-1", dc=2, add_str=True),
    # Custom maneuvers as the corpus carries them.
    _maneuver("c-slam", "Custom Maneuver", "[DAMAGE] Strike; Grab Two Limbs; Target Falls",
              ocv="-1", dcv="-1", dc=2, add_str=True, damage_type=2),
    _maneuver("c-bite", "Custom Maneuver", "Grab One Limb, +10 STR",
              ocv="+0", dcv="+0", dc=2, add_str=True),
]

#: Already built by PR #5, and needed beside them here.
ALREADY_BUILT = [
    _maneuver("m-grab", "Martial Grab", "Grab Two Limbs, [STRDC] for holding on",
              ocv="-1", dcv="-1", dc=2, add_str=True),
    _maneuver("m-choke", "Choke Hold", "Grab One Limb; [NNDDC]",
              ocv="-2", dcv="+0", dc=4, add_str=False),
    _maneuver("m-nerve", "Nerve Strike", "[NNDDC]",
              ocv="-1", dcv="+1", dc=4, add_str=False),
    _maneuver("m-disarm", "Martial Disarm", "Disarm; [STRDC] to Disarm",
              ocv="-1", dcv="+1", dc=2, add_str=True),
    _maneuver("m-escape", "Martial Escape", "[STRDC] vs. Grabs",
              ocv="+0", dcv="+0", dc=3, add_str=True),
]

RAVEL_AT = Position(10.0, 10.0, 0.0)
MARK_AT = Position(11.0, 10.0, 0.0)


def _doc_with(name: str, maneuvers: list[dict], *, runs: bool,
              stretches: bool = True) -> dict:
    doc = copy.deepcopy(require_authored_doc(name))
    doc["martial_arts"] = list(doc["martial_arts"]) + maneuvers
    if not stretches:
        # Her Stretching gives her many metres of reach (6E2 p.56); a charge
        # is about closing, so the charging student has an arm's length.
        doc["powers"] = [p for p in doc["powers"] if p.get("xmlid") != "STRETCHING"]
    if runs:
        # Ravel buys her Running down to nothing (-12m) and floats; FMove
        # charges on Running (`velocity_maneuvers`' ruling), so this student
        # kept her legs.
        for c in doc["characteristics"]:
            if c.get("xmlid") == "RUNNING":
                c["levels"] = 0
    return doc


def _built(doc: dict, id_: str, side: str) -> HeroCombatant:
    from kirby_cost.io.build_json import build_from_json

    return replace(HeroCombatant.from_build(build_from_json(doc), id=id_),
                   side=Side.named(side))


def _student(*, runs: bool = True, stretches: bool = True) -> HeroCombatant:
    """Ravel, having studied every maneuver above --- costed by kirby-cost."""
    return _built(_doc_with("Ravel", NEWLY_BUILT + ALREADY_BUILT, runs=runs,
                            stretches=stretches), "ravel", "a")


def _charger() -> HeroCombatant:
    """The student, on her feet and at arm's length: for the FMove tests."""
    return _student(runs=True, stretches=False)


def _ravel() -> HeroCombatant:
    return replace(HeroCombatant.from_build(require_authored("Ravel"), id="ravel"),
                   side=Side.named("a"))


def _bokor(id_: str = "mark") -> HeroCombatant:
    """Bokor, as imported: Mojo Hand (an HA) is an OAF, Transform an OAF and
    his Resistant Protection an IAF (6E1 p.379: all three can be taken)."""
    return replace(HeroCombatant.from_build(require_authored("Bokor"), id=id_),
                   side=Side.named("b"))


def _mark():
    return synthetic_combatant(
        id="mark", name="mark", ocv=6, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=15, ego=10, str_=15, con=18, pre=10, rec=6,
        pd=4, ed=4, rpd=0, red=0, md=0,
        max_stun=60, max_body=15, max_end=40, side=Side.named("b"),
    )


def _session(actor, mark, *, mark_at=MARK_AT, walls=()) -> CombatSession:
    scene = Scene(
        id="mat", name="Mat", bounds=SceneBounds(0, 0, 0, 60, 40, 10),
        surfaces=[], walls=list(walls), hazards=[], ambient=AmbientConditions(),
        combatant_positions={actor.id: RAVEL_AT, mark.id: mark_at},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3), combatants=[actor, mark],
    ).start()


def _menu(session, who: str = "ravel"):
    """The menu `run_phase` builds, through its own door."""
    return _situation_for(session, who).menu


def _offers(session, name: str, who: str = "ravel"):
    return [a for a in _menu(session, who)
            if a.kind == "maneuver" and a.power_name == name]


def _resolve(session, offer, roller, who: str = "ravel"):
    return resolve_chosen(session, session.combatants[who], offer,
                          template=TEMPLATE, roller=roller)


def _mv_id(session, effect: str, who: str = "ravel") -> str:
    """The id kirby-cost gave the bought maneuver with this EFFECT (it
    numbers the objects it builds; the doc's ids are not kept)."""
    return next(m.maneuver_id for m in session.combatants[who].maneuver_view()
                if m.effect == effect)


def _by_effect(session, effect: str, who: str = "ravel"):
    """The offers for the maneuver with this EFFECT (custom maneuvers all
    display as "Custom Maneuver", as in the corpus)."""
    return [a for a in _menu(session, who)
            if a.kind == "maneuver" and a._maneuver_view.effect == effect]


def _row(session, **match) -> dict:
    """The last action row whose payload carries every ``match`` item."""
    for e in reversed(session.event_log):
        if e.kind == "ActionResolved" and all(
                e.result_payload.get(k) == v for k, v in match.items()):
            return e.result_payload
    raise AssertionError(f"no ActionResolved row with {match}")


def _mojo(session) -> W.Weapon:
    return next(w for w in W.accessible_foci(session.combatants["mark"])
                if w.name == "Mojo Hand")


def _attack_names(session, who: str) -> set[str]:
    return {a.name for a in session.combatants[who].attacks}


class _Script:
    """A chooser that plays each actor's list of picks, in order.

    Each pick is a predicate on a menu offer; an actor with nothing left
    to play Dodges. Only the ACTOR'S own Phase is scripted --- an
    out-of-turn question (an Abort, a Held Action) gets the do-nothing
    offer, which is always first (`loop/reactions.py`).
    """

    def __init__(self, **picks):
        self.picks = {k: list(v) for k, v in picks.items()}
        self.played: list[tuple[str, str]] = []

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None):
            return situation.menu[0].action_id
        queue = self.picks.get(situation.actor.id) or []
        if queue:
            want = queue.pop(0)
            offer = next((a for a in situation.menu if want(a)), None)
            assert offer is not None, (
                f"{situation.actor.id}: no offer matched; menu was "
                f"{[a.action_id for a in situation.menu]}")
            self.played.append((situation.actor.id, offer.action_id))
            return offer.action_id
        dodge = [a for a in situation.menu if a.kind in ("dodge", "recover")]
        return (dodge or situation.menu)[0].action_id


def _play(session, chooser: _Script, *, roller, phases: int) -> CombatSession:
    """Step the fight through `run_phase`, refusing anything unresolvable,
    until every scripted pick has been played (or ``phases`` run out)."""
    encounter = Encounter(id="e", turn=session.timeline.turn,
                          segment=session.timeline.segment, sessions=[session])
    for _ in range(phases):
        if not any(chooser.picks.values()):
            break
        encounter = run_phase(encounter, chooser, roller=roller,
                              on_unresolvable="raise").encounter
    assert not any(chooser.picks.values()), f"unplayed picks: {chooser.picks}"
    return encounter.sessions[0]


def _maneuver_named(name):
    return lambda a: a.kind == "maneuver" and a.power_name == name


def _kind(kind, **attrs):
    return lambda a: a.kind == kind and all(getattr(a, k) == v for k, v in attrs.items())


# ===========================================================================
# Weapons
# ===========================================================================

def test_an_accessible_focus_is_a_weapon_and_an_inaccessible_one_is_not():
    """6E1 p.379: an Accessible Focus "can be hit by a Grab or other
    nonranged attack"; an Inaccessible one "can't be ... while that
    character is in combat"."""
    owned = {(w.name, w.focus) for w in W.accessible_foci(_bokor())}
    assert owned == {("Mojo Hand", "OAF"), ("Create Zombi", "OAF"),
                     ("Resistant Protection", "IAF")}
    assert W.accessible_foci(_ravel()) == []
    assert W.accessible_foci(_mark()) == []


def test_a_disarm_is_offered_per_weapon_in_his_hand_and_only_in_reach():
    """6E2 p.62: a Disarm knocks "the target's weapon or object" away, so a
    man holding nothing is not offered one; and it is hand-to-hand."""
    near = _session(_ravel(), _bokor())
    offered = {a._weapon.name for a in _menu(near) if a.kind == "disarm"}
    assert offered == {"Mojo Hand", "Create Zombi", "Resistant Protection"}
    armless = _built(_doc_with("Ravel", [], runs=False, stretches=False), "ravel", "a")
    far = _session(armless, _bokor(), mark_at=Position(30.0, 10.0, 0.0))
    assert not [a for a in _menu(far) if a.kind == "disarm"]
    unarmed = _session(_ravel(), _mark())
    assert not [a for a in _menu(unarmed) if a.kind == "disarm"]


def test_a_landed_disarm_knocks_the_weapon_off_his_sheet_through_run_phase():
    """6E2 p.62: the Attack Roll, the STR contest (ties to the attacker), and
    the weapon "goes flying 1d6+1 meters in the direction of the strike".
    Off his sheet for every reader: his Mojo Hand attack is gone, and his
    menu no longer offers it."""
    session = _session(_ravel(), _bokor())
    mojo = _mojo(session)
    assert "Mojo Hand" in _attack_names(session, "mark")
    chooser = _Script(ravel=[lambda a: a.kind == "disarm" and a._weapon == mojo])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)

    moved = [e for e in after.event_log if e.kind == "WeaponMoved"]
    assert [(e.cause, e.holder_id, e.weapon_name) for e in moved] == [
        ("disarm", "", "Mojo Hand")]
    # Ones: a tied contest (0 BODY each) goes to the attacker; 1d6+1 = 2m,
    # straight on along the line of the blow, from 11m to 13m.
    assert (moved[0].on_map, moved[0].x, moved[0].y) == (True, 13.0, 10.0)
    row = _row(after, kind="disarm")
    assert row["disarm_contest"]["won"] is True
    assert "Mojo Hand" not in _attack_names(after, "mark")
    assert not [a for a in _menu(after, "mark")
                if a.kind == "attack" and a._attack_view.name == "Mojo Hand"]


def test_a_replay_from_the_log_has_him_disarmed_too():
    """The weapon's place is in the log, absolute (the durations pattern):
    a session folded back up from its rows has him unarmed."""
    session = _session(_ravel(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _menu(session) if a.kind == "disarm" and a._weapon == mojo)
    after = _resolve(session, offer, _AlwaysLow(seed=1)).session

    replay = rewind_to_sequence(after, 0)
    assert "Mojo Hand" in _attack_names(replay, "mark")
    for event in after.event_log:
        replay = apply_event(replay, event)
    assert "Mojo Hand" not in _attack_names(replay, "mark")
    assert W.weapons_in_play(replay) == W.weapons_in_play(after)


def test_the_two_contests_and_their_tie_rules():
    """6E2 p.62: "If the attacker's BODY total is higher or the rolls tie,
    the Disarm succeeds ... If the defender's BODY total is higher, he
    retains his grip"; 6E1 p.379's wrench needs "more BODY"."""
    win = W.disarm_contest(_Faces(6), attacker_str=10, defender_str=10)
    assert win["won"] is True
    lose = W.disarm_contest(_TwoThenThree(), attacker_str=10, defender_str=15)
    assert (lose["attacker_body"], lose["defender_body"], lose["won"]) == (0, 6, False)
    tie = W.disarm_contest(_AlwaysLow(seed=1), attacker_str=10, defender_str=15)
    assert tie["won"] is True, "6E2 p.62: 'or the rolls tie'"
    wrench_tie = W.wrench_contest(_AlwaysLow(seed=1), attacker_str=10, defender_str=15)
    assert wrench_tie["won"] is False, "6E1 p.379: 'more BODY'"


class _TwoThenThree(RandomRoller):
    """Ones for two dice, sixes for three: the attacker low, the defender high."""

    def __init__(self):
        super().__init__(seed=1)

    def roll_dice(self, n):
        return [1 if n == 2 else 6] * n


def test_a_lost_contest_moves_nothing_and_says_so():
    session = _session(_ravel(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _menu(session) if a.kind == "disarm" and a._weapon == mojo)

    roller = _ContestLoser()
    after = _resolve(session, offer, roller).session
    row = _row(after, kind="disarm")
    assert row["hit"] is True and row["disarm_contest"]["won"] is False
    assert not [e for e in after.event_log if e.kind == "WeaponMoved"]
    assert "Mojo Hand" in _attack_names(after, "mark")


class _ContestLoser(RandomRoller):
    """The Attack Roll hits (the first 3d6 are ones), and after it every die
    is a one for TWO dice (Ravel's STR 10) and a six for THREE (Bokor's
    STR 15)."""

    def __init__(self):
        super().__init__(seed=1)
        self.first = True

    def roll_dice(self, n):
        if self.first and n == 3:
            self.first = False
            return [1, 1, 1]
        return [1 if n == 2 else 6] * n


def test_he_moves_to_his_weapon_and_picks_it_up():
    """6E2 p.62: "a Half Phase Action to move to the weapon ... plus another
    Half Phase Action to pick it up" (6E2 p.25). Back in his hand, back on
    his sheet."""
    session = _session(_ravel(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _menu(session) if a.kind == "disarm" and a._weapon == mojo)
    after = _resolve(session, offer, _AlwaysLow(seed=1)).session

    pick = next(a for a in _menu(after, "mark") if a.kind == "pick_up_weapon")
    assert pick._weapon == mojo
    assert pick.reposition_dest == (13.0, 10.0, 0.0), "2m off: he must move"
    back = _resolve(after, pick, _AlwaysLow(seed=1), who="mark").session
    moved = [e for e in back.event_log if e.kind == "WeaponMoved"]
    assert (moved[-1].cause, moved[-1].holder_id) == ("pick_up", "mark")
    assert "Mojo Hand" in _attack_names(back, "mark")
    assert not [a for a in _menu(back, "mark") if a.kind == "pick_up_weapon"]


def test_an_enemy_who_picks_it_up_denies_it_and_gains_nothing():
    """RULING (6E1 p.382, a Focus's applicability is the player's choice and
    HD records none): in another man's hand it is lost to its owner and no
    use to the holder."""
    session = _session(_ravel(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _menu(session) if a.kind == "disarm" and a._weapon == mojo)
    after = _resolve(session, offer, _AlwaysLow(seed=1)).session
    before = _attack_names(after, "ravel")

    pick = next(a for a in _menu(after) if a.kind == "pick_up_weapon")
    taken = _resolve(after, pick, _AlwaysLow(seed=1)).session
    assert W.holder_of(taken, mojo) == "ravel"
    assert "Mojo Hand" not in _attack_names(taken, "mark")
    assert _attack_names(taken, "ravel") == before


def test_takeaway_wrenches_it_into_his_hand_and_he_can_be_disarmed_of_it():
    """6E2 p.69: "Grab a target's weapon ... and can attempt to wrench it
    away"; 6E1 p.379: it comes free "if the attacker rolls more BODY".
    Takeaway's [STRDC] is +10 STR for the wrench. Its owner takes it back
    the way it went: a Disarm of the man holding it."""
    session = _session(_student(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _offers(session, "Takeaway") if a._weapon == mojo)
    after = _resolve(session, offer, _Faces(6)).session
    row = _row(after, maneuver_id=_mv_id(session, 'Grab Weapon, [STRDC] to take weapon away'))
    assert row["takeaway_contest"]["attacker_str"] == 10 + 10
    assert row["takeaway_contest"]["won"] is True
    assert W.holder_of(after, mojo) == "ravel"
    assert "Mojo Hand" not in _attack_names(after, "mark")
    assert mojo in W.weapons_in_play(after).held_by("ravel")

    back = next(a for a in _menu(after, "mark")
                if a.kind == "disarm" and a._weapon == mojo)
    knocked = _resolve(after, back, _AlwaysLow(seed=1), who="mark").session
    assert W.holder_of(knocked, mojo) is None


def test_a_tied_wrench_leaves_the_weapon_where_it_was():
    session = _session(_student(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _offers(session, "Takeaway") if a._weapon == mojo)
    after = _resolve(session, offer, _AlwaysLow(seed=1)).session
    assert _row(after, maneuver_id=_mv_id(session, 'Grab Weapon, [STRDC] to take weapon away'))["takeaway_contest"]["won"] is False
    assert W.holder_of(after, mojo) == "mark"


def test_disarming_throw_takes_it_and_puts_him_down(monkeypatch):
    # Its [STRDC] at DC 1 makes Ravel's wrench STR 15, Bokor's own: the
    # contest's rule is pinned above, so here it is won outright.
    wins = iter([(6, [6, 6, 6]), (0, [1, 1, 1])])
    monkeypatch.setattr(W, "str_body", lambda roller, strength: next(wins))
    session = _session(_student(), _bokor())
    mojo = _mojo(session)
    offer = next(a for a in _offers(session, "Disarming Throw") if a._weapon == mojo)
    after = _resolve(session, offer, _Faces(6)).session
    assert W.holder_of(after, mojo) == "ravel"
    assert PRONE in statuses_for(after, "mark")


def test_martial_disarm_through_run_phase_uses_its_str_bonus():
    """6E2 p.94: Martial Disarm's STR bonus is "only for purposes of
    determining the outcome of the Disarm STR Versus STR Contest"."""
    session = _session(_student(), _bokor())
    chooser = _Script(ravel=[lambda a: (a.kind == "maneuver"
                                        and a.power_name == "Martial Disarm"
                                        and a._weapon.name == "Mojo Hand")])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    row = _row(after, maneuver_id=_mv_id(session, 'Disarm; [STRDC] to Disarm'))
    assert row["disarm_contest"]["attacker_str"] == 10 + 10
    assert W.holder_of(after, _mojo(after)) is None


def test_disarm_reports_the_same_three_facts():
    """Moved from `test_blind_maneuvers`: the report belongs to the maneuver
    path, and Disarm is -2 OCV (6E2 p.58) and carries the same keys."""
    session = _session(_ravel(), _bokor())
    offer = next(a for a in _menu(session) if a.kind == "disarm")
    resolved = _resolve(session, offer, _AlwaysLow(seed=1))
    payload = _row(resolved.session, kind="disarm")
    to_hit = resolved.result.to_hit
    assert payload["effective_ocv"] == to_hit.effective_ocv
    assert payload["target_dcv"] == to_hit.effective_dcv
    assert payload["margin"] == to_hit.margin


def test_a_man_with_no_attack_powers_disarms_with_his_hands():
    """Moved from `test_subproject_b_maneuvers`: Disarm is a STR maneuver
    (6E2 p.58, p.62) and rolls the bare-handed Strike, whoever is holding
    what --- and it rolls with the caller's roller, never the session's."""
    session = _session(_ravel(), _bokor())
    offer = next(a for a in _menu(session) if a.kind == "disarm")

    class _Refuses(RandomRoller):
        def roll_dice(self, n):
            raise AssertionError("the session's roller was used")

    session = replace(session, dice_roller=_Refuses(seed=1))
    resolved = _resolve(session, offer, _AlwaysLow(seed=1))
    assert resolved.result.power_xmlid == "STR"


def test_a_slot_with_its_own_focus_is_its_own_weapon():
    """A Multipower slot bought OAF inside a pool that is not is one object
    (`kirby_combat.weapons`): taking it leaves the rest of the pool."""
    doc = copy.deepcopy(require_authored_doc("Ravel"))
    spear = next(p for p in doc["powers"] if p.get("name") == "String Spear")
    spear.setdefault("modifiers", []).append(
        {"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0})
    ravel = _built(doc, "ravel", "a")
    (weapon,) = W.accessible_foci(ravel)
    assert weapon.name == "String Spear"
    session = _session(ravel, _mark())
    assert {"String Spear", "String Storm"} <= _attack_names(session, "ravel")
    session = W.move_weapon(session, weapon, by_id="mark", cause=W.DISARMED,
                            holder_id=None, position=Position(5.0, 5.0, 0.0))
    names = _attack_names(session, "ravel")
    assert "String Spear" not in names and "String Storm" in names


# ===========================================================================
# Must Follow Block
# ===========================================================================

def test_counterstrike_follows_only_a_block_of_that_attacker():
    """Counterstrike ("[NORMALDC] Strike, Must Follow Block") is offered only
    in his Phase after a successful Block of THAT attacker (6E2 p.59-60:
    the Block, and its reward of acting first), and is gone after it."""
    session = _session(_student(), _mark())
    assert not _offers(session, "Counterstrike"), "no Block, no Counterstrike"

    chooser = _Script(
        ravel=[_kind("block"),
               _maneuver_named("Counterstrike")],
        mark=[_kind("strike", target_id="ravel")],
    )
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    block = _row(after, kind="block")
    assert block["success"] and block["attacker_id"] == "mark"
    row = _row(after, maneuver_id=_mv_id(session, '[NORMALDC] Strike, Must Follow Block'))
    assert row["hit"] is True
    assert not _offers(after, "Counterstrike"), "his Phase after has been used"


def test_a_counterstrike_not_earned_is_refused():
    """The resolver asks the log again: an offer carried into a fight where
    no Block of his succeeded is refused, never rolled."""
    session = _session(_student(), _mark())
    offer = _offers(_with_block(session), "Counterstrike")[0]
    assert offer.target_id == "mark"
    with pytest.raises(UnresolvableAction):
        _resolve(session, offer, _AlwaysLow(seed=1))


def _with_block(session):
    """Ravel Blocks; the mark's punch meets it (6E2 p.59)."""
    from kirby_combat.actions.reactive.block import Block

    session, _ = Block.declare(session, "ravel")
    punch = next(a for a in _menu(session, "mark")
                 if a.kind == "strike" and a.target_id == "ravel")
    return _resolve(session, punch, _AlwaysLow(seed=1), who="mark").session


# ===========================================================================
# Must Follow Grab: Crush and Grappling Throw (6E2 p.64)
# ===========================================================================

def test_crush_squeezes_the_held_man_and_keeps_the_hold(monkeypatch):
    """6E2 p.64: a later Squeeze "is an Attack Action ... requires an Attack
    Roll"; it "does regular STR damage ... the character retains his hold".
    Crush adds its 4 DC. The Grab's CV applies: the held man is at 1/2 DCV
    (6E2 p.64-66)."""
    session = _session(_student(), _mark())
    assert not _offers(session, "Crush"), "nobody held, nothing to Crush"
    seen = []
    original = recording.resolve_attack
    monkeypatch.setattr(recording, "resolve_attack",
                        lambda attack, template: seen.append(attack) or original(attack, template))

    chooser = _Script(ravel=[_maneuver_named("Martial Grab"), _maneuver_named("Crush")])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")
    row = _row(after, maneuver_id=_mv_id(session, '[NORMALDC] Crush, Must Follow Grab'))
    assert row["hit"] is True and row["squeeze"] is True
    crush = seen[-1]
    # STR 10's 2d6 + 4 DC (6E2 p.93; p.101).
    assert crush.power.damage_dice == 6
    assert crush.grab_dcv_factor == 0.5


def test_a_missed_crush_does_nothing_and_he_is_still_held():
    session = _session(_student(), _mark())
    held = _resolve(session, _offers(session, "Martial Grab")[0], _AlwaysLow(seed=1)).session
    after = _resolve(held, _offers(held, "Crush")[0], _AlwaysHigh(seed=1)).session
    assert _row(after, maneuver_id=_mv_id(session, '[NORMALDC] Crush, Must Follow Grab'))["hit"] is False
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")


def test_grappling_throw_puts_the_held_man_down_and_lets_him_go():
    """A Throw "requires him to let go of the victim" (6E2 p.64); the
    maneuver's Target Falls puts him down."""
    session = _session(_student(), _mark())
    chooser = _Script(ravel=[_maneuver_named("Martial Grab"),
                             _maneuver_named("Grappling Throw")])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    assert _row(after, maneuver_id=_mv_id(session, '[NORMALDC] Strike; Target Falls; Must Follow Grab'))["hit"] is True
    assert PRONE in statuses_for(after, "mark")
    assert Grab.is_grabbed(after, "mark") == (False, None)


# ===========================================================================
# FMove (6E2 p.72, p.101)
# ===========================================================================

def test_passing_strike_charges_hits_with_velocity_and_runs_on():
    """A Move By's charge, the maneuver's blow: STR 10's 2d6 + 1d6 for 12m of
    velocity (+v/10, 6E2 p.101), and "Hit or miss, the character finishes at
    the end of his movement path" (6E2 p.72)."""
    far = Position(18.0, 10.0, 0.0)
    session = _session(_charger(), _mark(), mark_at=far)
    assert not [a for a in _menu(session) if a.kind == "maneuver"
                and a.power_name == "Martial Grab"], "8m: no plain maneuver"
    assert _offers(session, "Passing Strike")
    chooser = _Script(ravel=[_maneuver_named("Passing Strike")])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    row = _row(after, maneuver_id=_mv_id(session, '[NORMALDC] +v/10; FMove'))
    assert row["hit"] is True and row["velocity_mps"] == 12.0
    from kirby_world.occupancy import position_of

    end = position_of(after.scene, "ravel")
    assert end.x > far.x, "past him, at the end of the run"


def test_flying_tackle_puts_both_down_where_it_hit():
    session = _session(_charger(), _mark(), mark_at=Position(16.0, 10.0, 0.0))
    after = _resolve(session, _offers(session, "Flying Tackle")[0], _AlwaysLow(seed=1)).session
    assert PRONE in statuses_for(after, "mark")
    assert PRONE in statuses_for(after, "ravel")
    from kirby_world.occupancy import position_of

    assert position_of(after.scene, "ravel").x < 16.0, "stopped where he hit"


def test_flying_grab_takes_hold_at_the_end_of_the_charge():
    session = _session(_charger(), _mark(), mark_at=Position(16.0, 10.0, 0.0))
    after = _resolve(session, _offers(session, "Flying Grab")[0], _AlwaysLow(seed=1)).session
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")


def test_passing_disarm_takes_the_weapon_on_the_way_past():
    # Bokor without his Invisibility: a charge is at a man you can see.
    doc = copy.deepcopy(require_authored_doc("Bokor"))
    doc["powers"] = [p for p in doc["powers"] if p.get("xmlid") != "INVISIBILITY"]
    session = _session(_charger(), _built(doc, "mark", "b"),
                       mark_at=Position(16.0, 10.0, 0.0))
    mojo = _mojo(session)
    offer = next(a for a in _offers(session, "Passing Disarm") if a._weapon == mojo)
    after = _resolve(session, offer, _AlwaysLow(seed=1)).session
    assert W.holder_of(after, mojo) is None


def test_no_fmove_where_the_charge_cannot_end_in_contact():
    session = _session(_charger(), _mark(), mark_at=Position(40.0, 10.0, 0.0))
    assert not _offers(session, "Passing Strike")
    # And a woman who floats and does not run charges nowhere.
    legless = _built(_doc_with("Ravel", NEWLY_BUILT, runs=False, stretches=False),
                     "ravel", "a")
    assert not _offers(_session(legless, _mark(), mark_at=Position(16.0, 10.0, 0.0)),
                       "Passing Strike")


# ===========================================================================
# Shove (6E2 p.81)
# ===========================================================================

def test_a_shove_moves_him_back_a_metre_per_five_str_and_hurts_nobody():
    """STR 10 + the maneuver's 15 STR "to Shove" = 5m; "Shoving does no
    damage to a target unless he's Shoved into a surface"."""
    session = _session(_student(), _mark())
    after = _resolve(session, _offers(session, "Shove")[0], _AlwaysLow(seed=1)).session
    row = _row(after, maneuver_id=_mv_id(session, '[STRDC] to Shove'))
    assert row["shove_m"] == 5.0 and row["stun_dealt"] == 0
    from kirby_world.occupancy import position_of

    assert position_of(after.scene, "mark").x == pytest.approx(16.0)


def test_a_shove_into_a_wall_does_str_damage():
    wall = Wall(id="w", name="wall",
                segment=(Position(13.0, 0.0, 0.0), Position(13.0, 40.0, 0.0)),
                height_m=3.0, def_value=5, body=10)
    session = _session(_student(), _mark(), walls=[wall])
    after = _resolve(session, _offers(session, "Shove")[0], _Faces(6)).session
    row = _row(after, maneuver_id=_mv_id(session, '[STRDC] to Shove'))
    assert row["shoved_into"] == "w"
    assert row["stun_dealt"] > 0


# ===========================================================================
# Martial Flash (6E1 p.228), a Grab's free Squeeze (6E2 p.64), free-text STR
# ===========================================================================

def test_martial_flash_blinds_the_sense_it_was_bought_against():
    """4 DC is 4d6 of Flash (kirby-cost `Maneuver.flash_dc`); BODY counted as
    Normal Damage, less Flash Defense, is Segments (6E1 p.228). Sixes: 8."""
    from kirby_combat.actions.flash import Flash

    session = _session(_student(), _mark())
    after = _resolve(session, _offers(session, "Martial Flash")[0], _Faces(6)).session
    flashed, groups = Flash.is_flashed(after, "mark")
    assert flashed and "sight" in groups
    applied = [e for e in after.event_log if e.kind == "FlashApplied"]
    assert applied and applied[-1].segments == 8


def test_a_grab_that_does_damage_squeezes_as_it_takes_hold():
    """6E2 p.64: "If the Grabber chooses to Squeeze ... in the same Segment
    in which he ... successfully Grabbed him, the Squeeze ... does not
    require an Attack Roll"."""
    session = _session(_student(), _mark())
    (slam,) = _by_effect(session, "[DAMAGE] Strike; Grab Two Limbs; Target Falls")
    after = _resolve(session, slam, _Faces(6)).session
    row = _row(after, maneuver_id=_mv_id(session, '[DAMAGE] Strike; Grab Two Limbs; Target Falls'))
    assert row["hit"] and row["stun_dealt"] > 0
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")
    assert PRONE in statuses_for(after, "mark")


def test_a_free_text_str_that_matches_its_dcs_is_the_holding_bonus():
    session = _session(_student(), _mark())
    (bite,) = _by_effect(session, "Grab One Limb, +10 STR")
    after = _resolve(session, bite, _AlwaysLow(seed=1)).session
    assert Grab.holding_str_bonus(after, "mark") == 10


# ===========================================================================
# Choke Hold's Life Support defence (6E2 p.86)
# ===========================================================================

def _breather(*, breathes: bool) -> HeroCombatant:
    """Bokor without his Resistant Protection (which stops both NNDs), with
    and without Life Support: Self-Contained Breathing."""
    doc = copy.deepcopy(require_authored_doc("Bokor"))
    doc["powers"] = [p for p in doc["powers"] if p.get("xmlid") != "FORCEFIELD"]
    if breathes:
        doc["powers"].append({
            "id": "scb", "xmlid": "LIFESUPPORT", "base_cost": 0.0,
            "alias": "Life Support", "name": "Self-Contained Breathing",
            "adders": [{"xmlid": "SELFCONTAINEDBREATHING", "base_cost": 10.0,
                        "selected": True}],
        })
    return _built(doc, "mark", "b")


@pytest.mark.parametrize("breathes", [True, False])
def test_choke_hold_is_stopped_by_self_contained_breathing(breathes):
    """6E2 p.86: "The defense against this NND is having rigid armor on the
    neck, Resistant Protection PD on the neck, or Life Support:
    Self-Contained Breathing." A Nerve Strike's is not (6E2 p.94)."""
    target = _breather(breathes=breathes)
    assert target.has_self_contained_breathing() is breathes
    session = _session(_student(), target)
    choke = _resolve(session, _offers(session, "Choke Hold")[0], _Faces(6)).session
    stun = _row(choke, maneuver_id=_mv_id(session, 'Grab One Limb; [NNDDC]'))["stun_dealt"]
    assert (stun == 0) is breathes
    nerve = _resolve(session, _offers(session, "Nerve Strike")[0], _Faces(6)).session
    assert _row(nerve, maneuver_id=_mv_id(session, '[NNDDC]'))["stun_dealt"] > 0


# ===========================================================================
# Martial Escape (6E2 p.94)
# ===========================================================================

def test_martial_escape_adds_its_str_to_a_full_break_out():
    """"The character adds the STR from this maneuver to his own STR when
    rolling BODY to break out from a Grab" --- [STRDC] at DC 3 is +15 STR.
    A Casual roll takes no time and is not the maneuver."""
    session = _session(_student(), _mark())
    held = Grab.declare_and_resolve(
        session, attacker_id="mark", target_id="ravel", attacker_str=15,
        target_str=10, attacker_ocv=20, target_dcv=0, attack_roll=3)[0]
    full = next(a for a in _menu(held) if a.action_id == "escape:grab:full")
    after = _resolve(held, full, _AlwaysLow(seed=1)).session
    assert _row(after, type="grab_escape")["escaper_str"] == 10 + 15
    casual = next(a for a in _menu(held) if a.action_id == "escape:grab:casual")
    after = _resolve(held, casual, _AlwaysLow(seed=1)).session
    assert _row(after, type="grab_escape")["escaper_str"] == 10 // 2


def test_an_escape_that_throws_puts_the_grabber_down():
    """A custom "[DAMAGE] vs Grabs, Target Falls" (damage type STR, as the
    corpus has it): on a successful break-out, the man who held him falls."""
    escaping = _maneuver("c-escthrow", "Custom Maneuver",
                         "[DAMAGE] vs Grabs, Target Falls",
                         ocv="+0", dcv="+0", dc=3, add_str=True, damage_type=1)
    ravel = _built(_doc_with("Ravel", [escaping], runs=True), "ravel", "a")
    session = _session(ravel, _mark())
    held = Grab.declare_and_resolve(
        session, attacker_id="mark", target_id="ravel", attacker_str=15,
        target_str=10, attacker_ocv=20, target_dcv=0, attack_roll=3)[0]
    full = next(a for a in _menu(held) if a.action_id == "escape:grab:full")
    after = _resolve(held, full, _Faces(6)).session
    assert Grab.is_grabbed(after, "ravel") == (False, None)
    assert PRONE in statuses_for(after, "mark")


# ===========================================================================
# The decoder, over HD's whole library
# ===========================================================================

#: Every Hand-To-Hand maneuver in Main6E.hdt, and whether it is built. The
#: defensive ones (Block / Dodge) are read by `actions/reactive/martial.py`,
#: and escapes by `martial_escape`; neither is an attack offer.
HD_LIBRARY = {
    "[NORMALDC] Strike": True,
    "[NORMALDC] +v/10 Strike, FMove": True,                       # Charge
    "Grab One Limb; [NNDDC]": True,                               # Choke Hold
    "[NORMALDC] Strike, Must Follow Block": True,                 # Counterstrike
    "[NORMALDC] Crush, Must Follow Grab": True,                   # Crush
    "Grab Weapon, [STRDC] to take weapon away; Target Falls": True,
    "Grab Two Limbs, [STRDC] for holding on; FMove": True,        # Flying Grab
    "[NORMALDC] +v/10 Strike; You Fall, Target Falls; FMove": True,
    "[NORMALDC] Strike; Target Falls; Must Follow Grab": True,    # Grappling Throw
    "Grab One Limb; [KILLINGDC], Disable": False,                 # Joint Break
    "Grab One Limb; [NNDDC]; Target Falls": True,
    "[KILLINGDC]": True,
    "[KILLINGDC], Target Falls": True,
    "[NORMALDC] Strike, Target Falls": True,
    "Disarm; [STRDC] to Disarm": True,
    "[FLASHDC]": True,
    "Grab Two Limbs, [STRDC] for holding on": True,
    "[NORMALDC] +v/10, Target Falls": True,
    "[NNDDC]": True,
    "Disarm, [STRDC] to Disarm; FMove": True,                     # Passing Disarm
    "[NORMALDC] +v/10; FMove": True,                              # Passing Strike
    "[NORMALDC] +v/10; Target Falls; FMove": True,                # Passing Throw
    "Disarm, [STRDC] to Disarm": True,
    "[NORMALDC] Strike; You Fall, Target Falls": True,
    "[STRDC] to Shove": True,
    "Grab Weapon, [STRDC] to take weapon away": True,             # Takeaway
    "[NORMALDC] Strike; Target Falls": True,
    "Bind, [STRDC]": False,                                       # Weapon Bind
}


@pytest.mark.parametrize("effect, built", sorted(HD_LIBRARY.items()))
def test_every_hd_library_maneuver_is_built_or_refused_by_name(effect, built):
    code = 0
    dc = 2
    try:
        decode_effect(name=effect, effect=effect,
                      damage=damage_family(effect, code), damage_classes=dc,
                      adds_str=not effect.startswith(("[NNDDC]", "Grab One Limb; [NNDDC]",
                                                       "[FLASHDC]")),
                      hd_defense="NORMAL", sense_input="Sight")
    except UnbuildableManeuver:
        assert not built, f"{effect!r} is refused"
    else:
        assert built, f"{effect!r} decodes, but is listed as not built"


# ===========================================================================
# A Block that does something besides blocking
# ===========================================================================

def test_ravels_grappling_block_takes_hold_of_the_man_it_stops():
    """Ravel's own Grappling Block ("Grab One Limb, Block", as imported): her
    Block is rolled at its +1 OCV (`reactive.martial`), and when it stops
    the blow she has hold of him (a Grab, 6E2 p.67). Through run_phase."""
    session = _session(_ravel(), _mark())
    chooser = _Script(ravel=[_kind("block")],
                      mark=[_kind("strike", target_id="ravel")])
    after = _play(session, chooser, roller=_AlwaysLow(seed=1), phases=12)
    assert _row(after, kind="block")["success"] is True
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")


def test_a_defensive_throw_puts_the_man_it_stops_down():
    throw = _maneuver("c-dthrow2", "Defensive Throw", "Block, Target Falls",
                      ocv="+1", dcv="+1", dc=0, add_str=False)
    doc = _doc_with("Ravel", [], runs=True)
    # In place of her Grappling Block, which is as good a Block (+1/+1) and
    # would be the one she raised (`reactive.martial.block_maneuver`).
    doc["martial_arts"] = [throw]
    after = _with_block(_session(_built(doc, "ravel", "a"), _mark()))
    assert _row(after, kind="block")["success"] is True
    assert PRONE in statuses_for(after, "mark")
    assert Grab.is_grabbed(after, "mark") == (False, None)
