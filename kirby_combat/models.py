"""HERO System 6E combat data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kirby_combat.participant import CombatParticipant, Stunnable


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
    is_ranged: bool = False       # True when range_m > 0
    reach_m: float = 0.0         # effective melee reach in metres (0.0 for ranged)
    avad: bool = False              # Attack Versus Alternate Defense / NND
    avad_defense: str = ""          # the named alternate defense (free text); "" when avad is False
    avad_does_body: bool = False    # AVAD does STUN only (6E1 p328) unless it bought Does BODY (+1)
    framework_xmlid: str = ""       # owning framework's TYPE (display / rules only)
    # The owning framework's object id — what consumers key on. The xmlid above
    # is a type and is ambiguous for the 113 corpus characters carrying two or
    # more frameworks. "" for a top-level power.
    framework_id: str = ""
    slot_id: str = ""               # the slot power's own object id ("" for a top-level power)
    # Identity of the power this view was derived from. The xmlid is a TYPE
    # ("this is an Energy Blast"), not an identity — a character can carry
    # several of the same type, and consumers that needed to find the source
    # power again were reduced to matching on xmlid + name. That is fragile in
    # both directions: two powers sharing a name both match, and a rename
    # silently detaches a power from its modifiers. It also failed outright
    # whenever the name was absent, which silently disabled AOE / TRIGGER /
    # SIDEEFFECTS / INCREASEDEND detection across the whole corpus.
    # None for synthetic views (the bare STR strike) that have no source power.
    source_id: int | None = None


@dataclass
class SlotView:
    """One slot in a framework (Multipower / Elemental Control / VPP)."""

    slot_id: str
    name: str
    active_points: int
    variable: bool
    kind: str                       # "attack" | "defense" | "movement" | "other"
    attack: "AttackPower | None" = None


@dataclass
class FrameworkView:
    """A power framework (Multipower / Elemental Control / VPP) with its
    reserve/pool size and typed slots. Populated by
    ``HeroCombatant.framework_view()``; consumed by kirby-api to enumerate
    available slots and enforce the reserve."""

    # The framework object's id — what consumers index on. The xmlid below is
    # a TYPE and is ambiguous for the 113 corpus characters carrying two or
    # more frameworks; it stays for display and rules, never as a key.
    framework_id: str
    xmlid: str
    name: str
    kind: str                       # "multipower" | "elemental_control" | "vpp"
    reserve_or_pool: int
    slots: list[SlotView]


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
    damage_negation: int = 0      # in DCs (each = -1 DC pre-attack)
    knockback_resistance: int = 0
    is_resistant: bool = False
    # Damage Reduction / Damage Negation are class-split per HERO 6E:
    # bought separately for "physical", "energy", or "mental".
    # Empty string means "applies to any class" (e.g. for legacy
    # records or test fixtures where class isn't specified).
    damage_class: str = ""        # "" | "physical" | "energy" | "mental"
    # Resistant DR works on Killing too; non-resistant DR only on
    # Normal damage + AVADs. (6E1 p185.) Same flag distinguishes
    # "Resistant Damage Negation" (default) from non-resistant
    # negation taken via the Nonresistant -¼ Limitation.
    dr_resistant: bool = True


@dataclass
class CombatSkillLevel:
    """A set of Combat Skill Levels and their allocation."""

    levels: int
    applies_to: str               # "ocv" | "dcv" | "dc" | "any"


@dataclass
class StatBlockCombatant(Stunnable, CombatParticipant):
    """A character or NPC participating in combat, described by a flat stat
    block rather than a build (HDC/LoadedHero). Vehicles and breakable
    objects (a stone wall, a door) subclass this: they have BODY/DEF from a
    material table, not a LoadedHero to wrap."""

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

    # ── CombatParticipant contract, for a stat block ──────────────────
    # CombatParticipant.combat_stats() / .state are abstract: every
    # participant must say where its stats and vitals live. Here they
    # live as plain fields on self, so both members are satisfied by
    # returning self -- "my stats are me" and "my state is me" are this
    # type's correct implementation, not a placeholder standing in for
    # one. The HD-shaped HeroCombatant satisfies the same contract by
    # computing from a LoadedHero instead.

    def combat_stats(self) -> "StatBlockCombatant":
        """Return self — flat fields ARE the stats. Mirrors
        :meth:`HeroCombatant.combat_stats` for uniform access."""
        return self

    @property
    def state(self) -> "StatBlockCombatant":
        """Return self — flat ``current_*`` fields ARE the state.
        Mirrors :attr:`HeroCombatant.state` for uniform access."""
        return self


@dataclass
class AttackInput:
    """All inputs needed to resolve a single attack.

    ``attacker`` / ``target`` may be either a flat ``StatBlockCombatant`` or
    the HD-shaped ``HeroCombatant``. Both are ``CombatParticipant``s and
    expose ``.combat_stats()`` and ``.state.current_*`` as a uniform
    interface. Resolution code reads through that interface and works on
    either shape without per-call dispatch.
    """

    attacker: Any  # StatBlockCombatant | HeroCombatant
    target: Any    # StatBlockCombatant | HeroCombatant
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
    target_passed_through: bool = False    # True if KB broke through a breakable object
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


@dataclass
class MovementCapability:
    """One movement mode available to a combatant (movement spec §1).

    Produced by ``HeroCombatant.movement_view()``. Mirrors ``AttackPower``
    in role: a flat, computed view of one mode read from characteristics
    (RUNNING/LEAPING) or powers (FLIGHT/TELEPORTATION/SWIMMING/TUNNELING).

    Fields:
        mode         — canonical name: running | leaping | flight |
                       teleportation | swimming | tunneling
        combat_m     — full-phase combat movement distance in metres
        noncombat_m  — noncombat distance (combat_m × NCM per mode)
        end_per_10m  — END cost per 10 metres moved (1 or 2)
        vertical_m   — maximum vertical distance in metres this mode can
                       gain. Per mode: flight / teleportation / tunneling =
                       combat_m (full movement in any direction); leaping =
                       combat_m / 2 (6E); running / swimming = 0.0.
                       Consumed downstream as `vertical_reach` by the vantage
                       search (scene/visibility.py) — a zero here means the
                       mode can never be offered a point above ground.
        active_cost  — the cost engine's Active Points for this mode, for
                       power-derived modes only (FLIGHT / TELEPORTATION /
                       SWIMMING / TUNNELING). None for the characteristic-
                       derived modes (RUNNING / LEAPING), which have no
                       power to read a cost from. Consumed downstream to
                       turn a Push's +10 Active Points into metres
                       (metres_per_point = combat_m / active_cost); None
                       there means "this mode cannot be pushed", never a
                       guessed constant.
    """

    mode: str
    combat_m: float
    noncombat_m: float
    end_per_10m: int
    vertical_m: float = 0.0
    active_cost: float | None = None


#: Deprecated alias. The flat type was called `Combatant` when it was the only
#: kind; it is one of three now (see kirby_combat.participant).
#:
#: It is kept for kirby-api, which is the only remaining importer:
#: ``kirby/combat/services/entity_service.py`` and
#: ``kirby/builds/combatant_loader.py``. Retiring it is therefore a cross-repo
#: change -- update those two call sites first, then delete this line.
#:
#: This deliberately does NOT say "kept for one release". It used to, and that
#: was untrue: 15 modules INSIDE this package imported and annotated with the
#: alias, so the deprecation clock measured nothing and "delete it next
#: release" would have broken the package itself. Those 15 were swept to
#: `StatBlockCombatant`; nothing in kirby-combat imports this name any more.
#: Verified 2026-08-25 by grep over kirby_combat/ and tests/.
Combatant = StatBlockCombatant
