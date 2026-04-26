"""Presence attacks — PRE attack pipeline + effects ladder."""
from kirby_combat.pre_attacks.presence import (
    PresenceAttackResult, resolve_presence_attack,
    base_pre_dice, can_act_after,
)

__all__ = [
    "PresenceAttackResult", "resolve_presence_attack",
    "base_pre_dice", "can_act_after",
]
