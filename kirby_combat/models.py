"""HERO System 6E combat data models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiceValues:
    """Raw dice roll results for a single attack."""

    to_hit: list[int] = field(default_factory=list)
    damage: list[int] = field(default_factory=list)
    hit_location: list[int] = field(default_factory=list)
    stun_multiplier: list[int] = field(default_factory=list)
    knockback: list[int] = field(default_factory=list)


@dataclass
class AttackPower:
    """A power or weapon used to attack."""

    xmlid: str
    name: str
    damage_dice: int
    half_die: bool
    plus_one: bool
    damage_type: str              # "normal" | "killing"
    defense_type: str             # "pd" | "ed" | "md" | "power" | "flash"
    range_m: float
    uses_str: bool
    str_min: int
    armor_piercing: int           # levels of armor piercing
    penetrating: int              # levels of penetrating
    increased_stun_mult: int      # +N to killing stun multiplier


@dataclass
class DefenseItem:
    """A single piece of armor, force field, or defensive ability."""

    name: str
    pd: int = 0
    ed: int = 0
    rpd: int = 0
    red: int = 0
    md: int = 0
    power_defense: int = 0
    flash_defense: int = 0
    hardened: int = 0             # levels of hardened
    impenetrable: int = 0         # levels of impenetrable
    damage_reduction_pct: int = 0
    damage_negation: int = 0
    knockback_resistance: int = 0
    is_resistant: bool = False


@dataclass
class CombatSkillLevel:
    """A set of Combat Skill Levels and their allocation."""

    levels: int
    applies_to: str               # "ocv" | "dcv" | "dc" | "any"


@dataclass
class Combatant:
    """A character or NPC participating in combat."""

    id: str
    name: str
    ocv: int
    dcv: int
    omcv: int
    dmcv: int
    spd: int
    dex: int
    ego: int
    str_: int
    con: int
    pre: int
    rec: int
    pd: int
    ed: int
    rpd: int
    red: int
    md: int
    power_defense: int
    flash_defense: int
    max_stun: int
    max_body: int
    max_end: int
    current_stun: int
    current_body: int
    current_end: int
    attacks: list[AttackPower] = field(default_factory=list)
    defenses: list[DefenseItem] = field(default_factory=list)
    csls: list[CombatSkillLevel] = field(default_factory=list)
    is_mentalist: bool = False
    is_npc: bool = False
    knockback_resistance: int = 0


@dataclass
class AttackInput:
    """All inputs needed to resolve a single attack."""

    attacker: Combatant
    target: Combatant
    power: AttackPower
    distance_m: float | None
    aim: str | None
    dice: DiceValues
    ocv_modifier: int = 0
    dcv_modifier: int = 0
    dc_modifier: int = 0


@dataclass
class ToHitResult:
    """Result of the to-hit calculation."""

    hit: bool
    roll: int
    target_number: int
    margin: int
    effective_ocv: int
    effective_dcv: int
    range_penalty: int
    hit_location_penalty: int
    csl_bonus: int
    audit: list[str] = field(default_factory=list)


@dataclass
class DamageResult:
    """Result of the damage roll and application."""

    stun: int
    body: int
    dice_values: DiceValues
    damage_type: str
    hit_location: str
    stun_multiplier: int
    body_multiplier: float
    is_partial: bool
    audit: list[str] = field(default_factory=list)


@dataclass
class DefenseProfile:
    """Aggregated defenses for a target against a specific attack."""

    total_defense: int
    resistant_defense: int
    non_resistant_defense: int
    damage_reduction_pct: int
    damage_negation: int
    knockback_resistance: int
    defense_tags: list[str] = field(default_factory=list)
    audit: list[str] = field(default_factory=list)


@dataclass
class KnockbackResult:
    """Result of knockback calculation."""

    dice: int
    distance_m: float
    damage_dice: int
    resisted: bool
    audit: list[str] = field(default_factory=list)


@dataclass
class AttackResult:
    """Complete result of a resolved attack."""

    hit: bool
    to_hit: ToHitResult
    damage: DamageResult | None
    defense: DefenseProfile | None
    stun_dealt: int
    body_dealt: int
    end_spent: int
    knockback: KnockbackResult | None
    status_changes: list[str]
    power_xmlid: str
    audit_trail: list[str] = field(default_factory=list)
