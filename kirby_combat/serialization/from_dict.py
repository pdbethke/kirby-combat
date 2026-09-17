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
        MovementCapability, FrameworkView, SlotView,
    )
    # The rest of a combatant's derived views (see hero_view.CombatantSnapshot).
    from kirby_combat.hero_view import MartialManeuverView
    from kirby_combat.perception import SenseCapability
    from kirby_combat.side import Side
    from kirby_combat.vehicles import Vehicle, Passenger
    from kirby_combat.masscombat import Unit, UnitMorale
    from kirby_combat.breakables.object_combatant import ObjectCombatant
    from kirby_combat.session.timeline import (
        Timeline, ActingSlot, ActionIntent, HeldAction,
    )
    from kirby_combat.session.combat_session import CombatSession
    # EVERY EVENT CLASS, DERIVED. This was a hand-written list beside the
    # import above, and it went stale silently: `VitalsChanged` -- the row
    # that now carries every point of STUN, BODY and END -- was in the
    # union, in `apply_event` and in the package's `__all__`, and
    # `from_dict` raised `unknown type 'VitalsChanged'` on it, so a
    # consumer persisting rows as JSON could not replay one point of
    # damage. Five more were missing with it (`BleedingSuffered`,
    # `PresenceApplied`, `PresenceFaded`, `ConstructDamaged`,
    # `ConstructSpawned`): six of twenty-eight.
    #
    # `EVENT_CLASSES` is `get_args(CombatEvent)` -- the union itself. An
    # event that exists is an event that deserialises, and there is no
    # second list to forget.
    from kirby_combat.session.events import EVENT_CLASSES, EventAuthor
    for cls in EVENT_CLASSES:
        _register(cls)
    for cls in [
        Scene, SceneBounds, Position, AmbientConditions,
        Surface, Wall, Hazard, HazardEffect,
        StatBlockCombatant, AttackPower, DefenseItem, CombatSkillLevel,
        DiceValues, AttackInput, ToHitResult, DamageResult,
        DefenseProfile, KnockbackResult, AttackResult,
        Vehicle, Passenger, Unit, ObjectCombatant,
        Timeline, ActingSlot, ActionIntent, HeldAction, CombatSession,
        EventAuthor,
        MovementCapability, FrameworkView, SlotView,
        MartialManeuverView, SenseCapability, Side,
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
    # tuple-typed fields go over the wire as a list for the same reason
    # (JSON has no tuple), and came back as one -- so
    # `BleedingSuffered.dice` (the rolled dice, 6E2 p.115) round-tripped to
    # a value that was not `==` to what went out. Found by the round-trip
    # gate once it walked the union instead of a hand-written list.
    if isinstance(field_type, str) and field_type.startswith("tuple[") and isinstance(value, list):
        return tuple(value)
    return value


def _hero_combatant_from_dict(data: dict) -> Any:
    """Rehydrate a HeroCombatant snapshot back into an instance.

    Mirrors the to_dict projection: rebuild via a synthetic-hero stub
    that reports the snapshotted characteristic values. The original
    LoadedHero is NOT round-trippable through this path (intentional —
    snapshots are point-in-time, not the canonical character; spec §7).
    To resume a session against the canonical character, call
    ``HeroCombatant.from_build(...)`` or ``hero_combatant_from_db(...)``
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

        def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
            # A snapshot has no purchase list to walk (self.powers is
            # empty above), so there is nothing conditional left to
            # apply — the snapshotted value already IS the temporal
            # value at the moment it was recorded. Consequence: this
            # is frozen, not live. Flipping identity on a rehydrated
            # combatant (``restored.state.in_hero_id = False``) is a
            # silent no-op in both directions — the stats stay exactly
            # what they were at record time regardless of ``ctx``.
            # Anyone needing a real identity flip must resume against
            # the canonical character via ``HeroCombatant.from_build(...)``
            # or ``hero_combatant_from_db(...)`` instead of this stub.
            return self.characteristic_value(xmlid)

    # The characteristic values the snapshot's stats are built from must be
    # the ones BEFORE drains and aids, because combat_stats() applies those to
    # whatever the hero reports. Reading the current (already-adjusted) values
    # applied every drain twice.
    #
    # "undrained" is written by to_dict whenever there is anything to apply.
    # Snapshots recorded before it existed are reconstructed by adding the
    # recorded adjustment back: exact, EXCEPT where a drain hit its floor and
    # clamped, which destroys the amount really taken — the same reason the
    # opening row exists in kirby-api rather than the log being walked
    # backwards.
    adjusted = data
    if "undrained" in data:
        adjusted = {**data, **data["undrained"]}
    elif data.get("drains") or data.get("aids"):
        adjusted = dict(data)
        for stat, delta in (data.get("drains") or {}).items():
            if stat in adjusted:
                adjusted[stat] = adjusted[stat] + delta
        for stat, delta in (data.get("aids") or {}).items():
            if stat in adjusted:
                adjusted[stat] = adjusted[stat] - delta

    data = adjusted
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
        in_hero_id=bool(data.get("in_hero_id", True)),
    )
    hc = HeroCombatant(
        id=data["id"],
        hero=hero,  # type: ignore[arg-type]
        state=state,
        knockback_resistance=int(data.get("knockback_resistance", 0)),
        side=from_dict(data["side"]),
        snapshot=_snapshot_from_dict(data),
    )
    return hc


#: The keys a snapshot must carry to describe a combatant that can fight.
#: NOT defaulted, and deliberately: the shape they replace defaulted every
#: one of them to empty, and an empty `attacks` list is a legal combatant --
#: so a rebuilt fighter with no attacks, no maneuvers, no frameworks and no
#: Combat Skill Levels resolved perfectly well and did nothing. A recording
#: written before this release cannot answer these questions at all, and
#: says so here rather than at the end of a fight that did no damage.
_REQUIRED_SNAPSHOT_KEYS = (
    "rpd", "red", "md", "power_defense", "flash_defense",
    "reach_m", "swimming_m", "str_source_id", "side",
    "attacks", "defenses", "csls", "senses", "movement", "maneuvers",
    "frameworks", "is_npc", "is_mentalist", "has_combat_sense",
    "has_self_contained_breathing", "skill_rolls",
)


def _snapshot_from_dict(data: dict) -> Any:
    """Rebuild the recorded views. See `hero_view.CombatantSnapshot`."""
    from kirby_combat.hero_view import CombatantSnapshot

    missing = [k for k in _REQUIRED_SNAPSHOT_KEYS if k not in data]
    if missing:
        raise ValueError(
            f"combatant snapshot {data.get('id')!r} is missing "
            f"{missing} -- it was recorded before kirby-combat 0.18.1, when "
            f"a rebuilt combatant carried no attacks, defenses, skills, "
            f"senses, movement, maneuvers, frameworks or Combat Skill "
            f"Levels and so could not fight. Re-record it from the "
            f"canonical character with HeroCombatant.from_build(...)."
        )
    return CombatantSnapshot(
        rpd=int(data["rpd"]),
        red=int(data["red"]),
        md=int(data["md"]),
        power_defense=int(data["power_defense"]),
        flash_defense=int(data["flash_defense"]),
        reach_m=float(data["reach_m"]),
        str_source_id=data["str_source_id"],
        swimming_m=float(data["swimming_m"]),
        attacks=[from_dict(a) for a in data["attacks"]],
        defenses=[from_dict(d) for d in data["defenses"]],
        csls=[from_dict(c) for c in data["csls"]],
        senses=[from_dict(x) for x in data["senses"]],
        movement=[from_dict(m) for m in data["movement"]],
        maneuvers=[from_dict(m) for m in data["maneuvers"]],
        frameworks=[from_dict(f) for f in data["frameworks"]],
        is_npc=bool(data["is_npc"]),
        is_mentalist=bool(data["is_mentalist"]),
        has_combat_sense=bool(data["has_combat_sense"]),
        has_self_contained_breathing=bool(
            data["has_self_contained_breathing"]),
        skill_rolls={str(k): int(v) for k, v in data["skill_rolls"].items()},
    )



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
