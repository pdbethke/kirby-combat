"""The turn loop — the engine driving a fight from first Phase to decision.

Sub-project D of the driver carve-out. Spec:
``kirby/docs/superpowers/specs/2026-09-06-the-turn-loop-into-the-engine-design.md``

  - ``roster``   — who is on whose side, and when the fight is decided
  - ``chooser``  — the seat; the one thing the engine does not decide
  - ``registry``  — the dispatch mechanism, and the countable gap
  - ``resolvers`` — one resolver per kind the engine can execute
  - ``run``      — the loop itself
"""
from kirby_combat.side import Side
from kirby_combat.loop.chooser import (
    Chooser, FirstLegalChooser, InvalidChoice, PhaseSituation, TacticChooser,
    validate_choice,
)
from kirby_combat.loop import resolvers as _resolvers  # noqa: F401  (registers them)
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, registered_kinds, resolve_chosen, resolves,
)
from kirby_combat.loop.run import (
    EncounterResult, PhaseResult, TurnResult,
    next_actor_id, run_encounter, run_phase,
)
from kirby_combat.roster import (
    AmbiguousSides, LastSideStanding, Roster, StopCondition, UnexpectedSide,
    Verdict,
)

__all__ = [
    "Side",
    "Chooser", "FirstLegalChooser", "InvalidChoice", "PhaseSituation",
    "TacticChooser", "validate_choice",
    "ResolvedAction", "UnresolvableAction", "registered_kinds",
    "resolve_chosen", "resolves",
    "EncounterResult", "PhaseResult", "StopCondition", "TurnResult",
    "next_actor_id", "run_encounter", "run_phase",
    "Roster", "Verdict", "LastSideStanding",
    "AmbiguousSides", "UnexpectedSide",
]
