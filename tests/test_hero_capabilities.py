"""Life-support / swim capability reads for suffocation gating (spec §1.5)."""
from fixtures.synthetic_hero import synthetic_combatant as Combatant


def test_default_combatant_can_swim_and_breathes_normally():
    c = Combatant(id="a", name="a", ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=20,
                  ego=15, str_=15, con=15, pre=15, rec=5, pd=5, ed=5, rpd=0, red=0,
                  md=5, power_defense=0, flash_defense=0, max_stun=30, max_body=15,
                  max_end=30, current_stun=30, current_body=15, current_end=30)
    assert c.can_swim() is True
    assert c.has_self_contained_breathing() is False


def test_cannot_swim_status_marks_non_swimmer():
    c = Combatant(id="cat", name="cat", ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=20,
                  ego=15, str_=15, con=15, pre=15, rec=5, pd=5, ed=5, rpd=0, red=0,
                  md=5, power_defense=0, flash_defense=0, max_stun=30, max_body=15,
                  max_end=30, current_stun=30, current_body=15, current_end=30)
    c.state.statuses.add("cannot_swim")
    assert c.can_swim() is False
