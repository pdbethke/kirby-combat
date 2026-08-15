import pathlib
import pytest
pytest.importorskip("kirby_cost")
from kirby_combat.hero_view import HeroCombatant

HELIOS = str(pathlib.Path(__file__).parent / "fixtures" / "HELIOS-CV1.hdc")


def test_framework_view_exposes_multipower_reserve_and_typed_slots():
    fws = HeroCombatant.from_hdc(HELIOS).framework_view()
    mp = next(f for f in fws if f.kind == "multipower")
    assert mp.reserve_or_pool > 0
    assert mp.slots, "multipower should have slots"
    assert all(s.slot_id and s.name for s in mp.slots)
    assert all(isinstance(s.variable, bool) and s.active_points >= 0 for s in mp.slots)
    # the NND attack slot is linked + carries avad
    assert any(s.attack is not None and s.attack.avad for s in mp.slots)
    # attack slots are classified as kind="attack"
    assert any(s.kind == "attack" for s in mp.slots)


ARTHON = str(pathlib.Path(__file__).parent / "fixtures" / "ARTHON-CV1.hdc")


def test_framework_view_vpp_pool_from_levels_not_basecost():
    """A VPP's pool lives on ``levels`` (base_cost is 0 for a VPP); the
    FrameworkView must report the real pool, not 0."""
    fws = HeroCombatant.from_hdc(ARTHON).framework_view()
    vpp = next(f for f in fws if f.kind == "vpp")
    assert vpp.reserve_or_pool == 80, (
        f"expected VPP pool 80 (levels), got {vpp.reserve_or_pool}"
    )
