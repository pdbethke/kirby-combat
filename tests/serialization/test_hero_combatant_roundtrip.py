"""HeroCombatant round-trip serialization tests (combatant-redesign step 7).

The combatant snapshot stored in ``combat_session.combatants_jsonb`` must
survive a to_dict / from_dict round trip with the combat-relevant state
preserved. The snapshot is intentionally lossy w.r.t. the source
LoadedHero — that's the canonical character; snapshots are point-in-time.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import AttackPower, DefenseItem
from kirby_combat.serialization import from_dict, to_dict

from fixtures.synthetic_hero import synthetic_combatant


def test_hero_combatant_to_dict_emits_flat_snapshot():
    """to_dict on HeroCombatant emits the snapshot shape (not the
    full LoadedHero)."""
    hc = synthetic_combatant(
        id="alpha", name="Alpha",
        ocv=10, dcv=8, spd=5, str_=20, pd=10, ed=10,
        max_stun=40, max_body=12, max_end=40,
        current_stun=33, current_body=12, current_end=27,
    )
    d = to_dict(hc)
    assert d["__type__"] == "HeroCombatant"
    assert d["id"] == "alpha"
    assert d["name"] == "Alpha"
    assert d["ocv"] == 10
    assert d["max_stun"] == 40
    assert d["current_stun"] == 33
    assert d["current_end"] == 27
    # Snapshot does NOT carry the full LoadedHero
    assert "hero" not in d
    assert "_char_values" not in d


def test_hero_combatant_round_trip_preserves_combat_state():
    """to_dict + from_dict round-trip preserves stats + state."""
    blast = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=20,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )
    armor = DefenseItem(name="Armor", rpd=4, red=4, is_resistant=True)

    original = synthetic_combatant(
        id="beta", name="Beta",
        ocv=8, dcv=8, spd=4, str_=15, con=18,
        pd=6, ed=6, rpd=4, red=4, md=3,
        max_stun=35, max_body=11, max_end=36,
        current_stun=20, current_body=11, current_end=18,
        knockback_resistance=4,
        attacks=[blast], defenses=[armor],
    )
    # Apply some state changes to make sure they round-trip
    original.state.statuses.add("dodging")
    original.state.drains["dex"] = 3
    original.state.aborted = True
    original.state.last_acted_segment = 8

    d = to_dict(original)
    restored = from_dict(d)

    assert isinstance(restored, HeroCombatant)
    assert restored.id == "beta"
    assert restored.name == "Beta"

    # Stats preserve
    s = restored.combat_stats()
    assert s.ocv == 8
    assert s.dcv == 8
    assert s.spd == 4
    assert s.rpd == 4
    assert s.md == 3
    assert s.max_stun == 35

    # State preserves
    assert restored.state.current_stun == 20
    assert restored.state.current_body == 11
    assert restored.state.current_end == 18
    assert "dodging" in restored.state.statuses
    assert restored.state.drains == {"dex": 3}
    assert restored.state.aborted is True
    assert restored.state.last_acted_segment == 8
    assert restored.knockback_resistance == 4


def test_snapshot_without_int_still_loads():
    """Combat recordings predate the int_ field. Replay must not break."""
    original = synthetic_combatant(id="delta", name="Delta")
    payload = to_dict(original)
    payload.pop("int_", None)
    restored = from_dict(payload)
    assert restored.combat_stats().int_ == 0


def test_hero_combatant_round_trip_when_state_is_default():
    """A freshly-loaded HeroCombatant with default state survives roundtrip."""
    original = synthetic_combatant(id="gamma", name="Gamma")
    d = to_dict(original)
    restored = from_dict(d)
    assert restored.id == "gamma"
    assert restored.state.current_stun == original.state.current_stun
    assert restored.state.statuses == set()
    assert restored.state.drains == {}
    assert restored.state.aborted is False


def test_a_civilian_snapshot_round_trips_with_the_flag_and_the_stats():
    """Ravel snapshotted as a civilian comes back a civilian, not a Hero.

    Before this fix, ``in_hero_id`` was dropped on the wire and always
    restored ``True`` — so a civilian snapshot's *stats* round-tripped
    correctly (they're frozen numbers, not recomputed), but the *flag*
    silently lied about which identity had been recorded.
    """
    from tests.corpus import require_authored

    civilian = HeroCombatant.from_hdc(require_authored("Ravel"), id="ravel")
    civilian.state.in_hero_id = False
    assert civilian.combat_stats().dex == 10
    assert civilian.combat_stats().spd == 2

    d = to_dict(civilian)
    assert d["in_hero_id"] is False
    assert d["dex"] == 10
    assert d["spd"] == 2

    restored = from_dict(d)
    assert restored.state.in_hero_id is False
    assert restored.combat_stats().dex == 10
    assert restored.combat_stats().spd == 2
