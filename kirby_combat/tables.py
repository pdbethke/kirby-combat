"""HERO System 6E combat data tables."""

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
    # BodyShot: center mass (chest/stomach); no OCV penalty
    "BodyShot":  {"label": "Body Shot",  "stunX": 3, "nStunX": 1,   "bodyX": 1,   "ocvMod":  0},
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


# ---------------------------------------------------------------------------
# SPD Chart: HERO 6E SPD → segments when character has a phase.
# Source: 6E1 pg 44 (SPD chart).
# ---------------------------------------------------------------------------
SPD_TO_SEGMENTS: dict[int, frozenset[int]] = {
    0:  frozenset(),
    1:  frozenset({7}),
    2:  frozenset({6, 12}),
    3:  frozenset({4, 8, 12}),
    4:  frozenset({3, 6, 9, 12}),
    5:  frozenset({3, 5, 8, 10, 12}),
    6:  frozenset({2, 4, 6, 8, 10, 12}),
    7:  frozenset({2, 4, 6, 7, 9, 11, 12}),
    8:  frozenset({2, 3, 5, 6, 8, 9, 11, 12}),
    9:  frozenset({2, 3, 5, 6, 8, 9, 11, 12}),
    10: frozenset({2, 3, 4, 5, 7, 8, 9, 10, 11, 12}),
    11: frozenset({2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}),
    12: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}),
}


def segments_for_spd(spd: int) -> frozenset[int]:
    """Return the set of segments (1-12) a combatant of given SPD has phases in.

    Out-of-range SPD clamps to [0, 12].
    """
    if spd < 0:
        spd = 0
    if spd > 12:
        spd = 12
    return SPD_TO_SEGMENTS[spd]
