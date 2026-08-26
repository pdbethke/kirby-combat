"""Resolve a Construct's effect against an occupant — gated by the occupant's
relevant defense (physical DEF / breathing-swimming / reserved mental). Spec §1.5.

The engine returns a result; the driver applies it to combatant
state and emits events. Stays pure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from kirby_combat.scene.construct import Construct

# HERO 6E2 suffocation (~p129): a character unable to breathe loses BODY as the
# breath-hold runs out. v1 models a flat per-segment BODY loss while submerged.
SUFFOCATION_BODY_PER_SEGMENT = 1

Outcome = Literal["damage", "suffocating", "immune", "slowed", "status", "none"]


@dataclass(frozen=True)
class ConstructEffectResult:
    construct_id: str
    combatant_id: str
    outcome: Outcome
    body_loss: int = 0
    stun_loss: int = 0
    status_inflicted: str | None = None
    audit: list[str] = field(default_factory=list)


def _fires(trigger: str, segment_tick: bool) -> bool:
    if trigger == "every_segment":
        return segment_tick
    return trigger in ("on_enter", "on_pass")


def resolve_construct_effect(
    construct: Construct,
    occupant,
    *,
    segment_tick: bool,
) -> ConstructEffectResult | None:
    """Resolve `construct.effect` against `occupant` (a HeroCombatant). Returns
    None if there is no effect or it does not fire this pass."""
    eff = construct.effect
    if eff is None or not _fires(eff.trigger, segment_tick):
        return None
    cid = construct.obj_id
    oid = occupant.id

    if eff.kind == "suffocation":
        if occupant.has_self_contained_breathing():
            return ConstructEffectResult(cid, oid, "immune",
                                         audit=[f"{oid} breathes (Life Support) — immune"])
        if occupant.can_swim():
            return ConstructEffectResult(cid, oid, "slowed",
                                         audit=[f"{oid} treads water — movement slowed"])
        return ConstructEffectResult(cid, oid, "suffocating",
                                     body_loss=SUFFOCATION_BODY_PER_SEGMENT,
                                     audit=[f"{oid} cannot swim — drowning, "
                                            f"-{SUFFOCATION_BODY_PER_SEGMENT} BODY"])

    if eff.kind == "damage":
        return ConstructEffectResult(cid, oid, "damage",
                                     audit=[f"{oid} takes {eff.damage_dice}d6 "
                                            f"{eff.damage_type} from {cid}"])

    if eff.kind == "status":
        return ConstructEffectResult(cid, oid, "status", status_inflicted=eff.status_inflicted,
                                     audit=[f"{oid} gains status {eff.status_inflicted!r} from {cid}"])

    # "mental" reserved — not resolved in v1.
    return None
