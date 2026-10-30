"""Movement actions: what moves a man that he did not choose (knockback).

The `MovementAction` family (`Running`, `Leaping`, `Flight`, `Swimming`,
`Teleportation`, `Tunneling`) lived here, unused since the loop moved people
through `placement.move_toward`, with an END rule that was not 6E (`ceil(m /
10) x end_per_10m`) and a x4/x1 noncombat table nothing cited. Deleted in
0.26.0. Each of its jobs has a live home: the distance a mode allows is
`HeroCombatant.movement_view` (`combat_m`, `noncombat_m`); its END is
`endurance.movement_end` (6E1 p.158); the move itself, with a destination,
is `placement.move_toward`.
"""
