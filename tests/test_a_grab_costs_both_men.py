"""Holding a man costs you, and being held costs him more.

The engine could Grab, and a Grab changed nothing about anyone's combat
ability afterwards. Western Hero p.104 -- the genre book for this
benchmark -- prices the hold precisely:

    "Assuming the Grabber holds on, the Grabber and victim are now 1/2
     DCV. The Grabber is full OCV against the victim and the victim is -3
     OCV against the Grabber; both are 1/2 OCV against other targets.
     These OCV and DCV modifiers for Grabbing and being Grabbed end
     immediately when the victim breaks free or is released."

None of it was applied. `cv_modifiers_for` folds Stunned, multi-attack,
sense penalties and Presence effects, and had no notion of a Grab, so a
man wrestling another man was as hard to shoot as a man standing free ---
which makes grappling strictly free, and therefore never worth doing to
anybody who is not already the only thing you can reach.

FOUR SEPARATE EFFECTS, and they are not the same shape:

  * 1/2 DCV, both men          -- a FACTOR, target-independent
  * 1/2 OCV against others     -- a FACTOR, and only against third parties
  * full OCV grabber -> victim -- no change, stated so it is not halved
  * -3 OCV victim -> grabber   -- a DELTA

`apply_cv_factor` is 6E2 p.39's halving and accepts 1.0/0.5/0.0 only, so
the factors go through it rather than a bare multiply --- the same seam
Surprise already uses in `resolve_to_hit`.
"""
from __future__ import annotations

from kirby_combat.grappling import grab_cv


class _Held:
    """A session double: doc holds frank; ike is a bystander."""

    def __init__(self):
        self.holds = {"frank": "doc"}

    def grabbed_by(self, cid):
        return self.holds.get(cid)

    def is_grabbing(self, cid):
        return cid in set(self.holds.values())


S = _Held()


def test_the_victim_is_half_dcv():
    assert grab_cv(S, attacker="ike", target="frank").dcv_factor == 0.5


def test_the_grabber_is_half_dcv_too():
    """Holding on is not free. This is what makes a Grab a commitment."""
    assert grab_cv(S, attacker="ike", target="doc").dcv_factor == 0.5


def test_a_bystander_is_unaffected():
    assert grab_cv(S, attacker="doc", target="ike").dcv_factor == 1.0


def test_the_grabber_keeps_full_OCV_against_his_victim():
    """"The Grabber is full OCV against the victim" --- stated in the
    book and therefore stated here, so no later halving creeps in."""
    cv = grab_cv(S, attacker="doc", target="frank")
    assert cv.ocv_factor == 1.0
    assert cv.ocv_delta == 0


def test_the_victim_is_minus_three_against_his_grabber():
    cv = grab_cv(S, attacker="frank", target="doc")
    assert cv.ocv_delta == -3
    assert cv.ocv_factor == 1.0


def test_both_men_are_half_OCV_against_anybody_else():
    assert grab_cv(S, attacker="frank", target="ike").ocv_factor == 0.5
    assert grab_cv(S, attacker="doc", target="ike").ocv_factor == 0.5


def test_a_free_man_attacking_a_free_man_is_untouched():
    cv = grab_cv(S, attacker="ike", target="ike")
    assert (cv.ocv_factor, cv.dcv_factor, cv.ocv_delta) == (1.0, 1.0, 0)


def test_the_factors_are_ones_the_engine_will_accept():
    """`apply_cv_factor` is grounded for 1.0/0.5/0.0 only and refuses
    anything else, so every factor this produces must be one of them."""
    from kirby_combat.cv_modifiers import apply_cv_factor

    for a, t in (("ike", "frank"), ("frank", "doc"), ("doc", "ike"),
                 ("ike", "ike")):
        cv = grab_cv(S, attacker=a, target=t)
        apply_cv_factor(8, cv.ocv_factor)
        apply_cv_factor(8, cv.dcv_factor)


# ---- and it has to reach a real attack roll ----

def _fight():
    """doc has frank in a hold; ike is free and shooting."""
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.actions.grab import Grab
    from kirby_combat.session import CombatSession
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    def man(id_):
        return synthetic_combatant(
            id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=18,
            ego=15, str_=15, con=15, pre=15, rec=5, pd=5, ed=5, rpd=0, red=0,
            md=5, power_defense=0, flash_defense=0, max_stun=30, max_body=15,
            max_end=30, current_stun=30, current_body=15, current_end=30)

    s = CombatSession.create(
        id="s", combatants=[man("doc"), man("frank"), man("ike")], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=11)).start()
    s, _ = Grab.declare_and_resolve(
        s, attacker_id="doc", target_id="frank", attacker_str=20,
        target_str=10, attacker_ocv=8, target_dcv=0, attack_roll=3)
    assert Grab.is_grabbed(s, "frank")[0] is True
    return s


def _shoot(session, attacker: str, target: str):
    import kirby_combat.loop.resolvers  # noqa: F401
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.models import AttackPower
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    gun = AttackPower(
        xmlid="RKA", name="Colt", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, beam=True)
    action = LegalAction(
        action_id=f"attack:{target}:src1", kind="attack", target_id=target,
        power_xmlid="RKA", power_name="Colt", summary="Shoot",
        _attack_view=gun)
    out = resolve_chosen(
        session, session.combatants[attacker], action,
        template=CombatTemplate.default_6e_superheroic(),
        roller=RandomRoller(seed=11))
    assert out.result is not None
    return out.result.to_hit


def test_a_held_man_is_measurably_easier_to_shoot():
    """The whole point: DCV 8 halved to 4 for a man being held."""
    session = _fight()
    held = _shoot(session, "ike", "frank").effective_dcv
    free = _shoot(session, "ike", "ike").effective_dcv
    assert held < free, f"a held man was no easier to hit: {held} vs {free}"


def test_the_grabber_is_easier_to_shoot_too():
    session = _fight()
    assert _shoot(session, "ike", "doc").effective_dcv < \
        _shoot(session, "ike", "ike").effective_dcv


def test_the_victim_shoots_his_grabber_at_minus_three():
    session = _fight()
    at_grabber = _shoot(session, "frank", "doc").effective_ocv
    baseline = _shoot(session, "ike", "doc").effective_ocv
    assert at_grabber == baseline - 3
