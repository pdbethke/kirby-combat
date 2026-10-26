"""Mental Illusions --- an ILLUSION named before the roll, the level it needs,
what the victim then does, and the damage an illusory attack can deal.

6E1 p.250: the mentalist makes an MCV Attack Roll; "If he succeeds, he defines
the illusion he wants the target to perceive, and the GM determines what level
of effect he needs on the Mental Illusions Effects Table to create that
illusion. The character then makes a standard Effect Roll, subtracts the
target's Mental Defense (if any), and compares the result ... If the Effect
Roll is not sufficient to reach the desired level, the attack has no effect
... If the Effect Roll is high enough ... the illusion is established in the
target's mind; the target won't know he's experiencing an illusion until he
succeeds with a Breakout Roll." Modelled exactly as Mind Control's ORDER was:
the attacker picks one of ``ILLUSIONS`` as the offer, and an established
result is a continuing effect folded by ``mental/continuing.py``, broken by
the same Breakout Rolls ("On the target's first Phase after a Mental Illusion
is established, he may attempt to see through or 'disbelieve' the illusion by
making a Breakout Roll", p.250).

THE SET OF ILLUSIONS is the book's own combat-relevant examples from each row
of the Effects Table (p.250 lists what each level covers; p.251 the EGO+30
row; p.253 harmful illusions). RULING, cosmetic changes (EGO+0) are not
offered: p.250's cosmetic list ("making friends look like (but not act like)
enemies", "a handgun looks like a different model handgun") changes nothing
the victim does, and "For the first three levels of Mental Illusions, the
victim still interacts with the real world" (p.251).

NOT APPLIED, as for Mind Control: the +/-10 for an illusion that matches or
contradicts a Psychological Complication, the +20 to make it remembered as
real, and the -5 "pre-programmed" illusion (p.251-252). The GM's extra
Breakout Rolls for an illusion that "doesn't react appropriately" (p.252) are
not rolled: the Time Chart schedule is the only one.

``attempt_disbelief`` below predates this and is NOT how a victim sees through
an illusion in a fight: p.250 makes disbelief a Breakout Roll, which is what
the loop rolls. It is kept only because it is exported.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from kirby_combat.mental.mind_control import breakout_modifier
from kirby_combat.models import StatBlockCombatant
from kirby_combat.tables import mental_illusion_degree


class IllusoryHarm(enum.Enum):
    """What an illusory attack may take off the victim (6E1 p.251 table, p.253).

    "If the attacker declares his Effect Roll at +10, the victim can take
    STUN from illusory attacks; if at +20, the character can take BODY and
    STUN." Normal Damage either way (p.253: "A character can take Normal
    Damage from a Mental Illusion").
    """
    STUN = "stun"
    STUN_AND_BODY = "stun_and_body"


@dataclass(frozen=True)
class Illusion:
    """One illusion a mentalist can cast in a fight, and what believing it does.

    Every field is stated for every illusion (no defaults): the flags are the
    effect, and an illusion that forgot one would silently do nothing.
    """
    name: str
    #: Points over EGO the Effect Roll (after Mental Defense) must reach.
    level: int
    page: str
    #: What the victim perceives, for the offer's summary.
    shows: str
    #: The illusionist vanishes from his perception (p.250, major change:
    #: "important objects (enemies, ...) ... vanish if present").
    hides_caster: bool
    #: His own side look and act like enemies (p.250, major change).
    allies_as_foes: bool
    #: He perceives nobody to fight (p.250, completely alters the setting:
    #: "a battlefield appears to be a peaceful meadow").
    no_foes: bool
    #: He no longer interacts with the real world (p.251, EGO+30).
    entranced: bool
    #: The damage the illusory attack may do, or None for a harmless one.
    harm: IllusoryHarm | None


#: p.253: "Typically causing damage requires at least 'major changes to
#: setting' (EGO +10)", plus the table's +10 (STUN) or +20 (BODY and STUN).
_MAJOR = 10
ILLUSIONS: tuple[Illusion, ...] = (
    Illusion(
        name="friends_as_foes", level=_MAJOR, page="6E1 p.250",
        shows="his friends look and act like enemies",
        hides_caster=False, allies_as_foes=True, no_foes=False, entranced=False,
        harm=None,
    ),
    Illusion(
        name="vanish", level=_MAJOR, page="6E1 p.250",
        shows="you vanish from his sight and mind",
        hides_caster=True, allies_as_foes=False, no_foes=False, entranced=False,
        harm=None,
    ),
    Illusion(
        name="phantom_attack", level=_MAJOR + 10, page="6E1 p.250-253",
        shows="an illusory attack strikes him (STUN only)",
        hides_caster=False, allies_as_foes=False, no_foes=False, entranced=False,
        harm=IllusoryHarm.STUN,
    ),
    Illusion(
        name="peaceful_meadow", level=20, page="6E1 p.250",
        shows="the battlefield becomes a peaceful meadow with nobody to fight",
        hides_caster=False, allies_as_foes=False, no_foes=True, entranced=False,
        harm=None,
    ),
    Illusion(
        name="phantom_wound", level=_MAJOR + 20, page="6E1 p.250-253",
        shows="an illusory attack wounds him (STUN and BODY)",
        hides_caster=False, allies_as_foes=False, no_foes=False, entranced=False,
        harm=IllusoryHarm.STUN_AND_BODY,
    ),
    Illusion(
        name="lost_in_illusion", level=30, page="6E1 p.251",
        shows="he is lost in another world, standing still at 1/2 DCV",
        hides_caster=False, allies_as_foes=False, no_foes=False, entranced=True,
        harm=None,
    ),
)

_BY_NAME = {i.name: i for i in ILLUSIONS}


def illusion_named(name: str) -> Illusion:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ValueError(
            f"unknown Mental Illusion {name!r}; one of {sorted(_BY_NAME)}"
        ) from None


#: RULING, 6E1 p.253: "The defense against damage from illusions is the
#: appropriate defense for the illusory attack: PD for an illusory fist, ED
#: for an illusory laser beam". The engine's illusory attack is the book's
#: own example, the Varanyi's energy pistol, so ED. The GM option to add
#: Mental Defense is not taken: Mental Defense already came off the Effect
#: Roll that sized the attack.
ILLUSORY_ATTACK_DEFENSE = "ed"

#: Normal Damage costs 5 Active Points per 1d6 (6E1 p.249 prices a Blast so),
#: which is how p.253's Storvak example turns "40 (the points of effect
#: rolled on the dice)/5" into 8d6.
_ACTIVE_POINTS_PER_DIE = 5


def illusory_attack_dice(effect_total: int, power_active_points: int) -> int:
    """6E1 p.253: "The maximum Active Points in an illusory attack equals the
    Effect Roll achieved with the Mental Illusions dice or the Active Points
    in the Mental Illusions power, whichever is less." The Effect Roll
    "achieved" is the one after Mental Defense, the figure compared with the
    table."""
    if power_active_points <= 0:
        raise ValueError("an illusory attack needs the power's Active Points")
    return min(effect_total, power_active_points) // _ACTIVE_POINTS_PER_DIE


@dataclass
class MentalIllusionResult:
    target_id: str
    target_ego: int
    effect_rolled: int           # the dice, before Mental Defense
    effect_total: int            # dice - Mental Defense, floored at 0 (6E1 p.151)
    margin: int
    degree: str
    illusion: str
    required_total: int          # EGO + the illusion's level
    established: bool
    breakout_modifier: int       # 6E1 p.152, 0 when not established
    #: The illusory attack's dice (p.253), or None for a harmless illusion.
    illusion_dice: int | None
    audit: list[str] = field(default_factory=list)


@dataclass
class DisbeliefResult:
    target_id: str
    roll: int
    target_number: int           # disbelief succeeds if roll <= TN
    success: bool
    illusion_ended: bool
    audit: list[str] = field(default_factory=list)


def resolve_mental_illusion(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    effect_dice_values: list[int],
    *,
    illusion: Illusion,
    power_active_points: int,
) -> MentalIllusionResult:
    """Roll for ``illusion``: (dice - MD) against EGO + the illusion's level.

    ``power_active_points`` sizes a harmful illusion's attack (p.253) and is
    read only when the illusion can do harm.
    """
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mental Illusion"
        )
    # 6E1 p.151: "Roll these dice, total them, and subtract the target's
    # Mental Defense (if any)."
    rolled = sum(effect_dice_values)
    total = max(0, rolled - int(target.md))
    margin = total - target.ego
    required = target.ego + illusion.level
    established = total >= required
    degree = mental_illusion_degree(total, target.ego)
    dice = (illusory_attack_dice(total, power_active_points)
            if illusion.harm is not None else None)
    audit = [
        f"Mental Illusion ({illusion.name}): dice {rolled} - MD {target.md} = {total} vs "
        f"EGO {target.ego} + {illusion.level} = {required} -> "
        f"{'ESTABLISHED' if established else 'no effect'} (degree {degree})"
    ]
    return MentalIllusionResult(
        target_id=target.id, target_ego=target.ego,
        effect_rolled=rolled, effect_total=total, margin=margin, degree=degree,
        illusion=illusion.name, required_total=required, established=established,
        breakout_modifier=breakout_modifier(total, required) if established else 0,
        illusion_dice=dice, audit=audit,
    )


def attempt_disbelief(
    target: StatBlockCombatant,
    illusion_effect_total: int,
    ego_roll_dice: list[int],
    contradiction_observed: bool,
) -> DisbeliefResult:
    """Target rolls 3d6; success if roll <= EGO + bonus from contradiction.

    Per 6E1 p109, the target only gets a disbelief check when given reason
    to doubt the illusion. The check is an EGO Roll versus the illusion's
    effect total: target rolls 3d6, must roll <= EGO_roll - (effect - EGO).
    Practically: TN = (9 + EGO/5) - max(0, illusion_effect_total - EGO).
    """
    if len(ego_roll_dice) != 3:
        raise ValueError(f"EGO roll needs 3d6, got {len(ego_roll_dice)}")
    audit: list[str] = []
    if not contradiction_observed:
        audit.append("No contradiction; no disbelief attempt allowed")
        return DisbeliefResult(
            target_id=target.id, roll=sum(ego_roll_dice),
            target_number=0, success=False, illusion_ended=False,
            audit=audit,
        )
    roll = sum(ego_roll_dice)
    from kirby_cost.engine.rolls import characteristic_roll
    base_tn = characteristic_roll(target.ego)
    illusion_margin = max(0, illusion_effect_total - target.ego)
    target_number = base_tn - illusion_margin
    success = roll <= target_number
    audit.append(
        f"Disbelief check: EGO Roll TN={target_number} (base {base_tn} - illusion margin {illusion_margin}); "
        f"roll={roll} -> {'SUCCESS' if success else 'FAIL'}"
    )
    return DisbeliefResult(
        target_id=target.id, roll=roll,
        target_number=target_number, success=success,
        illusion_ended=success, audit=audit,
    )
