"""HD-shaped participant — wraps a kirby-cost LoadedHero.

This is the "Phase 2 redesign" participant that stands alongside the flat
``models.StatBlockCombatant``. See spec at
``kirby/docs/superpowers/specs/2026-04-30-kirby-combat-combatant-redesign.md``.

Status (2026-08-25): the dataclasses, ``from_hdc()``, ``combat_stats()``,
``attack_view()``, ``defense_view()``, and ``movement_view()`` are all
implemented. Stat derivation (``_compute_stats_from_hero``) reads
characteristics straight from the cost engine and walks HD powers for
resistant/mental/power/flash defenses; ``combat_stats()`` layers live
Drain/Aid deltas and the rPD/rED cap on top of that. There is no
``to_legacy()`` bridge any more — the resolution layer is driven
directly from these views.

Two things flagged in earlier commits as pending are still genuinely
open, not just stale text:
- Framework slot lookup (``_find_power`` / ``attack_view(slot_xmlid=...)``)
  finds a named slot under its parent framework, but there is no
  session-driven active-slot allocation yet.
- ``_compute_stats_from_hero`` splits FORCEFIELD/ARMOR/RESISTANTPROTECTION
  levels between PD and ED by assuming an even half-and-half split,
  because per-adder PD/ED parsing isn't wired up.

A known, tracked (not accidental) issue: a large share of this file
(``_compute_damage_dice``, ``_build_attack_power``,
``_power_to_defense_item``, ``_damage_type_for_power``,
``_modifier_levels``, ``_movement_capabilities``, and similar) derives
build facts from HD powers — work that, per the platform's stated
architecture, belongs to kirby-cost rather than the combat engine.
Moving it is deliberately out of scope here; it is tracked as §3c of
``kirby/docs/superpowers/specs/2026-08-25-combatant-redesign-addendum.md``.

Why this exists alongside ``models.StatBlockCombatant``:

- The flat stat block lops off power frameworks (Multipower / VPP /
  Elemental Control), modifiers (Reduced Endurance, Penetrating,
  AP, etc.), adders, and Compound power decomposition. Real HD
  characters can't be represented losslessly.
- HDC round-trip fidelity is a hard requirement (see kirby skill).
  The flat shape can't produce an equivalent HDC on export.
- The cost engine (``kirby_cost.io.hdc_loader.LoadedHero``) is
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

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from kirby_combat.models import AttackPower, DefenseItem, MovementCapability
from kirby_combat.participant import CombatParticipant, Stunnable


#: The Mental Powers, per 6E1 p150. Owning any one of these is what makes a
#: character a mentalist for the purposes of the mental resolvers.
#: Deliberately excludes MENTALDEFENSE (a Defence Power) and MENTALAWARENESS
#: / CLAIRSENTIENCE (Senses) — those let you resist or perceive, not attack.
MENTAL_POWER_XMLIDS = frozenset({
    "EGOATTACK",        # Mental Blast
    "MENTALILLUSIONS",
    "MINDCONTROL",
    "MINDLINK",
    "MINDSCAN",
    "TELEPATHY",
})


if TYPE_CHECKING:
    # Avoid forcing kirby-cost import at module load time;
    # callers that don't use the new path won't pay the dep.
    from kirby_cost.io.hdc_loader import LoadedHero
    # Resolve the forward-ref on senses() -> list["SenseCapability"] (mirrors
    # how MovementCapability is imported, but lazily under TYPE_CHECKING —
    # perception imports hero_view at runtime, so a top-level import would
    # cycle). Perception isn't referenced here, so it's intentionally not
    # imported.
    from kirby_combat.perception import SenseCapability


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
    # int_ used to sit here. It moved into the defaulted region below
    # (default 10) so this dataclass stays constructible by keyword
    # without INT — see int_'s new declaration for the rationale.
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

    # Movement / reach
    reach_m: float = 0.0         # effective melee reach in metres (1m base + Stretching)

    #: 6E2 p.21 names INT as the GM's tie-break alternative to a DEX Roll.
    #: Carried here because timeline sorts on it; it was absent until
    #: 2026-08-26, which made timeline's INT branch dead code.
    #: Defaults to 10 — the HERO baseline for a normal human characteristic,
    #: and the value the old ``getattr(stats, "int_", ...)`` fallback used
    #: before INT was threaded through. A non-defaulted field would make an
    #: omission a construction error, which is right *inside* this repo but
    #: does not extend across the published-package boundary: kirby-api
    #: constructs combatants by keyword without always passing int_, and a
    #: TypeError there would ship as a breaking patch release.
    int_: int = 10


@dataclass(frozen=True)
class MartialManeuverView:
    """A combat-ready martial maneuver built from a character's OWN bought
    maneuver (not the static MARTIAL_MANEUVERS table). Feeds
    MartialArtsModifiers (actions/martial_arts.py) → resolve_attack.

    The boolean flags (is_attack/is_block/is_dodge/target_falls) are derived
    from the maneuver's raw EFFECT string — grounded in real character data
    (e.g. Martial Dodge effect="Dodge, Affects All Attacks, Abort";
    Martial Throw effect="[NORMALDC] +v/10, Target Falls").
    """

    maneuver_id: str       # stable id for declare(): "{xmlid}:{name}"
    name: str              # display/alias — what the menu shows ("Martial Dodge")
    ocv: int               # parsed flat OCV modifier (velocity → 0 at view time)
    dcv: int               # parsed flat DCV modifier
    dc_bonus: int          # extra damage classes
    add_str: bool          # whether STR damage is added
    damage_type: str       # "normal" | "killing"
    phase: str             # "1/2" | "full" | "none"
    category_is_ranged: bool
    reach_m: float         # HTH reach (0.0 if ranged)
    is_attack: bool        # makes a to-hit roll (False for Dodge/Escape/Block)
    is_block: bool         # reactive Block (abort-eligible)
    is_dodge: bool         # reactive Dodge (abort-eligible)
    target_falls: bool     # target knocked prone on a hit
    effect: str            # raw EFFECT string (display + future special handling)


# ─────────────────────────────────────────────────────────────────────────────
# HeroCombatant — the participant that wraps a LoadedHero
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HeroCombatant(Stunnable, CombatParticipant):
    """A character/NPC in combat, sourced from a HD model.

    ``hero`` is the source of truth (LoadedHero, full HD fidelity,
    round-trippable to HDC). ``state`` carries combat-session-only
    deltas. Together they describe a combatant completely.

    Usage:

        combatant = HeroCombatant.from_hdc("/path/to/character.hdc")
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
    # Stat-block-shaped read API
    #
    # The resolution layer (to_hit / damage / defense / knockback /
    # status / adjustments) was written against the flat
    # ``StatBlockCombatant`` and reads ``attacker.ocv``, ``target.pd``,
    # ``c.current_stun``, etc. directly. To let HeroCombatant flow into
    # those code paths WITHOUT rewriting every resolution call site,
    # expose the same fields as read-only properties — derived live from
    # ``combat_stats()`` and ``state``.
    #
    # These are the mirror image of ``StatBlockCombatant``'s
    # ``combat_stats()``/``state`` (which return ``self``, because its flat
    # fields ARE its stats and state). Together, both shapes expose the same
    # surface, so callers use ``c.ocv`` and ``c.combat_stats().ocv``
    # interchangeably on either. Both halves are permanent — the flat type
    # was renamed, not deleted, because Vehicle and ObjectCombatant subclass
    # it and have no LoadedHero to wrap.
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
    def int_(self) -> int: return self.combat_stats().int_
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
        """Every attack-shaped power on this combatant — top-level
        + sub_powers (Multipower / framework slots). One AttackPower
        instance per source power; **no deduplication by xmlid**.

        Many characters carry multiple powers of the same xmlid
        (a small unnamed ENERGYBLAST alongside a larger themed one;
        multipower batteries with several EB slots; two HKAs bought
        separately for different limbs). Callers must be able to
        address each one — disambiguate by `AttackPower.name`,
        damage_dice, or position. Use ``attack_view(xmlid, name=...)``
        to fetch a specific instance.
        """
        out: list[AttackPower] = []
        attack_xmlids = {
            "ENERGYBLAST", "RKA", "HKA", "EGOATTACK", "MENTALBLAST",
            "KILLINGATTACKRANGED", "KILLINGATTACKHTH",
            "HANDTOHANDATTACK", "HA",
        }
        seen_ids: set[int] = set()  # recursion guard, not xmlid dedup
        def _walk(power_list):
            for p in power_list or []:
                pid = id(p)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                x = (getattr(p, "xmlid", None) or "").upper()
                if x in attack_xmlids:
                    try:
                        out.append(_build_attack_power(
                            p, str_for_augmentation=self.combat_stats().str_,
                        ))
                    except (ValueError, TypeError, AttributeError):
                        pass
                sub = getattr(p, "sub_powers", None)
                if sub:
                    _walk(sub)
        _walk(self.hero.powers)
        return out

    @property
    def defenses(self) -> list[DefenseItem]:
        """Alias for ``defense_view()`` — read like a flat stat block."""
        return self.defense_view()

    @property
    def is_npc(self) -> bool:
        """Default False — combatant-redesign doesn't yet thread the
        is_npc flag through HeroCombatState. Override per-callsite if
        the legacy path was reading this."""
        return False

    @property
    def is_mentalist(self) -> bool:
        """Does this character own a Mental Power (6E1 p150)?

        Every mental resolver gates on this — mental_blast, mental_illusion,
        mental_entangle and telepathy all open with
        ``if not attacker.is_mentalist``. It was hardcoded ``return False``
        from faa9c65 ("step 6 partial"), so no character could use a Mental
        Power at all; a corpus villain holding TELEPATHY with OMCV 6 could
        not use it.

        6E1 p150 MENTAL POWERS lists exactly six. Note what is NOT on that
        list: MENTALDEFENSE is a Defence Power and MENTALAWARENESS a Sense.
        Resisting a mental attack is not making one, and MENTALDEFENSE is the
        single most common 'mental' xmlid in the corpus (230 instances), so
        counting it would make half the roster mentalists.

        Frameworks are walked, because mentalists routinely buy their powers
        as multipower slots.
        """
        def _any_mental(powers) -> bool:
            for p in powers or ():
                if (getattr(p, "xmlid", None) or "").upper() in MENTAL_POWER_XMLIDS:
                    return True
                if _any_mental(getattr(p, "sub_powers", None)):
                    return True
            return False

        return _any_mental(getattr(self.hero, "powers", None))

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

        Uses ``kirby_cost.io.hdc_loader.HDCLoader`` to parse the
        file, then constructs initial CombatState with full vitals.
        ``id`` defaults to the hero's name (lowercased, spaces →
        underscores) — caller can override for session-unique IDs.
        """
        from kirby_cost.io.hdc_loader import HDCLoader

        loader = HDCLoader()
        hero = loader.load_file(str(path))

        combatant_id = id if id is not None else (
            hero.name.lower().replace(" ", "_") if hero.name else "unnamed"
        )

        # Compute CombatStats once to derive the initial vitals via
        # _compute_stats_from_hero (real: characteristics from the cost
        # engine + defense powers walked and summed). The
        # NotImplementedError fallback below is defensive only —
        # _compute_stats_skeleton doesn't currently raise it — kept so a
        # future skeleton failure degrades to zeros instead of raising
        # out of from_hdc().
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

        rPD/rED post-cap: resistant defenses derived from a
        characteristic (via NAKEDMODIFIER+RESISTANT) cannot exceed
        the current characteristic total. So a Drain on PD also
        reduces rPD through the cap, even without a direct rPD drain.
        Aids on rPD/rED are NOT capped — they represent external
        bonuses (e.g. Force Wall Aid).
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
        # Cap derived rPD/rED at current PD/ED (post-drain). This is
        # what makes the naked-mod-resistant promotion real-time-safe:
        # a Drain on PD shrinks the rPD pool through this cap.
        # Skip if Aid on rpd/red is in play — the aid represents an
        # external resistant defense that doesn't depend on the
        # characteristic.
        if "rpd" not in self.state.aids:
            stats.rpd = min(stats.rpd, stats.pd)
        if "red" not in self.state.aids:
            stats.red = min(stats.red, stats.ed)
        stats.reach_m = _base_reach_m(self.hero)
        return stats

    def attack_view(
        self,
        power_xmlid: str,
        *,
        slot_xmlid: Optional[str] = None,
        name: Optional[str] = None,
        target: Optional["HeroCombatant"] = None,
        distance_m: Optional[float] = None,
    ) -> AttackPower:
        """Build an ``AttackPower`` view from one of this combatant's HD powers.

        Walks ``hero.powers`` for the matching xmlid (or framework slot),
        reads levels + base/level cost rules to compute damage_dice,
        scans assigned modifiers for Penetrating / Armor Piercing /
        Reduced Endurance flags, and returns the flat record the
        resolution layer consumes.

        Disambiguation: when a combatant has multiple powers of the
        same xmlid (common — an unnamed low-dice EB alongside a larger
        named one), pass ``name=`` to
        select a specific one. Without ``name``, returns the first
        match in walk order (top-level before sub_powers). Raises
        ``ValueError`` if no power matches.
        """
        if name is not None:
            target_name = name.strip().lower()
            target_xmlid = power_xmlid.upper()

            def _walk_named(power_list):
                for p in power_list or []:
                    x = (getattr(p, "xmlid", None) or "").upper()
                    pname = (getattr(p, "name", None) or "").strip().lower()
                    if x == target_xmlid and pname == target_name:
                        return p
                    sub = getattr(p, "sub_powers", None)
                    if sub:
                        found = _walk_named(sub)
                        if found is not None:
                            return found
                return None

            power = _walk_named(self.hero.powers)
            if power is None:
                raise ValueError(
                    f"power xmlid={power_xmlid!r} name={name!r} not found "
                    f"on {self.id!r}"
                )
            return _build_attack_power(
                power, str_for_augmentation=self.combat_stats().str_,
                hero=self.hero,
            )

        power = _find_power(self.hero, power_xmlid, slot_xmlid=slot_xmlid)
        if power is None:
            raise ValueError(
                f"power xmlid={power_xmlid!r} not found on {self.id!r}"
            )
        return _build_attack_power(
            power, str_for_augmentation=self.combat_stats().str_,
            hero=self.hero,
        )

    def str_strike_view(self) -> AttackPower:
        """Build the ``AttackPower`` for this combatant's implicit Strike.

        Every HERO 6E character has a baseline Strike maneuver that
        deals ``STR / 5`` d6 normal damage at melee range, costs
        STR/10 END (rounded up, ≥ 1), and uses the character's full
        OCV/DCV. This factory builds the ``AttackPower`` view for that
        maneuver so callers don't have to synthesise one — making
        Strike a first-class engine input alongside attack_view().

        Combatants whose sheets carry a built-up STR-based attack
        (HKA Claws, MartialStrike, custom HANDTOHANDATTACK, etc.)
        should still go through ``attack_view(xmlid)`` to pick up
        modifiers and naming. ``str_strike_view`` is the bare-handed
        baseline.
        """
        stats = self.combat_stats()
        # The engine's numbers, not a second copy of its arithmetic. These
        # two lines agreed with kirby-cost on all 61 STR values when this was
        # written, which is the point: nothing was keeping them that way.
        from kirby_cost.engine.damage import strike_dice
        full_dice, half_die = strike_dice(stats.str_)
        # The bare Strike IS the character's STR, so its identity is the STR
        # characteristic's object id. This was the one view carrying no id at
        # all, and a single identity-less view is enough to force every
        # consumer to keep a string fallback beside the id path.
        str_obj = next(
            (c for c in (getattr(self.hero, "characteristics", None) or [])
             if (getattr(c, "xmlid", "") or "").upper() == "STR"),
            None,
        )
        return AttackPower(
            source_id=getattr(str_obj, "id", None),
            xmlid="STR",
            name="Strike",
            damage_dice=full_dice,
            half_die=half_die,
            plus_one=False,
            damage_type="normal",
            defense_type="pd",
            range_m=0.0,
            uses_str=True,
            str_min=0,
            armor_piercing=0,
            penetrating=0,
            increased_stun_mult=0,
            is_ranged=False,
            reach_m=stats.reach_m,
        )

    def defense_view(self) -> list[DefenseItem]:
        """Build the active defense set from HD powers.

        Walks all defense-type powers (FORCEFIELD, RESISTANTPROTECTION,
        ARMOR, DAMAGEREDUCTION, MENTALDEFENSE, POWERDEFENSE,
        FLASHDEFENSE, KBRESISTANCE, etc.) and emits one DefenseItem
        per active defensive power. Characteristic-derived defenses
        (PD/ED) are NOT in this list — those go on CombatStats and
        the resolution layer reads them there. DefenseItem rows here
        represent power-bought defenses on top of the base.

        Recursive over sub_powers: HD's compound powers (e.g. Phoenix's
        "Born In Fire" wrapping two nested DAMAGEREDUCTION children for
        Physical + Energy) need to surface every leaf defense, not
        just the parent.
        """
        items: list[DefenseItem] = []
        seen: set[int] = set()

        def _walk(power_list):
            for power in power_list or []:
                pid = id(power)
                if pid in seen:
                    continue
                seen.add(pid)
                xmlid = (getattr(power, "xmlid", None) or "").upper()
                item = _power_to_defense_item(power, xmlid)
                if item is not None:
                    items.append(item)
                _walk(getattr(power, "sub_powers", None))

        _walk(self.hero.powers)
        return items

    def movement_view(self) -> list[MovementCapability]:
        """All movement modes available to this combatant, with distances + END.

        Mirrors ``attacks`` / ``defense_view``: one ``MovementCapability``
        entry per mode the combatant actually has (combat_m > 0).

        Characteristic-derived modes (RUNNING, LEAPING) come from the
        cost-engine figured values; power-derived modes (FLIGHT,
        TELEPORTATION, SWIMMING, TUNNELING) come from ``hero.powers``
        levels → metres. Zero-distance entries are suppressed.
        """
        return _movement_capabilities(self.hero)

    def senses(self) -> list["SenseCapability"]:
        """The character's Targeting Senses (spec §1a). Normal Sight always
        present; bought sense powers (IR, Radar, Mind Scan, …) added from
        hero.powers. Mirrors movement_view()."""
        from kirby_combat.perception import _sense_capabilities
        return _sense_capabilities(self.hero)

    def has_combat_sense(self) -> bool:
        """True if this combatant has the Combat Sense Talent (spec §1a).
        The seam Plan 2 reads to negate the HtH-blind penalty; mirrors
        ``senses()``. The HtH negation lives in Plan 2."""
        from kirby_combat.perception import has_combat_sense
        return has_combat_sense(self.hero)

    def skill_roll_value(self, xmlid: str) -> int | None:
        """The 3d6 roll target for a skill the character has (e.g. STEALTH),
        from the cost engine's computed ``Skill.roll_value``. ``None`` if the
        skill is absent or has no numeric roll (caller treats None as "can't
        hide" / auto-perceived). Same source the driver's throw ``_roll_skill``
        reads.

        Verified against a real STEALTH-bearing character: ``roll_value``
        is the correct attribute and is an ``int`` for roll-based skills. Some
        skills (e.g. PROFESSIONAL_SKILL variants) expose ``roll_value`` as an
        unbound method rather than a computed value — guard against non-numeric
        so those never crash a perception contest.
        """
        want = (xmlid or "").upper()
        for sk in getattr(self.hero, "skills", None) or []:
            if (getattr(sk, "xmlid", None) or "").upper() == want:
                rv = getattr(sk, "roll_value", None)
                if rv is None:
                    return None
                try:
                    return int(rv)
                except (TypeError, ValueError):
                    return None
        return None

    def maneuver_view(self) -> list["MartialManeuverView"]:
        """Build a MartialManeuverView per bought martial maneuver on this
        character (martial-arts §3). Reads ``self.hero.martial_arts``; parses
        the HD CV grammar via ``parse_cv``; reuses ``_base_reach_m`` for HTH
        reach. Robust to a missing list (returns ``[]``) and to a maneuver
        missing any field (getattr fallbacks).

        Only real maneuvers (``xmlid == "MANEUVER"``) are surfaced — the
        loader's MARTIALARTS section also yields a blank List wrapper
        (``GENERIC_OBJECT``) and extra-damage-class elements (``EXTRADC``),
        which are not declarable maneuvers and are filtered out.

        Flag heuristics are grounded in the maneuvers' actual EFFECT strings
        (real character data), not the display names:
          - is_dodge:  "dodge" in effect  (Martial Dodge: "Dodge, ...")
          - is_block:  "block" in effect  (Defensive Block: "Block, Abort")
          - target_falls: "target falls" in effect (Throws: "...; Target Falls")
          - is_attack: a to-hit maneuver — False for Dodge/Block and for
            Escape (escapes a Grab, no offensive roll: "[STRDC] vs. Grabs").
        """
        from kirby_combat.actions.cv_parser import parse_cv

        out: list[MartialManeuverView] = []
        reach = _base_reach_m(self.hero)
        for m in getattr(self.hero, "martial_arts", None) or []:
            # Only declarable maneuvers; skip List wrappers / EXTRADC elements.
            if (getattr(m, "xmlid", "") or "").upper() != "MANEUVER":
                continue

            effect = getattr(m, "effect", "") or ""
            effect_l = effect.lower()
            ocv = parse_cv(getattr(m, "ocv", "--")).flat()
            dcv = parse_cv(getattr(m, "dcv", "--")).flat()
            is_ranged = (getattr(m, "category", "Hand To Hand") or "").strip().lower().startswith("ranged")
            dt_int = int(getattr(m, "damage_type", 0) or 0)
            damage_type = "killing" if dt_int == 3 else "normal"

            is_dodge = "dodge" in effect_l
            is_block = "block" in effect_l
            # Dodge / Block are reactive (no offensive to-hit). Escape ("vs. Grabs")
            # breaks free of a Grab and rolls no attack either.
            is_escape = "vs. grabs" in effect_l or "escape" in effect_l
            is_attack = not (is_dodge or is_block or is_escape)
            target_falls = "target falls" in effect_l

            name = str(getattr(m, "display", "") or getattr(m, "_alias", "") or "Maneuver")
            out.append(MartialManeuverView(
                # The maneuver object's own id. It was "{xmlid}:{name}", which
                # collided in 110 corpus cases (every maneuver shares the
                # xmlid "MANEUVER", so the name was carrying the whole burden)
                # and forced callers into a colon-delimited parse.
                maneuver_id=str(getattr(m, "id", "") or ""),
                name=name,
                ocv=ocv,
                dcv=dcv,
                dc_bonus=int(getattr(m, "dc", 0) or getattr(m, "dcs", 0) or 0),
                add_str=bool(getattr(m, "add_str", False)),
                damage_type=damage_type,
                phase=str(getattr(m, "phase", "1/2") or "1/2"),
                category_is_ranged=is_ranged,
                reach_m=0.0 if is_ranged else reach,
                is_attack=is_attack,
                is_block=is_block,
                is_dodge=is_dodge,
                target_falls=target_falls,
                effect=effect,
            ))
        return out

    def framework_view(self) -> "list[FrameworkView]":
        """Power frameworks (Multipower / Elemental Control / VPP) with
        reserve/pool + typed slots, each attack slot linked to its
        AttackPower. Pure read over the build model. Empty for combatants
        with no framework.

        The slot_id formula mirrors ``_build_attack_power`` exactly:
          raw_id = str(getattr(power, "id", "") or "")
          slot_id = raw_id or f'{xmlid.upper()}#{id(power)}'
        Both paths run in the same process call, so id(power) is stable
        across self.attacks and this loop (same object in hero.powers).
        """
        from kirby_cost.io.framework_access import (  # lazy
            framework_kind, framework_slots, reserve_or_pool, slot_is_variable,
            vpp_pool,
        )
        from kirby_combat.models import FrameworkView, SlotView

        attack_by_slot: dict[str, "AttackPower"] = {
            a.slot_id: a for a in self.attacks if a.slot_id
        }
        out: list[FrameworkView] = []
        for p in (self.hero.powers or []):
            kind = framework_kind(p)
            if kind is None:
                continue
            slots: list[SlotView] = []
            for child in framework_slots(self.hero, p):
                cx = (getattr(child, "xmlid", "") or "").upper()
                # Exact same formula as _build_attack_power so attack_by_slot links.
                raw_id = str(getattr(child, "id", "") or "")
                sid = raw_id or f"{cx}#{id(child)}"
                atk = attack_by_slot.get(sid)
                slots.append(SlotView(
                    slot_id=sid,
                    name=(getattr(child, "name", None) or
                          getattr(child, "alias", "") or cx),
                    active_points=int(getattr(child, "active_cost", 0) or 0),
                    variable=slot_is_variable(p, child),
                    kind=("attack" if atk is not None else "other"),
                    attack=atk,
                ))
            out.append(FrameworkView(
                # The framework's identity. Consumers matched on xmlid, which
                # is ambiguous for the 113 corpus characters carrying two or
                # more frameworks; xmlid stays for display and rules.
                framework_id=str(getattr(p, "id", "") or ""),
                xmlid=(getattr(p, "xmlid", "") or ""),
                name=(getattr(p, "name", None) or
                      getattr(p, "alias", "") or "Framework"),
                kind=kind,
                # A VPP's pool lives on ``levels`` (base_cost is 0 for a VPP),
                # so read it via vpp_pool; Multipower/EC reserve is base_cost.
                reserve_or_pool=(vpp_pool(p) if kind == "vpp"
                                 else reserve_or_pool(p)),
                slots=slots,
            ))
        return out

    def has_self_contained_breathing(self) -> bool:
        """True if a Life Support power grants Self-Contained Breathing / no need
        to breathe — immune to suffocation. Walks hero.powers (the engine reads
        the LoadedHero; there is no flat helper)."""
        # TODO: does not recurse into sub_powers — a LIFESUPPORT inside a
        # Multipower/Framework slot is missed (matches attack_view's first-pass
        # behavior; revisit if a framework-housed Life Support character appears).
        for p in getattr(self.hero, "powers", []) or []:
            if (getattr(p, "xmlid", "") or "").upper() != "LIFESUPPORT":
                continue
            blob = " ".join([
                (getattr(p, "alias", "") or ""),
                (getattr(p, "name", "") or ""),
                " ".join((getattr(a, "alias", "") or "") for a in getattr(p, "adders", []) or []),
                " ".join((getattr(a, "option_alias", "") or "") for a in getattr(p, "adders", []) or []),
            ]).lower()
            if "self-contained breathing" in blob or "does not breathe" in blob or "self contained" in blob:
                return True
        return False

    def can_swim(self) -> bool:
        """False if explicitly flagged (the 'cannot_swim' session status — set by
        a driver or demo, for e.g. a cat) OR no swimming capability; else True.
        Everyone has base Swimming in 6E, so the marker is the decisive signal."""
        if "cannot_swim" in self.state.statuses:
            return False
        try:
            swim = float(self.hero.characteristic_value("SWIMMING")) or 4.0  # 6E base swimming
        except Exception:
            swim = 4.0  # 6E base swimming
        return swim > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — pure functions over a LoadedHero. These are the bridge between
# HD's full-fidelity model and the flat AttackPower / DefenseItem records the
# resolution layer consumes.
# ─────────────────────────────────────────────────────────────────────────────

# Reach constants (reach spec §1; corrected 2026-08-31)
# _BASE_REACH_M: 1m, per THREE citations — 6E2 p56 (which sets a character's
#   base Reach at one metre), 6E2 p40 (the Range Modifier table gives the reach
#   band its own row at 1m, listed separately from the next band up), and
#   6E1 p231 (a character with no Growth can hit only targets within his own
#   Reach, one metre).
#   This was 2.0, justified in a comment as 6E hex-adjacency (2m) with no
#   page behind it. A codex search finds no rule supporting a 2m reach.
#   Consequence (once the move_strike gate lands — nothing in this engine
#   gates on reach yet): many attacks that used to resolve as a direct strike
#   will require a real close, so the move_strike composite carries more
#   traffic.
# _STRETCH_M_PER_LEVEL: each level of the Stretching power extends reach by
#   1 metre. Verified against Main6E.hdt: LVLCOST="1" LVLVAL="1" → 1 CP per
#   1m, so LEVELS == metres of stretching. Evidence: Ravel.hdc LEVELS="8"
#   → 8m stretch, total reach 9m.
_BASE_REACH_M: float = 1.0
_STRETCH_M_PER_LEVEL: float = 1.0


def _base_reach_m(hero) -> float:
    """Effective melee reach in metres: 1m base + Stretching levels (in metres).

    6E2 p56 sets a character's base Reach at one metre; 6E2 p40 and 6E1 p231
    agree.

    Mirrors the power-walk pattern used for FORCEFIELD/can_swim().
    """
    stretch = 0
    for p in getattr(hero, "powers", []) or []:
        if (getattr(p, "xmlid", None) or "").upper() == "STRETCHING":
            stretch += int(getattr(p, "levels", 0) or 0)
    return _BASE_REACH_M + stretch * _STRETCH_M_PER_LEVEL


# ─────────────────────────────────────────────────────────────────────────────
# Movement capability view (movement spec §1)
#
# _MOVE_M_PER_LEVEL: each level of a movement power adds 1 metre of combat
#   speed. Verified against a real character: FLIGHT LEVELS="15" → 15m flight
#   (characteristic_value("FLIGHT") returns 0.0 — FLIGHT is a power, not a
#   characteristic; levels map 1:1 to metres). Applies equally to
#   TELEPORTATION, SWIMMING, and TUNNELING.
#
# END/NCM table — sourced directly from the movement classes:
#   running, leaping, flight, swimming: end_per_10m=1, noncombat_multiplier=4
#   teleportation:                       end_per_10m=2, noncombat_multiplier=1
#   tunneling:                           end_per_10m=1, noncombat_multiplier=1
# ─────────────────────────────────────────────────────────────────────────────

_MOVE_M_PER_LEVEL: float = 1.0

# xmlids for movement powers (characteristics RUNNING/LEAPING handled separately)
_MOVE_POWER_XMLIDS: frozenset[str] = frozenset(
    {"FLIGHT", "TELEPORTATION", "SWIMMING", "TUNNELING"}
)

# Per-mode END cost + noncombat multiplier
# Format: mode_name → (end_per_10m, noncombat_multiplier)
_MOVE_MODE_PARAMS: dict[str, tuple[int, int]] = {
    "running":      (1, 4),
    "leaping":      (1, 4),
    "flight":       (1, 4),
    "swimming":     (1, 4),
    "teleportation": (2, 1),
    "tunneling":    (1, 1),
    "climbing":     (1, 1),     # end_per_10m=1; no noncombat climb multiplier
}

# 6E1 p70: "Climbing speed varies according to the structure being climbed, but
# the base speed is 2m per Phase (at most)." There is no CLIMBING characteristic
# and no CLIMBING power — the Skill is not a movement stat — so unlike every
# other mode this rate cannot be read from the cost engine. It is a rulebook
# constant, cited, in the same spirit as this module's END/NCM table.
_CLIMB_BASE_M: float = 2.0

# Per-mode vertical capability, as a fraction of combat_m.
#
# vertical_m is consumed downstream as `vertical_reach` (see
# scene/visibility.py: a vantage candidate over a wall only qualifies when
# `observer.z + vertical_reach >= wall_top`). A zero here means the mode can
# never be offered a point above ground, so every value must reflect what the
# mode can actually do in RAW terms:
#
#   running       0.0  — ground movement only (movement_reach._running gates
#                        on same elevation).
#   leaping       0.5  — 6E: vertical leap is half the horizontal distance;
#                        matches movement_reach._leaping's vertical_cap.
#   flight        1.0  — flight is full movement in ANY direction, straight up
#                        included; movement_reach._flight is a 3D range check
#                        (capped by the scene ceiling), not a horizontal one.
#   swimming      0.0  — only legal toward a water surface, and
#                        movement_reach._swimming requires the destination to
#                        be IN water at that surface's elevation; a vertical
#                        vantage in open air is never a legal swim landing.
#   teleportation 1.0  — you arrive anywhere within range, altitude included.
#                        movement_reach._teleportation still requires a
#                        *supported* landing, so unsupported mid-air arrivals
#                        remain refused — this only stops the vantage search
#                        being pruned before that guard ever runs.
#   tunneling     1.0  — tunneling moves through material in any direction,
#                        including up. NOTE: movement_reach._tunneling is a v1
#                        simplification (same elevation only, material DEF
#                        deferred), so a raised tunneling destination is still
#                        refused at resolution time today; this value describes
#                        the mode's capability, and is inert until that
#                        resolver grows vertical support.
_MOVE_VERTICAL_FRACTION: dict[str, float] = {
    "running":       0.0,
    "leaping":       0.5,
    "flight":        1.0,
    "swimming":      0.0,
    "teleportation": 1.0,
    "tunneling":     1.0,
    "climbing":      1.0,       # climbing is vertical by definition
}

# Map power xmlid → canonical mode name
_MOVE_XMLID_TO_MODE: dict[str, str] = {
    "FLIGHT":        "flight",
    "TELEPORTATION": "teleportation",
    "SWIMMING":      "swimming",
    "TUNNELING":     "tunneling",
}


def _movement_capabilities(hero) -> list[MovementCapability]:
    """Enumerate every movement mode available to the hero.

    Emits one ``MovementCapability`` per mode that has combat_m > 0:
    - RUNNING and LEAPING come from ``hero.characteristic_value()``; these
      are the cost-engine figured characteristics (STR-derived for LEAPING),
      already in metres.
    - FLIGHT/TELEPORTATION/SWIMMING/TUNNELING are powers — walk hero.powers
      for each xmlid and convert levels → metres via ``_MOVE_M_PER_LEVEL``.

    Zero-distance modes (no levels, or characteristic value == 0) are
    omitted so callers never see dead entries.
    """
    out: list[MovementCapability] = []

    # ── Characteristic-derived modes ────────────────────────────────────────
    for xmlid, mode in (("RUNNING", "running"), ("LEAPING", "leaping")):
        combat_m = float(hero.characteristic_value(xmlid))
        if combat_m <= 0:
            continue
        end_per_10m, ncm = _MOVE_MODE_PARAMS[mode]
        vertical_m = combat_m * _MOVE_VERTICAL_FRACTION[mode]
        out.append(MovementCapability(
            mode=mode,
            combat_m=combat_m,
            noncombat_m=combat_m * ncm,
            end_per_10m=end_per_10m,
            vertical_m=vertical_m,
        ))

    # ── Power-derived modes ─────────────────────────────────────────────────
    for p in getattr(hero, "powers", []) or []:
        xmlid = (getattr(p, "xmlid", None) or "").upper()
        if xmlid not in _MOVE_POWER_XMLIDS:
            continue
        combat_m = int(getattr(p, "levels", 0) or 0) * _MOVE_M_PER_LEVEL
        if combat_m <= 0:
            continue
        mode = _MOVE_XMLID_TO_MODE[xmlid]
        end_per_10m, ncm = _MOVE_MODE_PARAMS[mode]
        try:
            active_cost = float(getattr(p, "active_cost", None))
        except (TypeError, ValueError):
            active_cost = None
        if active_cost is not None and active_cost <= 0:
            active_cost = None      # unusable as a points-per-metre divisor
        out.append(MovementCapability(
            mode=mode,
            combat_m=combat_m,
            noncombat_m=combat_m * ncm,
            end_per_10m=end_per_10m,
            vertical_m=combat_m * _MOVE_VERTICAL_FRACTION[mode],
            active_cost=active_cost,
        ))

    # ── Climbing (6E1 p70) ──────────────────────────────────────────────────
    # Neither a characteristic nor a power, so it gets its own unconditional
    # block: EVERY hero can climb ordinary things without the Skill. Having the
    # Climbing Skill gates DIFFICULT faces (enforced by the consumer against a
    # face's climb_difficulty), not whether the mode exists.
    _climb_end, _climb_ncm = _MOVE_MODE_PARAMS["climbing"]
    out.append(MovementCapability(
        mode="climbing",
        combat_m=_CLIMB_BASE_M,
        noncombat_m=_CLIMB_BASE_M * _climb_ncm,
        end_per_10m=_climb_end,
        vertical_m=_CLIMB_BASE_M * _MOVE_VERTICAL_FRACTION["climbing"],
        active_cost=None,
    ))

    return out


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


# NAKEDMODIFIER INPUT-field parsing.
#
# HD lets you buy a "naked advantage" (xmlid=NAKEDMODIFIER) that
# applies an Advantage to a slice of an existing power or
# characteristic. The classic defensive use is "Tough As Granite":
# buy a NAKEDMODIFIER carrying RESISTANT, with INPUT="for 45 PD/45 ED",
# meaning 45 points of the character's PD and 45 of their ED become
# resistant. Without this parse, GRANITEMAN-class bricks show rPD=0
# and die to any HKA — a foundational rules error in any sim.
_INPUT_DEFENSE_RE = re.compile(
    r"(\d+)\s*(PD|ED|MD|POWD|POWER\s*DEFENSE|FLASHD|FLASH\s*DEFENSE|MENTAL\s*DEFENSE)",
    re.IGNORECASE,
)


def _parse_input_for_defenses(input_str: str | None) -> dict[str, int]:
    """Parse a NAKEDMODIFIER INPUT string into {DEFENSE_KEY: points}.

    INPUT examples seen in published HDC:
      "for 45 PD/45 ED"     → {"PD": 45, "ED": 45}
      "for 30 ED"           → {"ED": 30}
      "for 20 Mental Def"   → {"MD": 20}

    Returns empty dict on no parse.
    """
    if not input_str:
        return {}
    out: dict[str, int] = {}
    for amount, kind in _INPUT_DEFENSE_RE.findall(input_str):
        k = re.sub(r"\s+", "", kind).upper()
        # Normalise common aliases to HeroCombatStats field-keyed names
        if k in ("MENTALDEFENSE",):
            k = "MD"
        elif k in ("POWERDEFENSE",):
            k = "POWD"
        elif k in ("FLASHDEFENSE",):
            k = "FLASHD"
        out[k] = out.get(k, 0) + int(amount)
    return out


def _has_assigned_modifier(power, target_xmlid: str) -> bool:
    target = target_xmlid.upper()
    for m in getattr(power, "assigned_modifiers", None) or []:
        if (getattr(m, "xmlid", "") or "").upper() == target:
            return True
    return False


def _compute_stats_from_hero(hero: "LoadedHero") -> HeroCombatStats:
    """Read cost-engine characteristic values + sum defense powers.

    ``hero.characteristic_value(xmlid)`` returns the effective integer
    after all bumps + figured-from-primary derivations, so the
    primaries (STR/DEX/CON/INT/EGO/PRE) and combat values
    (OCV/DCV/OMCV/DMCV/SPD) plus PD/ED/REC/END/STUN/BODY come straight
    from there.

    Resistant defenses (rPD/rED), MD, POWD, FLASHD are bought via
    powers, not characteristics. We walk hero.powers to total them.

    Real-time-correctness: this function is called fresh from
    ``combat_stats()`` on every read, so Drain/Aid effects (applied
    via ``state.drains``/``state.aids``) and Armor-Piercing
    advantages (applied at attack-resolve time in
    ``resolution.defense.compute_defense``) compose on top of these
    values without staleness. Don't cache per-combatant.

    Int boundary: ``hero.characteristic_value()`` returns float (the
    cost engine computes in floats; canon HDC/build-doc imports yield
    whole-valued floats like ``OCV=4.0``). HeroCombatStats declares
    int fields and the whole resolution layer assumes integer stats
    (``pre // 5`` dice counts, ``{margin:+d}`` audit formats), so we
    coerce HERE, at the engine→combat seam, rather than sprinkling
    int() downstream. Truncation is also the rules-correct reading for
    the one legitimately fractional case (5E figured SPD, e.g. 2.7
    plays as SPD 2).
    """
    def cv(xmlid: str) -> int:
        return int(hero.characteristic_value(xmlid))

    pd_bonus = 0   # extra non-resistant PD bought via PD-power rows
    ed_bonus = 0   # extra non-resistant ED bought via ED-power rows
    rpd = 0        # resistant PD from FORCEFIELD / ARMOR / RESISTANTPROTECTION
    red = 0
    md = 0
    powd = 0
    flashd = 0

    # Slice of base PD/ED that NAKEDMODIFIER+RESISTANT (or a RESISTANT
    # advantage on a bare PD/ED power row) converts from non-resistant
    # to resistant. Capped against the available pool at the end.
    naked_resistant: dict[str, int] = {"PD": 0, "ED": 0, "MD": 0,
                                        "POWD": 0, "FLASHD": 0}

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
            pd_bonus += levels
            # If this PD-power row carries a RESISTANT advantage, the
            # whole bonus is resistant.
            if _has_assigned_modifier(p, "RESISTANT"):
                naked_resistant["PD"] += levels
        elif xmlid == "ED":
            ed_bonus += levels
            if _has_assigned_modifier(p, "RESISTANT"):
                naked_resistant["ED"] += levels
        elif xmlid == "MENTALDEFENSE":
            md += levels
        elif xmlid == "POWERDEFENSE":
            powd += levels
        elif xmlid == "FLASHDEFENSE":
            flashd += levels
        elif xmlid == "NAKEDMODIFIER":
            # Defensive naked advantages: carry a RESISTANT or
            # HARDENED advantage targeting "for X PD/X ED/...".
            input_str = getattr(p, "input_value", None)
            parsed = _parse_input_for_defenses(input_str)
            if not parsed:
                continue
            if _has_assigned_modifier(p, "RESISTANT"):
                for k, amt in parsed.items():
                    if k in naked_resistant:
                        naked_resistant[k] += amt
            # HARDENED on a NAKEDMODIFIER affects how Penetrating /
            # AP interact with the named defense — not surfaced on
            # HeroCombatStats yet (it's a per-DefenseItem flag in the
            # current resolver). Tracked TODO.

    # Compose: pd/ed totals include naked resistant pools as
    # already counted in pd_bonus/ed_bonus or as part of cv("PD").
    # rpd is the sum of FORCEFIELD-style resistant + the naked-mod
    # slice of base PD that's been promoted to resistant. Cap at the
    # total available.
    base_pd = cv("PD") + pd_bonus
    base_ed = cv("ED") + ed_bonus
    final_rpd = min(rpd + naked_resistant["PD"], base_pd)
    final_red = min(red + naked_resistant["ED"], base_ed)
    final_md = md + naked_resistant["MD"]
    final_powd = powd + naked_resistant["POWD"]
    final_flashd = flashd + naked_resistant["FLASHD"]

    return HeroCombatStats(
        ocv=cv("OCV"),
        dcv=cv("DCV"),
        omcv=cv("OMCV"),
        dmcv=cv("DMCV"),
        spd=cv("SPD"),
        dex=cv("DEX"),
        ego=cv("EGO"),
        int_=cv("INT"),
        str_=cv("STR"),
        con=cv("CON"),
        pre=cv("PRE"),
        rec=cv("REC"),
        pd=base_pd,
        ed=base_ed,
        rpd=final_rpd,
        red=final_red,
        md=final_md,
        power_defense=final_powd,
        flash_defense=final_flashd,
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
        # HD encodes the % tier in OPTIONID ("LVL25"/"LVL50"/"LVL75"
        # optionally suffixed "RESISTANT") and the damage class in
        # INPUT ("Physical"/"Energy"/"Mental"). 6E1 p185.
        opt = (getattr(power, "option_id", "") or "").upper()
        pct = 0
        if "LVL75" in opt: pct = 75
        elif "LVL50" in opt: pct = 50
        elif "LVL25" in opt: pct = 25
        resistant = "RESISTANT" in opt
        cls = (getattr(power, "input_value", "") or "").strip().lower()
        # Normalise common aliases
        if cls in ("phys", "physical"): cls = "physical"
        elif cls in ("energy",): cls = "energy"
        elif cls in ("mental",): cls = "mental"
        else: cls = ""
        return DefenseItem(
            name=name,
            damage_reduction_pct=pct,
            damage_class=cls,
            dr_resistant=resistant,
            is_resistant=resistant,
        )
    if xmlid == "DAMAGENEGATION":
        # 5 CP per -1 DC (6E1 p185); HD encodes the DC count in
        # OPTIONID ("DCx" where x is the DC count) or in levels.
        # Class via INPUT.
        opt = (getattr(power, "option_id", "") or "").upper()
        dcs = levels
        if opt:
            # Common HD shapes: "DC1", "DC2", "MINUS5DC", etc.
            digits = re.findall(r"\d+", opt)
            if digits:
                dcs = max(dcs, int(digits[0]))
        cls = (getattr(power, "input_value", "") or "").strip().lower()
        if cls in ("phys", "physical"): cls = "physical"
        elif cls in ("energy",): cls = "energy"
        elif cls in ("mental",): cls = "mental"
        else: cls = ""
        return DefenseItem(
            name=name,
            damage_negation=dcs,
            damage_class=cls,
            dr_resistant=True,  # default per 6E1 p185 unless Nonresistant Lim
        )
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


def _damage_type_for_power(power, xmlid: str) -> str:
    """AttackPower.damage_type ('normal'|'killing'|'mental'), FROM THE POWER.

    Main6E states both facts on the power itself -- `KILLING="Yes"` and
    `DEFENSE="MENTAL"` -- and kirby-cost now carries them, so the xmlid lists
    this used to keep are gone. They were a second copy of the template.

    The xmlid is still taken for the fallback, but ONLY for an object that
    carries no such attribute at all -- a stub in this package's own tests.
    ABSENT and FALSE are different answers and the fallback must not confuse
    them: a campaign whose .hdt sets `KILLING="No"` on the killing attacks is
    SAYING no, and an xmlid list that overrode that would put the house rule
    back. That is the whole point of the facts coming from the template.
    """
    killing = getattr(power, "killing", None)
    defense = getattr(power, "defense", None)
    if killing is not None or defense is not None:
        if killing:
            return "killing"
        if (defense or "").upper() == "MENTAL":
            return "mental"
        return "normal"
    # Stub-shaped objects with no template behind them.
    if xmlid in {"RKA", "HKA", "KILLINGATTACK", "KILLINGATTACKRANGED",
                 "KILLINGATTACKHTH"}:
        return "killing"
    if xmlid in {"EGOATTACK", "MENTALBLAST"}:
        return "mental"
    return "normal"


def _defense_type_for_power(power, xmlid: str) -> str:
    """AttackPower.defense_type ('pd'|'ed'|'mental').

    MENTAL comes from the power: Main6E states `DEFENSE="MENTAL"` and
    kirby-cost now carries it.

    THE PD/ED SPLIT DOES NOT, and that is not an engine gap. Main6E says
    `DEFENSE="NORMAL"` for an HKA and for an Energy Blast alike -- the
    distinction is special effect, which the build does not record. So the
    heuristic below stays, and stays labelled: it is combat's guess, not a
    fact the engine declined to publish.
    """
    if (getattr(power, "defense", "") or "").upper() == "MENTAL":
        return "mental"
    if xmlid in {"EGOATTACK", "MENTALBLAST"}:      # stub fallback
        return "mental"
    if xmlid in {"HKA", "KILLINGATTACKHTH", "STR", "HANDTOHANDATTACK",
                 "HANDTOHAND"}:
        return "pd"
    return "ed"


def _compute_damage_dice(power, xmlid: str) -> tuple[int, bool, bool]:
    """Return (full_dice, half_die, plus_one) from HD's level fields.

    HD stores ``levels`` as the buy count and ``level_value`` as the
    dice-per-level increment, so dice = ``levels * level_value`` for every
    damage type. The cost engine is the authority on both, and its numbers
    are oracle-verified — trust them rather than hard-coding a rule per
    damage type.

    This previously special-cased killing attacks on the belief that they
    carried ``level_cost=5, level_value=⅓`` and advanced ½d6 per level, so it
    read ``levels`` as half-die STEPS (3 levels -> 3 // 2 = 1d6+½). That is
    not what the engine stores. Measured across the whole corpus, all 1,037
    killing attacks (575 HKA + 462 RKA) carry ``level_cost=15.0,
    level_value=1.0`` with ``base_cost=0`` — matching 6E1 p243, "15 character
    points for every 1d6 killing attack". The old formula therefore rendered
    EVERY killing attack at roughly half its real damage: Drago's 3d6
    "Dragori Sniper Rifle" came through as 1d6+½, which cannot scratch a
    DEF 6 wall. The ``base_cost >= 15`` branch never fired either — base_cost
    is 0 on all of them.
    """
    levels = int(getattr(power, "levels", 0) or 0)
    level_value = float(getattr(power, "level_value", 1.0) or 1.0)

    # A fractional product is a genuine half-die (HD writes 1d6+½ that way);
    # this keeps working if a template ever does use a fractional increment.
    raw = levels * level_value
    full = int(raw)
    half = (raw - full) >= 0.5
    return full, half, False


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


_STR_USING_XMLIDS = frozenset({
    "HKA", "STR", "KILLINGATTACKHTH", "HANDTOHANDATTACK", "HA",
})


def _str_augment_dice(
    full_dice: int, half_die: bool, damage_type: str, str_: int,
) -> tuple[int, bool]:
    """Add STR to an attack's dice -- delegated to kirby-cost.

    The arithmetic lived here and is now
    ``kirby_cost.engine.damage.augment_with_str``, unchanged: deriving dice
    is the build engine's province, and a second copy of it here is a
    divergence waiting to be found by someone who does not know it exists.

    Kept as a thin wrapper rather than inlined at the call sites so the
    module's own tests keep a name to reach for.
    """
    from kirby_cost.engine.damage import augment_with_str
    return augment_with_str(full_dice, half_die, damage_type, str_)


def _build_attack_power(
    power,
    *,
    str_for_augmentation: int = 0,
    # Degraded-mode contract: when hero is None, melee reach_m falls back to
    # 0.0 (see reach_m_val below). Callers that need correct melee reach MUST
    # pass hero=<the attacker's hero object>.
    hero=None,
) -> AttackPower:
    """Project a HD power into the flat AttackPower record.

    ``str_for_augmentation`` is the wielder's effective STR. When the
    attack's xmlid is a STR-using type (HKA, HANDTOHANDATTACK, HA),
    STR/5 DCs of damage are added to the base dice subject to the 6E
    Doubling Rule (cap at base DCs). Pass 0 (or omit) for views that
    don't need augmentation, e.g. when only inspecting the bare power.

    ``hero`` (optional): the attacker's hero object. When provided,
    ``is_ranged`` and ``reach_m`` are set on the returned AttackPower.
    Melee attacks carry the attacker's effective reach (1m base + Stretching);
    ranged attacks carry 0.0 for reach_m.
    """
    from kirby_cost.io.framework_access import framework_kind, avad_alternate_defense
    _fw_access = True

    xmlid = (getattr(power, "xmlid", None) or "").upper()
    name = (getattr(power, "name", None) or "").strip() or xmlid

    # Framework slot identity — slots are top-level powers whose .parent is a framework.
    parent = getattr(power, "parent", None)
    if _fw_access and parent is not None:
        try:
            fw_kind = framework_kind(parent)
        except Exception:
            fw_kind = None
    else:
        fw_kind = None
    framework_xmlid = (getattr(parent, "xmlid", "") or "") if fw_kind else ""
    framework_id = (str(getattr(parent, "id", "") or "") if fw_kind else "")
    if fw_kind:
        raw_id = str(getattr(power, "id", "") or "")
        slot_id = raw_id or f'{(getattr(power, "xmlid", "") or "").upper()}#{id(power)}'
    else:
        slot_id = ""

    # AVAD / NND detection — uses the Task-1 accessor which reads assigned_modifiers[].input.
    if _fw_access:
        try:
            avad_def = avad_alternate_defense(power)
        except Exception:
            avad_def = ""
    else:
        avad_def = ""
    # AVAD/NND does STUN only (6E1 p328) unless it bought the Does BODY (+1) Advantage.
    avad_does_body = _has_modifier(power, "DOESBODY")

    full_dice, half_die, plus_one = _compute_damage_dice(power, xmlid)
    damage_type = _damage_type_for_power(power, xmlid)
    defense_type = _defense_type_for_power(power, xmlid)

    uses_str = xmlid in _STR_USING_XMLIDS
    if uses_str and str_for_augmentation > 0:
        full_dice, half_die = _str_augment_dice(
            full_dice, half_die, damage_type, str_for_augmentation,
        )

    # Modifiers
    armor_piercing = _modifier_levels(power, "ARMORPIERCING")
    penetrating = _modifier_levels(power, "PENETRATING")
    reduced_end = _has_modifier(power, "REDUCEDEND")  # noqa: F841 (END calc TBD)

    # Range: HKA / STR-based attacks have no range; RKA + Blast etc. do.
    if xmlid in {"HKA", "KILLINGATTACKHTH", "STR", "HANDTOHANDATTACK", "HA"}:
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

    is_ranged = range_m > 0
    reach_m_val = 0.0 if is_ranged else (_base_reach_m(hero) if hero is not None else 0.0)

    return AttackPower(
        # Identity, so consumers can find this power again without guessing
        # from xmlid + name. See AttackPower.source_id.
        source_id=getattr(power, "id", None),
        xmlid=xmlid,
        name=name,
        damage_dice=full_dice,
        half_die=half_die,
        plus_one=plus_one,
        damage_type=damage_type,
        defense_type=defense_type,
        range_m=range_m,
        uses_str=uses_str,
        str_min=0,
        armor_piercing=armor_piercing,
        penetrating=penetrating,
        increased_stun_mult=0,
        is_ranged=is_ranged,
        reach_m=reach_m_val,
        avad=bool(avad_def),
        avad_defense=(avad_def or ""),
        avad_does_body=avad_does_body,
        framework_xmlid=framework_xmlid,
        framework_id=framework_id,
        slot_id=slot_id,
    )
