"""Tests for HERO System 6E combat data tables."""
import pytest
from kirby_combat.tables import (
    SPEED_TO_SEGMENTS,
    HIT_LOCATIONS,
    HIT_LOCATION_ROLL,
    RANGE_MODIFIER_TABLE,
    range_penalty,
)


class TestSpeedChart:
    def test_has_13_entries(self):
        assert len(SPEED_TO_SEGMENTS) == 13

    def test_keys_are_0_through_12(self):
        assert set(SPEED_TO_SEGMENTS.keys()) == set(range(13))

    def test_all_segment_values_in_range(self):
        for spd, segs in SPEED_TO_SEGMENTS.items():
            for seg in segs:
                assert 1 <= seg <= 12, f"SPD {spd} has invalid segment {seg}"

    def test_spd_0_is_empty(self):
        assert SPEED_TO_SEGMENTS[0] == []

    def test_spd_1_is_seven(self):
        assert SPEED_TO_SEGMENTS[1] == [7]

    def test_spd_6_is_even_segments(self):
        assert SPEED_TO_SEGMENTS[6] == [2, 4, 6, 8, 10, 12]

    def test_spd_12_is_every_segment(self):
        assert SPEED_TO_SEGMENTS[12] == list(range(1, 13))

    def test_spd_count_matches_speed(self):
        for spd in range(1, 13):
            assert len(SPEED_TO_SEGMENTS[spd]) == spd, (
                f"SPD {spd} should have {spd} segments, got {len(SPEED_TO_SEGMENTS[spd])}"
            )

    def test_segments_are_sorted(self):
        for spd, segs in SPEED_TO_SEGMENTS.items():
            assert segs == sorted(segs), f"SPD {spd} segments not sorted"

    def test_higher_spds_include_segment_12(self):
        # Per HERO 6E speed chart, SPD 2+ all include segment 12
        for spd in range(2, 13):
            assert 12 in SPEED_TO_SEGMENTS[spd], f"SPD {spd} should include segment 12"

    def test_spd_1_does_not_include_segment_12(self):
        # SPD 1 acts on segment 7 only (not 12)
        assert 12 not in SPEED_TO_SEGMENTS[1]


class TestHitLocations:
    REQUIRED_FIELDS = {"stunX", "nStunX", "bodyX", "ocvMod"}

    def test_has_required_fields_all_locations(self):
        for name, loc in HIT_LOCATIONS.items():
            for field in self.REQUIRED_FIELDS:
                assert field in loc, f"Location '{name}' missing field '{field}'"

    def test_head_values(self):
        head = HIT_LOCATIONS["Head"]
        assert head["stunX"] == 5
        assert head["bodyX"] == 2
        assert head["ocvMod"] == -8

    def test_chest_values(self):
        chest = HIT_LOCATIONS["Chest"]
        assert chest["stunX"] == 3
        assert chest["nStunX"] == 1
        assert chest["bodyX"] == 1
        assert chest["ocvMod"] == -3

    def test_ocv_mods_are_non_positive(self):
        for name, loc in HIT_LOCATIONS.items():
            assert loc["ocvMod"] <= 0, f"Location '{name}' has positive ocvMod {loc['ocvMod']}"

    def test_individual_locations_present(self):
        for loc in ["Head", "Hand", "Arm", "Shoulder", "Chest", "Stomach", "Vitals",
                    "Thigh", "Leg", "Foot"]:
            assert loc in HIT_LOCATIONS, f"Missing location '{loc}'"

    def test_grouped_locations_present(self):
        for loc in ["HeadShot", "HighShot", "BodyShot", "LowShot", "LegShot"]:
            assert loc in HIT_LOCATIONS, f"Missing grouped location '{loc}'"

    def test_vitals_values(self):
        vitals = HIT_LOCATIONS["Vitals"]
        assert vitals["stunX"] == 4
        assert vitals["nStunX"] == 1.5
        assert vitals["bodyX"] == 1.5
        assert vitals["ocvMod"] == -8

    def test_foot_values(self):
        foot = HIT_LOCATIONS["Foot"]
        assert foot["stunX"] == 1
        assert foot["ocvMod"] == -8


class TestHitLocationRoll:
    def test_covers_3_through_18(self):
        assert set(HIT_LOCATION_ROLL.keys()) == set(range(3, 19))

    def test_roll_3_is_head(self):
        assert HIT_LOCATION_ROLL[3] == "Head"

    def test_roll_18_is_foot(self):
        assert HIT_LOCATION_ROLL[18] == "Foot"

    def test_roll_10_is_chest(self):
        assert HIT_LOCATION_ROLL[10] == "Chest"

    def test_roll_11_is_chest(self):
        assert HIT_LOCATION_ROLL[11] == "Chest"

    def test_all_roll_values_are_valid_locations(self):
        for roll, loc in HIT_LOCATION_ROLL.items():
            assert loc in HIT_LOCATIONS, (
                f"Roll {roll} maps to '{loc}' which is not in HIT_LOCATIONS"
            )

    def test_roll_6_is_hand(self):
        assert HIT_LOCATION_ROLL[6] == "Hand"

    def test_roll_12_is_stomach(self):
        assert HIT_LOCATION_ROLL[12] == "Stomach"


class TestRangeModifier:
    def test_zero_distance_is_zero_penalty(self):
        assert range_penalty(0) == 0

    def test_8m_is_zero_penalty(self):
        assert range_penalty(8) == 0

    def test_just_over_8m_is_minus_2(self):
        assert range_penalty(9) == -2

    def test_16m_is_minus_2(self):
        assert range_penalty(16) == -2

    def test_17m_is_minus_4(self):
        assert range_penalty(17) == -4

    def test_32m_is_minus_4(self):
        assert range_penalty(32) == -4

    def test_33m_is_minus_6(self):
        assert range_penalty(33) == -6

    def test_64m_is_minus_6(self):
        assert range_penalty(64) == -6

    def test_128m_is_minus_8(self):
        assert range_penalty(128) == -8

    def test_250m_is_minus_10(self):
        assert range_penalty(250) == -10

    def test_penalty_increases_with_distance(self):
        penalties = [range_penalty(d) for d in [0, 10, 20, 40, 80, 160, 300]]
        for i in range(len(penalties) - 1):
            assert penalties[i] >= penalties[i + 1], (
                f"Penalty should not decrease with distance: {penalties}"
            )

    def test_range_modifier_table_has_expected_bands(self):
        assert RANGE_MODIFIER_TABLE[0] == 0
        assert RANGE_MODIFIER_TABLE[8] == 0
        assert RANGE_MODIFIER_TABLE[16] == -2
        assert RANGE_MODIFIER_TABLE[32] == -4
        assert RANGE_MODIFIER_TABLE[64] == -6
        assert RANGE_MODIFIER_TABLE[128] == -8
        assert RANGE_MODIFIER_TABLE[250] == -10
