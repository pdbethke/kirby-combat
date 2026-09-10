"""Being Surprised has to change the outcome, not just be knowable.

`perception.is_surprised` has answered the perception question since the
perception line shipped and had ZERO production callers. Nothing outside
`perception.py` mentioned surprise at all, so 6E2 p.52's halved DCV and
doubled STUN had never reached a resolver.

The ordering is the part that is easy to get wrong, and the two damage
types get it wrong in opposite directions:

  * KILLING STUN already multiplies BEFORE defenses, so the doubling
    joins it there: (BODY x STUNx x 2) - defense.
  * NORMAL STUN multiplies AFTER defenses, so the doubling must happen
    ahead of the subtraction on its own: (STUN x 2 - defense) x nSTUNx.

p.52: "Double the STUN damage before applying defenses (and, in campaigns
using the Hit Locations rules, before applying the STUN modifier for a
location)."

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from kirby_combat.resolution.hit_location import (
    effect_for, killing_damage, normal_damage,
)
from kirby_combat.resolution.surprise import Surprise

CHEST = effect_for("Chest")          # STUNx 3, nSTUNx 1, BODYx 1


def test_killing_stun_doubles_before_defenses():
    """5 BODY to the chest is 15 STUN; doubled it is 30, and a defense of
    20 leaves 10. Doubling AFTER defenses would leave nothing at all."""
    plain = killing_damage(5, total_defense=20, resistant_defense=0,
                           effect=CHEST)
    assert plain[0] == 0, "15 STUN against 20 defense stops dead"

    surprised = killing_damage(5, total_defense=20, resistant_defense=0,
                               effect=CHEST, stun_multiplier=2)
    assert surprised[0] == 10


def test_doubling_never_touches_body():
    """p.52 doubles the STUN. BODY is not STUN."""
    _, body = killing_damage(9, total_defense=0, resistant_defense=4,
                             effect=CHEST, stun_multiplier=2)
    plain_body = killing_damage(9, total_defense=0, resistant_defense=4,
                                effect=CHEST)[1]
    assert body == plain_body == 5


def test_normal_stun_doubles_before_defenses_too():
    """The multiplier the LOCATION applies still comes after defenses --
    that asymmetry is 6E2 p.111 and stays -- but p.52's doubling does
    not: (20 x 2 - 25) = 15, not (20 - 25) x 2 = 0."""
    plain = normal_damage(20, 4, total_defense=25, effect=CHEST)
    assert plain[0] == 0

    surprised = normal_damage(20, 4, total_defense=25, effect=CHEST,
                              stun_multiplier=2)
    assert surprised[0] == 15


def test_in_combat_surprise_does_not_double():
    """1/2 DCV yes, doubled STUN no -- p.52 is explicit that a character
    Surprised while in combat "takes regular STUN damage"."""
    s = Surprise(applies=True, out_of_combat=False)
    assert killing_damage(5, total_defense=20, resistant_defense=0,
                          effect=CHEST,
                          stun_multiplier=s.stun_multiplier)[0] == 0


# ---------------------------------------------------------------------------
# Through a whole attack, which is the only place it counts
# ---------------------------------------------------------------------------
def test_a_surprised_target_is_at_half_dcv():
    """6E2 p.52, in combat or out. The to-hit step is the only place a
    DCV exists, so this is where the factor has to land."""
    from kirby_combat.models import AttackInput, AttackPower, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.template import CombatTemplate

    class _Guy:
        def __init__(self, ocv=8, dcv=8):
            self.ocv, self.dcv = ocv, dcv
            self.omcv = self.dmcv = 3
            self.csls = []

    power = AttackPower(
        xmlid="HA", name="fist", damage_dice=4, half_die=False, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=0.0, uses_str=False,
        str_min=0, armor_piercing=0, penetrating=0, increased_stun_mult=0)
    template = CombatTemplate.default_6e_superheroic()

    def _dcv(surprise):
        return resolve_to_hit(AttackInput(
            attacker=_Guy(), target=_Guy(dcv=8), power=power,
            distance_m=None, aim=None,
            dice=DiceValues(to_hit=[3, 3, 3]), surprise=surprise,
        ), template).effective_dcv

    assert _dcv(None) == 8
    assert _dcv(Surprise(applies=True)) == 4
    assert _dcv(Surprise(applies=False)) == 8


def test_the_audit_names_the_rule():
    """A halved DCV that appears from nowhere is unreadable, and this
    engine's audit trail is how a fight is checked against the book."""
    from kirby_combat.models import AttackInput, AttackPower, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.template import CombatTemplate

    class _Guy:
        ocv = dcv = 8
        omcv = dmcv = 3
        csls: list = []

    power = AttackPower(
        xmlid="HA", name="fist", damage_dice=4, half_die=False, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=0.0, uses_str=False,
        str_min=0, armor_piercing=0, penetrating=0, increased_stun_mult=0)
    result = resolve_to_hit(AttackInput(
        attacker=_Guy(), target=_Guy(), power=power, distance_m=None, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3]),
        surprise=Surprise(applies=True, out_of_combat=True),
    ), CombatTemplate.default_6e_superheroic())
    assert any("Surprised" in line for line in result.audit)
