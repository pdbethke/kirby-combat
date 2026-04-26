"""Mental combat — parallel pipeline for OMCV/DMCV powers."""
from kirby_combat.mental.mental_combat import (
    MentalToHitResult, resolve_mental_to_hit,
)
from kirby_combat.mental.mind_control import (
    MindControlResult, MindControlState,
    resolve_mind_control, can_break_out_with_ego_roll,
)
from kirby_combat.mental.telepathy import (
    TelepathyResult, resolve_telepathy,
)
from kirby_combat.mental.mental_illusion import (
    MentalIllusionResult, DisbeliefResult,
    resolve_mental_illusion, attempt_disbelief,
)
from kirby_combat.mental.mental_blast import (
    MentalBlastResult, resolve_mental_blast,
)

__all__ = [
    "MentalToHitResult", "resolve_mental_to_hit",
    "MindControlResult", "MindControlState",
    "resolve_mind_control", "can_break_out_with_ego_roll",
    "TelepathyResult", "resolve_telepathy",
    "MentalIllusionResult", "DisbeliefResult",
    "resolve_mental_illusion", "attempt_disbelief",
    "MentalBlastResult", "resolve_mental_blast",
]
