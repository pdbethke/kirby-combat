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
    from kirby_combat.hero_view import CombatantSnapshot, HeroCombatant
    if isinstance(obj, HeroCombatant):
        s = obj.combat_stats()
        # EVERY DERIVED VIEW, read off the live combatant in one place.
        # The stat keys below are not enough to fight with: `attacks`,
        # `defenses`, `csls`, `senses`, `movement_view`, `maneuver_view`,
        # `framework_view` and the rest are all computed from `hero.powers`
        # / `.skills` / `.equipment` / `.martial_arts`, and `from_dict`
        # rebuilds around a stub hero that has none of them. See
        # `CombatantSnapshot`.
        view = CombatantSnapshot.of(obj)
        snapshot = {
            "__type__": "HeroCombatant",
            "id": obj.id,
            "name": obj.name,
            "ocv": s.ocv, "dcv": s.dcv, "omcv": s.omcv, "dmcv": s.dmcv,
            "spd": s.spd, "dex": s.dex, "ego": s.ego, "int_": s.int_, "str_": s.str_,
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
            "in_hero_id": obj.state.in_hero_id,
            "knockback_resistance": obj.knockback_resistance,
            # Which part of the fight this man is on. A `Side` is an
            # object with an identity, not a label, and it was dropped on
            # the wire entirely: a rebuilt roster was an N-way free-for-all
            # in which the two men who had been allies now had to kill each
            # other, and `last_side_standing` named a different winner.
            "side": to_dict(obj.side),
            # THE DERIVED VIEWS. Everything the resolution and enumeration
            # layers read off a combatant that the flat stat keys above
            # cannot answer.
            "attacks": [to_dict(a) for a in view.attacks],
            "defenses": [to_dict(d) for d in view.defenses],
            "csls": [to_dict(c) for c in view.csls],
            "senses": [to_dict(x) for x in view.senses],
            "movement": [to_dict(m) for m in view.movement],
            "maneuvers": [to_dict(m) for m in view.maneuvers],
            "frameworks": [to_dict(f) for f in view.frameworks],
            "str_source_id": view.str_source_id,
            "reach_m": view.reach_m,
            "swimming_m": view.swimming_m,
            "is_npc": view.is_npc,
            "is_mentalist": view.is_mentalist,
            "has_combat_sense": view.has_combat_sense,
            "has_self_contained_breathing": view.has_self_contained_breathing,
            "skill_rolls": dict(view.skill_rolls),
        }
        # The stat keys above are CURRENT — drains and aids already in them.
        # The drains/aids dicts are recorded too, and combat_stats() applies
        # them to whatever the hero reports, so a rehydrated combatant applied
        # them a SECOND time: Ravel with drains={"dex": 4} read DEX 15 live and
        # 11 after a round trip. Since replay folds forward from a captured
        # snapshot, every recorded fight containing a Drain replayed with wrong
        # numbers.
        #
        # So when there is anything to apply, record the block as it stands
        # BEFORE application — which is exactly what combat_stats computes
        # first, to read a Drain's floor off. The reader rebuilds from this and
        # applies once. Written only when non-empty, so the common snapshot is
        # byte-identical to what it was.
        if obj.state.drains or obj.state.aids:
            from kirby_cost.model.activation import ActivationContext

            from kirby_combat.hero_view import _compute_stats_from_hero
            base = _compute_stats_from_hero(
                obj.hero, ActivationContext(in_hero_id=obj.state.in_hero_id))
            snapshot["undrained"] = {
                "ocv": base.ocv, "dcv": base.dcv, "omcv": base.omcv,
                "dmcv": base.dmcv, "spd": base.spd, "dex": base.dex,
                "ego": base.ego, "int_": base.int_, "str_": base.str_,
                "con": base.con, "pre": base.pre, "rec": base.rec,
                "pd": base.pd, "ed": base.ed,
                "max_stun": base.max_stun, "max_body": base.max_body,
                "max_end": base.max_end,
            }
        return snapshot

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
