"""Mind Scan --- finding a mind, and the lock-on that lets other powers reach it.

6E1 p.263-266. A character with Mind Scan "makes an MCV Attack Roll versus the
DMCV of the target mind" at an OMCV penalty for the number of minds searched
(`attack_roll.mind_scan_omcv_modifier`). If it hits, "He declares the desired
Mind Scan level and makes a standard Effect Roll using the Mind Scan Effects
Table. If the Effect Roll is not enough to reach the desired level, the Mind
Scan has no effect ... If the Effect Roll is enough to achieve the desired
effect, the character has 'locked on' to the target with Mind Scan."

The Effects Table (p.266) is read against "total rolled on Mind Scan dice -
Mental Defense". Its levels:

* Greater than EGO --- Mind Link or first-level Telepathy, the direction.
* EGO +10 --- "Mentalist can use all Mental Powers ... on target".
* EGO +20 --- "He can attack with all attacks."

A fight scans for one reason --- to put Mental Powers on somebody it cannot
see --- so the level a combatant DECLARES is ``mental_powers``. The other two
are named so a result can say what it reached.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.mental.mind_control import breakout_modifier

#: Level over EGO each Mind Scan effect needs (6E1 p.266).
MIND_SCAN_LEVELS: dict[str, int] = {"contact": 0, "mental_powers": 10, "all_attacks": 20}

#: What a scan in a fight asks for: a lock other Mental Powers can use.
COMBAT_SCAN_LEVEL = "mental_powers"


@dataclass
class MindScanResult:
    target_id: str
    target_ego: int
    effect_rolled: int
    effect_total: int            # dice - Mental Defense, floored at 0
    desired: str
    required_total: int
    established: bool
    reached: str | None          # highest level the total reaches, or None
    breakout_modifier: int
    audit: list[str] = field(default_factory=list)


def resolve_mind_scan(attacker, target, effect_dice_values: list[int], *,
                      desired: str) -> MindScanResult:
    """The Effect Roll of a Mind Scan whose MCV Attack Roll already hit."""
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mind Scan"
        )
    if desired not in MIND_SCAN_LEVELS:
        raise ValueError(f"unknown Mind Scan level {desired!r}; one of {sorted(MIND_SCAN_LEVELS)}")
    rolled = sum(effect_dice_values)
    total = max(0, rolled - int(target.md))
    required = target.ego + MIND_SCAN_LEVELS[desired]
    established = total >= required
    reached = None
    for name, level in MIND_SCAN_LEVELS.items():
        if total >= target.ego + level:
            reached = name
    audit = [
        f"Mind Scan ({desired}): dice {rolled} - MD {target.md} = {total} vs "
        f"EGO {target.ego} + {MIND_SCAN_LEVELS[desired]} = {required} -> "
        f"{'LOCKED ON' if established else 'no lock'}"
    ]
    return MindScanResult(
        target_id=target.id, target_ego=target.ego,
        effect_rolled=rolled, effect_total=total, desired=desired,
        required_total=required, established=established, reached=reached,
        breakout_modifier=breakout_modifier(total, required) if established else 0,
        audit=audit,
    )
