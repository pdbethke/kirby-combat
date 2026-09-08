"""Per-phase legal-action enumeration for the combat driver.

Given an actor + the enemies they can see, return the list of actions
the engine considers legal for the actor's current phase. The list
is what gets handed to whatever picks one -- the list is the interface,
and the picker is already pluggable -- so it
can choose ONE.

Deferred / partial:
  * PRE attacks as a first-class action (see kirby_combat.pre_attacks)
  * Indirect advantage on LoS gating (driver defaults to False)

Movement (``move`` / ``move_to_cover``) and scene-aware attack modifiers
are enumerated when the caller passes ``has_scene=True``.

Everything here is a pure function — no DB, no engine state mutation.
The caller drives resolution by passing the chosen LegalAction's
``_attack_view`` to ``kirby_combat.actions.resolve_attack``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kirby_combat import within_reach
from kirby_combat.scene.cover import cover_ocv_modifier
from kirby_combat.actions.throw import resolve_object_throw
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.perception import flash_groups, perceive

if TYPE_CHECKING:
    from kirby_combat.scene import Construct

# Movement spec §3: tolerance for "lands meaningfully closer" + within-reach.
_EPS_M = 1e-6

# Throwing spec §4: debris mass proxy. A debris chunk's mass (kg) is its BODY
# times this constant — the input to the weight gate (can the actor lift it?).
# 50 kg/BODY is the v1 default (a BODY-3 stone chunk ≈ 150 kg, a one-hand-able
# rubble lump for a brick but not a normal). Tunable; documented per spec §4.
_DEBRIS_KG_PER_BODY = 50.0


def _xyz_dist(a: Any, b: Any) -> float:
    """3D Euclidean distance between two engine ``Position``-likes."""
    return math.sqrt(
        (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2
    )


def _construct_point(construct: Any) -> tuple[float, float, float] | None:
    """A construct's representative point for reach gating: segment midpoint
    (avg of the two endpoints) or polygon centroid (mean of vertices). None
    when the geometry is unreadable. Mirrors the consumer driver's construct-centroid helper
    — kept here so enumeration stays DB/engine-layer-clean (it only reads the
    Construct's own geometry, which is already threaded in)."""
    seg = getattr(construct, "segment", None)
    if seg is not None:
        a, b = seg
        return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0, (a.z + b.z) / 2.0)
    poly = getattr(construct, "polygon_xy", None)
    if poly:
        n = len(poly)
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        zlo, _zhi = getattr(construct, "elevation_range_m", (0.0, 0.0))
        return (cx, cy, float(zlo))
    return None


# Perception §4: a combatant counts as "adjacent to cover" for the Hide action
# when a cover-bearing feature (a wall or surface with cover_level > 0) sits
# within this radius of their position. Mirrors sim_ai.cover_at's adjacency_m.
_COVER_ADJACENCY_M = 2.0


def _feature_point(feature: Any) -> Any | None:
    """Representative engine ``Position`` for a scene cover feature: a wall's
    segment midpoint or a surface's polygon centroid. None when unreadable."""
    from kirby_combat.scene.scene import Position

    seg = getattr(feature, "segment", None)
    if seg is not None:
        a, b = seg
        return Position(x=(a.x + b.x) / 2.0, y=(a.y + b.y) / 2.0, z=(a.z + b.z) / 2.0)
    poly = getattr(feature, "polygon_xy", None)
    if poly:
        # polygon_xy is a flat [x0,y0,x1,y1,...] list (engine Surface shape).
        xs = poly[0::2]
        ys = poly[1::2]
        if not xs:
            return None
        z = float(getattr(feature, "elevation_m", 0.0) or 0.0)
        return Position(x=sum(xs) / len(xs), y=sum(ys) / len(ys), z=z)
    return None


def _actor_has_cover(actor: HeroCombatant, scene: Any) -> bool:
    """True when ``actor`` is adjacent to a cover-bearing scene feature
    (a wall or surface with ``cover_level > 0`` within ~2 m). This is the
    Hide-availability predicate — Hide is offered only when there's cover or
    concealment to break line-of-sight. Scene-less / no actor position → False
    (no cover info ⇒ no Hide). Reads the same geometry ``cover_at`` reads."""
    if scene is None:
        return False
    actor_pos = (
        (getattr(scene, "combatant_positions", None) or {}).get(actor.id)
    )
    if actor_pos is None:
        return False
    features = list(getattr(scene, "walls", None) or [])
    features += list(getattr(scene, "surfaces", None) or [])
    for feat in features:
        if (getattr(feat, "cover_level", 0) or 0) <= 0:
            continue
        pt = _feature_point(feat)
        if pt is None:
            continue
        if _xyz_dist(actor_pos, pt) <= _COVER_ADJACENCY_M + _EPS_M:
            return True
    return False


def _debris_mass_kg(body: int | None) -> float:
    """Mass proxy (kg) for a debris chunk of the given BODY."""
    return float(body or 1) * _DEBRIS_KG_PER_BODY


def _primary_lift_kg(str_value: int) -> float:
    """Cost-engine STR→lift (kg): ``25 · 2^(STR/5)`` (hero-designer
    ``Strength.primary_lift``). Computed directly from the integer STR so the
    gate never depends on the ``HeroCombatant``/``attack_view`` carrying a live
    ``hero`` (the bulk attacks builder doesn't always pass ``hero=``)."""
    return 25.0 * (2.0 ** (str_value / 5.0))


def _point_within_reach(actor_pos: Any, enemy_pos: Any, reach_m: float) -> Any:
    """A point on the actor→enemy line that sits ``reach_m`` short of the enemy
    (so a mover landing there is within melee reach). Returns an engine
    ``Position``. If the actor is already within reach, returns ``enemy_pos``
    unchanged."""
    from kirby_combat.scene.scene import Position

    d = _xyz_dist(actor_pos, enemy_pos)
    # The reach decision is the engine's (6E2 p56); the `d < _EPS_M` arm is a
    # degenerate-geometry guard (co-located actor and enemy — nothing to walk
    # back along), not a rule.
    if within_reach(d, reach_m).in_reach or d < _EPS_M:
        return enemy_pos
    # Walk back from the enemy toward the actor by reach_m.
    frac = (d - reach_m) / d
    return Position(
        x=actor_pos.x + (enemy_pos.x - actor_pos.x) * frac,
        y=actor_pos.y + (enemy_pos.y - actor_pos.y) * frac,
        z=actor_pos.z + (enemy_pos.z - actor_pos.z) * frac,
        facing=getattr(enemy_pos, "facing", 0.0),
    )

# PR-37: xmlids that map to mental-attack resolution (OMCV/DMCV, Mental
# Defense).  Defined at module level so the construct-enumeration block
# (below) can reuse it without duplicating the set.
_MENTAL_ATTACK_XMLIDS: frozenset[str] = frozenset(
    {"MENTALBLAST", "EGO_ATTACK", "EGOATTACK"}
)

# Perception §2: action ``kind``s that target an enemy's MIND (OMCV/DMCV, no
# line-of-sight) rather than its body. These gate on ``targetable_mental``;
# everything else targeted at an enemy gates on ``targetable_physical``.
_MENTAL_ACTION_KINDS: frozenset[str] = frozenset({
    "mental_blast", "mind_control", "mental_entangle",
    "mental_illusion", "telepathy",
})

# Perception §2 (tier-2): targeted ``kind``s that are inherently HAND-TO-HAND
# (require adjacency, no range). When an enemy is adjacent but unperceived, only
# these physical offers survive (carrying ``blind=True``); ranged physical
# offers are dropped.
_HTH_ACTION_KINDS: frozenset[str] = frozenset({
    "strike", "grab", "trip", "disarm", "throw", "maneuver",
})

# Perception §2: MOVEMENT kinds are repositioning, not a target-lock — moving
# toward (or past) where an enemy was last perceived is legitimate even when the
# actor can't currently perceive it (you move to GET line-of-sight). They carry
# ``target_id`` only to name the destination, so the targeting gate skips them;
# perception is re-evaluated at strike-resolution time. (``move_by`` /
# ``move_through`` are velocity attacks but are movement-led, same reasoning.)
_MOVEMENT_ACTION_KINDS: frozenset[str] = frozenset({
    "move", "move_strike", "move_by", "move_through",
})


def _src_id(power: Any) -> str:
    """The identity of a power or of the view built from it.

    Accepts either an engine object (``.id``) or an ``AttackPower`` view
    (``.source_id``, which carries the source object's id). Returns "" only
    when neither is present, which should no longer happen: kirby-combat
    >=0.3.22 gives every view an id, including the bare STR strike.
    """
    for attr in ("source_id", "id"):
        v = getattr(power, attr, None)
        if v is not None and v != "":
            return str(v)
    return ""


def _power_action_id(kind: str, target_id: str, ap: Any) -> str:
    """The token that names ONE power-based attack against ONE target.

    Identity is the source power's object id (kirby-combat >= 0.3.21 carries
    it as ``AttackPower.source_id``). The xmlid is a TYPE ("this is an Energy
    Blast") and the name is a display string; a character may legitimately
    carry two powers agreeing on both, and keying on them produced the same
    token for both — 630 measured cases across the corpus. The picker then had
    no way to say which one it meant, and whichever the lookup found first
    won, silently.

    The readable label is NOT lost: it lives in the action's ``summary``, so
    the model READS "Billy Club (2d6K)" while RETURNING an unambiguous token.

    Fallback for synthetic views with no source power (the bare STR strike):
    framework slots key on ``slot_id`` (stable per slot), everything else
    keeps the historical string form. Deliberately not "make the string more
    unique" — that is the same mistake with more decoration.
    """
    src_id = _src_id(ap)
    if src_id:
        return f"{kind}:{target_id}:{src_id}"
    # Framework slots carry the slot power's own id (kirby-combat's slot_id is
    # that id since >=0.3.22). Reached only if a view somehow arrives without
    # a source object at all.
    if getattr(ap, "slot_id", ""):
        return f"{kind}:{target_id}:{ap.slot_id}"
    raise ValueError(
        f"cannot build an action_id for {getattr(ap, 'xmlid', '?')!r}: the "
        f"view carries no id. Identity is an id — falling back to xmlid+name "
        f"is what made 630 corpus objects share a token, silently."
    )


@dataclass
class LegalAction:
    """One thing the actor could legally do this phase.

    ``action_id`` is a stable short token the picker returns to identify
    its choice. Format: ``<kind>:<target_id?>:<power_xmlid?>:<power_name?>``
    Kinds: ``attack`` | ``strike`` | ``dodge`` | ``set`` | ``recover``

    The ``attack`` / ``mental_blast`` offers do NOT follow that format: they
    key on the source power's object id (``<kind>:<target_id>:<source_id>``)
    because xmlid is a type and name is a display string, and the pair
    collided in 630 measured corpus cases. See ``_power_action_id``.

    Movement (spec §3): ``move:<enemy>`` / ``move_strike:<enemy>:<xmlid>`` are
    the RUNNING aliases (``mode="running"``); other modes encode the mode as
    ``move:<mode>:<enemy>`` / ``move_strike:<mode>:<enemy>:<xmlid>`` AND carry
    it on the ``mode`` field for the resolver.
    """
    action_id: str
    kind: str
    target_id: str | None
    power_xmlid: str | None
    power_name: str | None
    summary: str
    # Engine-side handle; only populated for attack/strike kinds.
    _attack_view: Any = None
    # Movement spec §3: the movement mode for move / move_strike kinds
    # (running | leaping | flight | teleportation | swimming | tunneling).
    # None for non-movement actions. Defaults to "running" for the bare
    # ``move:<enemy>`` / ``move_strike:<enemy>:<xmlid>`` running aliases.
    mode: str | None = None
    # True when this action is aimed at TERRAIN (a wall/construct) rather than
    # a combatant. Terrain offers led the action list -- six of the first six
    # entries in a 21-action menu -- while "Flight toward <enemy>" sat at #18,
    # so the picker spent 8 of 19 real actions demolishing scenery. Used for
    # PRESENTATION ORDER only; the legal set is unchanged.
    targets_construct: bool = False
    # Perception §2 (tier-2): set when this is an HtH offer kept against an
    # enemy the actor is adjacent to but does NOT perceive (occluded / invisible
    # / hidden). The resolver applies the ½ OCV / ½ DCV blind-combat penalty
    # (negated by Combat Sense) — Task 2. False for every perceived offer.
    blind: bool = False
    # Repositioning §2: for a ``reposition_strike`` (offensive: move to a LoS-
    # clear vantage and fire) / ``reposition`` (defensive: break contact), the
    # engine ``Position`` destination as an (x, y, z) tuple. Enumeration computes
    # it (via ``nearest_visible_point`` / ``nearest_hidden_point``); the resolver
    # consumes it (no recompute → no drift). None for every other kind.
    reposition_dest: tuple[float, float, float] | None = None
    # Spec §7: for a ``reposition_push``, the extra metres bought by Pushing
    # the movement power and the END that costs. Both 0 for every other kind.
    # push_move_m is DERIVED from the cost engine's active_cost — see
    # ``push_move_metres`` — never a constant.
    push_move_m: float = 0.0
    push_end: int = 0
    # Climbing: the wall this climb is against. None for every other kind.
    climb_wall_id: str | None = None


# Pushing a Power adds up to +10 Active Points at 1 END per Character Point
# (6E2 p133). PUSH_END is that END cost; PUSH_ACTIVE_POINTS is the RAW cap.
PUSH_ACTIVE_POINTS = 10
PUSH_END = 10


def push_move_metres(cap) -> float:
    """Extra metres a Push buys on this movement mode, or 0.0 when the mode
    cannot be pushed.

    The metres come OFF THE COST ENGINE: ``metres_per_point = combat_m /
    active_cost``, both computed by the engine, divided here. A hardcoded
    metres-per-point would be hand-rolled cost math in a consumer, which the
    north star forbids.

    Returns 0.0 — meaning "no push offer" — when ``active_cost`` is missing,
    zero, negative or non-numeric. That covers the characteristic-derived
    modes (RUNNING / LEAPING), which have no power to read a cost from; a
    guessed constant for them would be exactly the forbidden thing.
    """
    try:
        active_cost = float(getattr(cap, "active_cost", None))
        combat_m = float(getattr(cap, "combat_m", 0.0))
    except (TypeError, ValueError):
        return 0.0
    if active_cost <= 0.0 or combat_m <= 0.0:
        return 0.0
    return PUSH_ACTIVE_POINTS * (combat_m / active_cost)


def is_down(c: HeroCombatant) -> bool:
    """KO'd at STUN ≤ 0; unconscious / dying at BODY ≤ 0 per 6E1 p421.

    Used by both this module (gate enumeration) and the driver loop
    (skip phases for downed combatants, detect win condition).
    """
    return c.state.current_stun <= 0 or c.state.current_body <= 0


def _biggest_attack_dice(c: HeroCombatant) -> float:
    """The combatant's heaviest single-attack damage, in dice — the max of
    their enumerated attacks' damage_dice and their bare STR strike (STR/5).
    A blunt threat proxy; we don't resolve type (the matchup nudge is a
    heuristic, not a damage calc). Single-sourced here so both the matchup
    consumer's situation summary and the defensive-reposition gate use one calc."""
    attack_dice = [float(getattr(a, "damage_dice", 0) or 0) for a in c.attacks]
    st = c.combat_stats()
    str_strike = float(getattr(st, "str_", 0) or 0) / 5.0
    return max(attack_dice + [str_strike] + [0.0])


def _is_fragile_vs(actor: HeroCombatant, enemy: HeroCombatant) -> bool:
    """The ``kite_grapple`` matchup predicate: is ``actor`` the faster-but-fragile
    side vs ``enemy`` — a heavier hitter it should AVOID trading blows with, kiting
    away / using Dodge + grapple-throws instead?

    True when ALL hold (the matchup math ``_build_matchup_lines`` renders, lifted
    here so the defensive-reposition enumeration reuses it without duplicating the
    threat calc — repositioning §2):
      * ``actor`` acts more often (SPD higher, or SPD tie + higher DEX);
      * ``enemy``'s heaviest hit, net of the actor's worst-case defense, is
        ≥ ~30 % of the actor's STUN in ONE blow (one hit ≥ ⅓ of your STUN);
      * the actor has a Dodge or a throw maneuver to spend that speed edge on.

    Fail-open: any error reading a view → not fragile (no defensive nudge)."""
    try:
        a_st = actor.combat_stats()
        e_st = enemy.combat_stats()
        a_def = min(a_st.pd + a_st.rpd, a_st.ed + a_st.red)  # worst-case defense
        a_stun = max(1, int(a_st.max_stun))
        faster = (a_st.spd > e_st.spd) or (
            a_st.spd == e_st.spd and a_st.dex > e_st.dex
        )
        # Their heaviest hit, net of your worst-case defense (normal-attack
        # STUN ≈ dice × 3.5). A blunt proxy for "how hard do they hit you".
        e_net = max(0.0, _biggest_attack_dice(enemy) * 3.5 - a_def)
        fragile = (e_net / a_stun) >= 0.30  # one hit ≥ ~⅓ of your STUN
        try:
            mv = actor.maneuver_view()
        except Exception:  # noqa: BLE001
            mv = []
        has_dodge = any(getattr(m, "is_dodge", False) for m in mv)
        has_throw = any(getattr(m, "target_falls", False) for m in mv)
        return bool(faster and fragile and (has_dodge or has_throw))
    except Exception:  # noqa: BLE001 — never break enumeration over the predicate
        return False


# ── shared capability predicates ─────────────────────────────────────────────
# These are the single-source-of-truth predicates for enumerate_actions and
# for whatever renders a terrain summary for a chooser. Both call sites MUST
# use these helpers so the capability logic can't drift.


def has_live_own_force_wall(
    actor_id: str,
    constructs: list[Construct] | None,
) -> bool:
    """True when the actor already has a live force_wall up.

    A wall is "live" when its source_combatant_id matches actor_id AND
    its body > 0. A destroyed wall (body == 0 or None) does NOT suppress
    a new-wall offer — the actor is free to raise another.  Another
    caster's wall never blocks this actor's offer.
    """
    for c in (constructs or []):
        if (
            c.kind == "force_wall"
            and getattr(c, "source_combatant_id", None) == actor_id
            and (c.body or 0) > 0
        ):
            return True
    return False


def forcewall_power(hero: Any) -> Any | None:
    """Return the first FORCEWALL power on ``hero``, or None.

    Scans ``hero.powers``; callers should NOT inline this scan — use
    this helper so a XMLID spelling change only needs updating here.
    """
    for p in (getattr(hero, "powers", None) or []):
        if (getattr(p, "xmlid", "") or "").upper() == "FORCEWALL":
            return p
    return None


def has_live_own_darkness(
    actor_id: str,
    constructs: list[Construct] | None,
) -> bool:
    """True when the actor already has a live OWN darkness_zone up
    (sense-affecting §2 — the stacking guard, mirror of
    ``has_live_own_force_wall``).

    A darkness zone is "live" when its source_combatant_id matches
    actor_id. A darkness_zone is a persistent occluder with no body, so
    presence alone suppresses a second offer; another caster's darkness
    never blocks this actor's offer (source_combatant_id differs).
    """
    for c in (constructs or []):
        if (
            c.kind == "darkness_zone"
            and getattr(c, "source_combatant_id", None) == actor_id
        ):
            return True
    return False


def darkness_power(hero: Any) -> Any | None:
    """Return the first DARKNESS power on ``hero``, or None.

    Scans ``hero.powers``; callers should NOT inline this scan — use
    this helper so a XMLID spelling change only needs updating here.
    """
    for p in (getattr(hero, "powers", None) or []):
        if (getattr(p, "xmlid", "") or "").upper() == "DARKNESS":
            return p
    return None


def images_power(hero: Any) -> Any | None:
    """Return the first IMAGES power on ``hero``, or None (sense-affecting §3,
    the create-decoy enumeration gate).

    Scans ``hero.powers``; callers should NOT inline this scan — use this helper
    so a XMLID spelling change only needs updating here (mirror of
    ``darkness_power`` / ``forcewall_power``).
    """
    for p in (getattr(hero, "powers", None) or []):
        if (getattr(p, "xmlid", "") or "").upper() == "IMAGES":
            return p
    return None


def ranged_damaging_attacks(attacks: list[Any]) -> list[Any]:
    """Return the subset of ``attacks`` that are ranged, damaging,
    and non-mental — the same capability filter used by both the
    rapid_fire construct enumeration (Task 4) and the terrain-summary
    autofire nudge (Task 9).

    Predicate: damage_dice > 0, range_m > 0, xmlid NOT in
    _MENTAL_ATTACK_XMLIDS.  The mental exclusion matters because
    constructs are physical objects that do not have Mental Defense.
    """
    return [
        ap for ap in attacks
        if (ap.damage_dice or 0) > 0
        and ap.range_m is not None and ap.range_m > 0
        and (ap.xmlid or "").upper() not in _MENTAL_ATTACK_XMLIDS
    ]


def _friendly(c: HeroCombatant) -> str:
    return getattr(c.hero, "name", None) or c.id


@dataclass(frozen=True)
class PhysicalEntangleState:
    """The actor's own live physical Entangle, read off its combatant row
    (spec 2026-08-31). ``pd``/``ed`` are the ENTANGLE's defenses (escape
    damage soaks against them, 6E1 p218)."""
    body: int
    pd: int
    ed: int
    no_teleport: int
    takes_no_damage: bool


def _cover_midpoint(wall) -> tuple[float, float, float]:
    """The representative point of a cover feature --- its segment's middle.

    A wall is a line, not a spot, so "how far is that cover" needs one
    point to measure to. The midpoint is the same one `scene/cover.py`
    uses when it picks the nearest blocking wall, so the distance a menu
    quotes and the cover the rules compute refer to the same place.
    """
    a, b = wall.segment
    return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0, (a.z + b.z) / 2.0)


def _multi_attack_ocv(base_ocv: int, count: int) -> int:
    """The single OCV every shot of a `count`-attack sequence is taken at.

    STATE THE NUMBER, NOT THE RULE. A single-attack offer reads "(1d6K,
    OCV 5)" -- an absolute figure a reader can compare. A Multiple Attack
    used to read "cumulative -2 OCV per additional target", which is the
    same information only if the reader does the arithmetic. Anything
    choosing between the two was comparing a number against a rule.

    This was a LADDER ("5/3/1") until 2026-09-07, because the resolver
    charged one. 6E2 p.73 charges (N-1) x -2 on every roll instead, so
    there is one number to quote and the menu quotes it. Kept delegating
    to `MultipleAttack.compute` so the offer and the resolution cannot
    drift apart again.
    """
    from kirby_combat.actions.multiple_attack import MultipleAttack

    return MultipleAttack.compute(
        base_ocv=base_ocv, num_targets=max(1, count)).per_shot_ocv[0]


#: EVERY kind ``enumerate_actions`` can put on a menu.
#:
#: DECLARED, NOT DERIVED, and that is the point. Three of the offers below
#: build their kind from a VARIABLE rather than a literal --- ``kind =
#: "sweep" if is_hth else "multiple_attack"``, the interaction-skill loop,
#: and the climb loop --- so a scan matching ``kind="..."`` sees 51 of them
#: and misses eight. A test asserting "every offered kind has a resolver"
#: passed for a while against that incomplete set, and the gap only
#: surfaced when a real fight spent 27 of 31 Phases picking
#: ``multiple_attack`` and having it skipped.
#:
#: So the list lives here, by hand, and ``tests/loop/test_run.py`` checks
#: the resolver registry against it. Adding an offer means adding its kind
#: here, which is a deliberate step rather than something an AST walk can
#: quietly get wrong.
ALL_ACTION_KINDS = frozenset({
    "aid", "attack", "attack_construct", "block", "charm", "climb",
    "climb_fast", "conversation", "coordinate", "darkness_zone", "disarm",
    "disengage",
    "dispel", "dodge", "drain", "entangle", "escape_attack", "escape_str",
    "escape_teleport", "flash", "force_wall", "grab", "haymaker", "heal",
    "hide", "hold", "image_decoy", "maneuver", "mental_blast",
    "move_to_cover",
    "mental_entangle", "mental_illusion", "mind_control", "move", "move_by",
    "move_strike", "move_through", "multiple_attack", "persuasion",
    "pickup", "presence_attack", "presence_attack_group", "push",
    "rapid_fire", "reallocate", "reconfigure_vpp", "recover",
    "release_held", "reposition", "reposition_push", "reposition_strike",
    "reposition_vantage", "set", "spread", "strike", "sweep", "telepathy",
    "throw", "throw_object", "trading", "trip",
})


def enumerate_actions(
    actor: HeroCombatant,
    enemies: list[HeroCombatant],
    *,
    has_scene: bool = False,
    constructs: list[Construct] | None = None,
    distances: dict[str, float] | None = None,
    movement: list[Any] | None = None,
    scene: Any = None,
    held_target_ids: frozenset[str] | None = None,
    block_mental_powers: bool = False,
    open_held_action_ids: list[str] | None = None,
    blocked_lockout_ids: frozenset[str] | None = None,
    allow_coordinate: bool = True,
    actor_holding: bool = False,
    held_construct_id: str | None = None,
    concealment: dict[str, tuple[bool, bool]] | None = None,
    observer_flashed_groups: frozenset[str] | None = None,
    own_decoy_live: bool = False,
    decoy_targets: list[tuple[str, str]] | None = None,
    slot_allocation: dict[str, tuple[int, int, set[str], dict[str, int]]] | None = None,
    extra_attacks: list | None = None,
    physical_entangle: PhysicalEntangleState | None = None,
) -> list[LegalAction]:
    """Return the legal action menu for ``actor`` this phase.

    Empty list when the actor is KO'd / dying. Otherwise:
      * one Attack action per (alive enemy × actor's available
        attack power).
      * one Strike action per alive enemy (unarmed, STR/5 dice) if
        the actor has STR ≥ 5 and isn't already enumerating a
        HANDTOHANDATTACK / HA via ``actor.attacks``.
      * one Dodge action.
      * one Set action.
      * one Recover action when the actor is wounded (<½ STUN) or
        low on END (<⅓ END).
      * (PR-9) one ``move`` action per alive enemy when
        ``has_scene=True`` — the driver will read positions and
        step toward the chosen target.

    ``slot_allocation`` (Task 8): per-framework reserve gate. Maps
    ``framework_id → (reserve, used_points, active_slot_ids,
    slot_costs)``, where ``slot_costs: dict[slot_id, active_points]``.
    When provided:
      * slots whose cost (slot_costs[slot_id]) > remaining (reserve −
        used) are skipped UNLESS the slot is already active (in
        ``active_slot_ids``).
      * None / missing → no gate (all slots offered; existing
        single-attack behavior unchanged).
    Also offers one ``reallocate_slots:{framework_id}:{slot_id,...}``
    action per framework that has >1 slot (the actor can change the
    active set this phase without spending an attack).

    ``extra_attacks`` (Task 6): additional ``AttackPower`` instances to offer
    alongside ``actor.attacks`` — used to hydrate a VPP-built power (carrying
    framework_id + slot_id) so it's enumerated and resolves like any
    native attack. Merged before the empty-attacks str-strike fallback.
    """
    # BUILD-BACKED ACTORS ONLY, said plainly rather than as an AttributeError.
    #
    # This function reads `actor.hero` at 21 sites -- powers, skills, RUNNING,
    # the Force Wall / Darkness / Images power lookups -- so it enumerates for
    # a `HeroCombatant` and not for a flat `StatBlockCombatant`. That is
    # inherited, not chosen: it was carved out of a driver whose actors were
    # always build-backed.
    #
    # It matters because `StatBlockCombatant` is a first-class participant
    # elsewhere in this engine -- vehicles and breakable objects subclass it,
    # and `resolve_attack` takes either shape without dispatch. So a caller
    # can build a fight the resolver handles fine and the enumerator cannot,
    # which surfaced the moment the turn loop tried to drive one.
    #
    # Raising here names the limitation at the boundary. Widening enumeration
    # to flat stat blocks is real work (what does a wall's menu contain?) and
    # is deliberately not smuggled in behind a getattr default that would
    # silently return a shorter menu.
    if not hasattr(actor, "hero"):
        raise TypeError(
            f"enumerate_actions needs a build-backed combatant (HeroCombatant); "
            f"{type(actor).__name__} {getattr(actor, 'id', '?')!r} is a flat stat "
            f"block, which carries no `hero` to read powers and skills from."
        )
    actions: list[LegalAction] = []
    if is_down(actor):
        return actions

    s = actor.combat_stats()
    # Task 6: hydrated VPP-built powers (extra_attacks) are merged into the
    # actor's native attacks BEFORE the str-strike fallback, so a VPP-only
    # actor still gets its built power offered as an attack. These carry a
    # framework_id + slot_id and resolve through the existing
    # attack path. The VPP's framework_id is not a key in slot_allocation
    # (that dict is Multipower/EC only) → the reserve gate fails open for them.
    attack_powers = list(actor.attacks) + list(extra_attacks or [])
    # PR-43: Mental Paralysis (Mental Entangle) blocks mental power
    # use. Strip any mental-attack-shaped power from the menu before
    # the per-enemy expansion so mental_blast doesn't appear.
    if block_mental_powers:
        attack_powers = [
            ap for ap in attack_powers
            if (ap.xmlid or "").upper() not in _MENTAL_ATTACK_XMLIDS
        ]
    # PR-96: filter sibling LOCKOUT slots. The actor has fired one
    # LOCKOUT-modified slot earlier in this phase; the implicit
    # multipower group restricts them to that slot only until the
    # next phase. ``blocked_lockout_ids`` is the sibling set
    # (not including the locked-to slot itself).
    if blocked_lockout_ids:
        attack_powers = [
            ap for ap in attack_powers
            if _src_id(ap) not in blocked_lockout_ids
        ]

    # Pure brawler: no listed attack powers. Synthesize a Strike via STR.
    if not attack_powers and s.str_ >= 5:
        try:
            attack_powers = [actor.str_strike_view()]
        except Exception:
            attack_powers = []

    # Spec 2026-08-31: an Entangled character must escape before doing
    # anything else (6E1 p217) — the menu IS the escape ladder. Fail-open:
    # no entangle state, no change.
    if physical_entangle is not None and physical_entangle.body > 0:
        pe = physical_entangle
        ladder: list[LegalAction] = [
            LegalAction(
                action_id="escape:str_full", kind="escape_str",
                target_id=None, power_xmlid=None, power_name=None,
                summary=(f"Break free with full STR (Entangle BODY {pe.body},"
                         f" DEF {pe.pd}/{pe.ed}) — your action this phase"),
            ),
            LegalAction(
                action_id="escape:str_casual", kind="escape_str",
                target_id=None, power_xmlid=None, power_name=None,
                summary=("Shrug at the Entangle with Casual STR (half STR, "
                         "ZERO phase — you keep your action either way)"),
            ),
        ]
        if not pe.takes_no_damage:
            for ap in attack_powers:
                if (ap.damage_dice or 0) <= 0 or getattr(ap, "is_mental", False):
                    continue
                ladder.append(LegalAction(
                    action_id=f"escape:attack:{getattr(ap, 'source_id', None) or ap.xmlid}",
                    kind="escape_attack", target_id=None,
                    power_xmlid=ap.xmlid, power_name=ap.name,
                    summary=(f"Blast the Entangle apart with {ap.name or ap.xmlid}"
                             " (auto-hit, 6E1 p218)"),
                    _attack_view=ap,
                ))
        from kirby_combat import armor_piercing_levels
        _tp = next(
            (pw for pw in (getattr(actor.hero, "powers", None) or [])
             if (getattr(pw, "xmlid", "") or "").upper() == "TELEPORTATION"),
            None,
        )
        if _tp is not None and armor_piercing_levels(_tp) >= pe.no_teleport:
            ladder.append(LegalAction(
                action_id="escape:teleport", kind="escape_teleport",
                target_id=None, power_xmlid="TELEPORTATION", power_name=None,
                summary="Teleport out of the Entangle (6E1 p218)",
            ))
        return ladder

    alive_enemies = [e for e in enemies if not is_down(e)]

    # Reach spec §2: gate melee enumeration by real distance vs reach.
    # reach_m = actor's effective melee reach (1m base per 6E2 p56, plus 1m
    # per level of Stretching — the engine's figure, carried on the combat
    # stats view); half_move_m = how far RUNNING can close this phase.
    # `distances` maps enemy_id → metres (None / unknown ⇒ scene-less ⇒ no
    # gate, melee offered freely). The literal is only the fallback for a
    # stats view that somehow lacks the field, so it must be the 6E2 p56
    # base of 1m, not the superseded 2m.
    reach_m = float(getattr(s, "reach_m", 1.0))
    running_m = float(actor.hero.characteristic_value("RUNNING") or 0)
    half_move_m = max(0.0, running_m / 2.0)

    def _melee_gate(enemy_id: str) -> str:
        """Return 'direct' | 'close' | 'block' for a melee action vs enemy.

        'block' ⇒ don't offer this melee at all.
        """
        if not distances:                       # scene-less / unknown → no gate; only reached when enemies is empty
            return "direct"
        d = distances.get(enemy_id)
        if d is None:
            return "direct"
        # Ask the engine, do not re-derive. This used to be a bare
        # `d <= reach_m` with no epsilon while the engine (and the other
        # comparisons in this file) allowed `d <= reach_m + _EPS_M`, so
        # enumeration could refuse to offer a melee that the RESOLUTION gate
        # would have allowed. Sharing the engine's predicate ends that class
        # of disagreement.
        verdict = within_reach(d, reach_m)
        if verdict.in_reach:
            return "direct"
        # `shortfall_m` is exactly the gap a half-move has to cover.
        if half_move_m >= verdict.shortfall_m:
            return "close"
        return "block"

    def _is_melee(ap: Any) -> bool:
        return not getattr(ap, "is_ranged", (getattr(ap, "range_m", 0) or 0) > 0)

    # PR-37: _MENTAL_ATTACK_XMLIDS is module-level; referenced below for
    # the per-enemy loop AND the construct damaging-pool filter.

    def _limitation_label(actor: HeroCombatant, ap: Any) -> str:
        """PR-99: lift LIMITEDPOWER text from ap or its source power
        and format as ``" [limited: <text>; <text>]"``. Empty string
        when no limitations found. Truncated to 120 chars to keep
        action summaries scannable.
        """
        modifiers: list = list(
            getattr(ap, "assigned_modifiers", []) or [],
        )
        if not modifiers:
            # Find the SOURCE POWER by id. Matching on xmlid + name read the
            # limitation off whichever same-named power came first, so an
            # unrestricted attack could be labelled with its twin's
            # limitation — worse than no label, because the AI believes it.
            target_src = _src_id(ap)
            for src in (actor.hero.powers or []):
                if not target_src or str(getattr(src, "id", "")) != target_src:
                    continue
                modifiers = list(
                    getattr(src, "assigned_modifiers", []) or [],
                )
                break
        descriptions: list[str] = []
        for m in modifiers:
            if (getattr(m, "xmlid", "") or "").upper() != "LIMITEDPOWER":
                continue
            alias = (getattr(m, "alias", None) or "").strip()
            notes = (getattr(m, "notes", None) or "").strip()
            iv = (getattr(m, "input_value", None) or "").strip()
            if alias and notes:
                descriptions.append(f"{alias}: {notes}")
            elif alias:
                descriptions.append(alias)
            elif iv:
                descriptions.append(iv)
            elif notes:
                descriptions.append(notes)
        if not descriptions:
            return ""
        joined = "; ".join(descriptions)
        if len(joined) > 120:
            joined = joined[:117] + "..."
        return f" [limited: {joined}]"
    # Attack action per (enemy × power)
    for enemy in alive_enemies:
        for ap in attack_powers:
            pname = ap.name or ap.xmlid.lower()
            dmg_summary = (
                f"{ap.damage_dice or 0}d6K"
                if ap.damage_type == "killing"
                else f"{ap.damage_dice or 0}d6N"
            )
            xmlid_upper = (ap.xmlid or "").upper()
            limit_tag = _limitation_label(actor, ap)
            if xmlid_upper in _MENTAL_ATTACK_XMLIDS:
                aid = _power_action_id("mental_blast", enemy.id, ap)
                actions.append(LegalAction(
                    action_id=aid,
                    kind="mental_blast",
                    target_id=enemy.id,
                    power_xmlid=ap.xmlid,
                    power_name=ap.name or None,
                    summary=(
                        f"Mental Blast {_friendly(enemy)} with {pname} "
                        f"({ap.damage_dice or 0}d6 STUN-only, OMCV {s.omcv} "
                        f"vs DMCV — reduced by target's Mental Defense)"
                        f"{limit_tag}"
                    ),
                    _attack_view=ap,
                ))
                continue
            # Reach spec §2: gate melee (non-ranged) attacks by distance.
            # Ranged attacks are unaffected (their range is gated elsewhere).
            if _is_melee(ap):
                gate = _melee_gate(enemy.id)
                if gate == "block":
                    continue
                if gate == "close":
                    actions.append(LegalAction(
                        action_id=_power_action_id("move_strike", enemy.id, ap),
                        kind="move_strike",
                        target_id=enemy.id,
                        power_xmlid=ap.xmlid,
                        power_name=ap.name or None,
                        summary=(
                            f"Close to within reach via Running, then strike "
                            f"{_friendly(enemy)} with {pname} ({dmg_summary})"
                            f"{limit_tag}"
                        ),
                        _attack_view=ap,
                    ))
                    continue
            # Task 8: Multipower reserve gate.  When ``slot_allocation``
            # is provided and this power belongs to a framework, skip
            # the slot if its active_points exceed the remaining reserve
            # UNLESS the slot is already active (already drawing from
            # the reserve — it's in, not blocked).
            # Plain top-level powers (framework_id empty) are never
            # gated; None slot_allocation = no gate (fail-open).
            # Key the reserve gate on the framework OBJECT. Keyed on its
            # xmlid, a character with two Multipowers had both reserves
            # collapse under one entry.
            ap_fw = getattr(ap, "framework_id", "") or ""
            ap_sid = getattr(ap, "slot_id", "") or ""
            if slot_allocation is not None and ap_fw:
                alloc = slot_allocation.get(ap_fw)
                if alloc is not None:
                    reserve, used, active_ids, slot_costs = alloc
                    remaining = max(0, reserve - used)
                    # slot_costs maps slot_id → active_points (the cost
                    # to draw this slot from the framework reserve).
                    # Fall back to 0 (always fits) when the slot is absent
                    # from the map — safe default for non-variable slots
                    # or slots the driver hasn't seen before.
                    ap_pts = slot_costs.get(ap_sid, 0)
                    already_active = ap_sid in active_ids
                    if not already_active and ap_pts > remaining:
                        continue  # skip: not enough reserve room

            aid = _power_action_id("attack", enemy.id, ap)
            label = ap.name or pname
            if getattr(ap, "avad", False):
                label += f" (NND vs {ap.avad_defense} — bypasses normal PD/ED)"
            actions.append(LegalAction(
                action_id=aid,
                kind="attack",
                target_id=enemy.id,
                power_xmlid=ap.xmlid,
                power_name=ap.name or None,
                summary=(
                    f"Attack {_friendly(enemy)} with {label} "
                    f"({dmg_summary}, OCV {s.ocv}){limit_tag}"
                ),
                _attack_view=ap,
            ))

    # Martial-arts §4 (Task 4.1): the actor's OWN martial maneuvers.
    # ``actor.maneuver_view()`` (engine, already filtered to xmlid=="MANEUVER")
    # returns the character's real maneuvers (Defensive Strike, Joint Lock/Throw,
    # …) with their CV deltas. We offer only the ATTACK maneuvers offensively —
    # Dodge / Block / Escape (``is_attack`` False) are defensive and surface via
    # the abort path (Task 4.3), not here. Ranged maneuvers (none in 6E unarmed
    # MA, but the field exists) are skipped — they aren't melee and the reach
    # gate doesn't model their range.
    #
    # Reach gating reuses ``_melee_gate`` verbatim (same bands as melee attacks):
    #   "direct" → a ``maneuver`` offer; "close" → a ``move_strike`` composite
    #   that closes via half-move then performs the maneuver; "block" → skip.
    #
    # action_id encoding (Task 4.2 parses this back to the maneuver):
    #   direct → ``maneuver:{enemy.id}:{mv.maneuver_id}``
    #   close  → ``move_strike:maneuver:{enemy.id}:{mv.maneuver_id}``
    # The token names the maneuver OBJECT. It used to carry the maneuver's
    # INDEX in ``actor.maneuver_view()``, because the old maneuver_id was
    # "MANEUVER:Display Name" and its colon would have been ambiguous here.
    # An index is not an identity: it means "the Nth item as this process
    # built the list", so it silently renames every outstanding token if the
    # list changes, and it cannot survive the request boundary. kirby-combat
    # >=0.3.22 makes maneuver_id the object's own id, colon-free.
    # Wrapped defensively: a non-martial actor returns ``[]`` and a raising view
    # yields no maneuver offers (never breaks the rest of the menu).
    try:
        maneuvers = list(actor.maneuver_view())
    except Exception:
        maneuvers = []
    for mv in maneuvers:
        if not getattr(mv, "is_attack", False) or getattr(
            mv, "category_is_ranged", False
        ):
            continue
        mv_name = getattr(mv, "name", None) or "Maneuver"
        mv_ocv = getattr(mv, "ocv", 0)
        mv_dcv = getattr(mv, "dcv", 0)
        for enemy in alive_enemies:
            gate = _melee_gate(enemy.id)
            if gate == "block":
                continue
            if gate == "close":
                actions.append(LegalAction(
                    action_id=f"move_strike:maneuver:{enemy.id}:{mv.maneuver_id}",
                    kind="move_strike",
                    target_id=enemy.id,
                    power_xmlid="MANEUVER",
                    power_name=mv_name,
                    summary=(
                        f"Close to within reach via Running, then "
                        f"{mv_name} {_friendly(enemy)} "
                        f"(OCV {mv_ocv:+d}/DCV {mv_dcv:+d})"
                    ),
                ))
                continue
            actions.append(LegalAction(
                action_id=f"maneuver:{enemy.id}:{mv.maneuver_id}",
                kind="maneuver",
                target_id=enemy.id,
                power_xmlid="MANEUVER",
                power_name=mv_name,
                summary=(
                    f"{mv_name} vs {_friendly(enemy)} "
                    f"(OCV {mv_ocv:+d}/DCV {mv_dcv:+d})"
                ),
            ))

    # Task 8: Multipower reallocate offer.  When the actor has a power
    # framework with >1 slot, offer one
    # ``reallocate_slots:{framework_id}:{slot_id,...}`` action per
    # framework.  This is a zero-phase action: the actor can change
    # which slots are drawing from the reserve without spending an
    # attack phase.  Wrapped defensively — a raising framework_view
    # yields no offers (never breaks the menu).
    try:
        fw_views = actor.framework_view()
    except Exception:  # noqa: BLE001
        fw_views = []
    for fv in fw_views:
        if len(fv.slots) < 2:
            continue
        # Build a slot-list summary for the picker.
        slot_names = ", ".join(
            f"{sl.slot_id}({sl.active_points}pts)"
            for sl in fv.slots
        )
        actions.append(LegalAction(
            action_id=f"reallocate_slots:{fv.framework_id}:{','.join(sl.slot_id for sl in fv.slots)}",
            kind="reallocate",
            target_id=None,
            power_xmlid=fv.xmlid,
            power_name=fv.name,
            summary=(
                f"Reallocate {fv.name} reserve ({fv.reserve_or_pool} pts) — "
                f"choose which slots are active this phase. "
                f"Slots: {slot_names}"
            ),
        ))

    # Task 5: Variable Power Pool reconfigure offer. For each VPP framework,
    # offer one ``reconfigure_vpp:{framework_id}`` action: the actor builds
    # a brand-new power from the catalog (proposed + pool-validated by the
    # reconfigure service), gated on the VPP's control mechanics and persisted
    # as the new active config. Zero-phase like reallocate (consumes the phase,
    # no attack). Same defensive framework_view() above; reuse fw_views.
    for fv in fw_views:
        if fv.kind != "vpp":
            continue
        actions.append(LegalAction(
            action_id=f"reconfigure_vpp:{fv.framework_id}",
            kind="reconfigure_vpp",
            target_id=None,
            power_xmlid=fv.xmlid,
            power_name=fv.name,
            summary=(
                f"Reconfigure {fv.name} VPP (pool {fv.reserve_or_pool} AP) — "
                f"build a new power from the catalog"
            ),
        ))

    # Destructible constructs the actor can attack (break cover / clear a lane).
    # spec §3: one offer per construct (actor's highest-damage ranged attack;
    # fall back to highest-damage melee if no ranged powers exist).
    # Mental attacks (MENTALBLAST/EGOATTACK) are excluded — constructs are
    # physical objects that don't have Mental Defense.
    if has_scene and constructs:
        damaging = [
            ap for ap in attack_powers
            if (ap.damage_dice or 0) > 0
            and (ap.xmlid or "").upper() not in _MENTAL_ATTACK_XMLIDS
        ]
        ranged_damaging = ranged_damaging_attacks(attack_powers)
        best_pool = ranged_damaging or damaging
        # Pick the single highest-dice attack so the AI has the strongest option.
        primary = (
            max(best_pool, key=lambda ap: ap.damage_dice or 0)
            if best_pool else None
        )
        if primary is not None:
            pname = primary.name or (primary.xmlid or "").lower()
            # 6E2 p56: when the actor owns no ranged attack, `best_pool` falls
            # back to their best MELEE power — and a melee attack on a wall
            # still needs the wall inside their Reach. Without this filter a
            # melee-only actor was offered every destructible construct in the
            # arena and the resolver auto-hit it, punching a wall from across
            # the map. A ranged primary is never distance-filtered here (the
            # line-of-sight gate is what governs it).
            _primary_is_melee = not (
                primary.range_m and primary.range_m > 0
            )
            _c_actor_pos = (
                (getattr(scene, "combatant_positions", None) or {}).get(actor.id)
                if scene is not None else None
            )
            for c in constructs:
                if not getattr(c, "destructible", False):
                    continue
                # Never offer the actor's own spawned wall as a target —
                # shooting down your own Force Wall is self-sabotage.
                # Authored walls carry source_combatant_id None (unaffected).
                if getattr(c, "source_combatant_id", None) == actor.id:
                    continue
                if _primary_is_melee and _c_actor_pos is not None:
                    _cpt = _construct_point(c)
                    if _cpt is None:
                        continue
                    from kirby_combat.scene.scene import Position as _CPos

                    if not within_reach(
                        _xyz_dist(
                            _c_actor_pos,
                            _CPos(x=_cpt[0], y=_cpt[1], z=_cpt[2]),
                        ),
                        reach_m,
                    ).in_reach:
                        continue
                actions.append(LegalAction(
                    action_id=f"attack:construct:{c.obj_id}:{_src_id(primary)}",
                    kind="attack_construct",
                    target_id=c.obj_id,
                    targets_construct=True,
                    power_xmlid=primary.xmlid,
                    power_name=primary.name or None,
                    summary=(
                        f"Attack the {c.kind} (DEF {c.def_value} BODY {c.body}) with "
                        f"{pname} — destroy it to open a lane / strip cover"
                    ),
                    _attack_view=primary,
                ))
        # Spec §3 (Task 4): the Rapid Fire MANEUVER (6E2 p75 — not the Autofire
        # advantage) vs a destructible construct. Each shot is a separate attack,
        # so DEF applies PER SHOT: a burst shreds soft cover (wood) while
        # barely chipping hard cover (steel). Same capability test as the
        # PR-61 combatant rapid_fire enumeration: a ranged power
        # (range_m > 0); mental attacks already filtered out of `damaging`.
        rf_primary = (
            max(ranged_damaging, key=lambda ap: ap.damage_dice or 0)
            if ranged_damaging else None
        )
        if rf_primary is not None:
            rf_pname = rf_primary.name or (rf_primary.xmlid or "").lower()
            for c in constructs:
                if not getattr(c, "destructible", False):
                    continue
                # Same ownership filter as the attack:construct offer above.
                if getattr(c, "source_combatant_id", None) == actor.id:
                    continue
                actions.append(LegalAction(
                    action_id=f"{_power_action_id('rapid_fire', c.obj_id, rf_primary)}:3",
                    kind="rapid_fire",
                    target_id=c.obj_id,
                    targets_construct=True,
                    power_xmlid=rf_primary.xmlid,
                    power_name=rf_primary.name or None,
                    summary=(
                        f"RAPID FIRE {rf_pname} at the {c.kind} "
                        f"(DEF {c.def_value} BODY {c.body}): 3 shots, "
                        f"cumulative -2 OCV per shot, ½ DCV; DEF applies "
                        f"per shot, shredding soft cover (6E2 p75)"
                    ),
                    _attack_view=rf_primary,
                ))

    # Spec §3 (Task 8): a FORCEWALL-capable actor can raise a destructible
    # barrier between itself and the nearest enemy — the mirror of the
    # construct-destruction offers above. One offer regardless of the enemy
    # list; placement is resolved driver-side from persisted positions
    # (_resolve_force_wall), so it needs a scene.
    #
    # Stacking guard: suppress the offer when the actor already has a live
    # force_wall up (source_combatant_id matches actor, body > 0). A wall
    # that has been destroyed (body == 0 or None) does NOT suppress — the
    # actor is free to raise a new one. Another caster's wall never blocks
    # this actor's offer (source_combatant_id differs).
    # Uses has_live_own_force_wall + forcewall_power (shared helpers, above).
    if has_scene:
        if not has_live_own_force_wall(actor.id, constructs):
            fw_power = forcewall_power(actor.hero)
            if fw_power is not None:
                actions.append(LegalAction(
                    action_id=f"force_wall:{_src_id(fw_power)}",
                    kind="force_wall",
                    target_id=None,
                    power_xmlid="FORCEWALL",
                    power_name=getattr(fw_power, "name", None) or "Force Wall",
                    summary=(
                        "Raise a Force Wall between you and the nearest "
                        "enemy (blocks LoS and movement; can be attacked "
                        "down)"
                    ),
                ))

    # Sense-affecting §2 (Darkness): a DARKNESS-capable actor can drop a
    # sense-group darkness field between itself and the nearest enemy — an
    # area occluder for a Sense Group (Sight by default). Mirrors the force-
    # wall offer: one offer regardless of the enemy list; placement +
    # footprint are resolved driver-side from persisted positions
    # (_resolve_darkness_field), so it needs a scene. Once spawned, the
    # perception darkness gate reads it from Scene.constructs automatically —
    # combatants whose sense-line crosses it can't target across it (blind-
    # combat tier), while the creator with Personal Immunity perceives through.
    #
    # Stacking guard: suppress the offer when the actor already has a live OWN
    # darkness_zone up (has_live_own_darkness). Another caster's darkness never
    # blocks this actor's offer (source_combatant_id differs).
    if has_scene:
        if not has_live_own_darkness(actor.id, constructs):
            dk_power = darkness_power(actor.hero)
            if dk_power is not None:
                actions.append(LegalAction(
                    action_id=f"darkness_zone:{_src_id(dk_power)}",
                    kind="darkness_zone",
                    target_id=None,
                    power_xmlid="DARKNESS",
                    power_name=getattr(dk_power, "name", None) or "Darkness",
                    summary=(
                        "Drop a field of Darkness to block line of sight "
                        "between you and the nearest enemy (combatants can't "
                        "target across it; you see through your own if you "
                        "have Personal Immunity)"
                    ),
                ))

    # Sense-affecting §3 (Images): an IMAGES-capable actor can conjure a decoy
    # — a sensory illusion of a foe that draws enemy fire until disbelieved.
    # Mirrors the darkness/force-wall create offer: one offer, placement
    # resolved driver-side (_resolve_create_image_decoy); needs a scene.
    # Stacking guard: suppress when the actor already has a live OWN decoy
    # (``own_decoy_live``, computed driver-side from the decoy table).
    if has_scene and not own_decoy_live:
        img_power = images_power(actor.hero)
        if img_power is not None:
            actions.append(LegalAction(
                action_id=f"image_decoy:{_src_id(img_power)}",
                kind="image_decoy",
                target_id=None,
                power_xmlid="IMAGES",
                power_name=getattr(img_power, "name", None) or "Images",
                summary=(
                    "Conjure an Image decoy near the nearest enemy — a "
                    "lifelike illusion that draws fire; an enemy that fails "
                    "a PER roll to disbelieve wastes attacks on the phantom"
                ),
            ))

    # Throwing spec §4 (Task 2B.3): pick up an adjacent debris chunk to throw
    # next phase. For each ``kind="debris"`` construct whose representative
    # point sits within the actor's melee ``reach_m`` (segment midpoint /
    # polygon centroid vs the actor's scene position), offer a single
    # ``pickup:<obj_id>`` — gated on: the actor isn't already holding one
    # (``actor_holding``), STR ≥ 5, and the actor can LIFT the chunk's mass
    # (weight gate, below). Non-debris constructs (walls / hazards / force_
    # walls) are never offered — only spawned rubble is throwable.
    #
    # Weight gate (spec §4, v1): a debris chunk's mass ≈ ``BODY ·
    # _DEBRIS_KG_PER_BODY`` (50 kg/BODY default); offer only when the actor's
    # cost-engine primary lift (``25 · 2^(STR/5)`` kg) covers it. The lift is
    # computed straight from the integer STR (``_primary_lift_kg``) so it never
    # depends on a live ``hero`` riding the attack_view — the bulk attacks
    # builder doesn't always pass ``hero=``, but ``s.str_`` is always present.
    if (
        has_scene and constructs and not actor_holding and s.str_ >= 5
        and scene is not None
    ):
        actor_pos = (
            (getattr(scene, "combatant_positions", None) or {}).get(actor.id)
        )
        if actor_pos is not None:
            actor_lift_kg = _primary_lift_kg(s.str_)
            for c in constructs:
                if getattr(c, "kind", None) != "debris":
                    continue
                cpt = _construct_point(c)
                if cpt is None:
                    continue
                from kirby_combat.scene.scene import Position as _Pos

                cpos = _Pos(x=cpt[0], y=cpt[1], z=cpt[2])
                if not within_reach(
                    _xyz_dist(actor_pos, cpos), reach_m,
                ).in_reach:
                    continue
                pd = c.def_value if c.def_value is not None else 0
                # ``c.body`` is the chunk's CURRENT body (== max_body for a
                # fresh chunk); it's the figure the throw-damage cap reads.
                body = c.body if getattr(c, "body", None) is not None else 1
                if _debris_mass_kg(body) > actor_lift_kg + _EPS_M:
                    continue  # too heavy for this actor to lift/throw
                actions.append(LegalAction(
                    action_id=f"pickup:{c.obj_id}",
                    kind="pickup",
                    target_id=None,
                    power_xmlid=None,
                    power_name=None,
                    summary=(
                        f"Pick up the debris chunk (DEF {pd} BODY {body}) "
                        f"— throw it next phase"
                    ),
                ))

    # Throwing spec §4 (Task 2B.4): hurl the held debris chunk at an enemy.
    # When the actor is HOLDING a chunk (``actor_holding`` + ``held_construct_id``
    # threaded from the actor's row), offer one ``throw_object:<held_id>:<enemy>``
    # per LIVING enemy. This is a ranged-ish attack — NO reach gate (a brick
    # lobs a wall-chunk across the field). Damage = ``min(STR dice, PD+BODY)``
    # (codex cap), so the summary names the expected dice using the SAME engine
    # ``resolve_object_throw`` the resolver applies — enumeration and resolution
    # can't drift on the cap. The chunk's PD = ``def_value`` + BODY = current
    # ``body`` are read from the matching construct in ``constructs``.
    if actor_holding and held_construct_id and alive_enemies:
        held = None
        for c in (constructs or []):
            if getattr(c, "obj_id", None) == held_construct_id:
                held = c
                break
        if held is not None:
            held_pd = held.def_value if held.def_value is not None else 0
            held_body = held.body if getattr(held, "body", None) is not None else 0
            # blunt rubble → normal damage (v1: debris is always blunt).
            dice, _dtype = resolve_object_throw(
                s.str_, held_pd, held_body, "normal",
            )
            for enemy in alive_enemies:
                actions.append(LegalAction(
                    action_id=f"throw_object:{held_construct_id}:{enemy.id}",
                    kind="throw_object",
                    target_id=enemy.id,
                    power_xmlid=None,
                    power_name=None,
                    summary=(
                        f"Hurl the debris chunk (DEF {held_pd} BODY {held_body}) "
                        f"at {_friendly(enemy)} — {dice}d6N, "
                        f"min(STR dice, PD+BODY); consumes the chunk"
                    ),
                ))

    # Unarmed Strike if STR ≥ 5 and no HtH attack already in the list.
    # A gated HtH (move_strike) also counts so we don't double-offer a bare
    # punch alongside a HANDTOHANDATTACK close-and-strike.
    has_unarmed = any(
        a.power_xmlid in {"HANDTOHANDATTACK", "HA"}
        and a.kind in ("attack", "move_strike")
        for a in actions
    )
    if s.str_ >= 5 and not has_unarmed:
        try:
            strike = actor.str_strike_view()
        except Exception:
            strike = None
        if strike is not None:
            for enemy in alive_enemies:
                # Reach spec §2: gate the bare STR strike by distance too.
                gate = _melee_gate(enemy.id)
                if gate == "block":
                    continue
                if gate == "close":
                    # Dedup: the synthesized-STR brawler path may already have
                    # emitted this move_strike via the attack block above.
                    msid = f"move_strike:{enemy.id}:STR"
                    if not any(a.action_id == msid for a in actions):
                        actions.append(LegalAction(
                            action_id=msid,
                            kind="move_strike",
                            target_id=enemy.id,
                            power_xmlid="STR",
                            power_name="Strike",
                            summary=(
                                f"Close to within reach via Running, then "
                                f"punch {_friendly(enemy)} (STR/5 = "
                                f"{strike.damage_dice}d6N)"
                            ),
                        ))
                    continue
                actions.append(LegalAction(
                    action_id=f"strike:{enemy.id}",
                    kind="strike",
                    target_id=enemy.id,
                    power_xmlid="STRIKE",
                    power_name="Strike",
                    summary=(
                        f"Punch {_friendly(enemy)} (STR/5 = "
                        f"{strike.damage_dice}d6N, OCV {s.ocv})"
                    ),
                    _attack_view=strike,
                ))

    # PR-11: Presence attacks. One option per alive enemy. The
    # picker can choose to demoralize/rattle/cow rather than deal
    # damage — useful when the target has high defenses or when an
    # ally needs the target's OCV/DCV cut for the next attack.
    pre = actor.combat_stats().pre
    base_dice = pre // 5
    if base_dice >= 1:
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=f"presence_attack:{enemy.id}",
                kind="presence_attack",
                target_id=enemy.id, power_xmlid=None, power_name=None,
                summary=(
                    f"Presence Attack on {_friendly(enemy)} "
                    f"(PRE {pre} → {base_dice}d6 vs target's PRE) — "
                    f"demoralize / cower instead of damage"
                ),
            ))

    # Defensive / utility — always available.
    actions.append(LegalAction(
        action_id="dodge",
        kind="dodge",
        target_id=None, power_xmlid=None, power_name=None,
        summary=(
            "Dodge — +3 DCV until your next phase "
            "(full DCV bonus, but no attack)"
        ),
    ))
    actions.append(LegalAction(
        action_id="set",
        kind="set",
        target_id=None, power_xmlid=None, power_name=None,
        summary="Set — +1 OCV next phase (telegraphed strike)",
    ))
    # Perception §4: Hide — a self-targeted action (mirrors Dodge) offered only
    # when the actor has cover/concealment available (a cover feature within
    # reach) AND isn't already hidden. Resolving it sets the actor's is_hidden
    # flag; the perception gate then drops targeted offers against the actor
    # from enemies who can't perceive them. Hide breaks on the actor's next
    # overt attack (break-on-attack, driver-side).
    _actor_already_hidden = bool((concealment or {}).get(actor.id, (False, False))[1])
    if not _actor_already_hidden:
        try:
            _has_cover = _actor_has_cover(actor, scene)
        except Exception:
            _has_cover = False  # fail-closed: no Hide when cover can't be read
        if _has_cover:
            actions.append(LegalAction(
                action_id="hide",
                kind="hide",
                target_id=None, power_xmlid=None, power_name=None,
                summary=(
                    "Hide — break line-of-sight behind cover; enemies who "
                    "can't perceive you can't target you (breaks if you attack)"
                ),
            ))
    # PR-70 / PR-71 / PR-72: Adjustment + Healing powers.
    # Aid boosts allies, Healing restores STUN/BODY on allies, Drain
    # reduces enemy stats. Detected via xmlid on hero.powers.
    aid_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "AID"
    ]
    healing_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "HEALING"
    ]
    drain_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "DRAIN"
    ]
    # Aid + Healing target allies; we surface them targeting NONE so
    # the driver picks the most-needed ally at resolve time. The picker
    # picks "aid" or "heal" without selecting target — actor's own
    # team's most-wounded gets it.
    for ap in aid_powers:
        n = getattr(ap, "levels", 0) or 0
        limit_tag = _limitation_label(actor, ap)
        actions.append(LegalAction(
            action_id=_power_action_id("aid", "self", ap),
            kind="aid",
            target_id=None,
            power_xmlid=ap.xmlid,
            power_name=getattr(ap, "name", None) or "Aid",
            summary=(
                f"AID an ally ({n}d6 stat boost on most-wounded "
                f"teammate, fades at 5 points/turn){limit_tag}"
            ),
            _attack_view=ap,
        ))
    for ap in healing_powers:
        n = getattr(ap, "levels", 0) or 0
        limit_tag = _limitation_label(actor, ap)
        actions.append(LegalAction(
            action_id=_power_action_id("heal", "self", ap),
            kind="heal",
            target_id=None,
            power_xmlid=ap.xmlid,
            power_name=getattr(ap, "name", None) or "Healing",
            summary=(
                f"HEAL most-wounded ally ({n}d6 STUN restored)"
                f"{limit_tag}"
            ),
            _attack_view=ap,
        ))
    for ap in drain_powers:
        n = getattr(ap, "levels", 0) or 0
        limit_tag = _limitation_label(actor, ap)
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("drain", enemy.id, ap),
                kind="drain",
                target_id=enemy.id,
                power_xmlid=ap.xmlid,
                power_name=getattr(ap, "name", None) or "Drain",
                summary=(
                    f"DRAIN {_friendly(enemy)}'s stat ({n}d6 effect, "
                    f"fades at 5 pts/turn — STR/DEX/CON drain hobbles "
                    f"a brick fast){limit_tag}"
                ),
                _attack_view=ap,
            ))
    # PR-97: DISPEL — shut off one of target's defensive powers
    # (Force Field, Armor, DR, Density, Flight, Invisibility) for
    # one phase. Roll levels d6 vs target power's Active Points.
    dispel_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "DISPEL"
    ]
    for ap in dispel_powers:
        n = getattr(ap, "levels", 0) or 0
        # PR-98: surface VARIABLEEFFECT scope in the summary so the
        # picker sees "DISPEL Fire/Heat" not generic "DISPEL". The
        # full scope-token semantics live in the driver; here we
        # just lift the input_value text for human readability.
        scope_label = ""
        for m in (getattr(ap, "assigned_modifiers", []) or []):
            mx = (getattr(m, "xmlid", "") or "").upper()
            if mx == "VARIABLEEFFECT":
                iv = (getattr(m, "input_value", None) or "").strip()
                if iv:
                    scope_label = f" [scope: {iv}]"
                break
        limit_tag = _limitation_label(actor, ap)
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("dispel", enemy.id, ap),
                kind="dispel",
                target_id=enemy.id,
                power_xmlid=ap.xmlid,
                power_name=getattr(ap, "name", None) or "Dispel",
                summary=(
                    f"DISPEL one of {_friendly(enemy)}'s defenses "
                    f"({n}d6 vs the power's Active Points{scope_label} "
                    f"— Force Field, Armor, Flight, Invisibility all "
                    f"fair game; shut-off lasts one phase){limit_tag}"
                ),
                _attack_view=ap,
            ))
    # PR-73: Block as a first-class declaration (not just abort).
    # 6E1 p373: Block has -2 OCV penalty BUT successful Block grants
    # +1 OCV initiative bonus next phase against the blocked attacker.
    # Useful as a defensive setup when expecting a specific incoming.
    if alive_enemies:
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=f"block:{enemy.id}",
                kind="block",
                target_id=enemy.id,
                power_xmlid=None, power_name=None,
                summary=(
                    f"Block {_friendly(enemy)}'s expected attack: "
                    f"OCV vs OCV contest. Success → +1 OCV initiative "
                    f"vs them next phase (6E1 p373)"
                ),
            ))
    # PR-50: Interaction skills as social-combat actions per APG p34.
    # Charm / Persuasion / Conversation / Trading map to the same
    # MC degree ladder when used in combat (EGO+10/20/30 thresholds).
    # Detection: the actor's hero.skills carries the interaction skill.
    _INTERACTION_SKILL_XMLIDS = {
        "CHARM": ("charm", "Charm"),
        "PERSUASION": ("persuasion", "Persuasion"),
        "CONVERSATION": ("conversation", "Conversation"),
        "TRADING": ("trading", "Trading"),
    }
    actor_skills = {
        (getattr(s, "xmlid", "") or "").upper()
        for s in (getattr(actor.hero, "skills", []) or [])
    }
    for sx, (kind, label) in _INTERACTION_SKILL_XMLIDS.items():
        if sx not in actor_skills:
            continue
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=f"{kind}:{enemy.id}",
                kind=kind,
                target_id=enemy.id,
                power_xmlid=sx, power_name=label,
                summary=(
                    f"{label} {_friendly(enemy)}: skill roll vs "
                    f"target's complications/EGO; success bands map "
                    f"to MC degree ladder (APG p34)"
                ),
            ))
    # PR-48/RAW: Coordinate attacks with same-phase allies against one
    # target. The driver resolves roll + join + execution semantics.
    if alive_enemies and allow_coordinate:
        # A coordinate offer is power-agnostic (the attack is declared later),
        # so it is only worth offering against an enemy this actor could
        # actually contribute an attack to. Two conditions, and they are
        # deliberately NOT the same:
        #
        #   * a RANGED attack reaches across the map, and 6E2 p36 does not put
        #     it behind Reach — so an actor holding one can coordinate at any
        #     distance. Gating the offer on Reach alone would stop two snipers
        #     forty metres from a target from ever coordinating, which is the
        #     same over-gating this whole line of work exists to avoid.
        #   * an actor with only MELEE attacks can contribute nothing unless
        #     the enemy is already inside their Reach (6E2 p56). Coordination
        #     resolves on the pool's timing window, not after a half-move, so
        #     a "close" verdict is worth nothing here — "direct" only, the
        #     same standard Sweep and Throw use.
        # This is the construct the HAYMAKER offer below already uses
        # (``_has_ranged_attack or _has_landable_melee``), for the same reason:
        # Haymaker is likewise a power-agnostic declaration whose attack comes
        # later. Use ``_is_melee`` rather than a raw ``range_m > 0`` test so
        # the two agree — they diverge for any power with ``is_ranged=True``
        # and ``range_m=0``, which is exactly the shape a NORANGE limitation
        # will produce once the engine reads that modifier.
        _coord_has_ranged = any(not _is_melee(ap) for ap in attack_powers)
        for enemy in alive_enemies:
            if not _coord_has_ranged and _melee_gate(enemy.id) != "direct":
                continue
            actions.append(LegalAction(
                action_id=f"coordinate:{enemy.id}",
                kind="coordinate",
                target_id=enemy.id,
                power_xmlid=None, power_name=None,
                summary=(
                    f"Coordinate vs {_friendly(enemy)} — "
                    f"Teamwork (or Tactics/DEX fallback) to join a "
                    f"same-phase coordinated strike (6E2 p46)"
                ),
            ))
    # PR-18: Hold action — declare a held action to react when a
    # trigger fires. Phase is consumed on declare per 6E1 p378. Useful
    # when no current target deserves the attack but an ally is about
    # to act, OR when waiting for an enemy to leave cover.
    if alive_enemies:
        actions.append(LegalAction(
            action_id="hold",
            kind="hold",
            target_id=None, power_xmlid=None, power_name=None,
            summary=(
                "Hold action — wait for a trigger before acting "
                "(phase consumed; release on next phase to react)"
            ),
        ))
    # PR-69: release a previously-declared held action. One option
    # per open held-action row, passed in via open_held_action_ids: this
    # module is layer-clean and reads no database.
    if open_held_action_ids and alive_enemies:
        for held_id in open_held_action_ids:
            actions.append(LegalAction(
                action_id=f"release_held:{held_id}",
                kind="release_held",
                target_id=None, power_xmlid=None, power_name=None,
                summary=(
                    f"Release held action {held_id[:8]} — your "
                    f"trigger has fired; resolve the held intent now"
                ),
            ))
    # PR-21: Haymaker — declare this phase, +4 DC on the FOLLOWING
    # phase's attack, -5 DCV in the meantime (6E2 p73). High-risk
    # high-reward; the picker should choose it when the actor has a clear
    # opening but knows they can survive the DCV penalty (cover, ally
    # screening, etc.).
    # Reach spec §2 (extended): Haymaker is a +DC declaration applied to a
    # FOLLOWING attack. Offer it only when the actor has an attack it could
    # actually land: ANY ranged attack (range gated elsewhere), OR a MELEE
    # attack / bare STR strike against an in-reach enemy (direct band). A
    # melee-only actor at 30 m has nothing to haymaker — suppress it.
    _has_ranged_attack = any(not _is_melee(ap) for ap in attack_powers)
    _has_landable_melee = (
        any(
            _is_melee(ap) and _melee_gate(enemy.id) == "direct"
            for enemy in alive_enemies
            for ap in attack_powers
        )
        or (
            s.str_ >= 5
            and any(_melee_gate(enemy.id) == "direct" for enemy in alive_enemies)
        )
    )
    if alive_enemies and (_has_ranged_attack or _has_landable_melee):
        actions.append(LegalAction(
            action_id="haymaker",
            kind="haymaker",
            target_id=None, power_xmlid=None, power_name=None,
            summary=(
                "Haymaker — declare this phase for +4 DC on next "
                "attack (-5 DCV until resolved)"
            ),
        ))
    # PR-24: PRE attack vs the entire group of witnessing enemies
    # (6E2 p139). One roll, applied against each enemy's PRE. Useful
    # when the actor's PRE/5 is high enough to plausibly cow several
    # foes at once. Same dice eligibility (PRE/5 >= 1) as the single-
    # target version.
    if alive_enemies and len(alive_enemies) >= 2 and (s.pre // 5) >= 1:
        actions.append(LegalAction(
            action_id="presence_attack_group",
            kind="presence_attack_group",
            target_id=None, power_xmlid="PRESENCE_GROUP",
            power_name="Presence Attack (group)",
            summary=(
                f"Group PRE attack vs {len(alive_enemies)} enemies "
                f"(PRE/5 = {s.pre // 5}d6, one roll, individual "
                f"resolution per target)"
            ),
        ))

    # PR-61: Rapid Fire — multiple ranged shots at ONE target, full
    # phase, cumulative -2 OCV per shot, ½ DCV (6E2 p75). Differs
    # from Multiple Attack which targets multiple enemies; Rapid Fire
    # is for spamming one tough target. Only enumerate for ranged
    # powers (those with range_m > 0).
    if alive_enemies and attack_powers:
        for enemy in alive_enemies:
            for ap in attack_powers:
                if not (ap.range_m and ap.range_m > 0):
                    continue
                xmlid_upper = (ap.xmlid or "").upper()
                if xmlid_upper in {"MENTALBLAST", "EGO_ATTACK", "EGOATTACK"}:
                    continue
                pname = ap.name or ap.xmlid.lower()
                # Default: 3 shots. The picker chooses "rapid_fire" with
                # an implicit shot count; resolver uses 3.
                actions.append(LegalAction(
                    action_id=f"{_power_action_id('rapid_fire', enemy.id, ap)}:3",
                    kind="rapid_fire",
                    target_id=enemy.id,
                    power_xmlid=ap.xmlid,
                    power_name=ap.name or None,
                    summary=(
                        f"RAPID FIRE {pname} vs {_friendly(enemy)}: "
                        f"3 shots, all at OCV {_multi_attack_ocv(s.ocv, 3)} "
                        f"(-4 for three), ½ DCV, full-phase (6E2 p75)"
                    ),
                    _attack_view=ap,
                ))
    # PR-59: Multiple Attack — strike all alive enemies in one phase
    # at cumulative -2 OCV per additional target, half DCV per 6E2
    # p73. Surfaces as one action per attack power (target_id=None
    # signals "all alive enemies"). Only enumerated when there are
    # 2+ enemies — pointless for single-target.
    # PR-68: Sweep — HtH-only flavor of Multiple Attack (range_m
    # absent or 0). Same math, different framing for the picker.
    if len(alive_enemies) >= 2 and attack_powers:
        for ap in attack_powers:
            xmlid_upper = (ap.xmlid or "").upper()
            if xmlid_upper in {"MENTALBLAST", "EGO_ATTACK", "EGOATTACK"}:
                continue
            pname = ap.name or ap.xmlid.lower()
            is_hth = not (ap.range_m and ap.range_m > 0)
            kind = "sweep" if is_hth else "multiple_attack"
            label = "SWEEP" if is_hth else "MULTIPLE ATTACK"
            # 6E2 p56: every shot of a Sweep is a hand-to-hand attack, so it
            # can only touch enemies already inside the actor's Reach. Sweep
            # is FULL-PHASE, so there is no half-move in front of it — a
            # 'close' verdict is no use here and only 'direct' counts.
            # Without this the offer read "hit all N enemies" no matter how
            # far away they stood, and the resolver hit them all at
            # distance_m=0.0. Multiple Attack (ranged) is unaffected.
            if is_hth:
                reachable_enemies = [
                    e for e in alive_enemies
                    if _melee_gate(e.id) == "direct"
                ]
                # Fewer than 2 in reach is not a Sweep — the outer gate already
                # says the maneuver is pointless single-target, and a Sweep
                # narrowed to one enemy is a plain strike at ½ DCV.
                if len(reachable_enemies) < 2:
                    continue
            else:
                reachable_enemies = alive_enemies
            n = len(reachable_enemies)
            scope = (
                f"hit all {n} enemies" if n == len(alive_enemies)
                else f"hit the {n} of {len(alive_enemies)} enemies in reach"
            )
            actions.append(LegalAction(
                action_id=f"{_power_action_id(kind, 'self', ap)}:all",
                kind=kind,
                target_id=None,
                power_xmlid=ap.xmlid,
                power_name=ap.name or None,
                summary=(
                    f"{label} with {pname}: {scope}, EVERY shot at OCV "
                    f"{_multi_attack_ocv(s.ocv, n)} "
                    f"(-{2 * max(0, n - 1)} for {n} attacks); miss one and "
                    f"the rest miss too; full-phase, ½ DCV (6E2 p73)"
                ),
                _attack_view=ap,
            ))
    # PR-47: Push — spend +5 END for +1 DC on a specific attack
    # (6E2 p133). Per-power × per-enemy variant of attack with the
    # cost/damage tradeoff. We surface one "push" option per
    # (attack power × alive enemy) so the picker can choose which
    # attack to push without exploding the menu.
    if attack_powers:
        for enemy in alive_enemies:
            for ap in attack_powers:
                pname = ap.name or ap.xmlid.lower()
                xmlid_upper = (ap.xmlid or "").upper()
                if xmlid_upper in {"MENTALBLAST", "EGO_ATTACK", "EGOATTACK"}:
                    continue  # mental attacks have their own kind
                # Reach spec §2 (extended): pushing a MELEE attack at range is
                # the same phantom-punch bug — gate it. Pushing a RANGED attack
                # at range is legal, so only gate when the power is melee.
                if _is_melee(ap) and _melee_gate(enemy.id) != "direct":
                    continue
                base = ap.damage_dice or 0
                actions.append(LegalAction(
                    action_id=_power_action_id("push", enemy.id, ap),
                    kind="push",
                    target_id=enemy.id,
                    power_xmlid=ap.xmlid,
                    power_name=ap.name or None,
                    summary=(
                        f"PUSH {pname} vs {_friendly(enemy)}: "
                        f"+1 DC ({base + 1}d6 instead of {base}d6) "
                        f"for +5 END (6E2 p133)"
                    ),
                    _attack_view=ap,
                ))
    # PR-47: Spread — trade attack dice for OCV. Each die spread =
    # +1 OCV (6E2 p52). Surfaced as one "spread by 2" option per
    # attack power × enemy when the actor has at least 3 dice
    # available (so post-spread damage is non-trivial).
    if attack_powers:
        for enemy in alive_enemies:
            for ap in attack_powers:
                base = ap.damage_dice or 0
                if base < 3:
                    continue
                xmlid_upper = (ap.xmlid or "").upper()
                if xmlid_upper in {"MENTALBLAST", "EGO_ATTACK", "EGOATTACK"}:
                    continue
                # Reach spec §2 (extended): spreading a MELEE attack at range is
                # phantom-punching — gate it. Ranged spread at range is legal.
                if _is_melee(ap) and _melee_gate(enemy.id) != "direct":
                    continue
                pname = ap.name or ap.xmlid.lower()
                actions.append(LegalAction(
                    action_id=f"{_power_action_id('spread', enemy.id, ap)}:2",
                    kind="spread",
                    target_id=enemy.id,
                    power_xmlid=ap.xmlid,
                    power_name=ap.name or None,
                    summary=(
                        f"SPREAD {pname} vs {_friendly(enemy)}: "
                        f"sacrifice 2 dice ({base}d6 → {base - 2}d6) "
                        f"for +2 OCV (6E2 p52)"
                    ),
                    _attack_view=ap,
                ))
    # PR-22: Grab — physical hold on a single target. -1 OCV to hit
    # (6E2 p67), -2 DCV to the grabber while held. Target loses
    # actions until they break free (STR contest) or the grabber
    # releases. v1: declare+resolve in one phase, set is_held flag.
    if s.str_ >= 5:
        for enemy in alive_enemies:
            # Reach spec §2 (extended): Grab is a pure STR melee maneuver —
            # inherently adjacency-required. Spec A has no move-and-grab
            # composite, so offer ONLY when within reach (gate == 'direct');
            # suppress on 'close'/'block' (AI closes via move/move_strike).
            if _melee_gate(enemy.id) != "direct":
                continue
            actions.append(LegalAction(
                action_id=f"grab:{enemy.id}",
                kind="grab",
                target_id=enemy.id,
                power_xmlid="GRAB", power_name="Grab",
                summary=(
                    f"Grab {_friendly(enemy)} (-1 OCV to hit, "
                    f"-2 DCV until released)"
                ),
            ))
    # PR-32: Throw — only available when an enemy is currently held
    # (is_held flag on their session_combatant row). Damage = STR/5
    # d6N, target lands STR-scaled meters away. v1 assumes the actor
    # is the grabber (true in 1v1; multi-combatant disambiguation
    # via held_by_combatant_id is a follow-up). The held_target_ids
    # parameter lets the driver pre-compute who's eligible without
    # this function needing DB access.
    if s.str_ >= 5 and held_target_ids:
        held_set = set(held_target_ids)
        for enemy in alive_enemies:
            if enemy.id not in held_set:
                continue
            # 6E2 p56/p67: a Throw is hand-to-hand — you cannot hurl someone
            # you are not holding on to. ``held_target_ids`` is built from the
            # TARGET's bare ``is_held`` boolean, which records that SOMEBODY
            # has hold of them, not that THIS actor does and not where either
            # of them is standing. So an ally's Grab, or the actor's own Grab
            # followed by a move, left a held-but-distant enemy throwable from
            # across the arena — and the resolver auto-hits. Throw resolves
            # IMMEDIATELY, so a "close" verdict is worth nothing here: require
            # "direct", exactly as Sweep does.
            if _melee_gate(enemy.id) != "direct":
                continue
            throw_dc = s.str_ // 5
            actions.append(LegalAction(
                action_id=f"throw:{enemy.id}",
                kind="throw",
                target_id=enemy.id,
                power_xmlid="THROW", power_name="Throw",
                summary=(
                    f"Throw {_friendly(enemy)}: {throw_dc}d6N normal "
                    f"damage, target lands STR-scaled meters away "
                    f"(auto-hits, releases the hold)"
                ),
            ))
    # PR-38: Mind Control — derived directly from hero.powers since
    # MINDCONTROL isn't in the engine's "attacks" filter (which is
    # damage-shaped powers only). On success, target gets a degree
    # ladder (none / ego_push / simple / contrary / violent) that
    # gates what commands the controller can issue.
    # PR-43: skip ALL mental-source powers when paralysis is active.
    if block_mental_powers:
        mind_control_powers: list = []
    else:
        mind_control_powers = [
            p for p in (actor.hero.powers or [])
            if (getattr(p, "xmlid", "") or "").upper() in {"MINDCONTROL", "MIND_CONTROL"}
        ]
    for mc_power in mind_control_powers:
        # The dice count for a Mind Control power = levels (1d6 per
        # 5 Active Points, simplified to 1d6 per level for v1).
        mc_dice = getattr(mc_power, "levels", 0) or 0
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("mind_control", enemy.id, mc_power),
                kind="mind_control",
                target_id=enemy.id,
                power_xmlid=mc_power.xmlid,
                power_name=getattr(mc_power, "name", None) or "Mind Control",
                summary=(
                    f"Mind Control {_friendly(enemy)} ({mc_dice}d6 "
                    f"effect vs target EGO; degree ladder: simple → contrary "
                    f"→ violent commands)"
                ),
                _attack_view=mc_power,
            ))
    # Sense-affecting §1 (Flash): a FLASH power blinds a target's Sense
    # Group(s) for ``max(0, BODY - Flash Defense)`` Segments. Like Mind
    # Control, FLASH isn't damage-shaped so it's absent from the engine's
    # ``attacks`` filter — read it straight off ``hero.powers``. It's a
    # RANGED, physical offer: the perception gate below keys it on
    # ``targetable_physical`` (the actor must perceive the target to blind
    # it), and the dedicated resolver (_resolve_flash) rolls Flash BODY vs
    # the target's Flash Defense and persists per-Sense-Group flashed rows.
    flash_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "FLASH"
    ]
    for fl_power in flash_powers:
        fl_dice = getattr(fl_power, "levels", 0) or 0
        groups = sorted(flash_groups(fl_power)) or ["sight"]
        groups_label = "/".join(groups)
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("flash", enemy.id, fl_power),
                kind="flash",
                target_id=enemy.id,
                power_xmlid=fl_power.xmlid,
                power_name=getattr(fl_power, "name", None) or "Flash",
                summary=(
                    f"Flash {_friendly(enemy)} ({fl_dice}d6 Flash BODY vs "
                    f"{groups_label}; blinds for BODY − Flash Defense "
                    f"Segments — drops them into the blind-combat tier)"
                ),
                _attack_view=fl_power,
            ))

    # PR-43: Mental Entangle — ENTANGLE power with a child modifier
    # whose xmlid is VERSUSEGO ("Works Against EGO" advantage).
    # Defended by Mental Defense, escape via 3d6 EGO Roll, mental
    # paralysis (target can't use mental powers while bound).
    def _has_versus_ego(power) -> bool:
        for m in getattr(power, "assigned_modifiers", []) or []:
            mx = (getattr(m, "xmlid", "") or "").upper()
            if mx == "VERSUSEGO":
                return True
        return False

    if block_mental_powers:
        mental_entangle_powers: list = []
    else:
        mental_entangle_powers = [
            p for p in (actor.hero.powers or [])
            if (getattr(p, "xmlid", "") or "").upper() == "ENTANGLE"
            and _has_versus_ego(p)
        ]
    # PR-63: physical Entangle (6E1 p102). ENTANGLE without VERSUSEGO.
    # Persisted separately on the row; escape via STR contest.
    physical_entangle_powers = [
        p for p in (actor.hero.powers or [])
        if (getattr(p, "xmlid", "") or "").upper() == "ENTANGLE"
        and not _has_versus_ego(p)
    ]
    for pe_power in physical_entangle_powers:
        body_dice = getattr(pe_power, "levels", 0) or 0
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("entangle", enemy.id, pe_power),
                kind="entangle",
                target_id=enemy.id,
                power_xmlid=pe_power.xmlid,
                power_name=getattr(pe_power, "name", None) or "Entangle",
                summary=(
                    f"Entangle {_friendly(enemy)} ({body_dice}d6 BODY "
                    f"vs PD; target trapped, escape via STR contest)"
                ),
                _attack_view=pe_power,
            ))
    for me_power in mental_entangle_powers:
        body_dice = getattr(me_power, "levels", 0) or 0
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("mental_entangle", enemy.id, me_power),
                kind="mental_entangle",
                target_id=enemy.id,
                power_xmlid=me_power.xmlid,
                power_name=getattr(me_power, "name", None) or "Mental Entangle",
                summary=(
                    f"Mental Entangle vs {_friendly(enemy)} "
                    f"({body_dice}d6 BODY vs Mental Defense; "
                    f"target paralyzed mental-powers-only until "
                    f"they roll EGO to escape)"
                ),
                _attack_view=me_power,
            ))
    # PR-42: Mental Illusion — same source-power discovery pattern as
    # Mind Control. Effect dice → degree ladder vs target EGO. The
    # target perceives a sensory hallucination until they make a
    # disbelief check. Doesn't directly damage STUN/BODY (6E1 p109).
    if block_mental_powers:
        mental_illusion_powers: list = []
    else:
        mental_illusion_powers = [
            p for p in (actor.hero.powers or [])
            if (getattr(p, "xmlid", "") or "").upper() in {"MENTALILLUSION", "MENTAL_ILLUSION"}
        ]
    # PR-44: Telepathy — read thoughts. Effect roll vs target EGO →
    # degree (surface_thoughts → specific_memories → deep_thoughts →
    # subconscious). Doesn't damage. Intel arrives via the resolver's
    # result_payload, which lands in ActionResolved and is visible
    # in subsequent turn history.
    if block_mental_powers:
        telepathy_powers: list = []
    else:
        telepathy_powers = [
            p for p in (actor.hero.powers or [])
            if (getattr(p, "xmlid", "") or "").upper() == "TELEPATHY"
        ]
    for tp_power in telepathy_powers:
        tp_dice = getattr(tp_power, "levels", 0) or 0
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("telepathy", enemy.id, tp_power),
                kind="telepathy",
                target_id=enemy.id,
                power_xmlid=tp_power.xmlid,
                power_name=getattr(tp_power, "name", None) or "Telepathy",
                summary=(
                    f"Read {_friendly(enemy)}'s thoughts "
                    f"({tp_dice}d6 effect vs target EGO; degree gates "
                    f"intel depth: surface → memories → deep → "
                    f"subconscious)"
                ),
                _attack_view=tp_power,
            ))
    for mi_power in mental_illusion_powers:
        mi_dice = getattr(mi_power, "levels", 0) or 0
        for enemy in alive_enemies:
            actions.append(LegalAction(
                action_id=_power_action_id("mental_illusion", enemy.id, mi_power),
                kind="mental_illusion",
                target_id=enemy.id,
                power_xmlid=mi_power.xmlid,
                power_name=getattr(mi_power, "name", None) or "Mental Illusion",
                summary=(
                    f"Mental Illusion vs {_friendly(enemy)} "
                    f"({mi_dice}d6 effect vs target EGO; degree: "
                    f"partial / full / complete sensory hallucination)"
                ),
                _attack_view=mi_power,
            ))
    # PR-35: Trip — knock the target prone (6E2 p67). -1 OCV, no
    # damage, on hit the target's is_prone flag flips. Prone targets
    # take +2 OCV from melee attackers, -2 to their own OCV. Half-
    # phase action.
    if s.str_ >= 5:
        for enemy in alive_enemies:
            # Reach spec §2 (extended): Trip is a pure STR melee maneuver —
            # offer ONLY within reach (direct band). Suppress on close/block.
            if _melee_gate(enemy.id) != "direct":
                continue
            actions.append(LegalAction(
                action_id=f"trip:{enemy.id}",
                kind="trip",
                target_id=enemy.id,
                power_xmlid="TRIP", power_name="Trip",
                summary=(
                    f"Trip {_friendly(enemy)}: half-phase, -1 OCV, "
                    f"target falls prone (-2 to their OCV, +2 to "
                    f"melee attackers next phase)"
                ),
            ))
    # PR-35: Disarm — knock a weapon out of the target's hand (6E2
    # p65). -2 OCV. v1 narrative-only: lands an event in the audit log
    # but doesn't mechanically remove a weapon (we don't track weapons
    # granularly yet). Useful for the picker's strategic vocabulary.
    if s.str_ >= 5:
        for enemy in alive_enemies:
            # Reach spec §2 (extended): Disarm is a pure STR melee maneuver —
            # offer ONLY within reach (direct band). Suppress on close/block.
            if _melee_gate(enemy.id) != "direct":
                continue
            actions.append(LegalAction(
                action_id=f"disarm:{enemy.id}",
                kind="disarm",
                target_id=enemy.id,
                power_xmlid="DISARM", power_name="Disarm",
                summary=(
                    f"Disarm {_friendly(enemy)}: half-phase, -2 OCV, "
                    f"strip their weapon (narrative effect this phase)"
                ),
            ))
    # PR-33: Move-By + Move-Through — velocity-based maneuvers per
    # 6E2 p72. Both require a scene (positions must exist) and at
    # least minimal RUNNING. Move-By is half-phase, Move-Through
    # full-phase; the picker chooses based on damage-vs-self-risk
    # tradeoff. Damage scales with velocity, so high-RUNNING
    # combatants make these their bread and butter.
    if has_scene and s.str_ >= 5:
        try:
            running_m = actor.hero.characteristic_value("RUNNING")
        except Exception:
            running_m = 12.0
        if running_m and running_m >= 6.0:
            # Pre-compute the damage envelope so the summary can LEAD
            # with what the picker cares about (DCs landed) instead of
            # the cost (-OCV / -DCV / self-damage). Magnum-class
            # models take the first numeric they see as the salient
            # tradeoff; burying damage behind penalties biases them
            # away from these maneuvers.
            mb_str_dc = (s.str_ // 2) // 5
            mb_vel_dc = int(running_m // 10)
            mb_total = mb_str_dc + mb_vel_dc
            mt_str_dc = s.str_ // 5
            mt_vel_dc = int(running_m // 6)
            mt_total = mt_str_dc + mt_vel_dc
            mt_ocv_pen = int(running_m // 10)
            # 6E2 p56 + p72: a velocity maneuver is a CONTACT attack — the
            # damage comes from running into someone. So the offer is gated
            # not on where the enemy is now (the actor is meant to be far
            # away and charge) but on whether the charge can actually END in
            # contact: run ``movement_reach`` toward them with this
            # maneuver's own movement budget and ask the engine whether the
            # landing is within reach. Without this the offer was
            # unconditional and the resolver teleported the attacker to the
            # target's x/y with z untouched — 34 STUN delivered from a
            # rooftop to a street six metres below.
            #
            # This gate got MORE load-bearing as a side effect of correcting
            # base reach to 1m: direct strikes are refused more often, so an
            # unconditional velocity maneuver is picked more.
            #
            # Budgets follow the maneuvers' own phase costs, as the resolver
            # states them: Move-Through is full-phase and spends the whole
            # running allowance; Move-By is half-phase and spends half.
            # No scene geometry (legacy ``has_scene`` without positions) ⇒
            # nothing to judge ⇒ ungated, as everywhere else.
            _vel_positions = (
                (getattr(scene, "combatant_positions", None) or {})
                if scene is not None else {}
            )
            _vel_actor_pos = _vel_positions.get(actor.id)

            def _charge_connects(enemy_id: str, budget_m: float) -> bool:
                if _vel_actor_pos is None:
                    return True          # no geometry to judge
                _epos = _vel_positions.get(enemy_id)
                if _epos is None:
                    return True
                from kirby_combat.scene.movement_legality import (
                    movement_reach as _mr,
                )

                try:
                    out = _mr(
                        "running", _vel_actor_pos, _epos, budget_m, scene,
                        combatant_id=actor.id,
                    )
                except Exception:  # noqa: BLE001
                    # A scene this enumerator cannot walk is a scene it cannot
                    # judge, so it does not gate — the same fail-open contract
                    # every other gate here follows, and the resolution-side
                    # check still fires. (Several suites pass a stub scene
                    # object that carries only the fields THEY need.)
                    return True
                return bool(out.reachable) and within_reach(
                    _xyz_dist(out.landing, _epos), reach_m,
                ).in_reach

            for enemy in alive_enemies:
                if _charge_connects(enemy.id, running_m / 2.0):
                    actions.append(LegalAction(
                        action_id=f"move_by:{enemy.id}",
                        kind="move_by",
                        target_id=enemy.id,
                        power_xmlid="MOVE_BY", power_name="Move-By",
                        summary=(
                            f"Move-By {_friendly(enemy)}: "
                            f"{mb_total}d6N normal damage "
                            f"(STR/2 + vel/10, half-phase). "
                            f"Cost: -2 OCV / -2 DCV, 1/3 self-damage."
                        ),
                    ))
                if _charge_connects(enemy.id, running_m):
                    actions.append(LegalAction(
                        action_id=f"move_through:{enemy.id}",
                        kind="move_through",
                        target_id=enemy.id,
                        power_xmlid="MOVE_THROUGH", power_name="Move-Through",
                        summary=(
                            f"Move-Through {_friendly(enemy)}: "
                            f"{mt_total}d6N normal damage "
                            f"(STR + vel/6, full-phase, BIG hit). "
                            f"Cost: -{mt_ocv_pen} OCV / -3 DCV, "
                            f"1/2 self-damage."
                        ),
                    ))
    if (
        actor.state.current_stun < s.max_stun // 2
        or actor.state.current_end < s.max_end // 3
    ):
        actions.append(LegalAction(
            action_id="recover",
            kind="recover",
            target_id=None, power_xmlid=None, power_name=None,
            summary=(
                f"Recover — regain {s.rec} STUN + {s.rec} END "
                f"(skip phase, sitting-duck DCV ½)"
            ),
        ))

    # ── Movement (PR-9 + movement spec §3) ──────────────────────────────────
    #
    # Movement only makes sense when the session has a scene with positions.
    #
    # When the driver threads the actor's ``movement_view()`` (``movement``) +
    # the hydrated ``scene`` (with positions in ``scene.combatant_positions``),
    # we enumerate EVERY available mode (running / leaping / flight /
    # teleportation / swimming / tunneling), each gated by the engine
    # ``movement_reach`` against the real geometry — so a runner blocked by a
    # wall + elevation gets NO running offer while a leaper that clears the wall
    # does (spec §3 done-means). RUNNING keeps the bare ``move:<enemy>`` /
    # ``move_strike:<enemy>:<xmlid>`` ids (low churn — existing move tests are
    # unchanged); every other mode adds a ``:<mode>:`` segment.
    #
    # Action-id shape: ``move:<enemy>`` (running alias) / ``move:<mode>:<enemy>``;
    #                  ``move_strike:<enemy>:<xmlid>`` / ``move_strike:<mode>:<enemy>:<xmlid>``.
    # The mode is also carried explicitly on ``LegalAction.mode`` for the
    # resolver (Task 2.2).
    #
    # Distance rule: a pure reposition ``move`` uses the FULL combat distance
    # toward the enemy and is offered only when ``movement_reach`` is
    # ``reachable`` (a blocked mode lands short → not offered — keeps the gate
    # crisp + consistent with the move_strike gate). A ``move_strike`` composite
    # uses the HALF-move distance (move + strike in one phase, mirroring the
    # RUNNING half-move) and is offered when the half-move lands within melee
    # ``reach_m`` of the enemy.
    _gated_movement = (
        has_scene and movement and scene is not None
        and (getattr(scene, "combatant_positions", None) or {}).get(actor.id)
        is not None
    )
    if _gated_movement:
        from kirby_combat.scene.movement_legality import movement_reach

        positions = scene.combatant_positions
        actor_pos = positions[actor.id]
        # Dedup the capability list by mode, keeping the max combat_m (a VPP can
        # surface two FLIGHT entries — mirror movement_view's note).
        best_by_mode: dict[str, Any] = {}
        for cap in movement:
            cap_mode = getattr(cap, "mode", None)
            if not cap_mode:
                continue
            cur = best_by_mode.get(cap_mode)
            if cur is None or (cap.combat_m or 0) > (cur.combat_m or 0):
                best_by_mode[cap_mode] = cap

        # Best melee attack for the move_strike composite (highest dice). Mirrors
        # the RUNNING close+strike; None ⇒ no melee ⇒ no move_strike offered.
        melee_attacks = [ap for ap in attack_powers if _is_melee(ap)]
        best_melee = (
            max(melee_attacks, key=lambda ap: ap.damage_dice or 0)
            if melee_attacks else None
        )

        for enemy in alive_enemies:
            enemy_pos = positions.get(enemy.id)
            if enemy_pos is None:
                continue
            for mode, cap in best_by_mode.items():
                combat_m = float(cap.combat_m or 0)
                if combat_m <= 0:
                    continue
                half_m = combat_m / 2.0
                is_running = mode == "running"

                # ── pure reposition: full combat distance toward the enemy.
                repos = movement_reach(
                    mode, actor_pos, enemy_pos, combat_m, scene,
                    combatant_id=actor.id,
                )
                # move_strike (half-move + strike) is offered independently of
                # whether the full reposition ``move`` succeeds — intentional per
                # HERO half-move-and-strike rules: the actor may be able to close
                # to striking range on a half-move even when a full reposition is
                # blocked, so an enemy may get a move_strike offer without a move
                # offer.
                if repos.reachable:
                    aid = (
                        f"move:{enemy.id}" if is_running
                        else f"move:{mode}:{enemy.id}"
                    )
                    summary = (
                        f"Half-move toward {_friendly(enemy)} "
                        f"(up to {combat_m:g}m; cuts range penalty "
                        f"next phase)"
                    ) if is_running else (
                        f"{mode.title()} toward {_friendly(enemy)} "
                        f"(up to {combat_m:g}m)"
                    )
                    actions.append(LegalAction(
                        action_id=aid, kind="move", target_id=enemy.id,
                        power_xmlid=None, power_name=None, summary=summary,
                        mode=mode,
                    ))

                # ── move-and-strike: HALF-move to within melee reach, strike.
                # move_strike is offered independently of the full reposition
                # move above — see the comment there for the HERO rationale.
                if best_melee is not None:
                    strike_pt = _point_within_reach(
                        actor_pos, enemy_pos, reach_m,
                    )
                    ms = movement_reach(
                        mode, actor_pos, strike_pt, half_m, scene,
                        combatant_id=actor.id,
                    )
                    # Require reachable=True so a blocked/unknown mode whose
                    # landing falls back to from_pos never fires move_strike
                    # just because the actor already stands adjacent to the enemy.
                    within = ms.reachable and within_reach(
                        _xyz_dist(ms.landing, enemy_pos), reach_m,
                    ).in_reach
                    if not within:
                        # Modes that must land on a supported surface (teleport)
                        # can't aim at a mid-air point reach_m short of an
                        # elevated enemy; retry aiming at the enemy's own
                        # (supported) position — landing there is within reach.
                        # Only count this retry if the mode is actually reachable.
                        ms2 = movement_reach(
                            mode, actor_pos, enemy_pos, half_m, scene,
                            combatant_id=actor.id,
                        )
                        if ms2.reachable and within_reach(
                            _xyz_dist(ms2.landing, enemy_pos), reach_m,
                        ).in_reach:
                            within = True
                    if within:
                        ap = best_melee
                        pname = ap.name or (ap.xmlid or "").lower()
                        aid = (
                            f"move_strike:{enemy.id}:{ap.xmlid}" if is_running
                            else f"move_strike:{mode}:{enemy.id}:{ap.xmlid}"
                        )
                        summary = (
                            f"Close to within reach via Running, then strike "
                            f"{_friendly(enemy)} with {pname}"
                        ) if is_running else (
                            f"Close via {mode.title()} (up to {half_m:g}m), "
                            f"then strike {_friendly(enemy)} with {pname}"
                        )
                        actions.append(LegalAction(
                            action_id=aid, kind="move_strike",
                            target_id=enemy.id, power_xmlid=ap.xmlid,
                            power_name=ap.name or None, summary=summary,
                            _attack_view=ap, mode=mode,
                        ))

    elif has_scene:
        # Legacy / scene-without-positions fallback (PR-9): no movement view or
        # no positions threaded → offer the unconditional RUNNING half-move per
        # enemy (the pre-§3 behavior; ungated). Scene-less callers + tests that
        # pass ``has_scene=True`` without ``movement``/``scene`` rely on this.
        running_m = actor.hero.characteristic_value("RUNNING")
        half_move_m = max(0, running_m // 2)
        if half_move_m > 0:
            for enemy in alive_enemies:
                actions.append(LegalAction(
                    action_id=f"move:{enemy.id}",
                    kind="move",
                    target_id=enemy.id, power_xmlid=None, power_name=None,
                    summary=(
                        f"Half-move toward {_friendly(enemy)} "
                        f"(up to {half_move_m}m; cuts range penalty next phase)"
                    ),
                    mode="running",
                ))

    # ── Perception §2: the targeting gate ───────────────────────────────────
    #
    # An actor may only TARGET an enemy its character perceives. We compute the
    # engine ``perceive(actor, enemy, scene)`` ONCE per enemy (threading the
    # per-enemy invisible/hidden concealment the driver supplies) and apply a
    # three-tier, attack-type-aware gate to every targeted offer for that enemy:
    #
    #   * PHYSICAL offer (anything targeted that isn't a mental-attack kind):
    #       - kept as-is iff ``perceive.targetable_physical``;
    #       - else, if the enemy is ADJACENT (``_melee_gate == "direct"``), keep
    #         HtH-only physical offers, marking them ``blind`` (Task 2 applies
    #         the ½ OCV/½ DCV penalty), and DROP ranged physical offers;
    #       - else DROP all physical offers vs this enemy.
    #   * MENTAL offer (kind in ``_MENTAL_ACTION_KINDS``): kept iff
    #     ``perceive.targetable_mental``; else dropped.
    #
    # FAIL-OPEN: a scene-less call (no positions for either combatant) → perceive
    # returns targetable, so nothing is gated. Any error computing perceive (or
    # ``actor.senses()`` raising) → we do NOT gate that enemy (preserve current
    # behavior — the gate must never break an ordinary fight). Offers that are
    # NOT targeted at an alive enemy (dodge / set / recover / move / force_wall /
    # construct attacks / ally aid+heal / group/multi-target) pass through
    # untouched. ``concealment`` empty / None ⇒ every enemy is (False, False).
    conceal = concealment or {}
    # Sense-affecting §1 (Flash): the OBSERVER's (actor's) currently-flashed
    # Sense Groups. A sense whose group is flashed is skipped in ``perceive``,
    # so a sight-Flashed actor can't perceive the enemy it could otherwise see
    # → it drops into the blind-combat tier (no sight-targeted offer). Keys on
    # the actor, NOT the target — a single frozenset threaded into every perceive
    # call below. Empty / None ⇒ no senses flashed (current behavior).
    _flashed = observer_flashed_groups or frozenset()
    _enemy_ids = {e.id for e in alive_enemies}

    def _gate_targeted(action: LegalAction, perc: Any, gate_band: str) -> LegalAction | None:  # noqa: E501
        """Return the (possibly ``blind``-marked) action to keep, or None to
        drop it, given the per-enemy ``perceive`` result + reach band."""
        if action.kind in _MENTAL_ACTION_KINDS:
            return action if perc.targetable_mental else None
        # Physical offer.
        if perc.targetable_physical:
            return action
        # Unperceived physically. Only HtH offers survive, and only when the
        # actor is adjacent (within reach) — then they resolve blind.
        if gate_band == "direct" and action.kind in _HTH_ACTION_KINDS:
            action.blind = True
            return action
        return None

    if _enemy_ids:
        # Per-enemy perceive result; None ⇒ fail-open (don't gate this enemy).
        perc_by_enemy: dict[str, Any] = {}
        for enemy in alive_enemies:
            inv, hid = conceal.get(enemy.id, (False, False))
            try:
                perc_by_enemy[enemy.id] = perceive(
                    actor, enemy, scene,
                    target_invisible=bool(inv), target_hidden=bool(hid),
                    observer_flashed_groups=_flashed,
                )
            except Exception:
                perc_by_enemy[enemy.id] = None  # fail open

        gated: list[LegalAction] = []
        for a in actions:
            tid = a.target_id
            if tid is None or tid not in _enemy_ids:
                gated.append(a)          # not an enemy-targeted offer
                continue
            if a.kind in _MOVEMENT_ACTION_KINDS:
                gated.append(a)          # movement is repositioning, not a lock
                continue
            perc = perc_by_enemy.get(tid)
            if perc is None:
                gated.append(a)          # fail open for this enemy
                continue
            kept = _gate_targeted(a, perc, _melee_gate(tid))
            if kept is not None:
                gated.append(kept)
        actions = gated

        # Repositioning §2 (offensive ``reposition_strike``): when an enemy is
        # OCCLUDED (a wall blocks the line of fire) or OUT-OF-RANGE, offer a
        # move-to-a-clear-vantage-and-fire composite — IF a movement mode can
        # reach a line-of-sight-clear vantage. We REUSE the per-enemy
        # ``perceive`` result already computed for the gate above (``Perception.
        # kind``), so perception is never recomputed.
        #
        # For each qualifying enemy, for each movement mode the actor has, ask
        # the engine ``nearest_visible_point`` for a vantage within reach
        # (radius = half-move = combat_m/2; a reposition spends a half-move so
        # the other half-phase can fire). ``require_support`` is derived from
        # the mode: a mode that cannot hover is never offered a mid-air
        # destination it would be rejected from by ``movement_reach``. Validate
        # it's actually reachable + supported via ``movement_reach``, and —
        # for TELEPORTATION — require the
        # destination be VISIBLE from the actor (``has_line_of_sight``): no blind
        # blink to an unseen landing. One best offer per (enemy × mode), capped
        # at ≤3 per enemy so the menu stays scannable. The destination rides on
        # ``reposition_dest`` for the Task-2 resolver.
        #
        # FAIL-OPEN: any visibility / movement error → no offer for that mode
        # (never breaks the menu). Scene-less / no positions → no reposition.
        # Only OCCLUDED triggers offensive repositioning — the engine's
        # perceive() emits visible/occluded/hidden/invisible, never a distinct
        # "out_of_range" kind (a far-but-visible enemy is `visible`/targetable).
        # "Move closer because you're out of *range*" is a separate follow-up
        # (needs a distance-vs-attack-range check, not a perception kind) and is
        # partly covered by the existing move-toward / move_strike close.
        _REPOSITION_TRIGGER_PERCEPTIONS = ("occluded",)
        positions = (getattr(scene, "combatant_positions", None) or {}) if scene is not None else {}
        actor_pos = positions.get(actor.id)
        if scene is not None and actor_pos is not None:
            try:
                movement_caps = list(actor.movement_view())
            except Exception:
                movement_caps = []
            # The fire half of the composite uses the actor's strongest RANGED
            # damaging attack (you reposition to restore a LINE OF FIRE). Fall
            # back to the strongest damaging attack of any kind so a melee-only
            # actor still gets a reposition-and-hit offer.
            _ranged = ranged_damaging_attacks(attack_powers)
            _damaging = [ap for ap in attack_powers if (ap.damage_dice or 0) > 0]
            _best_pool = _ranged or _damaging
            best_attack = (
                max(_best_pool, key=lambda ap: ap.damage_dice or 0)
                if _best_pool else None
            )
            # NOT gated on best_attack. reposition_vantage is documented as a
            # full-move NO-ATTACK move toward a line of fire, yet it sat under
            # `best_attack is not None`, so a character with no ranged attack
            # pool was never offered it. That is precisely the brick with a
            # wall in front of him: the direct run is blocked (_running is a
            # straight-line check and stops at any wall), no vantage is
            # offered, and the only remaining way to make progress is to
            # demolish the wall. Which is what he did, repeatedly.
            # The STRIKE loop below still requires an attack; the vantage
            # loop no longer does.
            if movement_caps:
                from kirby_combat.resolution.line_of_sight import (
                    has_line_of_sight,
                )
                from kirby_combat.scene.movement_legality import (
                    mode_requires_support,
                    movement_reach,
                )
                from kirby_combat.scene.visibility import nearest_visible_point

                best_name = best_attack.name or (best_attack.xmlid or "").lower()
                for enemy in alive_enemies:
                    perc = perc_by_enemy.get(enemy.id)
                    if perc is None:
                        continue  # fail-open enemy → no reposition
                    if getattr(perc, "kind", None) not in _REPOSITION_TRIGGER_PERCEPTIONS:
                        continue
                    enemy_pos = positions.get(enemy.id)
                    if enemy_pos is None:
                        continue
                    offered_for_enemy = 0
                    strike_dests: set[tuple[str, tuple[float, float, float]]] = set()
                    for cap in movement_caps:
                        # Move-and-fire needs something to fire.
                        if best_attack is None:
                            break
                        # Evaluate EVERY mode's free half-move reach, even
                        # after the offer cap below is hit — strike_dests
                        # feeds the paid-Push suppression guard further down,
                        # which must hold regardless of the cap. Only
                        # whether we APPEND an offer is capped at 3.
                        half_move = float(getattr(cap, "combat_m", 0.0)) / 2.0
                        if half_move <= 0.0:
                            continue
                        try:
                            dest = nearest_visible_point(
                                actor_pos, enemy_pos, scene,
                                radius=half_move,
                                vertical_reach=float(getattr(cap, "vertical_m", 0.0)),
                                require_support=mode_requires_support(cap.mode),
                            )
                            if dest is None or dest == actor_pos:
                                continue
                            outcome = movement_reach(
                                cap.mode, actor_pos, dest, half_move, scene,
                                combatant_id=actor.id,
                            )
                            if not outcome.reachable:
                                continue
                            if cap.mode == "teleportation" and not has_line_of_sight(
                                scene, actor_pos, dest,
                            ):
                                continue  # no blind blink to an unseen landing
                        except Exception:
                            continue  # fail-open: no offer on error
                        strike_dests.add((cap.mode, (dest.x, dest.y, dest.z)))
                        if offered_for_enemy >= 3:
                            continue
                        actions.append(LegalAction(
                            action_id=f"reposition_strike:{cap.mode}:{offered_for_enemy}",
                            kind="reposition_strike",
                            target_id=enemy.id,
                            power_xmlid=best_attack.xmlid,
                            power_name=best_attack.name or None,
                            summary=(
                                f"Reposition via {cap.mode} to a clear vantage "
                                f"({dest.x:.1f}, {dest.y:.1f}, {dest.z:.1f}) and "
                                f"fire at {_friendly(enemy)} with {best_name}"
                            ),
                            mode=cap.mode,
                            reposition_dest=(dest.x, dest.y, dest.z),
                            _attack_view=best_attack,
                        ))
                        offered_for_enemy += 1

                    # XCOM's Dash: spend the WHOLE phase moving to a vantage
                    # the half-move cannot reach, forgoing this phase's
                    # attack. Offered ALONGSIDE reposition_strike, never as a
                    # fallback for it — a better position next phase can be
                    # worth a phase of fire, and that is a judgement about the
                    # fight, not a default.
                    vantage_offered = 0
                    for cap in movement_caps:
                        if vantage_offered >= 2:
                            break
                        full_move = float(getattr(cap, "combat_m", 0.0))
                        if full_move <= 0.0:
                            continue
                        try:
                            dest = nearest_visible_point(
                                actor_pos, enemy_pos, scene,
                                radius=full_move,
                                vertical_reach=float(getattr(cap, "vertical_m", 0.0)),
                                require_support=mode_requires_support(cap.mode),
                            )
                            if dest is None or dest == actor_pos:
                                continue
                            dest_xyz = (dest.x, dest.y, dest.z)
                            # An identical spot for strictly more cost is
                            # never the right offer.
                            if (cap.mode, dest_xyz) in strike_dests:
                                continue
                            outcome = movement_reach(
                                cap.mode, actor_pos, dest, full_move, scene,
                                combatant_id=actor.id,
                            )
                            if not outcome.reachable:
                                continue
                            if cap.mode == "teleportation" and not has_line_of_sight(
                                scene, actor_pos, dest,
                            ):
                                continue  # no blind blink to an unseen landing
                        except Exception:
                            continue  # fail-open: no offer on error
                        actions.append(LegalAction(
                            action_id=f"reposition_vantage:{cap.mode}:{vantage_offered}",
                            kind="reposition_vantage",
                            target_id=enemy.id,
                            power_xmlid=None,
                            power_name=None,
                            summary=(
                                f"Reposition via {cap.mode} to a clear vantage "
                                f"({dest.x:.1f}, {dest.y:.1f}, {dest.z:.1f}) "
                                f"on {_friendly(enemy)} — forgoes this phase's "
                                f"attack"
                            ),
                            mode=cap.mode,
                            reposition_dest=dest_xyz,
                        ))
                        vantage_offered += 1

                    # Spec §7: a vantage the free half-move cannot reach may
                    # be bought with END by Pushing the movement power
                    # (+10 Active Points at 1 END per Character Point,
                    # 6E2 p133). Unlike the full-move vantage this KEEPS the
                    # attack, so it takes the HALF-move radius plus the push.
                    # Offered only where the free option found nothing —
                    # paying END for a reachable destination is dominated.
                    push_offered = 0
                    for cap in movement_caps:
                        if push_offered >= 2:
                            break
                        if any(m == cap.mode for m, _d in strike_dests):
                            continue        # free option already reaches
                        bonus_m = push_move_metres(cap)
                        if bonus_m <= 0.0:
                            continue        # mode cannot be pushed
                        half_move = float(getattr(cap, "combat_m", 0.0)) / 2.0
                        if half_move <= 0.0:
                            continue
                        pushed_radius = half_move + bonus_m
                        try:
                            dest = nearest_visible_point(
                                actor_pos, enemy_pos, scene,
                                radius=pushed_radius,
                                vertical_reach=float(getattr(cap, "vertical_m", 0.0)),
                                require_support=mode_requires_support(cap.mode),
                            )
                            if dest is None or dest == actor_pos:
                                continue
                            outcome = movement_reach(
                                cap.mode, actor_pos, dest, pushed_radius, scene,
                                combatant_id=actor.id,
                            )
                            if not outcome.reachable:
                                continue
                            if cap.mode == "teleportation" and not has_line_of_sight(
                                scene, actor_pos, dest,
                            ):
                                continue  # no blind blink to an unseen landing
                        except Exception:
                            continue  # fail-open: no offer on error
                        actions.append(LegalAction(
                            action_id=f"reposition_push:{cap.mode}:{push_offered}",
                            kind="reposition_push",
                            target_id=enemy.id,
                            power_xmlid=best_attack.xmlid,
                            power_name=best_attack.name or None,
                            summary=(
                                f"Reposition via PUSHED {cap.mode} "
                                f"(+{bonus_m:.0f}m for +{PUSH_END} END, "
                                f"6E2 p133) to a clear vantage "
                                f"({dest.x:.1f}, {dest.y:.1f}, {dest.z:.1f}) "
                                f"and fire at {_friendly(enemy)} with {best_name}"
                            ),
                            mode=cap.mode,
                            reposition_dest=(dest.x, dest.y, dest.z),
                            push_move_m=bonus_m,
                            push_end=PUSH_END,
                            _attack_view=best_attack,
                        ))
                        push_offered += 1

        # Repositioning §2 (DEFENSIVE ``reposition`` — break contact): when the
        # actor is the matchup-fragile side (faster but fragile vs a heavier
        # hitter — ``_is_fragile_vs``, the shared ``kite_grapple`` predicate) AND
        # that hitter is in / near melee reach (``_melee_gate`` says we can be
        # struck this phase), offer a move to a HIDDEN / open-range point so the
        # fragile fighter can kite away instead of trading blows.
        #
        # Unlike the offensive ``reposition_strike`` (which spends a HALF-move to
        # leave a half-phase for firing), a defensive break-contact uses the FULL
        # combat move budget (``cap.combat_m``) — getting clear is the whole
        # phase. ``target_id`` is None (it is a move, not a target-lock). One best
        # offer per (enemy × mode), capped at ≤2 total so the menu stays scannable.
        #
        # FAIL-OPEN: any visibility / movement error → no offer (never breaks the
        # menu). Scene-less / no positions → no defensive reposition.
        if scene is not None and actor_pos is not None:
            try:
                _def_caps = list(actor.movement_view())
            except Exception:
                _def_caps = []
            if _def_caps:
                from kirby_combat.scene.movement_legality import (
                    mode_requires_support,
                    movement_reach,
                )
                from kirby_combat.scene.visibility import nearest_hidden_point

                _def_offered = 0
                for enemy in alive_enemies:
                    if _def_offered >= 2:
                        break
                    # In / near reach: the hitter can land a blow this phase
                    # (adjacent now, or one half-move closes). Out of reach →
                    # no contact to break.
                    if _melee_gate(enemy.id) not in ("direct", "close"):
                        continue
                    if not _is_fragile_vs(actor, enemy):
                        continue
                    enemy_pos = positions.get(enemy.id)
                    if enemy_pos is None:
                        continue
                    for cap in _def_caps:
                        if _def_offered >= 2:
                            break
                        full_move = float(getattr(cap, "combat_m", 0.0))
                        if full_move <= 0.0:
                            continue
                        try:
                            dest = nearest_hidden_point(
                                actor_pos, enemy_pos, scene,
                                radius=full_move,
                                vertical_reach=float(getattr(cap, "vertical_m", 0.0)),
                                require_support=mode_requires_support(cap.mode),
                            )
                            if dest is None or dest == actor_pos:
                                continue
                            outcome = movement_reach(
                                cap.mode, actor_pos, dest, full_move, scene,
                                combatant_id=actor.id,
                            )
                            if not outcome.reachable:
                                continue
                        except Exception:
                            continue  # fail-open: no offer on error
                        actions.append(LegalAction(
                            action_id=f"reposition:{cap.mode}:{_def_offered}",
                            kind="reposition",
                            target_id=None,
                            power_xmlid=None,
                            power_name=None,
                            summary=(
                                f"Reposition via {cap.mode} to break contact "
                                f"({dest.x:.1f}, {dest.y:.1f}, {dest.z:.1f})"
                            ),
                            mode=cap.mode,
                            reposition_dest=(dest.x, dest.y, dest.z),
                        ))
                        _def_offered += 1
                        break  # one best mode per enemy

    # Climbing (6E1 p70). Offered when the actor is on or beside a climbable
    # face — independent of whether any enemy is present (an empty
    # ``alive_enemies``/``_enemy_ids`` must not suppress climbing). Base
    # 2m/Phase; the optional +2m-per--3 trade is capped at one step, which
    # the rule's own GM-cap permits. Positions are read fresh here (not the
    # ``actor_pos``/``positions`` locals above, which are scoped inside
    # ``if _enemy_ids:``).
    # ------------------------------------------------------------------
    # MOVE TO COVER. Nobody used cover because nobody was ever OFFERED it.
    #
    # The engine gained walls with `cover_level`, `compute_cover_level` to
    # read them, and a Brief that names them -- and no action that put a
    # combatant behind one. Measured on the O.K. Corral benchmark: four
    # cover features on the page, zero cover picks across three fights.
    # The parked kirby-api driver HAD this (`_cover_move_actions`) and it
    # was left behind in the carve-out.
    #
    # OFFERED ONLY WHERE IT WOULD ACTUALLY HELP, which is how a tactics
    # game does it: cover is evaluated for the SPOT against the ACTUAL
    # threats, not asserted from the feature's own cover_level. A wall
    # behind you shields you from nobody, and an offer to hide behind it
    # is an option that cannot work -- the first version made exactly that
    # offer, and the actor moved, stopped against a wall it could not
    # cross, and ended the Phase no safer than it began.
    #
    # One offer per feature within a Half Move (6E2 p.42), so taking cover
    # still leaves an attack. Anything further is a full Move.
    _cover_positions = (
        (getattr(scene, "combatant_positions", None) or {})
        if scene is not None else {}
    )
    _cover_actor_pos = _cover_positions.get(actor.id)
    if scene is not None and _cover_actor_pos is not None:
        import math as _cover_math

        from kirby_combat.scene.cover import (
            compute_cover_level, cover_available, cover_breakdown,
        )
        from kirby_combat.scene.movement_legality import movement_reach

        _threats = [
            _cover_positions[e.id] for e in alive_enemies
            if e.id in _cover_positions
        ]
        _cover_half_move = max(
            0.0, float(actor.hero.characteristic_value("RUNNING") or 0) / 2.0
        )
        for _wall in (getattr(scene, "walls", None) or []):
            if int(getattr(_wall, "cover_level", 0) or 0) <= 0:
                continue
            _spot, _level = cover_available(
                _wall, _cover_actor_pos, _threats, scene,
            )
            if _level <= 0:
                continue        # would not shield this actor from these threats

            # COVER YOU ALREADY HAVE IS NOT AN ACTION.
            #
            # `fight_from_cover` plans two steps -- move to cover, then
            # shoot from it -- and `TacticChooser` reads steps[0] and
            # nothing else, so a two-step plan repeats its first step for
            # ever. Measured: Tom McLaury took cover three Phases running
            # and never fired a shot, and the Earps came through the fight
            # untouched because every man shooting at them had gone to
            # ground and stayed.
            #
            # The menu is the right place to stop it. Offering a move that
            # changes nothing is a no-op wearing an action's name; drop it
            # and the tactic falls through to `sustained_fire`, which is
            # what "take cover and fire from safety" meant.
            _here_now = max(
                (compute_cover_level(
                    shooter_pos=_t, target_pos=_cover_actor_pos,
                    target_is_prone_or_diving=False, scene=scene,
                ) for _t in _threats),
                default=0,
            )
            if _level <= _here_now:
                continue        # no better than where they already stand
            _d = _cover_math.dist(
                (_cover_actor_pos.x, _cover_actor_pos.y), (_spot.x, _spot.y),
            )
            if _d > _cover_half_move + 0.5:
                continue
            # AND THE SPOT MUST BE REACHABLE. The covered side of a
            # movement-blocking wall is often on the far side of it, and
            # you cannot walk through a wall to get behind it -- going
            # round the end is a longer path than `movement_reach` will
            # find, because it clamps toward the destination rather than
            # pathfinds. Without this the menu offered cover the actor
            # could only walk INTO: measured, the mover stopped against
            # the wall and finished the Phase no safer than it began.
            _reach = movement_reach(
                mode="running", from_pos=_cover_actor_pos, to_pos=_spot,
                distance_m=_cover_half_move, scene=scene,
                combatant_id=actor.id,
            )
            if not _reach.reachable:
                continue
            # STATE THE TRADE, NOT JUST THE NUMBER. Cover is applied per
            # shooter, so "cover 2/4" alone invites hiding from one man
            # while four others walk around it. The offer says how many of
            # them it actually covers.
            _covered, _total = cover_breakdown(_wall, _spot, _threats, scene)
            _exposed = _total - _covered
            _flank = (
                "" if _exposed <= 0
                else f"; {_exposed} of {_total} would still have a clear shot"
            )
            actions.append(LegalAction(
                action_id=f"move_to_cover:{_wall.id}",
                kind="move_to_cover",
                target_id=None,
                power_xmlid=None,
                power_name=getattr(_wall, "name", None) or _wall.id,
                summary=(
                    f"Take cover behind {getattr(_wall, 'name', None) or _wall.id} "
                    f"({_d:.1f}m away) — cover {_level}/4 against "
                    f"{_covered} of {_total} of them, so those attackers take "
                    f"{cover_ocv_modifier(_level * 25):+d} OCV against you"
                    f"{_flank}. Half Move, so you may still attack (6E2 p45)"
                ),
                reposition_dest=(_spot.x, _spot.y, _spot.z),
            ))

    # ── Disengage: leave the fight ────────────────────────────────────────
    #
    # THE DIRECTION NOTHING ELSE WENT. Every `move` offer is `move:<enemy>`
    # -- toward somebody. `reposition` breaks contact but only for a
    # fragile-versus-heavy matchup already inside melee reach, so in a
    # gunfight it never fires. Between them the engine offered sixty kinds
    # and no way to walk away, which is why every fight it has ever run
    # ended in unconsciousness: those were the only two ways the loop knew
    # a fighter could stop.
    #
    # The book needs no Flee maneuver -- moving away is moving. What was
    # missing is an offer pointing the other way. 6E2 p.139 supplies the
    # consequence side at PRE+30 ("may surrender, run away or faint"),
    # whose 0 DCV the engine already consumes and whose running it could
    # not express.
    #
    # Directly away from the enemies' CENTROID, not from the nearest one:
    # running from the closest man can walk you into the other three. Full
    # combat move, because getting clear is the whole Phase.
    _dis_positions = (
        (getattr(scene, "combatant_positions", None) or {})
        if scene is not None else {}
    )
    _dis_actor_pos = _dis_positions.get(actor.id)
    if scene is not None and _dis_actor_pos is not None and alive_enemies:
        import math as _dis_math

        from kirby_combat.scene.scene import Position as _DisPosition

        _foes = [
            _dis_positions[e.id] for e in alive_enemies
            if e.id in _dis_positions
        ]
        if _foes:
            _cx = sum(p.x for p in _foes) / len(_foes)
            _cy = sum(p.y for p in _foes) / len(_foes)
            _dx, _dy = _dis_actor_pos.x - _cx, _dis_actor_pos.y - _cy
            _mag = _dis_math.hypot(_dx, _dy)
            if _mag > 1e-6:
                try:
                    _run = next(
                        (c for c in actor.movement_view()
                         if getattr(c, "mode", "") == "running"), None,
                    )
                except Exception:
                    _run = None
                _budget = float(getattr(_run, "combat_m", 0.0) or 0.0)
                if _budget > 0:
                    _ux, _uy = _dx / _mag, _dy / _mag
                    _dest = _DisPosition(
                        _dis_actor_pos.x + _ux * _budget,
                        _dis_actor_pos.y + _uy * _budget,
                        _dis_actor_pos.z,
                    )
                    _gain = _dis_math.dist(
                        (_dest.x, _dest.y), (_cx, _cy),
                    ) - _dis_math.dist(
                        (_dis_actor_pos.x, _dis_actor_pos.y), (_cx, _cy),
                    )
                    actions.append(LegalAction(
                        action_id="disengage",
                        kind="disengage",
                        target_id=None,
                        power_xmlid=None,
                        power_name=None,
                        summary=(
                            f"Break off and get clear — run {_budget:.0f}m "
                            f"directly away from them, opening the range by "
                            f"about {_gain:.0f}m. Costs the whole Phase, so "
                            f"no attack; leaving the field ends your part in "
                            f"the fight"
                        ),
                        reposition_dest=(_dest.x, _dest.y, _dest.z),
                    ))

    _climb_positions = (
        (getattr(scene, "combatant_positions", None) or {})
        if scene is not None else {}
    )
    _climb_actor_pos = _climb_positions.get(actor.id)
    if scene is not None and _climb_actor_pos is not None:
        actor_pos = _climb_actor_pos
        from kirby_combat.climbing import (
            CLIMB_BASE_M, CLIMB_FAST_M, CLIMB_FAST_PENALTY,
        )
        from kirby_combat.scene.movement_legality import (
            CLIMB_FACE_REACH_M, _nearest_point_on_segment_xy,
            movement_reach,
        )
        from kirby_combat.scene.scene import Position as _ClimbPos
        from kirby_combat.scene.scene import is_climbable

        # 6E1 p70 gating needs only "does the hero HAVE the Skill" here;
        # the roll TARGET is read in the resolver via _skill_roll_target.
        # This module already reads skills this way at :1296.
        _has_climbing = any(
            (getattr(s, "xmlid", "") or "").upper() == "CLIMBING"
            for s in (getattr(actor.hero, "skills", []) or [])
        )
        for wall in (scene.walls or []):
            if not is_climbable(wall):
                continue
            difficulty = int(wall.climb_difficulty or 0)
            # 6E1 p70: difficult faces need the Skill; ordinary ones do not.
            if difficulty > 0 and not _has_climbing:
                continue
            a, b = wall.segment
            near = _nearest_point_on_segment_xy(
                actor_pos.x, actor_pos.y, a.x, a.y, b.x, b.y,
            )
            import math as _math
            if _math.hypot(near[0] - actor_pos.x,
                           near[1] - actor_pos.y) > CLIMB_FACE_REACH_M:
                continue
            base_z = min(a.z, b.z)
            top_z = base_z + wall.height_m
            if actor_pos.z >= top_z - 1e-6:
                continue        # already at the top; nothing to climb
            for kind, rate, extra in (
                ("climb", CLIMB_BASE_M, 0),
                ("climb_fast", CLIMB_FAST_M, CLIMB_FAST_PENALTY),
            ):
                dest_z = min(actor_pos.z + rate, top_z)
                dest = _ClimbPos(near[0], near[1], dest_z)
                # The move this Phase covers the climb rate PLUS whatever
                # slack was needed to close onto the exact face point from
                # within CLIMB_FACE_REACH_M — pass the actual 3D distance
                # so movement_reach validates legality (wall crossing,
                # face/base-top bounds) rather than re-gating on the rate
                # alone.
                _climb_dist = _math.dist(
                    (actor_pos.x, actor_pos.y, actor_pos.z),
                    (dest.x, dest.y, dest.z),
                )
                try:
                    if not movement_reach(
                        "climbing", actor_pos, dest, _climb_dist, scene,
                    ).reachable:
                        continue
                except Exception:
                    continue        # fail-open: no offer on error
                penalty = -difficulty + extra
                dcv_text = ("½ DCV and -2 DCs" if difficulty > 0
                            else "-1 DCV")
                actions.append(LegalAction(
                    action_id=f"{kind}:{wall.id}",
                    kind=kind,
                    target_id=None,
                    power_xmlid=None,
                    power_name=None,
                    summary=(
                        f"Climb {wall.name} "
                        f"({'difficult' if difficulty else 'ordinary'}"
                        f"{f', {penalty}' if penalty else ''}): "
                        f"{rate:.0f}m this Phase, "
                        f"{dest_z:.0f}m of {top_z:.0f} done, "
                        f"{dcv_text} while climbing; "
                        f"a bad roll drops you {actor_pos.z:.0f}m"
                    ),
                    mode="climbing",
                    reposition_dest=(dest.x, dest.y, dest.z),
                    climb_wall_id=str(wall.id),
                ))

    # Sense-affecting §3 (Images): attack offers against Image DECOYS the actor
    # perceives and has NOT disbelieved (the driver supplies the filtered
    # ``decoy_targets`` = (decoy_id, apparent_name); it excludes the caster's own
    # decoy + any observer who has disbelieved). Appended AFTER the perception
    # gate so they survive (decoys aren't in ``_enemy_ids`` — the gate passes
    # them through anyway, but the pre-filter already encodes "perceived"). The
    # offers are byte-identical in shape to a real-foe attack (apparent_name,
    # same summary) so the AI/player can't tell — that's the full-fool. Only
    # NON-mental attacks (an Image fools targeting senses, not the mind; a decoy
    # has no DMCV). v1: no reach gate on decoys — attacking one wastes the action
    # into the void regardless (the resolver + disbelief roll handle that).
    for decoy_id, apparent_name in (decoy_targets or []):
        dname = apparent_name or decoy_id
        for ap in attack_powers:
            if (ap.xmlid or "").upper() in _MENTAL_ATTACK_XMLIDS:
                continue
            pname = ap.name or ap.xmlid.lower()
            dmg_summary = (
                f"{ap.damage_dice or 0}d6K"
                if ap.damage_type == "killing"
                else f"{ap.damage_dice or 0}d6N"
            )
            # Same limitation tag the real-foe attack line carries, so a decoy
            # attack offer for a limited power is byte-identical (full-fool).
            limit_tag = _limitation_label(actor, ap)
            # A decoy attack must be as nameable as a real one — same rule.
            actions.append(LegalAction(
                action_id=_power_action_id("attack", decoy_id, ap),
                kind="attack",
                target_id=decoy_id,
                power_xmlid=ap.xmlid,
                power_name=ap.name or None,
                summary=(
                    f"Attack {dname} with {pname} "
                    f"({dmg_summary}, OCV {s.ocv}){limit_tag}"
                ),
                _attack_view=ap,
            ))

    return actions
