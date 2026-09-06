"""One Phase, written down — the last piece of a fight that runs anywhere.

WHAT THIS CLOSES. Three things stood between the engine and a fight it
could run on its own, and this is the third:

  1. Damage never reached the combatant  (closed: `apply_vitals_delta`)
  2. Nothing drove the turn loop         (closed: `kirby_combat.loop`)
  3. Nothing described the Phase         (closed: `Brief`, here)

A chooser that reads text needs the Phase described: who is acting, what
shape they are in, who is standing where, and what they may legally do.
That description was the last thing living in the parked wrapper, where it
was already a pure function of engine state --- measured to touch the
database zero times. Only its location was wrong.

THE BRACKETED TOKEN IS THE CONTRACT. Each offer is listed as
`[action_id] summary`. The summary is for whoever reads it; the id is what
a chooser returns and what `validate_choice` checks. Anything not on that
list is refused at the seat rather than three frames deeper.

A BRIEF IS A VIEW, NOT A RULE. It reads state and changes none, and it
names nothing about what might read it --- the same seam as `Chooser`: the
engine asks, and never learns what answered. A caller who wants a
different page builds one from the same objects.

Exercises:
  - Brief / CombatantLine, and PhaseSituation.brief()
  - a chooser that reads the Brief and answers with an action_id
  - the whole loop driven by that chooser, to a decision
"""
from __future__ import annotations

import dataclasses
import re

from kirby_combat.encounter import Encounter
from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.loop import PhaseSituation, Roster, run_encounter
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


class _MinimalHero:
    """Enough of a LoadedHero to enumerate. Built locally because examples
    run standalone and must not reach into `tests/`."""

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
class _Fighter(HeroCombatant):
    """A dataclass, because the engine replaces a combatant on every vitals
    change and `dataclasses.replace` carries fields only."""

    _attacks: list = dataclasses.field(default_factory=list)

    @property
    def attacks(self):
        return self._attacks

    @property
    def defenses(self):
        return []


def _fighter(name: str, side: Side, dex: int) -> HeroCombatant:
    hero = _MinimalHero(name, {
        "OCV": 9, "DCV": 5, "OMCV": 5, "DMCV": 5, "SPD": 4, "DEX": dex,
        "EGO": 14, "STR": 15, "CON": 18, "PRE": 15, "REC": 6, "INT": 13,
        "PD": 4, "ED": 4, "STUN": 35, "BODY": 12, "END": 40, "RUNNING": 12,
    })
    return _Fighter(
        id=name, hero=hero, side=side,
        state=HeroCombatState(current_stun=35, current_body=12, current_end=40),
        _attacks=[AttackPower(
            xmlid="ENERGYBLAST", name="Volley", damage_dice=7,
            half_die=False, plus_one=False,
            damage_type="normal", defense_type="ed", range_m=150,
            uses_str=False, str_min=0,
            armor_piercing=0, penetrating=0, increased_stun_mult=0,
            source_id=f"{name}-eb",
        )],
    )


class ReadsTheBrief:
    """A chooser that works only from the written page.

    It never inspects a combatant --- it reads the Brief's text, pulls the
    bracketed ids out of it, and answers with one. That is deliberately the
    same contract anything else would work under: the engine hands over a
    description and takes back a token.

    The rule here is trivial (prefer an attack, else the first offer) and
    that is the point: what matters is that a text-only reader can drive a
    real fight to a decision.
    """

    name = "reads-the-brief"

    #: `[action_id] summary` --- the bracketed token is the contract.
    OFFER = re.compile(r"^\s+\[([^\]]+)\]\s+(.*)$", re.MULTILINE)

    def __init__(self) -> None:
        self.pages: list[str] = []

    def choose(self, situation: PhaseSituation) -> str:
        page = situation.brief().render()
        self.pages.append(page)

        offers = self.OFFER.findall(page)
        for action_id, summary in offers:
            if action_id.startswith("attack:"):
                return action_id
        return offers[0][0]


def main() -> None:
    template = CombatTemplate.default_6e_superheroic()
    roller = RandomRoller(seed=31)

    session = CombatSession.create(
        id="field", scene=None, template=template, dice_roller=roller,
        combatants=[
            _fighter("Aurora", Side.named("Sentinels"), 25),
            _fighter("Bulwark", Side.named("Sentinels"), 20),
            _fighter("Nemesis", Side.named("Iron Chorus"), 22),
        ],
    ).start()
    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session])

    # ---- What one Phase looks like ----
    stepper = RandomRoller(seed=31)
    resolved = encounter.run_segment(roller=lambda: stepper.roll_dice(3))
    live = resolved.sessions[0]
    actor = live.combatants["Aurora"]
    roster = Roster(live)

    from kirby_combat.enumeration import enumerate_actions

    situation = PhaseSituation(
        actor=actor, menu=enumerate_actions(actor, roster.enemies_of(actor)),
        enemies=roster.enemies_of(actor), allies=roster.allies_of(actor),
        session=live, segment=live.timeline.segment, turn=live.timeline.turn,
    )
    brief = situation.brief()

    print("ONE PHASE, WRITTEN DOWN")
    print("=" * 66)
    page = brief.render()
    head = page.split("\n")
    print("\n".join(head[:14]))
    print(f"  ... and {len(brief) - 3} more offers")
    print("=" * 66)

    print(f"\n  The page is {len(page)} characters and names "
          f"{len(brief)} legal actions.")
    print("  Reading it changes nothing:", 
          f"Aurora still at {actor.state.current_stun} STUN.")

    # ---- A fight driven entirely from that page ----
    chooser = ReadsTheBrief()
    result = run_encounter(
        encounter, chooser, roller=RandomRoller(seed=31),
        on_unresolvable="skip", max_turns=20,
    )

    print("\nA FIGHT DRIVEN ONLY BY WHAT THE PAGE SAID")
    print(f"  decided : {result.complete}")
    print(f"  winner  : {result.winner}")
    print(f"  phases  : {result.phases}   pages read: {len(chooser.pages)}")
    if result.skipped_kinds:
        print(f"  skipped : {result.skipped_kinds}")
    standing = Roster(result.encounter.sessions[0]).standing
    print(f"  standing: { {s.name: len(v) for s, v in standing.items()} }")
    print("\n  No database. No web service. No network.")


if __name__ == "__main__":
    main()
