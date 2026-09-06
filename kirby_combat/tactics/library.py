"""Tactic registry + selectors.

A tactic is registered via @register at class-definition time. The
catalog is imported lazily so registration happens on first
``all_tactics()`` call.
"""
from __future__ import annotations

import importlib
from typing import Type

from kirby_combat.tactics.base import Plan, Situation, Tactic


_REGISTRY: list[Type[Tactic]] = []
_CATALOG_LOADED = False


def register(cls: Type[Tactic]) -> Type[Tactic]:
    """Decorator: register a Tactic subclass at class-definition time."""
    if cls.name and cls.name not in {c.name for c in _REGISTRY}:
        _REGISTRY.append(cls)
    return cls


def _ensure_catalog_loaded() -> None:
    global _CATALOG_LOADED
    if _CATALOG_LOADED:
        return
    # Triggers @register on each tactic class
    importlib.import_module("kirby_combat.tactics.catalog")
    _CATALOG_LOADED = True


def all_tactics() -> list[Tactic]:
    """Return one instance of every registered tactic."""
    _ensure_catalog_loaded()
    return [cls() for cls in _REGISTRY]


def applicable_tactics(situation: Situation) -> list[Tactic]:
    """Return all tactics that fire ``applicable(situation) == True``."""
    return [t for t in all_tactics() if t.applicable(situation)]


def select_tactic(
    candidates: list[Tactic], situation: Situation,
) -> Tactic | None:
    """Pick the best applicable tactic: highest priority, ties by name.

    Deterministic, and deliberately the ONLY selector the engine offers. Its
    kirby-api original took a model URL and called a selector service first,
    falling back to this on any error -- which put a network call inside a
    rules library and made the engine's answer depend on a service being up.

    A caller that wants something cleverer has the list: `applicable_tactics`
    returns everything that fires, and choosing among them is the consumer's
    job. That is the same split as enumeration -- the engine says what is
    legal, something else picks.
    """
    if not candidates:
        return None
    return sorted(candidates, key=lambda t: (-t.priority, t.name))[0]


def tactics_for(situation: Situation) -> list[Tactic]:
    """Every tactic that applies here, best first.

    `applicable()` is each tactic's own gate; this only orders what survives
    it. Priority is a fixed integer per tactic, so the ordering is stable and
    a caller can rely on the first entry being the strongest available
    suggestion rather than an arbitrary one.
    """
    return sorted(
        applicable_tactics(situation), key=lambda t: (-t.priority, t.name),
    )
