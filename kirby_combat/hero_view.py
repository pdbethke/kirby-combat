"""HD-shaped Combatant — wraps a hero-designer-python LoadedHero.

This is the "Phase 2 redesign" Combatant that supersedes the flat
``models.Combatant``. See spec at
``kirby/docs/superpowers/specs/2026-04-30-kirby-combat-combatant-redesign.md``.

Status: STEP 1 LIVE (2026-05-02). The dataclasses, ``from_hdc()``,
``combat_stats()``, ``attack_view()``, and ``defense_view()`` are
implemented and verified end-to-end against the kirby-combat
resolution engine via a to_legacy() bridge — see commit message for
the demo. Refinements pending in steps 2-4: framework slot lookup,
modifier-aware modifier accumulation, defense-power adder split for
PD vs ED.

Why this exists alongside ``models.Combatant``:

- The flat Combatant lops off power frameworks (Multipower / VPP /
  Elemental Control), modifiers (Reduced Endurance, Penetrating,
  AP, etc.), adders, and Compound power decomposition. Real HD
  characters can't be represented losslessly.
- HDC round-trip fidelity is a hard requirement (see kirby skill).
  The flat shape can't produce an equivalent HDC on export.
- The cost engine (``hero_designer.io.hdc_loader.LoadedHero``) is
  already the canonical HD-shaped model. The combat engine should
  consume it directly.

Migration path is incremental: this file ships first as a non-breaking
addition. Resolution code (``to_hit``, ``damage``, ``defense``)
keeps its current signatures — it consumes the same flat
``AttackInput`` / ``AttackPower`` / ``DefenseItem`` records. What
changes is the *construction*: instead of hand-built records on the
caller side, a HeroCombatant builds them at attack time from its
LoadedHero + state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from kirby_combat.models import AttackPower, DefenseItem

if TYPE_CHECKING:
    # Avoid forcing hero-designer-python import at module load time;
    # callers that don't use the new path won't pay the dep.
    from hero_designer.io.hdc_loader import LoadedHero


# ─────────────────────────────────────────────────────────────────────────────
# Position — kept here for now to avoid a Scene import cycle. Will move to
# kirby_combat.scene when migration step 3 lands.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Position:
    """3D position in the active Scene's coordinate space (meters)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CombatState — runtime delta over a static LoadedHero
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HeroCombatState:
    """Everything that changes during one combat session.

    The LoadedHero on a HeroCombatant is read-only during a session
    (ground truth from the HDC import). All run-time changes —
    damage taken, END spent, statuses applied, framework slot
    selection, charges burned — live here.
    """

    # Vital stat tracking
    current_stun: int
    current_body: int
    current_end: int

    # Position + status
    position: Position = field(default_factory=Position)
    statuses: set[str] = field(default_factory=set)
    """Active conditions: {"stunned", "unconscious", "entangled", "flash:N", ...}.
    String tags chosen for serializability; richer status metadata can attach
    via separate dicts when needed."""

    # Framework slot allocation
    active_slot_per_framework: dict[str, str] = field(default_factory=dict)
    """Map of framework xmlid → currently-allocated slot xmlid. Empty until
    the combatant first declares a slot use; persists across phases until
    the combatant changes allocation (which costs an action in 6E)."""

    # Adjustments (Aid/Drain/Transfer applied to this combatant)
    drains: dict[str, int] = field(default_factory=dict)
    """Stat name → -delta currently applied. Fade rate tracked separately."""
    aids: dict[str, int] = field(default_factory=dict)
    """Stat name → +delta currently applied."""

    # Charges
    used_charges: dict[str, int] = field(default_factory=dict)
    """Power xmlid → number of charges spent in this combat."""

    # Action state
    held_actions: list["Any"] = field(default_factory=list)
    """References to in-flight Held Actions; concrete shape comes from the
    session module in step 3."""
    last_acted_segment: Optional[int] = None
    aborted: bool = False
    """True if this combatant has aborted their next action this phase."""


# ─────────────────────────────────────────────────────────────────────────────
# CombatStats — computed view of effective stats at a point in time
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HeroCombatStats:
    """Effective stats AT A POINT IN TIME, derived from hero + state.

    This is what AttackInput.attacker actually needs for resolution.
    The resolution layer (``to_hit``, ``damage``, ``defense``,
    ``recovery``) reads from this — never directly from LoadedHero.

    Cheap to recompute per attack; we don't cache. If the cost engine
    ever becomes a hot-path bottleneck we can revisit.
    """

    # Combat values
    ocv: int
    dcv: int
    omcv: int
    dmcv: int
    spd: int

    # Primary characteristics
    dex: int
    ego: int
    str_: int
    con: int
    pre: int
    rec: int

    # Defenses
    pd: int
    ed: int
    rpd: int
    red: int
    md: int
    power_defense: int
    flash_defense: int

    # Vital pool maximums
    max_stun: int
    max_body: int
    max_end: int


# ─────────────────────────────────────────────────────────────────────────────
# HeroCombatant — the HD-shaped Combatant
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HeroCombatant:
    """A character/NPC in combat, sourced from a HD model.

    ``hero`` is the source of truth (LoadedHero, full HD fidelity,
    round-trippable to HDC). ``state`` carries combat-session-only
    deltas. Together they describe a combatant completely.

    Usage:

        combatant = HeroCombatant.from_hdc("/path/to/Stone_Cold.hdc")
        combatant.combat_stats()                 # → HeroCombatStats
        combatant.attack_view("CONEOFCOLD",      # → AttackPower
                              target=other,
                              distance_m=12.0)
        combatant.defense_view()                 # → list[DefenseItem]
    """

    id: str
    """Session-scoped identifier (NOT the HDC file's character_name)."""

    hero: "LoadedHero"
    """Read-only during a session. Full HD model — characteristics,
    powers, skills, modifiers, adders, frameworks."""

    state: HeroCombatState
    """All run-time changes during the session."""

    # Cached scalars (computed once at session start; updated only on
    # rare state changes like a permanent KB-RES gain)
    knockback_resistance: int = 0

    # ─────────────────────────────────────────────────────────────────────
    # Legacy-Combatant-shaped read API (combatant-redesign step 6)
    #
    # The resolution layer (to_hit / damage / defense / knockback /
    # status / adjustments) was written against the flat Combatant
    # and reads ``attacker.ocv``, ``target.pd``, ``c.current_stun``,
    # etc. directly. To let HeroCombatant flow into those code paths
    # WITHOUT rewriting every resolution call site, expose the same
    # fields as read-only properties — derived live from
    # ``combat_stats()`` and ``state``.
    #
    # These are the inverse of the no-op shims on legacy Combatant
    # (which had the fields and added ``combat_stats()``/``state``
    # accessors). Together, both shapes expose the same surface.
    # When LegacyCombatant deletes, the no-op shims go but these
    # properties stay — callers permanently use ``c.ocv`` /
    # ``c.combat_stats().ocv`` interchangeably.
    # ─────────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        n = getattr(self.hero, "name", None)
        return n or self.id

    @property
    def ocv(self) -> int: return self.combat_stats().ocv
    @property
    def dcv(self) -> int: return self.combat_stats().dcv
    @property
    def omcv(self) -> int: return self.combat_stats().omcv
    @property
    def dmcv(self) -> int: return self.combat_stats().dmcv
    @property
    def spd(self) -> int: return self.combat_stats().spd
    @property
    def dex(self) -> int: return self.combat_stats().dex
    @property
    def ego(self) -> int: return self.combat_stats().ego
    @property
    def str_(self) -> int: return self.combat_stats().str_
    @property
    def con(self) -> int: return self.combat_stats().con
    @property
    def pre(self) -> int: return self.combat_stats().pre
    @property
    def rec(self) -> int: return self.combat_stats().rec
    @property
    def pd(self) -> int: return self.combat_stats().pd
    @property
    def ed(self) -> int: return self.combat_stats().ed
    @property
    def rpd(self) -> int: return self.combat_stats().rpd
    @property
    def red(self) -> int: return self.combat_stats().red
    @property
    def md(self) -> int: return self.combat_stats().md
    @property
    def power_defense(self) -> int: return self.combat_stats().power_defense
    @property
    def flash_defense(self) -> int: return self.combat_stats().flash_defense
    @property
    def max_stun(self) -> int: return self.combat_stats().max_stun
    @property
    def max_body(self) -> int: return self.combat_stats().max_body
    @property
    def max_end(self) -> int: return self.combat_stats().max_end

    @property
    def current_stun(self) -> int: return self.state.current_stun
    @property
    def current_body(self) -> int: return self.state.current_body
    @property
    def current_end(self) -> int: return self.state.current_end

    @property
    def attacks(self) -> list[AttackPower]:
        """Build the attack list from defining hero powers. Walked
        on demand — callers that iterate this often should cache
        themselves. Top-level + sub_powers (Multipower slots)."""
        out: list[AttackPower] = []
        attack_xmlids = {
            "ENERGYBLAST", "RKA", "HKA", "EGOATTACK", "MENTALBLAST",
            "KILLINGATTACKRANGED", "KILLINGATTACKHTH",
        }
        seen: set[str] = set()
        def _walk(power_list):
            for p in power_list or []:
                x = (getattr(p, "xmlid", None) or "").upper()
                if x in attack_xmlids and x not in seen:
                    try:
                        out.append(self.attack_view(p.xmlid))
                        seen.add(x)
                    except ValueError:
                        pass
                sub = getattr(p, "sub_powers", None)
                if sub:
                    _walk(sub)
        _walk(self.hero.powers)
        return out

    @property
    def defenses(self) -> list[DefenseItem]:
        """Alias for ``defense_view()`` — read like a legacy Combatant."""
        return self.defense_view()

    @property
    def is_npc(self) -> bool:
        """Default False — combatant-redesign doesn't yet thread the
        is_npc flag through HeroCombatState. Override per-callsite if
        the legacy path was reading this."""
        return False

    @property
    def is_mentalist(self) -> bool:
        return False

    @property
    def csls(self) -> list:
        """CombatSkillLevels — empty until the relational rows are
        wired through hero_view (future step)."""
        return []

    # ─────────────────────────────────────────────────────────────────────
    # Factories
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def from_hdc(cls, path: str | Path, *, id: Optional[str] = None) -> "HeroCombatant":
        """Load a HeroCombatant from an HDC file on disk.

        Uses ``hero_designer.io.hdc_loader.HDCLoader`` to parse the
        file, then constructs initial CombatState with full vitals.
        ``id`` defaults to the hero's name (lowercased, spaces →
        underscores) — caller can override for session-unique IDs.
        """
        from hero_designer.io.hdc_loader import HDCLoader

        loader = HDCLoader()
        hero = loader.load_file(str(path))

        combatant_id = id if id is not None else (
            hero.name.lower().replace(" ", "_") if hero.name else "unnamed"
        )

        # Compute CombatStats once to derive the initial vitals.
        # combat_stats() will be filled in by a subsequent commit; for
        # now we plug in placeholder zeros so the from_hdc() path is at
        # least round-trippable through the dataclass shell.
        try:
            stats = cls._compute_stats_skeleton(hero)
            initial_stun = stats.max_stun
            initial_body = stats.max_body
            initial_end = stats.max_end
        except NotImplementedError:
            initial_stun = 0
            initial_body = 0
            initial_end = 0

        return cls(
            id=combatant_id,
            hero=hero,
            state=HeroCombatState(
                current_stun=initial_stun,
                current_body=initial_body,
                current_end=initial_end,
            ),
            knockback_resistance=0,  # computed in a later commit
        )

    @staticmethod
    def _compute_stats_skeleton(hero: "LoadedHero") -> HeroCombatStats:
        """Initial-vital seed for from_hdc(). Reads cost-engine
        characteristic values via ``hero.characteristic_value(xmlid)``
        and walks defense-type powers for resistant/mental/power/flash
        totals.

        This is a sub-piece of the full ``combat_stats()`` that runs
        without a CombatState (since at from_hdc() time there's no
        state yet to apply drains/aids from). The full instance method
        layers state deltas on top.
        """
        return _compute_stats_from_hero(hero)

    # ─────────────────────────────────────────────────────────────────────
    # Views (consumed by the resolution layer)
    # ─────────────────────────────────────────────────────────────────────

    def combat_stats(self) -> HeroCombatStats:
        """Effective integer stats at this moment.

        Reads cost-engine-computed characteristic values from
        ``hero.characteristic_value(xmlid)``, walks defense powers for
        resistant/mental/power/flash totals, then applies any active
        drains/aids from ``state``.
        """
        stats = _compute_stats_from_hero(self.hero)
        # Apply drains (negative deltas) + aids (positive deltas).
        # Drain stats keys match HeroCombatStats field names.
        for stat, delta in self.state.drains.items():
            current = getattr(stats, stat, None)
            if current is not None:
                setattr(stats, stat, max(0, current - delta))
        for stat, delta in self.state.aids.items():
            current = getattr(stats, stat, None)
            if current is not None:
                setattr(stats, stat, current + delta)
        return stats

    def attack_view(
        self,
        power_xmlid: str,
        *,
        slot_xmlid: Optional[str] = None,
        target: Optional["HeroCombatant"] = None,
        distance_m: Optional[float] = None,
    ) -> AttackPower:
        """Build an ``AttackPower`` view from one of this combatant's HD powers.

        Walks ``hero.powers`` for the matching xmlid (or framework slot),
        reads levels + base/level cost rules to compute damage_dice,
        scans assigned modifiers for Penetrating / Armor Piercing /
        Reduced Endurance flags, and returns the flat record the
        resolution layer consumes.
        """
        power = _find_power(self.hero, power_xmlid, slot_xmlid=slot_xmlid)
        if power is None:
            raise ValueError(
                f"power xmlid={power_xmlid!r} not found on {self.id!r}"
            )
        return _build_attack_power(power)

    def defense_view(self) -> list[DefenseItem]:
        """Build the active defense set from HD powers.

        Walks all defense-type powers (FORCEFIELD, RESISTANTPROTECTION,
        ARMOR, DAMAGEREDUCTION, MENTALDEFENSE, POWERDEFENSE,
        FLASHDEFENSE, KBRESISTANCE, etc.) and emits one DefenseItem
        per active defensive power. Characteristic-derived defenses
        (PD/ED) are NOT in this list — those go on CombatStats and
        the resolution layer reads them there. DefenseItem rows here
        represent power-bought defenses on top of the base.
        """
        items: list[DefenseItem] = []
        for power in self.hero.powers:
            xmlid = (getattr(power, "xmlid", None) or "").upper()
            item = _power_to_defense_item(power, xmlid)
            if item is not None:
                items.append(item)
        return items


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — pure functions over a LoadedHero. These are the bridge between
# HD's full-fidelity model and the flat AttackPower / DefenseItem records the
# resolution layer consumes.
# ─────────────────────────────────────────────────────────────────────────────


# Defense xmlids that appear on hero.powers and contribute to defense_view().
_DEFENSE_XMLIDS = {
    "FORCEFIELD",                    # 6E: still parses; display 'Resistant Protection'
    "RESISTANTPROTECTION",
    "ARMOR",                          # 5E carryover; some HDC files still use it
    "DAMAGENEGATION",
    "DAMAGEREDUCTION",
    "MENTALDEFENSE",
    "POWERDEFENSE",
    "FLASHDEFENSE",
    "KBRESISTANCE",
    "FORCEWALL",                      # treats as defensive in this iteration
}


def _has_modifier(power, mod_xmlid: str) -> bool:
    """True if the power has an assigned modifier matching xmlid."""
    mods = getattr(power, "assigned_modifiers", None) or []
    target = mod_xmlid.upper()
    for m in mods:
        if (getattr(m, "xmlid", None) or "").upper() == target:
            return True
    return False


def _modifier_levels(power, mod_xmlid: str) -> int:
    """Return the levels on a specific modifier (0 if missing)."""
    mods = getattr(power, "assigned_modifiers", None) or []
    target = mod_xmlid.upper()
    for m in mods:
        if (getattr(m, "xmlid", None) or "").upper() == target:
            return int(getattr(m, "levels", 0) or 0)
    return 0


def _compute_stats_from_hero(hero: "LoadedHero") -> HeroCombatStats:
    """Read cost-engine characteristic values + sum defense powers.

    ``hero.characteristic_value(xmlid)`` returns the effective integer
    after all bumps + figured-from-primary derivations, so the
    primaries (STR/DEX/CON/INT/EGO/PRE) and combat values
    (OCV/DCV/OMCV/DMCV/SPD) plus PD/ED/REC/END/STUN/BODY come straight
    from there.

    Resistant defenses (rPD/rED), MD, POWD, FLASHD are bought via
    powers, not characteristics. We walk hero.powers to total them.
    """
    cv = hero.characteristic_value

    pd_bonus = 0   # extra non-resistant PD bought via PD-power rows
    ed_bonus = 0   # extra non-resistant ED bought via ED-power rows
    rpd = 0
    red = 0
    md = 0
    powd = 0
    flashd = 0
    for p in hero.powers:
        xmlid = (getattr(p, "xmlid", None) or "").upper()
        levels = int(getattr(p, "levels", 0) or 0)
        if xmlid in {"FORCEFIELD", "RESISTANTPROTECTION", "ARMOR"}:
            # In 6E, levels on these powers can be split via PD/ED
            # adders. Without per-adder parsing we assume the levels
            # split half-and-half. Refined in step 3+.
            rpd += levels // 2 + (levels % 2)
            red += levels // 2
        elif xmlid == "PD":
            # Bare PD as a *power* row (e.g. Takofanes' "Undying Form"
            # buys +23 PD as a non-resistant defense power, separate
            # from the PD characteristic). Adds straight to PD total.
            pd_bonus += levels
        elif xmlid == "ED":
            ed_bonus += levels
        elif xmlid == "MENTALDEFENSE":
            md += levels
        elif xmlid == "POWERDEFENSE":
            powd += levels
        elif xmlid == "FLASHDEFENSE":
            flashd += levels

    return HeroCombatStats(
        ocv=cv("OCV"),
        dcv=cv("DCV"),
        omcv=cv("OMCV"),
        dmcv=cv("DMCV"),
        spd=cv("SPD"),
        dex=cv("DEX"),
        ego=cv("EGO"),
        str_=cv("STR"),
        con=cv("CON"),
        pre=cv("PRE"),
        rec=cv("REC"),
        pd=cv("PD") + pd_bonus,
        ed=cv("ED") + ed_bonus,
        rpd=rpd,
        red=red,
        md=md,
        power_defense=powd,
        flash_defense=flashd,
        max_stun=cv("STUN"),
        max_body=cv("BODY"),
        max_end=cv("END"),
    )


def _power_to_defense_item(power, xmlid: str) -> DefenseItem | None:
    """Convert a defense-type HD power to a DefenseItem record.

    Returns None if the power is not a defense type (caller iterates
    every power and filters via this).
    """
    if xmlid not in _DEFENSE_XMLIDS:
        return None

    name = (getattr(power, "name", None) or "").strip() or xmlid
    levels = int(getattr(power, "levels", 0) or 0)
    hardened = _modifier_levels(power, "HARDENED")
    impenetrable = _modifier_levels(power, "IMPENETRABLE")

    if xmlid in {"FORCEFIELD", "RESISTANTPROTECTION", "ARMOR"}:
        rpd = levels // 2 + (levels % 2)
        red = levels // 2
        return DefenseItem(
            name=name, rpd=rpd, red=red,
            hardened=hardened, impenetrable=impenetrable,
            is_resistant=True,
        )
    if xmlid == "DAMAGEREDUCTION":
        # Levels mean different things by power-skill choice; treat
        # raw levels as the % reduction and refine in step 3+.
        return DefenseItem(name=name, damage_reduction_pct=levels)
    if xmlid == "DAMAGENEGATION":
        return DefenseItem(name=name, damage_negation=levels)
    if xmlid == "MENTALDEFENSE":
        return DefenseItem(name=name, md=levels, hardened=hardened)
    if xmlid == "POWERDEFENSE":
        return DefenseItem(name=name, power_defense=levels, hardened=hardened)
    if xmlid == "FLASHDEFENSE":
        return DefenseItem(name=name, flash_defense=levels, hardened=hardened)
    if xmlid == "KBRESISTANCE":
        return DefenseItem(name=name, knockback_resistance=levels)
    return None


# Damage-dice computation: HERO 6E charges per d6 of damage by power.
# Energy Blast / Blast: 5 pts/d6.
# Killing Attacks: 15 pts/d6 for the first die, with half-die granularity.
# Mental Blast / Ego Attack: 10 pts/d6.
# RKA-class falls under killing.
_PTS_PER_DIE_NORMAL = 5
_PTS_PER_DIE_KILLING = 15
_PTS_PER_DIE_MENTAL = 10


def _damage_type_for_power(xmlid: str) -> str:
    """Return AttackPower.damage_type ('normal'|'killing'|'mental')
    based on the source power xmlid."""
    if xmlid in {"RKA", "HKA", "KILLINGATTACK", "KILLINGATTACKRANGED",
                 "KILLINGATTACKHTH"}:
        return "killing"
    if xmlid in {"EGOATTACK", "MENTALBLAST"}:
        return "mental"
    return "normal"


def _defense_type_for_power(xmlid: str) -> str:
    """Return AttackPower.defense_type ('pd'|'ed'|'mental') for which
    defense category the attack tests against."""
    if xmlid in {"EGOATTACK", "MENTALBLAST"}:
        return "mental"
    # Energy Blast / RKA / HKA typically alternate by SFX. Without a
    # reliable signal in hero-designer-python's parse we default to
    # PD for HKA/HTH and ED for ranged blasts. Refined in step 4
    # when SFX-aware modifiers land.
    if xmlid in {"HKA", "KILLINGATTACKHTH", "STR", "HANDTOHANDATTACK",
                 "HANDTOHAND"}:
        return "pd"
    return "ed"


def _compute_damage_dice(power, xmlid: str) -> tuple[int, bool, bool]:
    """Return (full_dice, half_die, plus_one) from HD's level fields.

    HD stores ``levels`` as the buy count, ``level_value`` as the
    dice/level increment, and ``level_cost`` as points/level.
    For normal attacks (Energy Blast / Blast): level_cost=5,
    level_value=1.0 → each level = 1 d6.
    For killing attacks (HKA / RKA): level_cost=5, level_value=⅓
    in the cost engine — they advance ½d6 per level via a special
    counter.

    We use ``levels * level_value`` for normal/mental and a
    half-die-step counter for killing.
    """
    levels = int(getattr(power, "levels", 0) or 0)
    level_value = float(getattr(power, "level_value", 1.0) or 1.0)
    damage_type = _damage_type_for_power(xmlid)

    if damage_type == "killing":
        # Killing attacks step ½d6 every level. 1 lvl = 1 pip / 0,
        # 2 lvls = ½d6, 3 lvls = 1d6, etc. Inspect base_cost too:
        # if base_cost ≥ 15 the power starts at 1d6 K and levels add.
        base_cost = float(getattr(power, "base_cost", 0) or 0)
        # Total dice expressed as half-d6 steps (5 = 1d6+1, 4 = 1d6, etc.)
        # Approximation: each level adds 1 step. base_cost 0 starts at 0.
        steps = levels  # half-die steps
        if base_cost >= 15:
            # Power starts at 1d6 (= 2 steps) and levels add on top.
            steps += 2
        full = steps // 2
        half = bool(steps % 2)
        return full, half, False

    if damage_type == "mental":
        full = int(levels * level_value)
        return full, False, False

    # Normal (Energy Blast etc.)
    full = int(levels * level_value)
    return full, False, False


def _find_power(hero: "LoadedHero", power_xmlid: str, *,
                slot_xmlid: Optional[str] = None):
    """Locate a power by xmlid on hero.powers, walking sub_powers.

    Search order:
      1. If ``slot_xmlid`` is given, find the framework (parent) by
         ``power_xmlid`` and return its slot whose xmlid matches.
      2. Otherwise, breadth-first walk of ``hero.powers`` and every
         power's ``sub_powers``, returning the first xmlid match.
         This means a top-level Energy Blast wins over a Multipower
         slot Energy Blast — top-level is examined first.

    Step 3 will wire proper slot-allocation lookup driven by the
    session's ``active_slot_per_framework`` state.
    """
    target = power_xmlid.upper()

    if slot_xmlid is not None:
        slot_target = slot_xmlid.upper()
        for p in hero.powers:
            x = (getattr(p, "xmlid", None) or "").upper()
            if x == target:
                for sub in getattr(p, "sub_powers", None) or []:
                    sx = (getattr(sub, "xmlid", None) or "").upper()
                    if sx == slot_target:
                        return sub
        return None

    # BFS — top-level first, then one level of sub_powers.
    queue = list(hero.powers)
    seen: set[int] = set()
    while queue:
        p = queue.pop(0)
        if id(p) in seen:
            continue
        seen.add(id(p))
        x = (getattr(p, "xmlid", None) or "").upper()
        if x == target:
            return p
        sub = getattr(p, "sub_powers", None) or []
        queue.extend(sub)
    return None


def _build_attack_power(power) -> AttackPower:
    """Project a HD power into the flat AttackPower record."""
    xmlid = (getattr(power, "xmlid", None) or "").upper()
    name = (getattr(power, "name", None) or "").strip() or xmlid
    full_dice, half_die, plus_one = _compute_damage_dice(power, xmlid)
    damage_type = _damage_type_for_power(xmlid)
    defense_type = _defense_type_for_power(xmlid)

    # Modifiers
    armor_piercing = _modifier_levels(power, "ARMORPIERCING")
    penetrating = _modifier_levels(power, "PENETRATING")
    reduced_end = _has_modifier(power, "REDUCEDEND")  # noqa: F841 (END calc TBD)

    # Range: HKA / STR-based attacks have no range; RKA + Blast etc. do.
    if xmlid in {"HKA", "KILLINGATTACKHTH", "STR", "HANDTOHANDATTACK"}:
        range_m = 0.0
    else:
        # Standard 6E ranged power: range = active points / 5 in meters.
        # We don't have active_cost for sure (some HDC parses fail);
        # fall back to levels * 5 / 5 = levels meters.
        ap = getattr(power, "active_cost", None)
        try:
            range_m = float(ap) if ap else float(getattr(power, "levels", 0))
        except (TypeError, ValueError):
            range_m = 0.0

    return AttackPower(
        xmlid=xmlid,
        name=name,
        damage_dice=full_dice,
        half_die=half_die,
        plus_one=plus_one,
        damage_type=damage_type,
        defense_type=defense_type,
        range_m=range_m,
        uses_str=(xmlid in {"HKA", "STR", "KILLINGATTACKHTH",
                            "HANDTOHANDATTACK"}),
        str_min=0,
        armor_piercing=armor_piercing,
        penetrating=penetrating,
        increased_stun_mult=0,
    )
