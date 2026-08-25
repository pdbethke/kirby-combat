"""Recovery resolution — Phase 12, Post-Segment 12, Full Recovery.

per HERO 6E1:
- A conscious character with a phase at segment 12 may take a "Recovery Action"
  (full-phase action) to gain REC STUN + REC END, capped at max.
- At the end of every turn (after segment 12), all characters — conscious or
  KO'd — gain REC STUN + REC END automatically ("Post-Segment 12 Recovery").
- Full Recovery (out of combat, ~20 minutes rest) restores STUN, END, and BODY
  to max. This function handles only STUN + END; BODY recovery is separate.

A KO'd character (see kirby_combat.participant.Stunnable.is_ko for
the threshold definition) cannot take a Recovery Action (phase_12) but still
benefits from Post-Segment 12 Recovery and Full Recovery.

Step 2 of the combatant-redesign migration
(kirby/docs/superpowers/specs/2026-04-30-kirby-combat-combatant-redesign.md
§4 step 2): this is the only file that reads ``combatant.current_stun /
max_stun / rec`` directly and the spec calls it out as the first to
migrate. We accept BOTH legacy ``Combatant`` and the new
``HeroCombatant`` and dispatch internally — ducks via
``hasattr(combatant, "state")``. Once steps 3-6 retire the legacy
type, the dispatch helper goes away.
"""
from __future__ import annotations

from typing import Union

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate


_VALID_RECOVERY_TYPES: frozenset[str] = frozenset({
    "phase_12",
    "post_12",
    "full_recovery",
})


def _vitals(combatant) -> tuple[int, int, int, int, int]:
    """Return (current_stun, current_end, rec, max_stun, max_end) regardless
    of whether ``combatant`` is a legacy ``Combatant`` or a ``HeroCombatant``.

    HeroCombatant carries vitals on ``state`` (current_*) and computes
    rec/max_* via ``combat_stats()``. Legacy Combatant is flat.
    """
    if hasattr(combatant, "state") and hasattr(combatant, "combat_stats"):
        # HeroCombatant
        s = combatant.combat_stats()
        return (
            int(combatant.state.current_stun),
            int(combatant.state.current_end),
            int(s.rec),
            int(s.max_stun),
            int(s.max_end),
        )
    # Legacy flat Combatant
    return (
        int(combatant.current_stun),
        int(combatant.current_end),
        int(combatant.rec),
        int(combatant.max_stun),
        int(combatant.max_end),
    )


def compute_recovery(
    combatant: Union[Combatant, HeroCombatant],
    template: CombatTemplate,
    recovery_type: str,
) -> tuple[int, int]:
    """Compute signed (stun_delta, end_delta) for a recovery event.

    Deltas are non-negative — apply via ``current_* += delta``.

    Arguments:
        combatant: the character recovering. Accepts either the legacy
            flat ``Combatant`` or the new HD-shaped ``HeroCombatant``.
        template: CombatTemplate — reserved for future house-rule hooks
            (e.g. modified recovery rates). Currently unused but kept in
            the signature so callers don't have to refactor later.
        recovery_type: one of "phase_12", "post_12", "full_recovery".

    Raises:
        ValueError: unknown recovery_type.
    """
    if recovery_type not in _VALID_RECOVERY_TYPES:
        raise ValueError(f"unknown recovery_type: {recovery_type!r}")

    current_stun, current_end, rec, max_stun, max_end = _vitals(combatant)

    if recovery_type == "full_recovery":
        stun_delta = max(0, max_stun - current_stun)
        end_delta = max(0, max_end - current_end)
        return stun_delta, end_delta

    if recovery_type == "phase_12":
        # Read the rule, do not restate it. `_vitals` unpacks current_stun to
        # a raw int for the arithmetic below, but we still hold the
        # participant, and `Stunnable.is_ko` computes from
        # `combatant.state.current_stun` -- the same value `_vitals` just
        # read. Duplicating `current_stun <= 0` here is how the KO threshold
        # came to be written in three places at once.
        #
        # Read inside this branch, not above it: it is the only branch that
        # asks the question, and a participant with no STUN track (an
        # ObjectCombatant) has no `is_ko` to read at all.
        if combatant.is_ko:
            # 6E: KO'd characters cannot take a Recovery Action.
            return 0, 0
        # Fall through to standard REC recovery, capped at max.

    # Both phase_12 (when not KO'd) and post_12 apply REC, capped at max.
    stun_delta = min(rec, max_stun - current_stun)
    end_delta = min(rec, max_end - current_end)
    return max(0, stun_delta), max(0, end_delta)
