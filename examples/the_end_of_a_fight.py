"""How a fight ends: its terms, the question to the GM, and the one event.

WHAT THIS DEMONSTRATES. A fight ends only when `SessionEnded` is in its log
(`kirby_combat.ending`), and how it gets there is the fight's own TERMS,
stated once as it starts: which stop condition decides it, and whether the
engine ends it on its own or asks the GM first.

  1. AUTO-STOP. Last side standing, final: the Phase after the last man on
     one side goes down, the engine writes `SessionEnded` itself.
  2. ASK. The same fight, but the engine proposes the end instead
     (`EndProposed`) and holds the fight still until the GM answers. The GM
     says no (`EndDeclined`: reinforcements are coming), the fight carries
     on, and the same verdict is not asked again; later the GM calls it.
  3. Replay. Everything above is in the log, so a fight rebuilt from it ends
     the same way.

Before 2026-11-24 `SessionEnded` existed and nothing emitted it: no fight's
log recorded its end, so a replay could not show it and a campaign had
nothing to carry consequences back on.

NO DATABASE, NO WEB SERVICE. The fighters are the four-armies example's.

Exercises:
  - state_terms / terms_of — the fight's terms, in its log
  - ended — the event that ended it, or None
  - open_proposal / answer_end — the question to the GM, and the answer
  - call_fight — the GM ends it now
"""
from __future__ import annotations

from dataclasses import replace

from the_battle_of_four_armies import _encounter, _soldier

from kirby_combat.ending import (
    EndMode, FightTerms, StopKind, answer_end, call_fight, ended,
    open_proposal, terms_of,
)
from kirby_combat.loop import FirstLegalChooser, run_phase
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_dice import RandomRoller

GM = "the-gm"
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


def _roster():
    return [_soldier("Paragon", HEROES, 23), _soldier("Tyrant", VILLAINS, 21)]


def _step_to_the_end(enc, *, limit: int = 400):
    """Step Phase by Phase, as a networked consumer does, until the fight
    ends or stops on a question."""
    roller = RandomRoller(seed=3)
    for _ in range(limit):
        phase = run_phase(enc, FirstLegalChooser(), roller=roller,
                          on_unresolvable="skip")
        enc = phase.encounter
        if phase.kind in ("ended", "end_question"):
            return enc, phase.kind
    raise AssertionError("the fight neither ended nor asked")


def main() -> None:
    print("THE END OF A FIGHT — no database, no web service.")

    # ── 1. Auto-stop ───────────────────────────────────────────────────
    terms = FightTerms(stop=StopKind.LAST_SIDE_STANDING,
                       end_mode=EndMode.AUTO_STOP)
    enc, kind = _step_to_the_end(_encounter(_roster(), seed=3, terms=terms))
    session = enc.sessions[0]
    end = ended(session)
    stated = terms_of(session)
    print(f"\n  1. terms: {stated.stop.value}, {stated.end_mode.value}")
    print(f"     {kind}: {end.ending.upper()}, won by {end.winner!r}, "
          f"confirmed by the {end.author.type}")
    assert kind == "ended" and end.author.type == "engine"

    # ── 2. Ask ─────────────────────────────────────────────────────────
    ask = FightTerms(stop=StopKind.LAST_SIDE_STANDING, end_mode=EndMode.ASK)
    enc, kind = _step_to_the_end(_encounter(_roster(), seed=3, terms=ask))
    question = open_proposal(enc.sessions[0])
    print(f"\n  2. {kind}: the engine asks — {question.ending}, "
          f"{question.winner!r} wins. End the fight?")
    assert kind == "end_question" and ended(enc.sessions[0]) is None

    declined = answer_end(enc.sessions[0], accept=False, gm_id=GM)
    print("     The GM says no: reinforcements are on their way.")
    again = run_phase(replace(enc, sessions=[declined]), FirstLegalChooser(),
                      roller=RandomRoller(seed=4), on_unresolvable="skip")
    print(f"     The fight carries on (next: {again.kind or 'a Phase'}); "
          "the same verdict is not asked again.")
    assert again.kind != "end_question"

    done = call_fight(again.session, gm_id=GM)
    end = ended(done)
    print(f"     Later the GM calls it: {end.ending.upper()}, confirmed by "
          f"the {end.author.type} ({end.author.id}).")
    assert end.author.type == "gm"

    # ── 3. Replay ──────────────────────────────────────────────────────
    first = done.event_log[0]
    rebuilt = CombatSession.create(
        id=done.id, combatants=_roster(), scene=None,
        template=done.template, dice_roller=None,
    )
    for event in done.event_log:
        rebuilt = apply_event(rebuilt, event)
    print(f"\n  3. Rebuilt from its {len(done.event_log)} rows (from "
          f"{first.kind}): status {rebuilt.status}, ended by "
          f"{ended(rebuilt).ending}.")
    assert ended(rebuilt) == ended(done) and terms_of(rebuilt) == terms_of(done)


if __name__ == "__main__":
    main()
