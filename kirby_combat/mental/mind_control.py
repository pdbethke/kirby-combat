"""Mind Control --- an ORDER, the level it needs, and the Breakout Roll.

6E1 p.255: the mentalist makes an MCV Attack Roll, gives the target an order,
"the GM determines what level of effect the character needs on the Mind
Control Effects Table to establish that control, based on how agreeable the
target is to the command", then makes an Effect Roll, "subtracts the target's
Mental Defense (if any)", and compares. "If the Effect Roll is insufficient to
reach the desired level, the attack has no effect."

THE ORDERS a fight can give, and the level each needs, come from the book's
own combat guidance for each tier (6E1 p.256) --- see ``ORDERS``. The degree
ladder is kept for the record (what the roll WOULD have bought), but it is the
order that decides what happens.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import StatBlockCombatant
from kirby_combat.tables import mind_control_degree


#: The orders Mind Control can give in a fight, to the level over EGO each
#: needs (6E1 p.256, one row per tier's combat example):
#:
#: * ``spare`` --- "leave me and mine alone, fight someone else". EGO+10
#:   "could make the victim choose a target that's a poor choice for him to
#:   attack, but it couldn't make him leave the battle, stop fighting".
#: * ``withdraw`` --- "get out of this fight". EGO+20: "a character ...
#:   could be forced to flee from the combat ... but not to surrender,
#:   attack one of his allies/teammates, or hurt himself."
#: * ``turn`` --- "attack your friends". Beyond what EGO+20 allows, so
#:   EGO+30, "actions he is violently opposed to doing".
ORDERS: dict[str, int] = {"spare": 10, "withdraw": 20, "turn": 30}


@dataclass
class MindControlResult:
    """Result of a Mind Control Effect Roll."""
    target_id: str
    target_ego: int
    effect_rolled: int                  # the dice, before Mental Defense
    effect_total: int                   # effect_rolled - MD, floored at 0
    margin: int                         # effect_total - target_ego
    degree: str                         # none / ego_push / simple / contrary / violent
    order: str
    required_total: int                 # EGO + the order's level
    established: bool                   # effect_total >= required_total
    #: 6E1 p.152: "-1 for every 5 points of effect rolled over the minimum
    #: needed to achieve the desired level of effect". 0 when not
    #: established.
    breakout_modifier: int
    audit: list[str] = field(default_factory=list)


@dataclass
class MindControlState:
    """Active Mind Control state on a target."""
    target_id: str
    degree: str
    effect_total: int


def breakout_modifier(effect_total: int, required_total: int) -> int:
    """6E1 p.152: -1 to the Breakout Roll per full 5 points over the minimum.

    "if a mentalist tries to achieve an EGO +20 effect and rolls EGO +30 for
    his Effect Roll, the Breakout Roll is at -2." Shared by every
    continuing-effect power that establishes (Mind Control, Mind Scan).
    """
    over = effect_total - required_total
    return -(over // 5) if over > 0 else 0


def resolve_mind_control(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    effect_dice_values: list[int],
    *,
    order: str,
) -> MindControlResult:
    """Roll for ``order``: (dice - MD) against EGO + the order's level."""
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mind Control"
        )
    if order not in ORDERS:
        raise ValueError(f"unknown Mind Control order {order!r}; one of {sorted(ORDERS)}")
    rolled = sum(effect_dice_values)
    total = max(0, rolled - int(target.md))
    margin = total - target.ego
    required = target.ego + ORDERS[order]
    established = total >= required
    degree = mind_control_degree(total, target.ego)
    audit = [
        f"Mind Control ({order}): dice {rolled} - MD {target.md} = {total} vs "
        f"EGO {target.ego} + {ORDERS[order]} = {required} -> "
        f"{'ESTABLISHED' if established else 'no effect'} (degree {degree})"
    ]
    return MindControlResult(
        target_id=target.id, target_ego=target.ego,
        effect_rolled=rolled, effect_total=total, margin=margin, degree=degree,
        order=order, required_total=required, established=established,
        breakout_modifier=breakout_modifier(total, required) if established else 0,
        audit=audit,
    )


def can_break_out_with_ego_roll(
    target: StatBlockCombatant, ego_roll_dice: list[int], *, modifier: int = 0,
) -> bool:
    """The Breakout Roll: 3d6 <= EGO Roll + ``modifier`` (6E1 p.152).

    "A character's Breakout Roll equals his EGO Roll (9 + (EGO/5))", modified
    by the effect's margin (``breakout_modifier``) and, on later attempts, by
    the Time Chart bonus. Characteristic Roll rounding per 6E1 p.41.
    """
    if len(ego_roll_dice) != 3:
        raise ValueError(f"EGO roll needs 3d6, got {len(ego_roll_dice)}")
    from kirby_cost.engine.rolls import characteristic_roll
    return roll_succeeds(sum(ego_roll_dice), characteristic_roll(target.ego) + int(modifier))


def roll_succeeds(roll: int, target_number: int) -> bool:
    """A 3d6 roll-under against ``target_number``. 6E1 p.57: "a roll of 3
    always succeeds, and a roll of 18 always fails" --- which is what keeps
    a Breakout Roll at -10 from being no roll at all."""
    return roll == 3 or (roll != 18 and roll <= target_number)
