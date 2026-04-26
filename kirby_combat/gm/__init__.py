"""GM tooling — overrides, GM-on-behalf-of attacks, spawn/despawn."""
from kirby_combat.gm.overrides import (
    make_tier1_stun_adjust, make_tier1_status_application,
    make_tier2_dice_override, make_tier2_retroactive_abort,
    make_tier3_spawn, make_tier3_scene_mutation,
    apply_tier1_override, apply_tier3_spawn, apply_tier3_despawn,
)
from kirby_combat.gm.gm_attack import (
    GMAttackDeclaration, make_gm_attack, can_actor_pay_end,
)
from kirby_combat.gm.spawn_despawn import (
    spawn_combatant, despawn_combatant,
    is_active_target, spawn_skips_immediate_segment,
)

__all__ = [
    "make_tier1_stun_adjust", "make_tier1_status_application",
    "make_tier2_dice_override", "make_tier2_retroactive_abort",
    "make_tier3_spawn", "make_tier3_scene_mutation",
    "apply_tier1_override", "apply_tier3_spawn", "apply_tier3_despawn",
    "GMAttackDeclaration", "make_gm_attack", "can_actor_pay_end",
    "spawn_combatant", "despawn_combatant",
    "is_active_target", "spawn_skips_immediate_segment",
]
