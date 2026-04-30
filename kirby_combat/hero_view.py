"""HD-shaped Combatant — wraps a hero-designer-python LoadedHero.

This is the "Phase 2 redesign" Combatant that supersedes the flat
``models.Combatant``. See spec at
``kirby/docs/superpowers/specs/2026-04-30-kirby-combat-combatant-redesign.md``.

Status: SKELETON ONLY (2026-04-30). The dataclasses and from_hdc()
shell are live; ``combat_stats()``, ``attack_view()``, and
``defense_view()`` raise NotImplementedError. Subsequent commits on
the ``combatant-redesign`` branch will fill them in.

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
        """Internal: shell for combat_stats(). Filled in by next commit.

        Raises NotImplementedError so callers know the bridge is
        skeleton-only on this branch.
        """
        raise NotImplementedError(
            "HeroCombatant stat derivation lands in the next "
            "combatant-redesign commit. For now from_hdc() loads the "
            "LoadedHero and constructs the dataclass shell only."
        )

    # ─────────────────────────────────────────────────────────────────────
    # Views (consumed by the resolution layer)
    # ─────────────────────────────────────────────────────────────────────

    def combat_stats(self) -> HeroCombatStats:
        """Effective integer stats at this moment.

        Computes from ``hero.characteristics`` (with cost-engine
        derivation), then applies any active drains/aids from state.
        """
        # See spec §3 + §6. Implementation lands in next commit.
        raise NotImplementedError("combat_stats() implementation pending — next commit")

    def attack_view(
        self,
        power_xmlid: str,
        *,
        slot_xmlid: Optional[str] = None,
        target: Optional["HeroCombatant"] = None,
        distance_m: Optional[float] = None,
    ) -> AttackPower:
        """Build an AttackPower view from one of this combatant's HD powers.

        Walks the LoadedHero power tree, finds the power matching
        ``power_xmlid``, applies modifiers + adders + levels, accounts
        for active framework slot allocation, and returns the flat
        record the resolution layer consumes.
        """
        raise NotImplementedError("attack_view() implementation pending — next commit")

    def defense_view(self) -> list[DefenseItem]:
        """Build the active defense set from HD powers + state.

        Filters powers by defense type (Resistance, Defense, Force
        Field, Armor, etc.), applies modifiers, and accounts for
        sustained vs. inactive END-cost defenses.
        """
        raise NotImplementedError("defense_view() implementation pending — next commit")
