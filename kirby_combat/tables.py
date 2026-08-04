"""HERO System 6E combat data tables."""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Speed Chart: SPD -> list of segments in which that combatant acts
# ---------------------------------------------------------------------------
SPEED_TO_SEGMENTS: dict[int, list[int]] = {
    0:  [],
    1:  [7],
    2:  [6, 12],
    3:  [4, 8, 12],
    4:  [3, 6, 9, 12],
    5:  [3, 5, 8, 10, 12],
    6:  [2, 4, 6, 8, 10, 12],
    7:  [2, 4, 6, 7, 9, 11, 12],
    8:  [2, 3, 5, 6, 8, 9, 11, 12],
    9:  [2, 3, 4, 6, 7, 8, 10, 11, 12],
    10: [2, 3, 4, 5, 6, 8, 9, 10, 11, 12],
    11: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    12: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}

# ---------------------------------------------------------------------------
# Hit Locations: name -> {label, stunX, nStunX, bodyX, ocvMod}
# Individual locations (rolled on 3d6) + grouped shots (aimed fire)
# ---------------------------------------------------------------------------
HIT_LOCATIONS: dict[str, dict] = {
    # Individual locations
    "Head":     {"label": "Head",     "stunX": 5, "nStunX": 2,   "bodyX": 2,   "ocvMod": -8},
    "Hand":     {"label": "Hand",     "stunX": 1, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -6},
    "Arm":      {"label": "Arm",      "stunX": 2, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -5},
    "Shoulder": {"label": "Shoulder", "stunX": 3, "nStunX": 1,   "bodyX": 1,   "ocvMod": -5},
    "Chest":    {"label": "Chest",    "stunX": 3, "nStunX": 1,   "bodyX": 1,   "ocvMod": -3},
    "Stomach":  {"label": "Stomach",  "stunX": 4, "nStunX": 1.5, "bodyX": 1,   "ocvMod": -7},
    "Vitals":   {"label": "Vitals",   "stunX": 4, "nStunX": 1.5, "bodyX": 1.5, "ocvMod": -8},
    "Thigh":    {"label": "Thigh",    "stunX": 2, "nStunX": 1,   "bodyX": 1,   "ocvMod": -4},
    "Leg":      {"label": "Leg",      "stunX": 2, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -6},
    "Foot":     {"label": "Foot",     "stunX": 1, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -8},

    # Grouped shots (aimed fire at a body region)
    # HeadShot: aim at the head/neck area; -4 OCV
    "HeadShot":  {"label": "Head Shot",  "stunX": 5, "nStunX": 2,   "bodyX": 2,   "ocvMod": -4},
    # HighShot: upper body (head/shoulder/arm); -2 OCV
    "HighShot":  {"label": "High Shot",  "stunX": 3, "nStunX": 1,   "bodyX": 1,   "ocvMod": -2},
    # BodyShot: center mass (Hands/Arms/Shoulders/Chest/Stomach/Vitals/Thighs/Legs); -1 OCV per 6E1 p465 §Combat Modifiers
    "BodyShot":  {"label": "Body Shot",  "stunX": 3, "nStunX": 1,   "bodyX": 1,   "ocvMod": -1},
    # LowShot: lower body (thigh/leg/foot); -2 OCV
    "LowShot":   {"label": "Low Shot",   "stunX": 2, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -2},
    # LegShot: legs specifically; -4 OCV
    "LegShot":   {"label": "Leg Shot",   "stunX": 2, "nStunX": 0.5, "bodyX": 0.5, "ocvMod": -4},
}

# ---------------------------------------------------------------------------
# Hit Location Roll Table: 3d6 result -> location name
# ---------------------------------------------------------------------------
HIT_LOCATION_ROLL: dict[int, str] = {
    3:  "Head",
    4:  "Head",
    5:  "Head",
    6:  "Hand",
    7:  "Arm",
    8:  "Arm",
    9:  "Shoulder",
    10: "Chest",
    11: "Chest",
    12: "Stomach",
    13: "Vitals",
    14: "Vitals",
    15: "Thigh",
    16: "Leg",
    17: "Foot",
    18: "Foot",
}

# ---------------------------------------------------------------------------
# Range Modifier Table: distance band max (m) -> OCV penalty
# -2 per doubling of range past 8m
# ---------------------------------------------------------------------------
RANGE_MODIFIER_TABLE: dict[int, int] = {
    0:   0,
    8:   0,
    16:  -2,
    32:  -4,
    64:  -6,
    128: -8,
    250: -10,
}

# Sorted band boundaries for lookup
_RANGE_BANDS = sorted(RANGE_MODIFIER_TABLE.keys())


def range_penalty(distance_m: float) -> int:
    """Return the OCV penalty for attacking at the given distance in metres.

    Penalty is 0 for 0-8m, then -2 per doubling past 8m.
    Uses the RANGE_MODIFIER_TABLE band lookup.
    """
    for band in _RANGE_BANDS:
        if distance_m <= band:
            return RANGE_MODIFIER_TABLE[band]
    # Beyond the last defined band — extend the pattern
    # Each doubling past 250m adds another -2
    import math
    if distance_m <= 0:
        return 0
    doublings = math.ceil(math.log2(distance_m / 8)) if distance_m > 8 else 0
    return max(RANGE_MODIFIER_TABLE[250], -doublings * 2)


# HERO 6E SPD → segments helper.
# Reads from the authoritative SPEED_TO_SEGMENTS table above, returns a frozenset
# for immutability and membership-check ergonomics.

def segments_for_spd(spd: int) -> frozenset[int]:
    """Return the set of segments (1-12) a combatant of given SPD has phases in.

    Reads from SPEED_TO_SEGMENTS (the Phase-1 oracle-validated chart).
    Out-of-range SPD clamps to [0, 12].
    """
    if spd < 0:
        spd = 0
    if spd > 12:
        spd = 12
    return frozenset(SPEED_TO_SEGMENTS[spd])


# ---------------------------------------------------------------------------
# Martial Maneuvers — 6E2 p93 §STANDARD MARTIAL MANEUVERS table.
# Verified against Codex (throwback tenant, Hero System 6E2 p93) on 2026-04-25.
#
# Each entry encodes the modifiers a character applies when declaring this
# maneuver. `dc_bonus` is the extra Damage Classes added on top of STR (so
# "STR Strike" = 0, "STR +2d6 Strike" = 2, "STR +4d6 Strike" = 4). Special
# damage encodings (HKA ½d6, NND, Throw v/5) are flagged via `notes` rather
# than dc_bonus — the Martial Arts action interprets those.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MartialManeuver:
    """A single 6E martial maneuver from 6E2 p93."""
    name: str               # display name
    ocv: int                # OCV modifier
    dcv: int                # DCV modifier
    dc_bonus: int           # extra DC added to a STR-Strike baseline
    phase: str              # "half" | "full" | "none"
    notes: str              # short tag/effect descriptor


#: Per 6E2 p93 §STANDARD MARTIAL MANEUVERS. 14 standard + 2 element entries.
MARTIAL_MANEUVERS: dict[str, MartialManeuver] = {
    "choke_hold":       MartialManeuver("Choke Hold",       -2, 0, 0, "half", "Grab One Limb; 2d6 NND"),
    "defensive_strike": MartialManeuver("Defensive Strike", +1, +3, 0, "half", "STR Strike"),
    "killing_strike":   MartialManeuver("Killing Strike",   -2, 0, 0, "half", "HKA 1/2d6"),
    "legsweep":         MartialManeuver("Legsweep",         +2, -1, 1, "half", "STR +1d6 Strike; Target Falls"),
    "martial_block":    MartialManeuver("Martial Block",    +2, +2, 0, "half", "Block, Abort"),
    "martial_disarm":   MartialManeuver("Martial Disarm",   -1, +1, 0, "half", "Disarm; +10 STR to Disarm roll"),
    "martial_dodge":    MartialManeuver("Martial Dodge",     0, +5, 0, "half", "Dodge, Affects All Attacks, Abort"),
    "martial_escape":   MartialManeuver("Martial Escape",   +0, +0, 0, "half", "+15 STR vs. Grabs"),
    "martial_grab":     MartialManeuver("Martial Grab",     -1, -1, 0, "half", "Grab Two Limbs; +10 STR for holding on"),
    "martial_strike":   MartialManeuver("Martial Strike",   +0, +2, 2, "half", "STR +2d6 Strike"),
    "martial_throw":    MartialManeuver("Martial Throw",    +0, +1, 0, "half", "STR +v/5; Target Falls"),
    "nerve_strike":     MartialManeuver("Nerve Strike",     -1, +1, 0, "half", "2d6 NND"),
    "offensive_strike": MartialManeuver("Offensive Strike", -2, +1, 4, "half", "STR +4d6 Strike"),
    "sacrifice_throw":  MartialManeuver("Sacrifice Throw",  +2, +1, 0, "half", "STR Strike; You Fall, Target Falls"),
    # Elements — no phase/OCV/DCV impact; pricing-only or composability flags.
    "plus_one_dc":      MartialManeuver("+1 Damage Class",  +0, +0, 1, "none", "Adds to all Martial Maneuvers"),
    "weapon_element":   MartialManeuver("Weapon Element",   +0, +0, 0, "none", "Allows use of Martial Arts with weapons"),
}


# ---------------------------------------------------------------------------
# Mental Power degree ladders — margin (effect_roll - target.EGO) thresholds.
# 6E1 pg 101 (Mind Control), pg 116 (Telepathy), pg 109 (Mental Illusion).
# Each ladder maps margin -> tier name. Higher tiers strictly imply lower
# tiers reached.
# ---------------------------------------------------------------------------

#: 6E1 p101 Mind Control degrees.
MIND_CONTROL_DEGREES: list[tuple[int, str]] = [
    (0, "ego_push"),         # EGO+0:  push/nudge suggestion
    (10, "simple"),          # EGO+10: simple commands within target's normal behavior
    (20, "contrary"),        # EGO+20: commands contrary to personality
    (30, "violent"),         # EGO+30: violent acts against friends/self
]


def mind_control_degree(effect_roll_total: int, target_ego: int) -> str:
    """Return the degree tier reached by effect_roll_total vs EGO + degree threshold."""
    margin = effect_roll_total - target_ego
    reached = "none"
    for threshold, name in MIND_CONTROL_DEGREES:
        if margin >= threshold:
            reached = name
    return reached


#: 6E1 p116 Telepathy degrees.
TELEPATHY_DEGREES: list[tuple[int, str]] = [
    (0, "surface_thoughts"),     # EGO+0:  current surface thoughts
    (10, "specific_memories"),   # EGO+10: specific memories on request
    (20, "deep_thoughts"),       # EGO+20: deep thoughts and beliefs
    (30, "subconscious"),        # EGO+30: subconscious + blocked memories
]


def telepathy_degree(effect_roll_total: int, target_ego: int) -> str:
    margin = effect_roll_total - target_ego
    reached = "none"
    for threshold, name in TELEPATHY_DEGREES:
        if margin >= threshold:
            reached = name
    return reached


#: 6E1 p109 Mental Illusion degrees.
MENTAL_ILLUSION_DEGREES: list[tuple[int, str]] = [
    (0, "simple"),                # EGO+0:  simple, brief illusion
    (10, "moderate"),             # EGO+10: moderately convincing
    (20, "elaborate"),            # EGO+20: elaborate, multi-sense illusion
    (30, "perfect"),              # EGO+30: perfect, indistinguishable from reality
]


def mental_illusion_degree(effect_roll_total: int, target_ego: int) -> str:
    margin = effect_roll_total - target_ego
    reached = "none"
    for threshold, name in MENTAL_ILLUSION_DEGREES:
        if margin >= threshold:
            reached = name
    return reached


# ---------------------------------------------------------------------------
# Presence Attack effects ladder — margin over target's PRE.
# 6E2 p139.
# ---------------------------------------------------------------------------

#: The 6E2 p138 Presence Attack Table, keyed on (roll total - target's PRE).
#:
#: 6E2 p139 is explicit that a roll which merely EQUALS the target's PRE has
#: already landed: "If the total on the Presence Attack dice at least equals
#: the target's PRE, the target is impressed." This table previously started
#: at ``(0, "no_effect")``, which shifted every tier 10 points high and meant
#: an attacker needed PRE+10 to buy the effect RAW grants at PRE+0 — a high
#: PRE was a Characteristic you could pay for and not cash in.
#:
#: Names follow the book rather than paraphrasing it, because the old set
#: ("impressed" sitting at +20) is what made the off-by-one-tier plausible in
#: the first place.
PRESENCE_ATTACK_EFFECTS: list[tuple[int, str]] = [
    # margin, effect          6E2 p139 combat consequence
    (0,  "impressed"),        # attacker may act before him this Phase
    (10, "very_impressed"),   # + only a Half Phase Action next Phase
    (20, "awed"),             # will not act for 1 Full Phase; 1/2 DCV
    (30, "cowed"),            # 0 DCV; may surrender, run away, or faint
    (40, "overwhelmed"),      # GM option: as cowed, far severer mentally
]

#: Tiers at which the target is too far gone to act. NOTE: RAW is stricter —
#: at "awed" (PRE+20) the target "will not act for 1 Full Phase" — but
#: consuming the table's mechanical consequences is separate work from
#: getting the table itself right, so this preserves the previous meaning
#: (only the worst tiers stop a target) under the corrected names.
_CANNOT_ACT = frozenset({"cowed", "overwhelmed"})


def presence_attack_effect(roll_total: int, target_pre: int) -> str:
    """The 6E2 p138 table entry for this roll against this target.

    Below the target's PRE there is no entry on the table at all, so a roll
    that falls short returns ``"no_effect"``.
    """
    margin = roll_total - target_pre
    effect = "no_effect"
    for threshold, name in PRESENCE_ATTACK_EFFECTS:
        if margin >= threshold:
            effect = name
    return effect
