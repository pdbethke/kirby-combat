"""Lazer Aborts to Dodge — 6E2 p.24, reproduced.

This is a conformance check that happens to be readable: the rulebook's own
worked examples are restated below, the engine's turn loop (`run_phase`) is
driven through them, and every Segment the book names is ASSERTED against
what the engine did. If the engine ever stops agreeing with the book, this
script exits non-zero and `tests/test_examples.py` fails with it.

THE BOOK'S SCENARIOS (6E2 p.24), PARAPHRASED — this project ships no rules
text; open your own copy:

  1. Lazer (SPD 5: Phases in Segments 3, 5, 8, 10 and 12) is attacked in
     Segment 6 and Aborts to Dodge. That uses up his Segment 8 Phase: in
     Segment 8 he can do nothing, though he still has the Dodge's DCV. He
     acts again in Segment 10.
  2. Attacked in Segment 5 BEFORE his DEX comes up, he still has his
     Segment 5 Phase, so the Abort spends that one instead. He keeps
     Segment 8.
  3. Holding a Phase when he's attacked, he Aborts with the Held Action and
     loses no further Phase. (The book's example is a Half Move followed by
     a Held Half Phase; here he Holds his whole Phase. The clause is the
     same one: "Holding a Phase or Half Phase".)
  4. A DEX 20, SPD 4 character (Phases 3, 6, 9, 12) Aborts his Segment 3
     Phase in Segment 2, to Block. He can do nothing in Segment 3, and
     attacks in Segment 6.
  5. Once a character has used his Phase in a Segment, he can't Abort
     again until the next Segment: Lazer attacks in Segment 5 and is
     attacked back the same Segment, and is not allowed to Abort.

The windows are fixed when the Abort is declared and travel on the
`AbortDeclared` event, so a fight replayed from its log expires them at the
same moments as the fight that ran.

Run with:
    .venv/bin/python examples/raw_lazer.py
"""
from __future__ import annotations

from kirby_dice import RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def _attack(source_id: str, *, melee: bool) -> AttackPower:
    range_m = 0 if melee else 100
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=4,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=range_m,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, source_id=source_id, is_ranged=range_m > 0,
    )


def _man(id_: str, *, side: Side, spd: int, dex: int, melee: bool = False):
    # STUN and BODY high enough that nobody is knocked out mid-example:
    # the examples are about the clock, not the damage.
    return synthetic_combatant(
        id=id_, name=id_, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=spd, dex=dex, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=20, ed=20, rpd=0, red=0, md=3, power_defense=0, flash_defense=0,
        max_stun=200, max_body=50, max_end=200,
        current_stun=200, current_body=50, current_end=200,
        side=side, attacks=[_attack(f"{id_}-atk", melee=melee)],
    )


class Script:
    """Each man's choices, by Segment.

    ``own``: (actor, segment) -> kind for his own Phase ("attack" is aimed at
    his opponent). Anything unscripted is a Set, or a Strike for a man with
    no ranged attack to Set with.
    ``react``: (defender, segment) -> the Abort he takes when attacked.
    Every own Phase and every Abort question is logged in ``asked``.
    """

    def __init__(self, opponent: dict[str, str], *, own, react):
        self.opponent, self.own, self.react = opponent, own, react
        self.asked: list[tuple[str, int, str]] = []

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, situation):
        actor = situation.actor.id
        # The live session's clock: `run_phase` advances the Segment itself.
        seg = situation.session.timeline.segment
        oot = getattr(situation, "out_of_turn", None)
        if oot is None:
            self.asked.append((actor, seg, "own"))
            kind = self.own.get((actor, seg))
            if kind is None:
                # Idle: a Set where it's offered, otherwise a plain Strike.
                # Neither changes anybody's DCV, so neither can disturb the
                # clock being measured.
                kinds = {o.kind for o in situation.menu}
                kind = "set" if "set" in kinds else "strike"
            for offer in situation.menu:
                if offer.kind == kind and (
                        kind not in ("attack", "strike")
                        or offer.target_id == self.opponent[actor]):
                    return offer.action_id
            raise AssertionError(f"{actor}: no {kind!r} in {situation.action_ids}")
        self.asked.append((actor, seg, oot.reason.value))
        if oot.reason.value == "abort":
            kind = self.react.get((actor, seg), "no_abort")
            for offer in situation.menu:
                if offer.kind == kind:
                    return offer.action_id
            raise AssertionError(f"{actor}: no {kind!r} in {situation.action_ids}")
        return situation.menu[0].action_id


def _fight(a, b, *, own, react, until: tuple[int, int]):
    """Run the loop from the start of the fight until (turn, segment) is past."""
    session = CombatSession.create(
        id="s", combatants=[a, b], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=11),
    ).start()
    ref = [Encounter(id="e", turn=1, segment=12, sessions=[session])]
    script = Script({a.id: b.id, b.id: a.id}, own=own, react=react)
    events = []
    roller = RandomRoller(seed=11)
    while (ref[0].turn, ref[0].segment) <= until:
        result = run_phase(ref[0], script, roller=roller, on_unresolvable="raise")
        events.extend(result.events)
        ref[0] = result.encounter
    return script, events


def _abort(events, who):
    return [e for e in events if e.kind == "AbortDeclared" and e.combatant_id == who]


def _spent(events, who, segment):
    return [e for e in events if e.kind == "PhaseSpent" and e.combatant_id == who
            and e.turn == 2 and e.segment == segment]


def _shots_at(events, who, segment):
    """Attacks resolved against `who` in Turn 2's `segment`."""
    out, seg = [], None
    for e in events:
        if e.kind == "SegmentAdvanced" and e.to_turn == 2:
            seg = e.to_segment
        if (seg == segment and e.kind == "ActionResolved"
                and e.result_payload.get("target_id") == who
                and "hit" in e.result_payload):
            out.append(e)
    return out


def main() -> None:
    # ── 1. Attacked in Segment 6 ────────────────────────────────────────
    rule("1. Lazer (SPD 5) is attacked in Segment 6 and Aborts to Dodge")
    lazer = _man("lazer", side=HEROES, spd=5, dex=10)
    foe = _man("foe", side=VILLAINS, spd=6, dex=30)      # Phases 2,4,6,8,10,12
    script, events = _fight(
        lazer, foe,
        own={("foe", 6): "attack", ("foe", 8): "attack"},
        react={("lazer", 6): "dodge"},
        until=(2, 10),
    )
    (abort,) = _abort(events, "lazer")
    print(f"\n  Abort declared: gives up Segment {abort.aborted_segment}, "
          f"Dodge lasts until Segment {abort.bonus_until_segment}")
    assert (abort.aborted_turn, abort.aborted_segment) == (2, 8)

    (spent8,) = _spent(events, "lazer", 8)
    print(f"  Segment 8:  Lazer's Phase is spent, reason {spent8.reason!r}")
    assert spent8.reason == "aborted"
    assert ("lazer", 8, "own") not in script.asked

    (shot8,) = _shots_at(events, "lazer", 8)
    print(f"  Segment 8:  the foe fires again; Lazer's DCV is "
          f"{shot8.result_payload['target_dcv']} (5, +3 for the Dodge)")
    assert shot8.result_payload["target_dcv"] == 5 + 3
    assert ("lazer", 8, "abort") not in script.asked     # locked out

    print("  Segment 10: Lazer acts again")
    assert ("lazer", 10, "own") in script.asked

    # ── 2. Attacked in Segment 5, before his DEX ───────────────────────
    rule("2. Attacked in Segment 5 before his DEX comes up")
    lazer = _man("lazer", side=HEROES, spd=5, dex=10)
    foe = _man("foe", side=VILLAINS, spd=5, dex=30)      # also 3,5,8,10,12
    script, events = _fight(
        lazer, foe,
        own={("foe", 5): "attack"},
        react={("lazer", 5): "dodge"},
        until=(2, 8),
    )
    (abort,) = _abort(events, "lazer")
    (spent5,) = _spent(events, "lazer", 5)
    print(f"\n  Abort gives up Segment {abort.aborted_segment}; "
          f"his Segment 5 Phase is spent, reason {spent5.reason!r}")
    assert (abort.aborted_turn, abort.aborted_segment) == (2, 5)
    assert spent5.reason == "aborted"
    print("  Segment 8:  Lazer acts, as the book says")
    assert ("lazer", 8, "own") in script.asked

    # ── 3. Holding his Phase ───────────────────────────────────────────
    rule("3. Holding his Phase, he Aborts with the Held Action")
    lazer = _man("lazer", side=HEROES, spd=5, dex=30)
    foe = _man("foe", side=VILLAINS, spd=5, dex=10)
    script, events = _fight(
        lazer, foe,
        own={("lazer", 5): "hold", ("foe", 5): "attack"},
        react={("lazer", 5): "dodge"},
        until=(2, 8),
    )
    (abort,) = _abort(events, "lazer")
    print(f"\n  Abort uses the Held Phase (Segment {abort.aborted_segment}); "
          f"Dodge lasts until Segment {abort.bonus_until_segment}")
    assert (abort.aborted_turn, abort.aborted_segment) == (2, 5)
    print("  Segment 8:  Lazer acts; no further Phase was lost")
    assert not _spent(events, "lazer", 8) or _spent(events, "lazer", 8)[0].reason != "aborted"
    assert ("lazer", 8, "own") in script.asked

    # ── 4. Abort to Block a Segment early ──────────────────────────────
    rule("4. DEX 20, SPD 4: Aborts his Segment 3 Phase in Segment 2, to Block")
    hero = _man("hero", side=HEROES, spd=4, dex=20, melee=True)  # 3,6,9,12
    foe = _man("foe", side=VILLAINS, spd=6, dex=30, melee=True)  # 2,4,6,...
    script, events = _fight(
        hero, foe,
        own={("foe", 2): "attack", ("hero", 6): "attack"},
        react={("hero", 2): "block"},
        until=(2, 6),
    )
    (abort,) = _abort(events, "hero")
    (spent3,) = _spent(events, "hero", 3)
    print(f"\n  Block declared in Segment 2; gives up Segment "
          f"{abort.aborted_segment}; Segment 3 Phase spent, reason {spent3.reason!r}")
    assert (abort.aborted_turn, abort.aborted_segment) == (2, 3)
    assert spent3.reason == "aborted"
    hero_attacks = [e for e in events if e.kind == "ActionResolved"
                    and e.result_payload.get("power_source_id") == "hero-atk"]
    print(f"  Segment 6:  he attacks ({len(hero_attacks)} attack resolved)")
    assert ("hero", 6, "own") in script.asked and len(hero_attacks) == 1

    # ── 5. No Abort after acting ───────────────────────────────────────
    rule("5. Lazer attacks in Segment 5, then is attacked back the same Segment")
    lazer = _man("lazer", side=HEROES, spd=5, dex=30)
    defender = _man("defender", side=VILLAINS, spd=5, dex=10)
    script, events = _fight(
        lazer, defender,
        own={("lazer", 5): "attack", ("defender", 5): "attack"},
        react={("lazer", 5): "dodge"},
        until=(2, 5),
    )
    print("\n  Lazer is never asked whether he Aborts, and no Abort is recorded")
    assert ("lazer", 5, "abort") not in script.asked
    assert not _abort(events, "lazer")

    rule("END — every Segment 6E2 p.24 names, confirmed through the turn loop.")


if __name__ == "__main__":
    main()
