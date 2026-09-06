"""Four armies, one engine, no database — a fight driven to its decision.

WHAT THIS DEMONSTRATES. The engine now owns the turn loop. Whose Phase it is
(6E2 p.18), who acts first (6E2 p.19-21), what they may legally do, what that
does, when the Turn wraps and the free Post-Segment 12 Recovery fires (6E2
p.131), and when the fight is decided (6E1 p.421) are all answered here,
inside `kirby-combat`, with nothing but its leaf packages installed.

Until 2026-09-06 all of that lived in a web service's driver: 258 lines of
database-bound "whose Phase is it", 38 more of SQL-backed "is it over", and a
1,070-line dispatcher. A fight could not be run without a container.

SIDES, AND WHY `None` MEANS "THEIR OWN SIDE". `side` is a free string with no
cap on how many there are. The tempting default -- everyone unlabelled shares
one "default" side -- is what a database column does, and it breaks the
free-for-all silently: every fighter would be on one team, "at most one side
still standing" would be true before the first punch, and the fight would end
at Phase 0 with a winner. Treating an absent side as a side of one makes the
team battle and the free-for-all the same rule. Both are shown below.

THE CHOOSER IS THE ONLY THING THE ENGINE DOES NOT DECIDE. `FirstLegalChooser`
is deterministic and deliberately not a tactic -- it exists so a fight can be
driven without anything clever in the seat. `TacticChooser` picks by role and
doctrine. Anything that consults a model is a chooser written outside this
engine; the engine never learns what is on the other end.

WHAT A NETWORKED CONSUMER DOES WITH THIS. Every function returns new state
plus the events that produced it. A web service persists and broadcasts those
events and decides nothing -- it extrudes the loop rather than owning it.

Exercises:
  - run_encounter / run_phase / next_actor_id
  - FirstLegalChooser, TacticChooser, and a hand-written chooser
  - side_of / standing_sides / last_side_standing, with four armies
  - a caller-supplied stop condition replacing last-side-standing
  - registered_kinds() — the honest size of what the engine can execute
"""
from __future__ import annotations

import dataclasses

from kirby_combat.encounter import Encounter
from kirby_combat.loop import (
    FirstLegalChooser, PhaseSituation, Roster, TacticChooser, Verdict,
    next_actor_id, registered_kinds, run_encounter, run_phase,
)
from kirby_combat.side import Side
from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

ARMIES = ("Crimson", "Azure", "Verdant", "Golden")


def _blast(source_id: str) -> AttackPower:
    """``source_id`` is required, not decorative: an action_id is built from
    the source power's object id. Falling back to xmlid+name is what made
    630 corpus objects share a token, silently."""
    return AttackPower(
        xmlid="ENERGYBLAST", name="Volley", damage_dice=7,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=150,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id,
    )


# ── A minimal LoadedHero stand-in ────────────────────────────────────────
#
# `enumerate_actions` needs a BUILD-BACKED combatant: it reads `actor.hero`
# at 21 sites for powers, skills and RUNNING. A flat `StatBlockCombatant`
# raises a `TypeError` saying so -- which is a real limitation of the
# enumerator, inherited from the driver it was carved out of, and named at
# the boundary rather than hidden behind a shorter menu.
#
# Built locally rather than importing the test fixture: examples run
# standalone (see `tests/test_examples.py`) and must not reach into `tests/`.
# Same approach as `examples/one_turn.py`.
class _MinimalHero:
    def __init__(self, name: str, chars: dict[str, int]) -> None:
        self.name = name
        self.template_name = "example.hdt"
        self._chars = chars
        self.powers: list = []
        self.skills: list = []
        self.perks: list = []
        self.talents: list = []
        self.complications: list = []
        self.equipment: list = []

    def characteristic_value(self, xmlid: str) -> int:
        return self._chars.get(xmlid.upper(), 0)

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        return self.characteristic_value(xmlid)


@dataclasses.dataclass
class _Soldier(HeroCombatant):
    """A HeroCombatant whose attacks are stated rather than derived.

    `HeroCombatant.attacks` normally computes from `hero.powers`; this
    example carries one Volley directly so the fight is about the loop
    rather than about anyone's build.

    A DATACLASS, AND THAT IS LOAD-BEARING. The engine replaces a combatant
    on every vitals change -- `dataclasses.replace` rebuilds through
    `__init__` and carries FIELDS ONLY. A plain subclass holding `_attacks`
    as an instance attribute loses its weapons the first time it takes a
    hit, and a `__init__` that does not accept every inherited field fails
    the replace outright. The same trap cost `tests/fixtures/
    synthetic_hero.py` its attacks and resistant defenses, silently, on
    every movement END spend.
    """

    _attacks: list = dataclasses.field(default_factory=list)

    @property
    def attacks(self):
        return self._attacks

    @property
    def defenses(self):
        return []


def _soldier(id: str, side: Side | None, dex: int) -> HeroCombatant:
    hero = _MinimalHero(id, {
        "OCV": 9, "DCV": 5, "OMCV": 5, "DMCV": 5, "SPD": 4, "DEX": dex,
        "EGO": 14, "STR": 15, "CON": 18, "PRE": 15, "REC": 6, "INT": 13,
        "PD": 4, "ED": 4, "STUN": 35, "BODY": 12, "END": 40, "RUNNING": 12,
    })
    state = HeroCombatState(current_stun=35, current_body=12, current_end=40)
    return _Soldier(
        id=id, hero=hero, state=state, side=side,
        _attacks=[_blast(f"{id}-eb")],
    )


def _encounter(roster, seed: int) -> Encounter:
    session = CombatSession.create(
        id="field", combatants=roster, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=seed),
    ).start()
    # Combat begins on Segment 12 (6E2 p.20, "BEGINNING COMBAT").
    return Encounter(id="battle", turn=1, segment=12, sessions=[session])


def _report(title: str, result) -> None:
    print(f"\n  {title}")
    print(f"    decided : {result.complete}")
    print(f"    winner  : {result.winner}")
    print(f"    turns   : {result.turns}   phases: {result.phases}")
    if result.skipped_kinds:
        # Never silent: kinds the engine cannot yet execute are counted.
        print(f"    skipped : {result.skipped_kinds}")
    if result.notes:
        print(f"    notes   : {'; '.join(result.notes)}")
    standing = Roster(result.encounter.sessions[0]).standing
    print(f"    standing: { {s.name: len(v) for s, v in standing.items()} }")


def main() -> None:
    print("THE BATTLE OF FOUR ARMIES — no database, no web service.")
    print(f"\n  The engine can currently execute {len(registered_kinds())} "
          f"action kinds: {', '.join(sorted(registered_kinds()))}.")
    print("  `enumerate_actions` can OFFER 52. The gap is counted, not hidden:")
    print("  an unresolvable pick is either raised or recorded as a skip.")

    # ---- Four armies, three soldiers each ----
    roster = [
        _soldier(f"{army}-{n + 1}", Side.named(army), 24 - n)
        for army in ARMIES
        for n in range(3)
    ]
    result = run_encounter(
        _encounter(roster, seed=5), FirstLegalChooser(),
        roller=RandomRoller(seed=5), on_unresolvable="skip", max_turns=30,
    )
    _report("Four armies, twelve soldiers, last army standing:", result)

    # ---- The same rule, nobody labelled: an N-way free-for-all ----
    brawl = [_soldier(name, None, 24 - i) for i, name in enumerate("ABCDE")]
    result = run_encounter(
        _encounter(brawl, seed=11), FirstLegalChooser(),
        roller=RandomRoller(seed=11), on_unresolvable="skip", max_turns=30,
    )
    _report("Five unlabelled fighters — each their own side:", result)
    print("    (with a shared 'default' side this would have ended at Phase 0)")

    # ---- Doctrine in the seat ----
    result = run_encounter(
        _encounter([_soldier("Paragon", Side.named("heroes"), 23),
                    _soldier("Tyrant", Side.named("villains"), 21)], seed=3),
        TacticChooser(),
        roller=RandomRoller(seed=3), on_unresolvable="skip", max_turns=20,
    )
    _report("A duel, picked by role and doctrine:", result)

    # ---- A caller-supplied ending ----
    class FirstBlood:
        """A caller's own ending, as a class implementing StopCondition.

        Objects over strings, classes over functions: a stop condition is a
        thing with a rule, not a bare callable."""

        def decide(self, roster):
            for c in roster.combatants:
                if c.state.current_stun < c.combat_stats().max_stun:
                    return Verdict(over=True, winner=Side.of(c))
            return Verdict(over=False)

    result = run_encounter(
        _encounter([_soldier("Duellist", Side.named("a"), 25),
         _soldier("Rival", Side.named("b"), 20)], seed=3),
        FirstLegalChooser(), roller=RandomRoller(seed=3),
        until=FirstBlood(), on_unresolvable="skip", max_turns=10,
    )
    _report("A duel to first blood — the caller's rule, not the engine's:", result)

    # ---- One Phase at a time: what a networked session actually steps ----
    #
    # `run_encounter` is a convenience over `run_phase`. A web service does
    # not want a fight run to completion in one call -- it wants to step one
    # Phase, broadcast what happened, and wait. That is `run_phase`, and it
    # is the same function `run_encounter` calls in its own inner loop.
    print("\n  Stepping a fight one Phase at a time:")
    encounter = _encounter(
        [_soldier("Vanguard", Side.named("north"), 24),
         _soldier("Warden", Side.named("south"), 19)], seed=13,
    )
    stepper = RandomRoller(seed=13)
    encounter = encounter.run_segment(roller=lambda: stepper.roll_dice(3))
    template = CombatTemplate.default_6e_superheroic()

    while (actor_id := next_actor_id(encounter.sessions[0])) is not None:
        actor = encounter.sessions[0].combatants[actor_id]
        phase = run_phase(
            encounter.sessions[0], FirstLegalChooser(),
            template=template, roller=stepper, on_unresolvable="skip",
        )
        encounter = dataclasses.replace(encounter, sessions=[phase.session])
        dealt = getattr(phase.result, "stun_dealt", None)
        print(
            f"    {actor.hero.name} ({Side.of(actor)}) -> {phase.kind}"
            + (f", {dealt} STUN" if dealt else "")
            + f"   [{len(phase.events)} events to broadcast]"
        )

    # ---- What a networked consumer extrudes ----
    log = result.encounter.sessions[0].event_log
    print(f"\n  The last fight produced {len(log)} events. A web service persists")
    print("  and broadcasts these; it decides nothing. Kinds emitted:")
    kinds: dict[str, int] = {}
    for event in log:
        kinds[event.kind] = kinds.get(event.kind, 0) + 1
    for kind, n in sorted(kinds.items()):
        print(f"    {kind:<20} {n}")


if __name__ == "__main__":
    main()
