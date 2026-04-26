"""from_dict — type-dispatched deserialization."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, get_args, get_origin

# Populated below as modules are imported.
_TYPE_REGISTRY: dict[str, type] = {}


def _register(cls: type) -> None:
    _TYPE_REGISTRY[cls.__name__] = cls


def _ensure_registry() -> None:
    """Import types lazily to avoid circular deps."""
    if _TYPE_REGISTRY:
        return
    from kirby_combat.scene import (
        Scene, SceneBounds, Position, AmbientConditions,
        Surface, Wall, Hazard, HazardEffect,
    )
    from kirby_combat.models import (
        Combatant, AttackPower, DefenseItem, CombatSkillLevel,
        DiceValues, AttackInput, ToHitResult, DamageResult,
        DefenseProfile, KnockbackResult, AttackResult,
    )
    from kirby_combat.vehicles import Vehicle, Passenger
    from kirby_combat.masscombat import Unit, UnitMorale
    from kirby_combat.breakables.object_combatant import ObjectCombatant
    from kirby_combat.session.timeline import Timeline, ActingSlot, HeldAction
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.events import (
        EventAuthor, SessionStarted, SegmentAdvanced, ActionDeclared,
        ActionResolved, RecoveryTaken, MovementResolved, StatusChanged,
        AbortDeclared, HeldActionDeclared, HeldActionReleased,
        AdjustmentApplied, AdjustmentFaded, EntangleApplied, EntangleEscape,
        FlashApplied, FlashRecovered, EnvironmentalTriggered, GMOverride,
        SessionEnded,
    )
    for cls in [
        Scene, SceneBounds, Position, AmbientConditions,
        Surface, Wall, Hazard, HazardEffect,
        Combatant, AttackPower, DefenseItem, CombatSkillLevel,
        DiceValues, AttackInput, ToHitResult, DamageResult,
        DefenseProfile, KnockbackResult, AttackResult,
        Vehicle, Passenger, Unit, ObjectCombatant,
        Timeline, ActingSlot, HeldAction, CombatSession,
        EventAuthor, SessionStarted, SegmentAdvanced, ActionDeclared,
        ActionResolved, RecoveryTaken, MovementResolved, StatusChanged,
        AbortDeclared, HeldActionDeclared, HeldActionReleased,
        AdjustmentApplied, AdjustmentFaded, EntangleApplied, EntangleEscape,
        FlashApplied, FlashRecovered, EnvironmentalTriggered, GMOverride,
        SessionEnded,
    ]:
        _register(cls)
    # Enums register too so we can rehydrate enum-valued fields if needed.
    _TYPE_REGISTRY["UnitMorale"] = UnitMorale  # type: ignore[assignment]


def _coerce_field(field_type: Any, value: Any) -> Any:
    """Best-effort coerce a primitive value into its declared type.

    Handles Enum subclasses (rehydrate from value), datetime ISO strings.
    """
    # Enums rehydrate from value if value is a primitive
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        if isinstance(value, field_type):
            return value
        try:
            return field_type(value)
        except (ValueError, KeyError):
            return value
    if field_type is datetime and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def from_dict(data: Any) -> Any:
    """Reverse of to_dict. Non-dict inputs pass through."""
    if data is None or isinstance(data, (int, float, str, bool)):
        return data
    if isinstance(data, list):
        return [from_dict(x) for x in data]
    if isinstance(data, dict):
        _ensure_registry()
        type_name = data.get("__type__")
        if type_name is None:
            return {k: from_dict(v) for k, v in data.items()}
        cls = _TYPE_REGISTRY.get(type_name)
        if cls is None:
            raise TypeError(f"unknown type {type_name!r}")
        if not is_dataclass(cls):
            raise TypeError(f"type {type_name!r} is not a dataclass")
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in data:
                raw = from_dict(data[f.name])
                kwargs[f.name] = _coerce_field(f.type, raw)
        return cls(**kwargs)
    raise TypeError(f"cannot deserialize {type(data).__name__}")
