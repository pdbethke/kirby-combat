"""What every thing in a fight IS, and what they all share.

An abstract base class, deliberately, not a typing.Protocol. A
runtime_checkable Protocol's isinstance() checks attribute PRESENCE only --
not types, not signatures, not return values -- so a class with `id = 42` and
`combat_stats(self, wrong, args, here)` satisfies one. This codebase's
recurring defect is things that look right and are not; a contract that can be
met by accident belongs nowhere near it. An ABC refuses to instantiate an
incomplete subclass, at construction, loudly.

The base carries what EVERY participant shares. Capability that only some have
-- passengers, materials, mental combat -- goes on mixins, so the common
ancestor does not accumulate other people's features.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CombatParticipant(ABC):
    """Anything that can take part in a fight."""

    #: Session-scoped identifier. NOT a character name or a database id.
    id: str

    #: Display name, for logs and narration.
    name: str

    @abstractmethod
    def combat_stats(self) -> Any:
        """The effective integer stats at this moment.

        A build-backed participant computes these from its LoadedHero; a
        stat-block participant holds them directly. Callers must not reach
        past this for OCV/DCV/DEX/SPD -- doing so is what let the flat and
        HD-shaped types diverge, and is what the no-op shim was hiding.
        """

    @property
    @abstractmethod
    def state(self) -> Any:
        """Run-time condition: current STUN/BODY/END and status flags."""

    # ── behaviour every participant shares ────────────────────────────
    #
    # These live here because they were living in THREE places: the KO rule
    # was written in mental/mental_blast.py, again in resolution/recovery.py,
    # and a third time in that file's docstring. Resolving an attack and
    # resolving a recovery are different jobs; neither of them is "define
    # what unconscious means".

    @property
    def is_ko(self) -> bool:
        """Unconscious. 6E: at 0 STUN or below, not merely below zero."""
        return int(self.state.current_stun) <= 0

    @property
    def is_conscious(self) -> bool:
        return not self.is_ko


class Breakable:
    """Mixin: a participant that can be destroyed rather than knocked out.

    Objects take BODY and break; they have no STUN behaviour at all. This is
    the first mixin rather than a field on the base precisely to establish the
    line -- a hero is not Breakable, and CombatParticipant should not grow a
    `material` attribute that only walls use.

    ``is_destroyed`` is a METHOD, not a property, deliberately matching the
    two pre-existing implementations it will later sit alongside:
    ``kirby_combat/breakables/object_combatant.py:65`` and
    ``kirby_combat/masscombat/unit.py:75`` are both methods, and their call
    sites (``o.is_destroyed()``, ``u.is_destroyed()``) already use the
    method convention. A property here would be a silent landmine for the
    re-parenting task -- MRO would pick a winner without complaint, and if
    the property won, ``o.is_destroyed()`` would evaluate the bool and then
    try to call it (``TypeError: 'bool' object is not callable``). Matching
    the existing shape makes inheriting this mixin later a no-op instead of
    a breaking change.
    """

    def is_destroyed(self) -> bool:
        return int(self.state.current_body) <= 0
