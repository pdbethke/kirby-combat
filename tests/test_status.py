"""Tests for status change determination (Task 8)."""
from __future__ import annotations

import pytest

from kirby_combat.resolution.status import determine_status_changes


def test_no_status_change() -> None:
    """Normal damage that doesn't cross any threshold produces no status changes."""
    result = determine_status_changes(
        stun_before=30,
        stun_after=20,
        body_before=12,
        body_after=10,
        con=20,
        max_body=12,
    )
    # stun_dealt=10, con=20 → not stunned; stun_after=20>0 → not KO; body_after=10>-12 → not dead
    assert result == []


def test_stunned() -> None:
    """25 STUN dealt > 20 CON → Stunned status."""
    result = determine_status_changes(
        stun_before=40,
        stun_after=15,
        body_before=12,
        body_after=11,
        con=20,
        max_body=12,
    )
    # stun_dealt=25 > 20 CON → stunned
    assert "Stunned" in result
    assert "Knocked Out" not in result
    assert "Dead" not in result


def test_knocked_out() -> None:
    """STUN drops to -5 → Knocked Out status."""
    result = determine_status_changes(
        stun_before=10,
        stun_after=-5,
        body_before=12,
        body_after=11,
        con=20,
        max_body=12,
    )
    # stun_after=-5 ≤ 0 → KO; stun_dealt=15 < 20 CON → not stunned; body_after=11>-12 → alive
    assert "Knocked Out" in result
    assert "Dead" not in result


def test_death() -> None:
    """BODY drops to -13 with max_body=12 → Dead status (body_after ≤ -max_body)."""
    result = determine_status_changes(
        stun_before=5,
        stun_after=-20,
        body_before=2,
        body_after=-13,
        con=15,
        max_body=12,
    )
    # body_after=-13 ≤ -12 → dead; stun_after=-20 ≤ 0 → KO too
    assert "Dead" in result
    assert "Knocked Out" in result


def test_stunned_and_ko() -> None:
    """Attack deals > CON STUN and drops target below 0 STUN → both Stunned and Knocked Out."""
    result = determine_status_changes(
        stun_before=25,
        stun_after=-5,
        body_before=12,
        body_after=10,
        con=20,
        max_body=12,
    )
    # stun_dealt=30 > 20 CON → stunned; stun_after=-5 ≤ 0 → KO; body_after=10>-12 → alive
    assert "Stunned" in result
    assert "Knocked Out" in result
    assert "Dead" not in result
