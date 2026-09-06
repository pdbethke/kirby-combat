"""apply_vitals_delta — the one place a STUN/BODY/END change lands on a combatant.

WHY THIS EXISTS. Two private copies of this fold already lived in the
engine, and they had drifted apart:

  - ``encounter.py::_apply_stun_end_recovery`` — STUN and END, no BODY.
  - ``actions/movement/base.py::_decrement_end`` — END only.

Each carried its own paragraph explaining the same shape dispatch, and
neither could apply BODY, which is what an attack mostly deals. Both now
delegate here.

THE SHAPE DISPATCH, ONCE. A combatant's vitals live in one of two places
depending on its class, and the discriminator is an identity check:
``StatBlockCombatant.state`` returns ``self`` — its flat ``current_*``
fields ARE its state — so ``combatant.state is combatant`` distinguishes
it from ``HeroCombatant``, whose vitals sit on a separate
``HeroCombatState`` dataclass. That identity is load-bearing, not
stylistic: making ``StatBlockCombatant.state`` return a copy would route
every stat-block change into the HeroCombatant branch, which
``dataclasses.replace``s a ``state`` field a stat block does not have.
See ``StatBlockCombatant.state``'s own docstring in ``models.py``.

NOTHING IS CLAMPED, AND THAT IS THE RULE, NOT AN OMISSION. STUN below
zero is meaningful — ``Stunnable.is_ko`` is ``current_stun <= 0``, and 6E
reads how far below zero a character fell to decide how long they stay
down. BODY below zero is likewise how the dying rules are expressed.
Clamping either at zero would destroy the number that the rule needs,
which is exactly the failure that made the Krackle replay unfixable: END
clamps on spend, so the amount really taken was gone and no inversion
recovered it. A caller that wants a ceiling (Recovery must not push STUN
past ``max_stun``) computes the bounded delta itself and passes it —
``resolution/recovery.py`` already does precisely that with
``min(rec, max_stun - current_stun)``.

The returned combatant is always new; the input is never mutated.
"""
from __future__ import annotations

from dataclasses import replace


def apply_vitals_delta(combatant, *, stun: int = 0, body: int = 0, end: int = 0):
    """Return a NEW combatant with the given deltas added to its current
    STUN/BODY/END. Deltas are signed: damage is negative, recovery positive.

    Works on both combatant shapes (see the module docstring). Values are
    not clamped in either direction.
    """
    if combatant.state is not combatant:
        # HeroCombatant: vitals live on a separate HeroCombatState dataclass.
        new_state = replace(
            combatant.state,
            current_stun=combatant.state.current_stun + stun,
            current_body=combatant.state.current_body + body,
            current_end=combatant.state.current_end + end,
        )
        return replace(combatant, state=new_state)
    # StatBlockCombatant: current_* are fields on self.
    return replace(
        combatant,
        current_stun=combatant.current_stun + stun,
        current_body=combatant.current_body + body,
        current_end=combatant.current_end + end,
    )
