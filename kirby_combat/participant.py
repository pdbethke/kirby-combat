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

    # `state` -- run-time condition: current STUN/BODY/END and status
    # flags -- is deliberately NOT an `@abstractmethod @property` here.
    # The mechanical reason:
    #
    # HeroCombatant satisfies "I have a state" with a required dataclass
    # FIELD (`state: HeroCombatState`, no default). ABCMeta computes
    # `__abstractmethods__` at class-body-execution time -- before the
    # `@dataclass` decorator ever runs -- and a bare annotation with no
    # assignment never lands in the class's `__dict__`. So if `state` were
    # an `@abstractmethod @property` here, `getattr(HeroCombatant, "state")`
    # would still resolve to THIS class's abstract property at the moment
    # ABCMeta checks, HeroCombatant would stay permanently abstract, and
    # every call site that constructs one (~330 tests) would raise
    # `TypeError: Can't instantiate abstract class HeroCombatant without an
    # implementation for abstract method 'state'`. That is not hypothetical
    # -- it is what happened the first time this was tried.
    #
    # A dataclass field WITH a default would dodge that, but giving `state`
    # a default makes it optional in the constructor -- a real behaviour
    # change to paper over a typing problem, which is worse than the
    # problem.
    #
    # So enforcement moves to `__init_subclass__` (records whether a
    # concrete subclass provides `state`, by ANY means -- a property, like
    # StatBlockCombatant's, or a plain/dataclass field, like
    # HeroCombatant's) plus `__new__` (raises at INSTANTIATION, matching
    # the ordinary ABC experience -- and keeping `combat_stats` a real
    # `@abstractmethod`, whose own instantiation-time TypeError this
    # deliberately mirrors in wording). Do NOT "simplify" this back into
    # `@abstractmethod @property def state` -- see above; it silently
    # breaks the first subclass shaped like HeroCombatant.

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # A subclass that is itself still abstract (missing `combat_stats`,
        # or an intermediate mixin never meant to be instantiated) is not
        # yet obligated to provide `state` -- only a class someone can
        # actually try to instantiate is checked.
        if getattr(cls, "__abstractmethods__", None):
            return
        has_state = any(
            "state" in vars(klass).get("__annotations__", {})
            or "state" in vars(klass)
            for klass in cls.__mro__
            if klass is not object
        )
        # Recorded on the class itself (not raised here) so that a missing
        # `state` fails at INSTANTIATION with the word "abstract" in the
        # message, exactly like a genuine `@abstractmethod` would -- class
        # DEFINITION must still succeed, the way `class Foo(ABC): ...`
        # with a missing abstractmethod succeeds and only `Foo()` fails.
        cls._combat_participant_missing_state = not has_state

    def __new__(cls, *args: Any, **kwargs: Any) -> "CombatParticipant":
        if getattr(cls, "_combat_participant_missing_state", False):
            raise TypeError(
                f"Can't instantiate abstract class {cls.__name__} without "
                f"an implementation for abstract method 'state'"
            )
        return super().__new__(cls)

    # NOTE: `is_ko` / `is_conscious` deliberately do NOT live here. They are
    # on the `Stunnable` mixin below, because they are true of only part of
    # the hierarchy. See that class for the measurement that proved it.


class Stunnable:
    """Mixin: a participant with a STUN track, which can be knocked out.

    The KO rule is defined here, once. It was previously written in THREE
    places -- mental/mental_blast.py, resolution/recovery.py, and that file's
    docstring. Resolving an attack and resolving a recovery are different
    jobs; neither of them is "define what unconscious means".

    Why a mixin and not a member of CombatParticipant: it WAS on the shared
    base, and that was measured wrong for the breakable third of the
    hierarchy. Running it on 2026-08-25, before the fix::

        ObjectCombatant.make(material='wood')   # an undamaged door
        -> current_stun=0  is_ko=True  is_conscious=False  is_destroyed=False

        Vehicle.make(..., max_stun=0)           # an undamaged van
        -> current_stun=0  is_ko=True

    An intact door reported itself unconscious. ``ObjectCombatant.make``
    hardcodes ``current_stun=0`` because, per 6E2 p152 and ``Breakable``'s own
    docstring below, objects "take BODY and break; they have no STUN behaviour
    at all" -- so ``current_stun <= 0`` is its permanent resting state, not a
    condition. Nothing had caught fire only because ``is_ko`` had no
    production caller; ``resolution/recovery.py`` became the first one in the
    same change, which is why this had to be fixed before that was wired up.

    ``StatBlockCombatant`` and ``HeroCombatant`` mix this in.
    ``ObjectCombatant`` deliberately does not (it opts back out -- see
    ``breakables/object_combatant.py``) and ``Vehicle`` narrows it for the
    no-STUN-track case.
    """

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
