"""The turn loop — the engine driving a fight from first Phase to decision.

Sub-project D of the driver carve-out. Spec:
``kirby/docs/superpowers/specs/2026-09-06-the-turn-loop-into-the-engine-design.md``

  - ``sides``    — who is on whose team, and when the fight is decided
  - ``chooser``  — the seat; the one thing the engine does not decide
  - ``registry`` — chosen action -> resolution, with the gap made countable
  - ``run``      — the loop itself
"""
from kirby_combat.loop.chooser import (
    Chooser, FirstLegalChooser, InvalidChoice, PhaseSituation, TacticChooser,
    validate_choice,
)
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, registered_kinds, resolve_chosen, resolves,
)
from kirby_combat.loop.run import (
    EncounterResult, PhaseResult, StopCondition, TurnResult,
    next_actor_id, run_encounter, run_phase,
)
from kirby_combat.loop.sides import last_side_standing, side_of, standing_sides

__all__ = [
    "Chooser", "FirstLegalChooser", "InvalidChoice", "PhaseSituation",
    "TacticChooser", "validate_choice",
    "ResolvedAction", "UnresolvableAction", "registered_kinds",
    "resolve_chosen", "resolves",
    "EncounterResult", "PhaseResult", "StopCondition", "TurnResult",
    "next_actor_id", "run_encounter", "run_phase",
    "last_side_standing", "side_of", "standing_sides",
]
