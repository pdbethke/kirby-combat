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
        StatBlockCombatant, AttackPower, DefenseItem, CombatSkillLevel,
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
        StatusEffectsChanged,
        AbortDeclared, HeldActionDeclared, HeldActionReleased,
        AdjustmentApplied, AdjustmentFaded, EntangleApplied, EntangleEscape,
        FlashApplied, FlashRecovered, EnvironmentalTriggered, GMOverride,
        SessionEnded,
    )
    for cls in [
        Scene, SceneBounds, Position, AmbientConditions,
        Surface, Wall, Hazard, HazardEffect,
        StatBlockCombatant, AttackPower, DefenseItem, CombatSkillLevel,
        DiceValues, AttackInput, ToHitResult, DamageResult,
        DefenseProfile, KnockbackResult, AttackResult,
        Vehicle, Passenger, Unit, ObjectCombatant,
        Timeline, ActingSlot, HeldAction, CombatSession,
        EventAuthor, SessionStarted, SegmentAdvanced, ActionDeclared,
        ActionResolved, RecoveryTaken, MovementResolved, StatusChanged,
        StatusEffectsChanged,
        AbortDeclared, HeldActionDeclared, HeldActionReleased,
        AdjustmentApplied, AdjustmentFaded, EntangleApplied, EntangleEscape,
        FlashApplied, FlashRecovered, EnvironmentalTriggered, GMOverride,
        SessionEnded,
    ]:
        _register(cls)
    # Enums register too so we can rehydrate enum-valued fields if needed.
    _TYPE_REGISTRY["UnitMorale"] = UnitMorale  # type: ignore[assignment]
    # `to_dict` still tags a StatBlockCombatant "Combatant" on the wire (a
    # pinned tag -- see to_dict.py -- so already-persisted sessions written
    # before the combatant-redesign rename keep loading). Accept BOTH tags
    # here so nothing written by either version fails: a fresh dict tagged
    # "StatBlockCombatant" already resolves via `_register` above (its
    # __name__); this line adds the old tag as a second name for the same
    # class.
    _TYPE_REGISTRY["Combatant"] = StatBlockCombatant


def _coerce_field(field_type: Any, value: Any) -> Any:
    """Best-effort coerce a primitive value into its declared type.

    Handles Enum subclasses (rehydrate from value), datetime ISO strings.
    `field_type` may be a string (PEP 563/forward ref) — we look it up in
    the type registry.
    """
    # Resolve string-typed (forward-ref) field types via the registry.
    resolved = field_type
    if isinstance(field_type, str):
        resolved = _TYPE_REGISTRY.get(field_type, field_type)

    if isinstance(resolved, type) and issubclass(resolved, Enum):
        if isinstance(value, resolved):
            return value
        try:
            return resolved(value)
        except (ValueError, KeyError):
            return value
    if resolved is datetime and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    # frozenset-typed fields (e.g. StatusEffectsChanged.added/.removed) go
    # over the wire as a sorted list (JSON has no set type — see
    # to_dict.py's set/frozenset branch). `field_type` is a string here
    # (PEP 563 forward ref, e.g. "frozenset[str]") since it never matches
    # a registered class; rehydrate the list back into a frozenset rather
    # than leaving it a list, so the round-tripped instance is `==` to
    # the original.
    if isinstance(field_type, str) and field_type.startswith("frozenset[") and isinstance(value, list):
        return frozenset(value)
    return value


def _hero_combatant_from_dict(data: dict) -> Any:
    """Rehydrate a HeroCombatant snapshot back into an instance.

    Mirrors the to_dict projection: rebuild via a synthetic-hero stub
    that reports the snapshotted characteristic values. The original
    LoadedHero is NOT round-trippable through this path (intentional —
    snapshots are point-in-time, not the canonical character; spec §7).
    To resume a session against the canonical character, call
    ``HeroCombatant.from_hdc(...)`` or ``hero_combatant_from_db(...)``
    instead.
    """
    from kirby_combat.hero_view import HeroCombatant, HeroCombatState

    # Inline minimal stub hero (avoids importing the test fixture from
    # production code).
    class _SnapshotHero:
        def __init__(self, name: str, char_values: dict[str, int]) -> None:
            self.name = name
            self.template_name = "snapshot"
            self.powers: list = []
            self.skills: list = []
            self.perks: list = []
            self.talents: list = []
            self.complications: list = []
            self.equipment: list = []
            self._char_values = char_values

        def characteristic_value(self, xmlid: str) -> int:
            return self._char_values.get(xmlid.upper(), 0)

    char_values = {
        "OCV": data["ocv"], "DCV": data["dcv"],
        "OMCV": data["omcv"], "DMCV": data["dmcv"],
        "SPD": data["spd"], "DEX": data["dex"], "EGO": data["ego"],
        # .get, not [...]: snapshots written before 2026-08-26 have no
        # "int_" key, and a recorded combat must still replay.
        "INT": data.get("int_", 0),
        "STR": data["str_"], "CON": data["con"], "PRE": data["pre"],
        "REC": data["rec"],
        "PD": data["pd"], "ED": data["ed"],
        "STUN": data["max_stun"], "BODY": data["max_body"],
        "END": data["max_end"],
    }
    hero = _SnapshotHero(name=data["name"], char_values=char_values)
    state = HeroCombatState(
        current_stun=int(data["current_stun"]),
        current_body=int(data["current_body"]),
        current_end=int(data["current_end"]),
        statuses=set(data.get("statuses") or []),
        drains=dict(data.get("drains") or {}),
        aids=dict(data.get("aids") or {}),
        used_charges=dict(data.get("used_charges") or {}),
        active_slot_per_framework=dict(data.get("active_slot_per_framework") or {}),
        last_acted_segment=data.get("last_acted_segment"),
        aborted=bool(data.get("aborted", False)),
    )
    hc = HeroCombatant(
        id=data["id"],
        hero=hero,  # type: ignore[arg-type]
        state=state,
        knockback_resistance=int(data.get("knockback_resistance", 0)),
    )

    # Power-derived defenses (rPD/rED/MD/POWD/FLASHD) aren't
    # characteristics in 6E — they come from powers. The snapshot
    # carries them as flat ints. The base combat_stats() walks
    # hero.powers (empty in our snapshot stub) and returns 0 for
    # all of these. Patch combat_stats() on this instance to inject
    # the snapshotted values.
    base_compute = hc.combat_stats
    snap_rpd = int(data.get("rpd", 0))
    snap_red = int(data.get("red", 0))
    snap_md = int(data.get("md", 0))
    snap_powd = int(data.get("power_defense", 0))
    snap_flashd = int(data.get("flash_defense", 0))

    def _patched_combat_stats():
        s = base_compute()
        s.rpd = snap_rpd
        s.red = snap_red
        s.md = snap_md
        s.power_defense = snap_powd
        s.flash_defense = snap_flashd
        return s

    hc.combat_stats = _patched_combat_stats  # type: ignore[method-assign]
    # The base HeroCombatant computes attacks/defenses from
    # hero.powers (empty here). Snapshot has them as flat lists —
    # patch in via instance attrs that the property checks.
    if "attacks" in data:
        hc._snapshot_attacks = [from_dict(a) for a in data["attacks"]]  # type: ignore[attr-defined]
    if "defenses" in data:
        hc._snapshot_defenses = [from_dict(d) for d in data["defenses"]]  # type: ignore[attr-defined]
    # Override the property-based attacks/defenses so rehydrated rows
    # see the snapshot. The base property looks at hero.powers (empty
    # for snapshots) and returns [].
    object.__setattr__(
        hc, "_snapshot_override_attacks", hc.__dict__.get("_snapshot_attacks", []),
    )
    object.__setattr__(
        hc, "_snapshot_override_defenses", hc.__dict__.get("_snapshot_defenses", []),
    )
    return hc


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
        # HeroCombatant: special-case path (not a flat dataclass-fields
        # roundtrip — see _hero_combatant_from_dict for the reconstruction).
        if type_name == "HeroCombatant":
            return _hero_combatant_from_dict(data)
        cls = _TYPE_REGISTRY.get(type_name)
        if cls is None:
            raise TypeError(f"unknown type {type_name!r}")
        if not is_dataclass(cls):
            raise TypeError(f"type {type_name!r} is not a dataclass")
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            # Skip init=False fields (e.g., the `kind` Literal on each event
            # subclass) — they auto-populate via __init__ default.
            if not f.init:
                continue
            if f.name in data:
                raw = from_dict(data[f.name])
                kwargs[f.name] = _coerce_field(f.type, raw)
            elif f.name == "int_":
                # StatBlockCombatant snapshots written before 2026-08-26
                # have no "int_" key. Default it rather than raising, so
                # a recorded combat can still replay.
                kwargs["int_"] = 0
        return cls(**kwargs)
    raise TypeError(f"cannot deserialize {type(data).__name__}")
