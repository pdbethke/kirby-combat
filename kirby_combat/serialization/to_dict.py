"""Convert engine objects to JSON-safe dicts.

Every output dict includes `__type__` discriminator for from_dict to dispatch.
Primitives pass through unchanged. Enum values emit `.value`. Sets emit as lists.
Tuples emit as lists (JSON has no tuple). Datetimes emit as ISO strings.
"""
from __future__ import annotations

from dataclasses import is_dataclass, fields
from datetime import datetime
from enum import Enum
from typing import Any

from kirby_combat.models import StatBlockCombatant

# The wire tag is a contract with PERSISTED data (payload_jsonb rows already
# written to combat_session), not a mirror of the Python class name. When
# StatBlockCombatant was renamed from `Combatant` (combatant-redesign step
# 6), `type(obj).__name__` changed out from under every already-recorded
# session -- so this ONE type's tag is pinned explicitly rather than
# derived, keyed on the exact type (not `isinstance`) so Vehicle and
# ObjectCombatant, which subclass StatBlockCombatant but were never called
# "Combatant" on the wire, are untouched.
_STABLE_WIRE_TAGS: dict[type, str] = {
    StatBlockCombatant: "Combatant",
}


def to_dict(obj: Any) -> Any:
    """Recursively convert to JSON-safe shape."""
    if obj is None or isinstance(obj, (int, float, str, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, set) or isinstance(obj, frozenset):
        return sorted([to_dict(x) for x in obj], key=str)
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}

    # HeroCombatant special case: don't dump the full LoadedHero (huge,
    # not portable). Project to a flat snapshot with the same fields
    # the legacy Combatant emits, marked with __type__ so from_dict
    # routes back through the HD-shaped reconstruction.
    # See spec §7 — combatant snapshots are point-in-time, not the
    # canonical character. JSONB blob in combat_session.combatants_jsonb
    # only needs enough to rehydrate combat state.
    from kirby_combat.hero_view import HeroCombatant
    if isinstance(obj, HeroCombatant):
        s = obj.combat_stats()
        return {
            "__type__": "HeroCombatant",
            "id": obj.id,
            "name": obj.name,
            "ocv": s.ocv, "dcv": s.dcv, "omcv": s.omcv, "dmcv": s.dmcv,
            "spd": s.spd, "dex": s.dex, "ego": s.ego, "str_": s.str_,
            "con": s.con, "pre": s.pre, "rec": s.rec,
            "pd": s.pd, "ed": s.ed, "rpd": s.rpd, "red": s.red,
            "md": s.md,
            "power_defense": s.power_defense,
            "flash_defense": s.flash_defense,
            "max_stun": s.max_stun, "max_body": s.max_body, "max_end": s.max_end,
            "current_stun": obj.state.current_stun,
            "current_body": obj.state.current_body,
            "current_end": obj.state.current_end,
            "statuses": sorted(obj.state.statuses),
            "drains": dict(obj.state.drains),
            "aids": dict(obj.state.aids),
            "used_charges": dict(obj.state.used_charges),
            "active_slot_per_framework": dict(obj.state.active_slot_per_framework),
            "last_acted_segment": obj.state.last_acted_segment,
            "aborted": obj.state.aborted,
            "knockback_resistance": obj.knockback_resistance,
            # Public-view projection of attacks/defenses (the lossy
            # fields that round-trip through synthetic_combatant on
            # the from_dict side).
            "attacks": [to_dict(a) for a in obj.attacks],
            "defenses": [to_dict(d) for d in obj.defenses],
        }

    if is_dataclass(obj):
        type_tag = _STABLE_WIRE_TAGS.get(type(obj), type(obj).__name__)
        result: dict[str, Any] = {"__type__": type_tag}
        for f in fields(obj):
            result[f.name] = to_dict(getattr(obj, f.name))
        return result
    # Fallback: try vars()
    if hasattr(obj, "__dict__"):
        type_tag = _STABLE_WIRE_TAGS.get(type(obj), type(obj).__name__)
        result = {"__type__": type_tag}
        for k, v in vars(obj).items():
            if not k.startswith("_"):
                result[k] = to_dict(v)
        return result
    raise TypeError(f"cannot serialize {type(obj).__name__}")
