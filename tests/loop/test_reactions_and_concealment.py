"""Acting out of turn, Blocks that stop blows, Hides that end, Images that draw fire.

Every test here drives `run_phase` or `resolve_chosen` --- the live path --- and
fails on the engine before this port: the out-of-turn Abort did not exist, a
Block stopped nothing, a Held Action was never used, a Hide never ended, an
Image was never a target, and a Martial Dodge bought +3 like anybody's.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from conftest import blast, encounter_of, fighter  # tests/loop/conftest.py
from kirby_combat.actions.images import Images
from kirby_combat.concealment import HIDE_BROKEN, hidden_from
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


class Ones(RandomRoller):
    """Every die shows 1: every Attack Roll and Block hits, every DEX and PER
    Roll is made by the most it can be."""

    def roll_dice(self, n, sides=6):
        return [1] * n


class Script:
    """A chooser told what each man does, on his Phase and out of it.

    ``own``: actor id -> (kind, target id or None) for his own Phase.
    ``react``: defender id -> the Abort he takes when attacked.
    ``held``: holder id -> (kind, target id) when asked about his Held Action.
    Anything unscripted takes the first offer (do nothing, out of turn).
    """

    def __init__(self, own=None, react=None, held=None):
        self.own, self.react, self.held = own or {}, react or {}, held or {}
        self.asked: list[tuple[str, str | None]] = []

    def choose(self, situation):
        actor = situation.actor.id
        oot = getattr(situation, "out_of_turn", None)
        self.asked.append((actor, oot.reason.value if oot else None))
        if oot is None:
            want = self.own.get(actor)
        elif oot.reason.value == "abort":
            want = (self.react[actor], None) if actor in self.react else None
        else:
            want = self.held.get(actor)
        if want is not None:
            kind, target = want
            for offer in situation.menu:
                if offer.kind == kind and (target is None or offer.target_id == target):
                    return offer.action_id
            raise AssertionError(f"{actor}: no {kind!r} offer in {situation.action_ids}")
        return situation.menu[0].action_id


def _resolved(events, **match):
    out = []
    for e in events:
        p = getattr(e, "result_payload", None)
        if isinstance(p, dict) and all(p.get(k) == v for k, v in match.items()):
            out.append(e)
    return out


def _attacks_on(events, target):
    return [e for e in events if getattr(e, "kind", "") == "ActionResolved"
            and e.result_payload.get("target_id") == target
            and "hit" in e.result_payload]


def _martial(c, *maneuvers):
    """Give a synthetic fighter bought maneuvers, in HD's own columns."""
    c.hero.martial_arts = [
        SimpleNamespace(xmlid="MANEUVER", effect=effect, ocv=ocv, dcv=dcv,
                        display=name, category="Hand To Hand", damage_type=0,
                        id=f"mv-{i}", phase="1/2", dc=0, add_str=False)
        for i, (name, effect, ocv, dcv) in enumerate(maneuvers)
    ]
    return c


MARTIAL_DODGE = ("Martial Dodge", "Dodge, Affects All Attacks, Abort", "--", "+5")
MARTIAL_BLOCK = ("Martial Block", "Block, Abort", "+2", "+2")


def _duel(attacker=None, defender=None, *, melee=False):
    a = attacker or fighter("a", side=HEROES, dex=30)
    d = defender or fighter("d", side=VILLAINS, dex=10)
    if melee:
        a.attacks[:] = [blast("a-fist", dice=6, range_m=0)]
    return encounter_of(a, d)


# ── the out-of-turn Abort (6E2 p.24) ─────────────────────────────────────────

def test_the_target_is_asked_and_his_dodge_meets_the_shot():
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "dodge"})
    result = run_phase(_duel(), chooser, roller=RandomRoller(seed=3),
                       on_unresolvable="raise")

    assert ("d", "abort") in chooser.asked
    aborts = [e for e in result.events if e.kind == "AbortDeclared"]
    assert [(e.combatant_id, e.to_action) for e in aborts] == [("d", "dodge")]
    shot = _attacks_on(result.events, "d")[-1]
    assert result.events.index(aborts[0]) < result.events.index(shot)
    assert shot.result_payload["target_dcv"] == 5 + 3          # 6E2 p.55


def test_the_abort_costs_him_the_phase_he_had_not_yet_used():
    """6E2 p.24: attacked in Segment 5 before his DEX came up, Lazer "would
    instead have lost his Action in Segment 5"."""
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "dodge"})
    first = run_phase(_duel(), chooser, roller=RandomRoller(seed=3),
                      on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=RandomRoller(seed=4),
                       on_unresolvable="raise")
    spent = [e for e in second.events if e.kind == "PhaseSpent"
             and e.combatant_id == "d"]
    assert spent and spent[0].reason == "aborted"


def test_declining_keeps_his_phase_and_his_dcv():
    chooser = Script(own={"a": ("attack", "d")})
    result = run_phase(_duel(), chooser, roller=RandomRoller(seed=3),
                       on_unresolvable="raise")
    assert not [e for e in result.events if e.kind == "AbortDeclared"]
    assert _attacks_on(result.events, "d")[-1].result_payload["target_dcv"] == 5


def test_no_block_is_offered_against_a_bullet():
    """6E2 p.59: Blocks affect Ranged attacks only with the GM's permission."""
    seen = {}

    class Peek(Script):
        def choose(self, situation):
            oot = getattr(situation, "out_of_turn", None)
            if oot is not None:
                seen["kinds"] = {o.kind for o in situation.menu}
            return super().choose(situation)

    run_phase(_duel(), Peek(own={"a": ("attack", "d")}),
              roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert seen["kinds"] == {"no_abort", "dodge"}


def test_a_stunned_man_is_not_asked():
    """6E2 p.106: "he cannot even Abort to a defensive Action"."""
    from kirby_combat.session.events import ActionDeclared

    enc = _duel()
    s = enc.sessions[0]
    decl = ActionDeclared(
        id="x", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_combatant("a"),
        combatant_id="a", action_type="attack", targets=["d"], parameters={})
    s = apply_event(s, decl)
    s = apply_event(s, ActionResolved(
        id="y", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=decl.timestamp, author=make_author_combatant("a"),
        declaration_event_id="x",
        result_payload={"kind": "attack", "hit": True, "target_id": "d",
                        "stun_dealt": 0, "body_dealt": 0,
                        "status_changes": ["Stunned"], "segment": 12}))
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "dodge"})
    run_phase(replace(enc, sessions=[s]), chooser, roller=RandomRoller(seed=3),
              on_unresolvable="raise")
    assert ("d", "abort") not in chooser.asked


# ── Martial Dodge feeds the plain Dodge (6E2 p.93) ──────────────────────────

def test_a_martial_dodge_is_worth_five():
    d = _martial(fighter("d", side=VILLAINS, dex=40), MARTIAL_DODGE)
    chooser = Script(own={"d": ("dodge", None), "a": ("attack", "d")})
    first = run_phase(_duel(defender=d), chooser, roller=RandomRoller(seed=3),
                      on_unresolvable="raise")
    assert first.actor_id == "d"
    second = run_phase(first.encounter, chooser, roller=RandomRoller(seed=4),
                       on_unresolvable="raise")
    assert _attacks_on(second.events, "d")[-1].result_payload["target_dcv"] == 5 + 5


# ── a Block stops the blow (6E2 p.59-60) ────────────────────────────────────

def test_a_block_stops_the_punch():
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "block"})
    result = run_phase(_duel(melee=True), chooser, roller=Ones(seed=1),
                       on_unresolvable="raise")
    blocks = _resolved(result.events, kind="block")
    assert blocks and blocks[0].result_payload["success"] is True
    blow = _attacks_on(result.events, "d")[-1].result_payload
    assert blow["blocked"] is True and blow["stun_dealt"] == 0
    assert result.session.combatants["d"].current_stun == 40
    assert any(e.kind == "BlockPriorityGained" for e in result.events)


def test_a_missed_block_lets_the_attack_roll_and_ends_the_blocking():
    """6E2 p.59: "If the Block misses, the attack doesn't automatically hit
    the Blocker; the attacker still has to succeed with his Attack Roll";
    p.60: "If the character misses any of his Blocks, he cannot Block
    further attacks"."""
    from kirby_combat.synthetic import synthetic_combatant

    brute = synthetic_combatant(
        id="a", name="a", ocv=30, dcv=5, spd=4, dex=30, str_=15, con=18,
        pd=4, ed=4, max_stun=40, max_body=12, max_end=40, side=HEROES,
        attacks=[blast("a-fist", dice=6, range_m=0)])
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "block"})
    result = run_phase(_duel(attacker=brute), chooser, roller=Ones(seed=1),
                       on_unresolvable="raise")
    blocks = _resolved(result.events, kind="block")
    assert [b.result_payload["success"] for b in blocks] == [False]
    blow = _attacks_on(result.events, "d")[-1].result_payload
    assert blow["hit"] is True and blow["stun_dealt"] > 0

    again = resolve_chosen(
        result.session, result.session.combatants["a"],
        LegalAction(action_id="attack:d:a-fist", kind="attack", target_id="d",
                    power_xmlid="ENERGYBLAST", power_name="Blast", summary="",
                    _attack_view=brute.attacks[0]),
        template=TEMPLATE, roller=Ones(seed=1))
    assert not _resolved(again.events, kind="block")


def test_each_further_block_is_at_minus_two_and_a_martial_block_adds_its_ocv():
    """6E2 p.60's cumulative -2; 6E2 p.93's Martial Block OCV +2, DCV +2."""
    from kirby_combat.actions.reactive.block import Block

    enc = _duel(defender=_martial(fighter("d", side=VILLAINS, dex=10), MARTIAL_BLOCK),
                melee=True)
    s, _ = Block.declare(enc.sessions[0], "d")
    punch = LegalAction(action_id="attack:d:a-fist", kind="attack", target_id="d",
                        power_xmlid="ENERGYBLAST", power_name="Blast", summary="",
                        _attack_view=enc.sessions[0].combatants["a"].attacks[0])
    first = resolve_chosen(s, s.combatants["a"], punch, template=TEMPLATE, roller=Ones(seed=1))
    second = resolve_chosen(first.session, s.combatants["a"], punch,
                            template=TEMPLATE, roller=Ones(seed=1))
    ocvs = [b.result_payload["blocker_ocv"]
            for b in _resolved(second.session.event_log, kind="block")]
    assert ocvs == [9 + 2, 9 + 2 - 2]


def test_a_block_on_his_own_phase_is_rolled_when_the_blow_comes():
    """The `block` offer declares; nothing is rolled until an attack arrives."""
    chooser = Script(own={"d": ("block", "a"), "a": ("attack", "d")})
    d = fighter("d", side=VILLAINS, dex=40)
    first = run_phase(_duel(defender=d, melee=True), chooser, roller=Ones(seed=1),
                      on_unresolvable="raise")
    assert first.actor_id == "d"
    assert not _resolved(first.events, kind="block")
    second = run_phase(first.encounter, chooser, roller=Ones(seed=1),
                       on_unresolvable="raise")
    assert _resolved(second.events, kind="block")[0].result_payload["success"] is True
    assert _attacks_on(second.events, "d")[-1].result_payload["stun_dealt"] == 0


# ── Held Actions (6E2 p.22) ─────────────────────────────────────────────────

def _holding_encounter():
    h = fighter("h", side=HEROES, dex=30)
    x = fighter("x", side=VILLAINS, dex=10)
    chooser = Script(own={"h": ("hold", None)})
    first = run_phase(encounter_of(h, x), chooser, roller=Ones(seed=1),
                      on_unresolvable="raise")
    assert first.actor_id == "h" and first.kind == "hold"
    return first.encounter


def test_a_held_action_is_used_before_the_next_mans_phase():
    chooser = Script(held={"h": ("attack", "x")}, own={"x": ("set", None)})
    result = run_phase(_holding_encounter(), chooser, roller=Ones(seed=1),
                       on_unresolvable="raise")
    assert result.actor_id == "x"
    released = [e for e in result.events if e.kind == "HeldActionReleased"]
    shot = _attacks_on(result.events, "x")
    xs_own = [e for e in result.events if e.kind == "ActionDeclared"
              and e.combatant_id == "x"]
    assert released and shot and xs_own
    assert result.events.index(shot[0]) < result.events.index(xs_own[0])


def test_a_held_action_lapses_when_his_next_phase_segment_begins():
    """6E2 p.22: "he loses any Held Action when the next Segment in which he
    has a Phase begins"."""
    enc = _holding_encounter()
    chooser = Script()
    lapsed = []
    for _ in range(6):
        result = run_phase(enc, chooser, roller=Ones(seed=1), on_unresolvable="raise")
        enc = result.encounter
        lapsed += [e for e in result.events if e.kind == "HeldActionReleased"
                   and e.trigger_observed == "phase_expired"]
        if lapsed:
            break
    assert lapsed
    assert (enc.sessions[0].timeline.turn, enc.sessions[0].timeline.segment) == (2, 3)


# ── Hide ends on an attack ──────────────────────────────────────────────────

def test_attacking_out_of_hiding_gives_him_away():
    enc = _duel()
    s = enc.sessions[0]
    s = apply_event(s, ActionResolved(
        id="hide", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_combatant("a"),
        declaration_event_id="", result_payload={"kind": "hide", "unseen_by": ["d"]}))
    assert hidden_from(s, "d") == {"a"}
    result = run_phase(replace(enc, sessions=[s]), Script(own={"a": ("attack", "d")}),
                       roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert _resolved(result.events, kind=HIDE_BROKEN)
    assert hidden_from(result.session, "d") == set()


def test_setting_does_not_give_him_away():
    enc = _duel()
    s = enc.sessions[0]
    s = apply_event(s, ActionResolved(
        id="hide", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_combatant("a"),
        declaration_event_id="", result_payload={"kind": "hide", "unseen_by": ["d"]}))
    result = run_phase(replace(enc, sessions=[s]), Script(own={"a": ("set", "d")}),
                       roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert hidden_from(result.session, "d") == {"a"}


# ── Image decoys draw fire (6E1 p.238-239) ──────────────────────────────────

def test_an_image_draws_the_shot_and_the_shooter_sees_through_it():
    c = fighter("c", side=VILLAINS, dex=10)
    o = fighter("o", side=HEROES, dex=30)
    enc = encounter_of(c, o)
    s, placed = Images.place(enc.sessions[0], caster_id="c", position=(0.0, 0.0, 0.0),
                             sense_groups=["SIGHTGROUP"], roller=Ones(seed=1))
    assert placed.hit
    chooser = Script(own={"o": ("attack", placed.image_id)})
    result = run_phase(replace(enc, sessions=[s]), chooser, roller=Ones(seed=1),
                       on_unresolvable="raise")
    shot = _resolved(result.events, into_the_void=True)
    assert shot and shot[0].result_payload["target_id"] == placed.image_id
    assert result.session.combatants["c"].current_stun == 40
    assert Images.disbelieved_by(result.session, placed.image_id, "o")
    # Seen through: it is no longer on his menu, and still stands.
    assert Images.get(result.session, placed.image_id) is not None


# ── with Presence and Rage (6E2 p.25, p.139; 6E1 p.424-425) ─────────────────

def _rage(session, who, target):
    from kirby_combat.session.events import RageRolled, make_author_engine

    return apply_event(session, RageRolled(
        id=f"rage-{who}", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=session.event_log[-1].timestamp, author=make_author_engine(),
        combatant_id=who, complication_id="rage-in combat", roll_kind="go",
        roll=3, target_number=14, succeeded=True, berserk=False,
        target_id=target, reason="in_combat",
        turn=session.timeline.turn, segment=session.timeline.segment,
    ))


class HeldPeek(Script):
    """Records the menus a holder is shown out of turn."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.held_menus: list[set] = []

    def choose(self, situation):
        oot = getattr(situation, "out_of_turn", None)
        if oot is not None and oot.reason.value == "held_action":
            self.held_menus.append(list(situation.menu))
        return super().choose(situation)


def _three_with_a_holder():
    h = fighter("h", side=HEROES, dex=30)
    x = fighter("x", side=VILLAINS, dex=10)
    y = fighter("y", side=VILLAINS, dex=5)
    first = run_phase(encounter_of(h, x, y), Script(own={"h": ("hold", None)}),
                      roller=Ones(seed=1), on_unresolvable="raise")
    assert first.kind == "hold"
    return first.encounter


def test_a_raging_man_is_not_asked_to_abort():
    """6E1 p.424-425: he does not defend himself; an Abort is only ever to a
    defensive Action (6E2 p.23)."""
    enc = _duel()
    s = _rage(enc.sessions[0], "d", "a")
    chooser = Script(own={"a": ("attack", "d")}, react={"d": "dodge"})
    result = run_phase(replace(enc, sessions=[s]), chooser,
                       roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert ("d", "abort") not in chooser.asked
    assert not [e for e in result.events if e.kind == "AbortDeclared"]


def test_a_raging_holder_is_offered_only_his_target_and_no_defence():
    enc = _three_with_a_holder()
    s = _rage(enc.sessions[0], "h", "y")
    chooser = HeldPeek()
    run_phase(replace(enc, sessions=[s]), chooser, roller=Ones(seed=1),
              on_unresolvable="raise")
    menu = chooser.held_menus[0]
    kinds = {a.kind for a in menu}
    assert not kinds & {"dodge", "block"}, kinds
    assert {a.target_id for a in menu if a.target_id} <= {"y"}


def test_a_very_impressed_holder_has_only_half_phase_actions():
    """6E2 p.139: PRE+10 leaves him a Half Phase Action --- from a Hold too."""
    from kirby_combat.action_time import FULL_PHASE_KINDS
    from kirby_combat.pre_attacks.presence_effects import PresenceEffects

    enc = _three_with_a_holder()
    s, _ = PresenceEffects.apply(enc.sessions[0], target_id="h", attacker_id="x",
                                 tier="very_impressed")
    chooser = HeldPeek()
    run_phase(replace(enc, sessions=[s]), chooser, roller=Ones(seed=1),
              on_unresolvable="raise")
    kinds = {a.kind for a in chooser.held_menus[0]}
    assert "attack" in kinds
    assert not kinds & FULL_PHASE_KINDS, kinds


def test_a_presence_attack_from_a_hold_does_not_use_it():
    """6E2 p.25: a Presence Attack takes No Time. He makes it out of turn and
    is still Holding --- once a Phase --- and the free attack does not leak
    into his own next Phase."""
    from kirby_combat.loop.reactions import usable_hold
    from kirby_combat.pre_attacks.in_the_phase import PRESENCE_KINDS

    enc = _three_with_a_holder()
    chooser = HeldPeek(held={"h": ("presence_attack", "x")})
    result = run_phase(enc, chooser, roller=Ones(seed=1), on_unresolvable="raise")
    assert [e for e in result.events if e.kind == "ActionDeclared"
            and e.combatant_id == "h" and e.action_type in PRESENCE_KINDS]
    assert not [e for e in result.events if e.kind == "HeldActionReleased"]
    assert usable_hold(result.session, "h") is not None

    # Asked again before the next man: no second free Presence Attack.
    chooser.held = {}
    again = run_phase(result.encounter, chooser, roller=Ones(seed=1),
                      on_unresolvable="raise")
    assert not {a.kind for a in chooser.held_menus[-1]} & PRESENCE_KINDS

    # His own next Phase (Turn 2, Segment 3) offers it again.
    enc, own_menus = again.encounter, []

    class Own(Script):
        def choose(self, situation):
            if situation.actor.id == "h" and situation.out_of_turn is None:
                own_menus.append({a.kind for a in situation.menu})
            return super().choose(situation)

    for _ in range(8):
        step = run_phase(enc, Own(), roller=Ones(seed=1), on_unresolvable="raise")
        enc = step.encounter
        if own_menus:
            break
    assert own_menus and own_menus[0] & PRESENCE_KINDS
