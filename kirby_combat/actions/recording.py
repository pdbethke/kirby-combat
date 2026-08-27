"""Session-aware wrappers around pure action resolvers (attack, Block).

``AttackAction.resolve`` (and the ``resolve_attack`` dispatcher in
``actions/__init__.py``) is a pure calculator: a total function of its
inputs with no session coupling, which is exactly what makes it trivial
to test and safe to call from anywhere. That purity is an asset and is
left untouched here.

The gap it leaves is that nothing ever records the outcome anywhere —
callers that DO have a session (and want the attack's effects on the
event log) had no session-aware entry point to call, so kirby-api grew
its own ``ActionResolved`` construction instead
(``llm_driver.py:_emit_resolution``). This module adds that entry point
inside kirby-combat, following the same shape already used by
``Flash.apply`` (``actions/flash.py``) and ``Grab.declare_and_resolve``
(``actions/grab.py``): run the pure calculation, then emit the event(s)
that describe it.

This lives in its own module (rather than being folded into
``actions/base.py``) because it is a different kind of thing from the
pipeline in that file: ``base.py`` holds pure, session-free resolution
logic shared by the concrete attack action classes, while this module is
glue between that pure core and the event-sourced ``CombatSession``. Its
only reason to import ``CombatSession``/``apply_event``/``ActionResolved``
at all is to record — mixing that into ``base.py`` would put session
plumbing in the one place the brief explicitly wants kept pure.

Opt-in only: existing callers of ``resolve_attack`` / ``AttackAction.resolve``
are completely unaffected — nothing here changes their behaviour, and
nothing here emits anything on their behalf. A caller must choose to call
``resolve_attack_in_session`` instead, which is what keeps this from
double-logging against kirby-api's own emission.

``resolve_block_in_session`` (below) does the same thing for
``Block.resolve`` (``actions/reactive/block.py``): that resolver is also a
pure calculator, so a Block's outcome never reached the event log, and
``Block.acts_first_priority`` (6E2 p.60, "ACTING FIRST") had no live
caller anywhere. See that function's docstring for the ``kind`` value it
chose and the limits of what it wires versus what it returns for a caller
to wire further.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from kirby_combat.actions import resolve_attack
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.actions.reactive.block import Block, BlockResult
from kirby_combat.models import AttackInput, AttackResult
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)
from kirby_combat.template import CombatTemplate

#: The only ``action_type``/payload ``"kind"`` values kirby-api's own filter
#: accepts (``situation_builder.py:687-688``: ``kind not in ("attack",
#: "strike", "grab")``). Anything else is silently dropped by that filter,
#: not rejected as an error -- see ``resolve_attack_in_session``'s inline
#: comment on ``result_payload["kind"]``. Kept as a runtime tuple (not just
#: a type-checker-only ``Literal``) so a caller can assert against it
#: directly, e.g. ``assert "haymaker" not in ACCEPTED_ACTION_KINDS``.
ACCEPTED_ACTION_KINDS: tuple[str, ...] = get_args(
    Literal["attack", "strike", "grab"]
)
ActionKind = Literal["attack", "strike", "grab"]


def resolve_attack_in_session(
    session: CombatSession,
    attack: AttackInput,
    template: CombatTemplate,
    *,
    declaration_event_id: str | None = None,
    action_type: ActionKind = "attack",
) -> tuple[CombatSession, AttackResult]:
    """Resolve an attack and record the outcome on the session's event log.

    Runs the pure ``resolve_attack`` calculation unchanged, then emits an
    ``ActionResolved`` carrying the outcome — most importantly
    ``status_changes``, which the pure resolver computes
    (``AttackAction.resolve``, via ``determine_status_changes``) but has no
    session to hand it to, so today it is discarded by every caller that
    doesn't hand-roll its own recording.

    If ``declaration_event_id`` is omitted, an ``ActionDeclared`` is emitted
    first (mirroring ``Flash.apply`` / ``Grab.declare_and_resolve``) and its
    id is used as the resolution's ``declaration_event_id``. Pass an existing
    id when the caller already declared the action itself.

    Returns ``(new_session, result)`` — ``result`` is exactly what
    ``resolve_attack`` returned; nothing about the pure result is altered.
    """
    from kirby_combat.session.apply import apply_event

    result = resolve_attack(attack, template)

    attacker_id = attack.attacker.id
    target_id = attack.target.id
    now = datetime.now(timezone.utc)

    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type=action_type,
            targets=[target_id],
            parameters={"power_xmlid": attack.power.xmlid},
        )
        s = apply_event(s, declared)
        decl_id = declared.id

    # Established payload keys, matched to what kirby-api's own
    # _emit_resolution-style construction already writes (llm_driver.py
    # reads "hit" at situation_builder.py:690 / soliloquy.py:256-258,
    # "stun_dealt" at soliloquy.py:139,260, "body_dealt" at
    # soliloquy.py:140,263). "status_changes" is new: nothing persists it
    # today even though llm_driver.py checks `result.status_changes` for
    # "Stunned" in six places (2757, 6215, 7997, 8176, 9861, 9938) —
    # re-deriving it every request because it was never recorded. "Knocked
    # Out" is one of the strings `determine_status_changes` may return
    # (kirby_combat/resolution/status.py), so it is already carried inside
    # status_changes rather than duplicated as a separate boolean key.
    # "kind" is required, not decorative: situation_builder.py:687-688 does
    # `kind = result.get("kind")` then filters on
    # `kind not in ("attack", "strike", "grab")` -- exactly
    # `ACCEPTED_ACTION_KINDS` above -- and soliloquy.py:255 reads
    # `payload.get("kind") or "action"` for narration. A payload without it
    # is silently dropped by that filter (not an error — just invisible) and
    # narrated as the generic "action". Sourced from `action_type`, which
    # already defaults to "attack" and lets a caller pass "strike"/"grab"
    # where those are the accurate label. `action_type`'s ``ActionKind``
    # annotation constrains it to that same set at the type-checker level
    # (a plain `str` here previously let `action_type="haymaker"` reproduce
    # the silent-drop with every test green -- see review finding #3).
    result_payload: dict[str, Any] = {
        "kind": action_type,
        "hit": result.hit,
        "stun_dealt": result.stun_dealt,
        "body_dealt": result.body_dealt,
        "status_changes": list(result.status_changes),
        "power_xmlid": result.power_xmlid,
        "target_id": target_id,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    return s, result


def resolve_block_in_session(
    session: CombatSession,
    *,
    blocker_id: str,
    attacker_id: str,
    blocker_ocv: int,
    blocker_dice: list[int],
    attacker_ocv: int,
    declaration_event_id: str | None = None,
) -> tuple[CombatSession, BlockResult, dict[str, str]]:
    """Resolve a Block and record the outcome on the session's event log.

    Runs the pure ``Block.resolve`` calculation unchanged (``actions/
    reactive/block.py``), then emits an ``ActionResolved`` carrying the
    outcome — the same gap ``resolve_attack_in_session`` closes for
    attacks: ``Block.resolve`` is a pure calculator with no session, so
    nothing recorded a Block's outcome anywhere before this.

    If ``declaration_event_id`` is omitted, this calls ``mark_aborting``
    (``actions/reactive/abort.py``) to emit the ``AbortDeclared`` Block
    already declares itself with via ``Block.declare`` (which is exactly
    ``mark_aborting(session, combatant_id, to_action="block")``) -- and by
    doing so on this default path, THIS function is now a caller feeding
    ``session.timeline.aborted_this_phase``, a ONE-WAY LATCH that nothing
    in this package ever clears (``statuses.py``'s ``ABORTED`` comment:
    "aborted for the rest of the fight", not "aborted this phase") -- and uses
    its id as the resolution's ``declaration_event_id``. Pass the id
    ``Block.declare`` already returned when the caller declared the Block
    itself; this parameter exists so callers who separate declare/resolve
    across a Segment boundary (the normal case for a reactive defense)
    don't get a second, spurious ``AbortDeclared``.

    ``kind`` on the payload is ``"block"`` — a deliberate, distinct value,
    not one of the three kirby-api's attack filter accepts (`kind not in
    ("attack", "strike", "grab")` at situation_builder.py:687-688). A
    Block is not an attack, a strike, or a grab, and mislabeling it as one
    of those to slip past that filter would be worse than the filter
    simply not recognizing it yet: extending kirby-api's filter to also
    accept "block" is kirby-api's call, out of scope here.

    ``Block.acts_first_priority`` (6E2 p.60, "ACTING FIRST") had no live
    caller anywhere in kirby_combat before this. This function is that
    caller: it computes the priority mapping from the just-resolved
    ``BlockResult`` and returns it as the third tuple element — `{}` on a
    failed Block, `{blocker_id: attacker_id}` on a successful one — so a
    caller that owns an ``Encounter`` can merge it into
    ``Encounter.acts_first`` itself (via ``dataclasses.replace``, since
    ``Encounter`` is immutable). This function does not reach into
    ``Encounter.acts_first`` itself: doing so needs a driver that holds
    both a ``CombatSession`` and its ``Encounter`` together, and no such
    driver exists in kirby_combat today (nor does this task touch
    ``encounter.py`` to add one) — leaving that merge to the returned
    value is the honest state of the wiring, not a half-connected guard
    that looks wired and isn't.

    Returns ``(new_session, result, acts_first_priority)`` — ``result`` is
    exactly what ``Block.resolve`` returned; nothing about the pure result
    is altered.
    """
    from kirby_combat.session.apply import apply_event

    result = Block.resolve(
        blocker_ocv=blocker_ocv, blocker_dice=blocker_dice,
        attacker_ocv=attacker_ocv,
    )

    now = datetime.now(timezone.utc)

    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        s, declared = mark_aborting(s, blocker_id, to_action="block")
        decl_id = declared.id

    result_payload: dict[str, Any] = {
        "kind": "block",
        "success": result.success,
        "blocker_id": blocker_id,
        "attacker_id": attacker_id,
        "blocker_roll": result.blocker_roll,
        "blocker_margin": result.blocker_margin,
        "attacker_ocv": result.attacker_ocv,
        "blocker_ocv": result.blocker_ocv,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(blocker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    priority = Block.acts_first_priority(result, blocker_id, attacker_id)

    return s, result, priority


__all__ = [
    "resolve_attack_in_session",
    "resolve_block_in_session",
    "ACCEPTED_ACTION_KINDS",
    "ActionKind",
]
