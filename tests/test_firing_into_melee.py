"""Shoot at a man who is holding somebody, and you may hit the hostage.

Asked directly, and 6E2 p.45 has it:

    "Gamemasters may, if they wish, use the normal Behind Cover rules
     when a character tries to make a Ranged Attack against a character
     in the middle of a HTH Combat with one or more other persons
     ('firing into melee')... The attacker then makes his Attack Roll
     against the target's DCV, including the OCV penalty from Behind
     Cover. If the roll misses solely as a result of the Behind Cover OCV
     penalty (i.e., it misses by less than or equal to the penalty), then
     the attacker may have actually hit the cover - one of the other
     people in the melee. The GM decides which combatant is the potential
     target... The attacker must make another Attack Roll against that
     target, using only his base OCV (no bonuses from Combat Skill
     Levels, Combat Maneuvers, or the like apply)."

THREE THINGS THE PAGE INSISTS ON, and each is a test here:

  * the near-miss band is CLOSED --- "misses by less than or equal to the
    penalty". A shot that misses by more than the penalty missed on its
    own merits and endangers nobody.
  * the second roll uses BASE OCV ONLY. No Combat Skill Levels, no
    maneuver bonus, no Set. A marksman gets no help hitting the man he
    was trying not to hit.
  * it is OPTIONAL --- "Gamemasters may, if they wish" --- so it is
    template-gated like 6E2 p.115's Bleeding, and OFF unless a campaign
    asks for it.

-2 OCV IS A JUDGEMENT, and a grounded one. The page leaves the figure to
the GM ("based on the number of combatants, how quickly they're moving
around, their relative sizes"), and its own Behind Cover example on the
same page prices a rock that "protects roughly half of Andarra" at -2
OCV. One man held in front of another is the same shape of obstruction,
so -2 is the default and the template can change it.
"""
from __future__ import annotations

from kirby_combat.grappling import melee_cover, MeleeCover


class _Held:
    """doc holds frank; ike is free."""

    def grabbed_by(self, cid):
        return {"frank": "doc"}.get(cid)

    def is_grabbing(self, cid):
        return cid == "doc"

    def combatant_ids(self):
        return ("doc", "frank", "ike")


S = _Held()


def test_a_man_holding_somebody_is_shot_at_through_a_body():
    cover = melee_cover(S, attacker="ike", target="doc")
    assert cover.applies
    assert cover.ocv_penalty == -2
    assert cover.other_body == "frank"


def test_the_held_man_is_shot_at_through_his_grabber():
    """It runs both ways --- the grabber is a body in front of the
    victim just as much as the reverse."""
    cover = melee_cover(S, attacker="ike", target="frank")
    assert cover.applies
    assert cover.other_body == "doc"


def test_a_man_in_the_open_is_not_fired_into():
    assert melee_cover(S, attacker="doc", target="ike").applies is False


def test_the_grabber_shooting_his_own_victim_is_not_firing_into_melee():
    """He is not shooting past anybody; he has hold of him."""
    assert melee_cover(S, attacker="doc", target="frank").applies is False


def test_the_victim_shooting_his_grabber_likewise():
    assert melee_cover(S, attacker="frank", target="doc").applies is False


# ---- the near-miss band ----

def test_a_miss_inside_the_penalty_may_have_hit_the_other_man():
    """"misses by less than or equal to the penalty"."""
    cover = MeleeCover(other_body="frank", ocv_penalty=-2)
    assert cover.strays(missed_by=1) is True
    assert cover.strays(missed_by=2) is True


def test_a_miss_beyond_the_penalty_endangers_nobody():
    """It missed on its own merits, not because of the bodies."""
    assert MeleeCover(other_body="frank", ocv_penalty=-2).strays(missed_by=3) is False


def test_a_hit_strays_nowhere():
    assert MeleeCover(other_body="frank", ocv_penalty=-2).strays(missed_by=0) is False
    assert MeleeCover(other_body="frank", ocv_penalty=-2).strays(missed_by=-4) is False


def test_no_cover_never_strays():
    assert MeleeCover().applies is False
    assert MeleeCover().strays(missed_by=1) is False


# ---- the optional-rule gate, and a stray shot that lands ----

def _fight(*, firing_into_melee: bool):
    """doc holds frank; ike shoots at doc from across the lot."""
    import dataclasses

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

    template = dataclasses.replace(
        CombatTemplate.default_6e_superheroic(),
        use_firing_into_melee=firing_into_melee)
    s = CombatSession.create(
        id="s", combatants=[man("doc"), man("frank"), man("ike")], scene=None,
        template=template, dice_roller=RandomRoller(seed=2)).start()
    s, _ = Grab.declare_and_resolve(
        s, attacker_id="doc", target_id="frank", attacker_str=20,
        target_str=10, attacker_ocv=8, target_dcv=0, attack_roll=3)
    return s, template


def _shoot(session, template, roll_seed: int):
    import kirby_combat.loop.resolvers  # noqa: F401
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.models import AttackPower
    from kirby_dice import RandomRoller

    gun = AttackPower(
        xmlid="RKA", name="Colt", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, beam=True)
    return resolve_chosen(
        session, session.combatants["ike"],
        LegalAction(action_id="attack:doc:src1", kind="attack",
                    target_id="doc", power_xmlid="RKA", power_name="Colt",
                    summary="Shoot doc", _attack_view=gun),
        template=template, roller=RandomRoller(seed=roll_seed))


def test_the_rule_is_off_unless_the_campaign_asks():
    """"Gamemasters may, if they wish" --- template-gated like 6E2
    p.115's Bleeding, and OFF by default."""
    from kirby_combat.template import CombatTemplate

    assert CombatTemplate.default_6e_superheroic().use_firing_into_melee is False


def test_with_the_rule_off_the_shot_takes_no_cover_penalty():
    session, template = _fight(firing_into_melee=False)
    out = _shoot(session, template, roll_seed=4)
    assert "Firing into melee" not in " ".join(out.result.to_hit.audit)


def test_with_the_rule_on_the_bodies_cost_the_shooter_OCV():
    session, template = _fight(firing_into_melee=True)
    out = _shoot(session, template, roll_seed=4)
    assert "Firing into melee" in " ".join(out.result.to_hit.audit)


def test_the_penalty_actually_lowers_the_OCV():
    on, t_on = _fight(firing_into_melee=True)
    off, t_off = _fight(firing_into_melee=False)
    assert _shoot(on, t_on, 4).result.to_hit.effective_ocv == \
        _shoot(off, t_off, 4).result.to_hit.effective_ocv - 2


# ---- the stray shot itself ----

def test_a_near_miss_is_re_rolled_against_the_other_man():
    """"the attacker may have actually hit the cover - one of the other
    people in the melee... another Attack Roll against that target,
    using only his base OCV."

    Driven through the real resolver over many seeds: with the rule on,
    at least one shot must be recorded as straying, or the branch is
    decoration.
    """
    strayed = 0
    for seed in range(40):
        session, template = _fight(firing_into_melee=True)
        out = _shoot(session, template, roll_seed=seed)
        if any("strayed" in line for line in (out.result.to_hit.audit or [])):
            strayed += 1
    assert strayed > 0, "no shot ever strayed in 40 attempts"


def test_no_shot_strays_while_the_rule_is_off():
    for seed in range(40):
        session, template = _fight(firing_into_melee=False)
        out = _shoot(session, template, roll_seed=seed)
        assert not any("strayed" in line
                       for line in (out.result.to_hit.audit or []))


def test_the_second_roll_uses_base_OCV_only():
    """"using only his base OCV (no bonuses from Combat Skill Levels,
    Combat Maneuvers, or the like apply)". Asserted on the helper so the
    claim does not depend on finding a straying seed."""
    from kirby_combat.grappling import stray_ocv

    assert stray_ocv(base_ocv=8, effective_ocv=14) == 8
    assert stray_ocv(base_ocv=8, effective_ocv=2) == 8


# ---- the stray shot that never went off ----

def _activation_gun(activation: int):
    """The Colt above, bought with 6E1 p.375's Activation Roll."""
    from kirby_combat.models import AttackPower

    return AttackPower(
        xmlid="RKA", name="Colt", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, beam=True,
        activation_roll=activation)


def _scripted_stray(first_roll, *, stray_activation):
    """One shot that misses inside the cover penalty, then the stray.

    Dice per attack, in the order the engine draws them: to-hit 3d6, damage,
    Hit Location 3d6, the STUN Multiplier 1d6, and then the Activation Roll
    at the door. The first shot activates (9 against a 14-); the stray's
    Activation is the scripted one.
    """
    import kirby_combat.loop.resolvers  # noqa: F401
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_dice import FakeRoller

    session, template = _fight(firing_into_melee=True)
    pool = [
        first_roll, [3, 3], [3, 3, 3], [1], [3, 3, 3],          # the shot
        [3, 3, 3], [3, 3], [3, 3, 3], [1], stray_activation,    # the stray
    ]
    return resolve_chosen(
        session, session.combatants["ike"],
        LegalAction(action_id="attack:doc:src1", kind="attack",
                    target_id="doc", power_xmlid="RKA", power_name="Colt",
                    summary="Shoot doc", _attack_view=_activation_gun(14)),
        template=template, roller=FakeRoller(pool))


def test_a_stray_whose_weapon_does_not_go_off_does_not_crash():
    """6E2 p.45's stray goes through `resolve_attack_in_session` like any
    other shot -- which means it makes its own Activation Roll (6E1 p.375),
    and a power that does not fire comes back with `to_hit=None`.

    `_maybe_stray` guards `to_hit is None` on the INCOMING result and
    nothing guarded the stray's, so `stray_result.to_hit.hit` raised
    AttributeError out of the middle of the Phase -- past
    `on_unresolvable="skip"` -- for any Activation-limited weapon fired
    into a melee. 18 against a 14- is a failure.
    """
    out = _scripted_stray([5, 5, 4], stray_activation=[6, 6, 6])
    audit = out.result.to_hit.audit or []
    assert any("strayed to frank" in line for line in audit)
    assert any("the weapon did not go off" in line for line in audit)


def test_the_failed_stray_is_recorded_as_a_failed_activation():
    """The bystander's row says the weapon jammed rather than that he was
    missed -- a stray that vanished would read as a shot never taken."""
    out = _scripted_stray([5, 5, 4], stray_activation=[6, 6, 6])
    payloads = [e.result_payload for e in out.events
                if getattr(e, "result_payload", None)
                and "activated" in e.result_payload]
    failed = [p for p in payloads if p["activated"] is False]
    assert len(failed) == 1, "the stray's failed activation was not recorded"
    assert failed[0]["target_id"] == "frank"
    assert failed[0]["hit"] is False
    assert failed[0]["activation_roll"] == 18


def test_a_stray_whose_weapon_does_go_off_still_resolves():
    """Guards the guard: the ordinary stray must keep working, and must
    still say whether it hit."""
    out = _scripted_stray([5, 5, 4], stray_activation=[3, 3, 3])
    audit = out.result.to_hit.audit or []
    assert any("strayed to frank" in line for line in audit)
    assert not any("did not go off" in line for line in audit)
    assert any(line.endswith("HIT") or line.endswith("missed")
               for line in audit if "strayed" in line)
