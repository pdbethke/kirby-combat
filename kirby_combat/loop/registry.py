"""Turning a chosen ``LegalAction`` into a resolved one.

THE GAP THIS MAKES COUNTABLE. Measured 2026-09-06: ``enumerate_actions``
can offer **52** kinds of action, and the engine could execute **none** of
them from that menu. The rules largely exist --- some thirty modules under
``kirby_combat/actions/`` --- but nothing mapped a chosen action onto them.
That mapping lived in the parked kirby-api driver as 39 ``_resolve_*``
methods behind a 1,070-line dispatcher, tangled with the database.

This module is the MECHANISM --- the decorator, the dispatch and the raise.
The resolvers themselves live in ``loop/resolvers.py``, which is what grows
as the carve-out proceeds; this file should not.

It is deliberately small and honest rather than a stub of all 52:

``resolve_chosen`` dispatches on ``LegalAction.kind``. A kind with no
registered resolver raises ``UnresolvableAction`` naming it.

**THE RAISE IS THE DESIGN.** A registry that silently skipped unknown kinds
would turn a 46-kind gap into a fight that quietly does nothing on half its
Phases --- precisely the class of failure this carve-out exists to end, and
the same shape as the bug where every AOE/TRIGGER modifier was silently
inert because a name never matched. Raising makes the gap a number:
``registered_kinds()`` is asserted by a test, so each migration out of
kirby-api moves it, and no migration has to touch the loop.

The loop offers ``on_unresolvable="raise" | "skip"`` for callers who want a
long fight to make progress while the registry fills. A skip is always
recorded on the Phase result --- never invisible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from kirby_combat.enumeration import LegalAction

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


class UnresolvableAction(Exception):
    """A chosen action's ``kind`` has no registered resolver.

    Carries the kind so a caller can report exactly which rule is still
    outside the engine, rather than "something went wrong in a Phase".
    """

    def __init__(self, kind: str, action_id: str = "") -> None:
        self.kind = kind
        self.action_id = action_id
        known = ", ".join(sorted(registered_kinds()))
        super().__init__(
            f"no resolver registered for action kind {kind!r}"
            + (f" (action {action_id!r})" if action_id else "")
            + f"; the engine can currently resolve: {known}"
        )


@dataclass
class ResolvedAction:
    """What one resolved Phase produced.

    ``events`` is the slice of the session's log this resolution appended,
    which is what a networked consumer extrudes: it persists and broadcasts
    these, and owns no rule about what they mean.
    """

    session: "CombatSession"
    kind: str
    action_id: str
    result: Any = None
    events: list[Any] = field(default_factory=list)


#: kind -> resolver. Populated by ``@resolves`` at import time.
_RESOLVERS: dict[str, Callable[..., ResolvedAction]] = {}


def resolves(*kinds: str):
    """Register a resolver for one or more ``LegalAction.kind`` values."""

    def decorate(fn: Callable[..., ResolvedAction]):
        for kind in kinds:
            if kind in _RESOLVERS:
                raise ValueError(f"resolver for {kind!r} already registered")
            _RESOLVERS[kind] = fn
        return fn

    return decorate


def registered_kinds() -> frozenset[str]:
    """Every kind the engine can resolve today.

    Asserted by a test on purpose --- see the module docstring. This number
    growing is the measure of the carve-out's progress.
    """
    return frozenset(_RESOLVERS)


def _events_since(before: "CombatSession", after: "CombatSession") -> list[Any]:
    return list(after.event_log[len(before.event_log):])


def resolve_chosen(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Execute one chosen action, returning the new session and its events.

    Raises ``UnresolvableAction`` for a kind the engine cannot yet perform.
    """
    resolver = _RESOLVERS.get(action.kind)
    if resolver is None:
        raise UnresolvableAction(action.kind, action.action_id)
    return resolver(session, actor, action, template=template, roller=roller)
