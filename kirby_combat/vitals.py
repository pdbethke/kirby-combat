"""The one place a STUN/BODY/END change lands on a combatant, and the one
door a caller goes through to make one.

WHY THIS EXISTS. Two private copies of this fold already lived in the
engine, and they had drifted apart:

  - ``encounter.py::_apply_stun_end_recovery`` — STUN and END, no BODY.
    (Gone 2026-09-17: `apply_event` folds `RecoveryTaken` itself, so the
    wrapper had no caller left.)
  - ``actions/movement/base.py::_decrement_end`` — END only. (Gone the
    same day, for the same reason.)

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

AND IT IS NOT CALLED DIRECTLY ANY MORE, except by `apply_event`. A
resolver that wants to hurt somebody calls `record_vitals_change` below,
which builds the event and lets the dispatcher do the writing --- see
that function, and `session/events.py`'s `VitalsChanged`, for why the
old mutate-then-log arrangement could not be replayed.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone


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


def record_vitals_change(
    session, combatant_id: str, *,
    stun: int = 0, body: int = 0, end: int = 0, reason: str,
):
    """Record a STUN/BODY/END change and let `apply_event` apply it.

    THE EMITTER, so that there is exactly one. Nine places in this engine
    used to fold a vital onto `session.combatants` themselves and then
    (sometimes) log something near it; every one of them calls this
    instead, so the change and the row that describes it can no longer
    come apart. Returns `(new_session, event)` --- the event, because a
    resolver hands its events out on its result and a change a consumer
    never sees is a change it cannot replay.

    Deltas are SIGNED: damage and spends are negative. `reason` is
    required rather than defaulted, because "something happened to his
    STUN" is not a record; the reader has to be able to tell a Push from
    a punch.

    A zero change emits nothing. It is not a decision, and a log full of
    `stun=0, body=0` rows for every miss would bury the hits.
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import VitalsChanged, make_author_engine

    if stun == 0 and body == 0 and end == 0:
        return session, None
    event = VitalsChanged(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        combatant_id=combatant_id,
        stun=stun, body=body, end=end,
        reason=reason,
    )
    return apply_event(session, event), event
