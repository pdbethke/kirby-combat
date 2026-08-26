"""Construct effect resolution incl. capability-gated suffocation (spec §1.5)."""
from kirby_combat.scene import Construct, ConstructEffect, Position
from kirby_combat.scene.effects import resolve_construct_effect
from fixtures.synthetic_hero import synthetic_combatant


def _occupant(*statuses):
    c = synthetic_combatant(id="o", name="o", ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=20,
                  ego=15, str_=15, con=15, pre=15, rec=5, pd=5, ed=5, rpd=0, red=0,
                  md=5, power_defense=0, flash_defense=0, max_stun=30, max_body=15,
                  max_end=30, current_stun=30, current_body=15, current_end=30)
    for s in statuses:
        c.state.statuses.add(s)
    return c


def _pool():
    return Construct(obj_id="pool", kind="hazard_zone",
                     polygon_xy=[(0, 0), (4, 0), (4, 4), (0, 4)], elevation_range_m=(-2.0, 0.0),
                     permeability="porous",
                     effect=ConstructEffect(kind="suffocation", gating="breathing_swimming",
                                            trigger="every_segment"))


def test_swimmer_is_safe_but_slowed():
    r = resolve_construct_effect(_pool(), _occupant(), segment_tick=True)
    assert r is not None and r.outcome == "slowed" and r.body_loss == 0


def test_cannot_swim_suffocates():
    r = resolve_construct_effect(_pool(), _occupant("cannot_swim"), segment_tick=True)
    assert r.outcome == "suffocating" and r.body_loss >= 1


def test_status_effect_only_on_segment_tick_when_every_segment():
    assert resolve_construct_effect(_pool(), _occupant("cannot_swim"), segment_tick=False) is None
