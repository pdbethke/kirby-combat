"""Recovery resolution — Phase 12, Post-Segment 12, Full Recovery.

HERO 6E1 pg 423:
- A conscious character with a phase at segment 12 may take a "Recovery Action"
  (full-phase action) to gain REC STUN + REC END, capped at max.
- At the end of every turn (after segment 12), all characters — conscious or
  KO'd — gain REC STUN + REC END automatically ("Post-Segment 12 Recovery").
- Full Recovery (out of combat, ~20 minutes rest) restores STUN, END, and BODY
  to max. This function handles only STUN + END; BODY recovery is separate.

KO'd = current_stun <= 0. A KO'd character cannot take a Recovery Action (phase_12)
but still benefits from Post-Segment 12 Recovery and Full Recovery.
"""
from __future__ import annotations

from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate


_VALID_RECOVERY_TYPES: frozenset[str] = frozenset({
    "phase_12",
    "post_12",
    "full_recovery",
})


def compute_recovery(
    combatant: Combatant,
    template: CombatTemplate,
    recovery_type: str,
) -> tuple[int, int]:
    """Compute signed (stun_delta, end_delta) for a recovery event.

    Deltas are non-negative — apply via `current_* += delta`.

    Arguments:
        combatant: the character recovering.
        template: CombatTemplate — reserved for future house-rule hooks
            (e.g. modified recovery rates). Currently unused but kept in the
            signature so callers don't have to refactor later.
        recovery_type: one of "phase_12", "post_12", "full_recovery".

    Raises:
        ValueError: unknown recovery_type.
    """
    if recovery_type not in _VALID_RECOVERY_TYPES:
        raise ValueError(f"unknown recovery_type: {recovery_type!r}")

    is_ko = combatant.current_stun <= 0

    if recovery_type == "full_recovery":
        stun_delta = max(0, combatant.max_stun - combatant.current_stun)
        end_delta = max(0, combatant.max_end - combatant.current_end)
        return stun_delta, end_delta

    if recovery_type == "phase_12":
        if is_ko:
            # 6E: KO'd characters cannot take a Recovery Action.
            return 0, 0
        # Fall through to standard REC recovery, capped at max.

    # Both phase_12 (when not KO'd) and post_12 apply REC, capped at max.
    stun_delta = min(combatant.rec, combatant.max_stun - combatant.current_stun)
    end_delta = min(combatant.rec, combatant.max_end - combatant.current_end)
    return max(0, stun_delta), max(0, end_delta)
