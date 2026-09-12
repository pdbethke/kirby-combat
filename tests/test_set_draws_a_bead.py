"""Set: aim at a MAN, with a GUN, and have it actually count.

6E2 p.81, the whole maneuver:

    "This Combat Maneuver represents the effects of taking extra time to
     aim at a target with a Ranged attack, thereby improving one's
     accuracy. Set does not work with HTH Combat attacks. An attacker who
     wants to Set must spend a Full Phase aiming at the target (this is
     known in some genres as 'drawing a bead')... A character who has Set
     on a target receives a +1 OCV to all attacks against that target
     until he loses his Set. A character must Set on a specific target
     (either an individual or an object); he can't just Set until a
     target presents itself."

`set` was offered 520 times across the western benchmarks and taken zero
times. Five things were wrong with it at once:

  1. offered with `target_id=None` --- "he can't just Set until a target
     presents itself"
  2. offered unconditionally, including to an actor with only HTH
     attacks --- "Set does not work with HTH Combat attacks"
  3. `Set.ocv_bonus` was read by NOTHING but its own unit test, so
     declaring a Set had no mechanical effect whatsoever
  4. the bonus ignored the target, where the rule grants it only against
     the man you drew a bead on
  5. the offer described a "telegraphed strike" --- melee flavour for a
     ranged-only maneuver --- and promised "+1 OCV next phase" where the
     rule says "until he loses his Set"

(3) is this repo's dominant defect class in its purest form: computed,
correct, delivered nowhere. A man could spend his Phase aiming and be no
more accurate for it.
"""
from __future__ import annotations

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat.enumeration import enumerate_actions


def _sets(*, ranged: bool) -> list:
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4,
                     assigned_modifiers=[_StubPower(xmlid="BEAM")])
    fists = _StubPower(xmlid="HANDTOHANDATTACK", name="Fists", levels=4)
    actor = _combatant(id="frank", powers=[gun if ranged else fists])
    enemy = _combatant(id="wyatt", powers=[gun])
    return [a for a in enumerate_actions(actor, [enemy],
                                         distances={"wyatt": 20.0})
            if a.kind == "set"]


def test_a_gunfighter_may_draw_a_bead():
    assert _sets(ranged=True) != []


def test_a_set_names_the_man():
    """6E2 p.81: he cannot just Set until a target presents itself."""
    assert all(a.target_id == "wyatt" for a in _sets(ranged=True))


def test_a_man_with_only_fists_may_not_Set():
    """6E2 p.81: "Set does not work with HTH Combat attacks."."""
    assert _sets(ranged=False) == []


# ---- the bonus has to reach an attack roll ----

def _man(id_: str):
    """A combatant built the way `test_tactical_modifiers._c` builds one
    --- `synthetic_combatant` is keyword-only and takes the whole stat
    block, so there is no one-argument shortcut."""
    from fixtures.synthetic_hero import synthetic_combatant

    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=18, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session():
    """A started session, built the way `test_tactical_modifiers` does.

    `CombatSession.create(...).start()` rather than the dataclass
    constructor: the raw ctor needs a Timeline with four positional
    arguments, and hand-rolling one here would be a second way to build a
    session that drifts from the real one.
    """
    from kirby_combat.session import CombatSession
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    return CombatSession.create(
        id="s1",
        combatants=[_man("frank"), _man("wyatt"), _man("ike")],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        # Seeded, not empty: the session's own roller is what the
        # attack resolver reaches for, and `FakeRoller([])` exhausts
        # on the first shot.
        dice_roller=RandomRoller(seed=7),
    ).start()


def _session_with_set(target_id: str | None):
    from kirby_combat.actions.set_action import Set

    session, _ = Set.declare(_session(), "frank", target_id=target_id)
    return session


def test_the_bonus_applies_against_the_man_you_aimed_at():
    from kirby_combat.actions.set_action import Set

    s = _session_with_set("wyatt")
    assert Set.ocv_bonus(s, "frank", target_id="wyatt") == 1


def test_the_bonus_does_not_follow_you_to_another_man():
    """6E2 p.81 grants it "to all attacks against that target" --- not to
    whatever the attacker swings at next."""
    from kirby_combat.actions.set_action import Set

    s = _session_with_set("wyatt")
    assert Set.ocv_bonus(s, "frank", target_id="ike") == 0


def test_an_unset_combatant_gets_nothing():
    from kirby_combat.actions.set_action import Set

    assert Set.ocv_bonus(_session(), "frank", target_id="wyatt") == 0


# ---- and it has to reach the ROLL, which is the whole point ----

def test_a_set_actually_improves_the_attack_roll():
    """`Set.ocv_bonus` was read by NOTHING but its own unit test.

    The resolver declared the Set and no attack ever asked for the
    bonus, so a man could spend his Phase aiming and be no more accurate
    for it. This drives the real attack resolver and reads the OCV the
    engine itself audited, so the assertion cannot pass on a bonus that
    is computed and dropped.
    """
    from kirby_combat.actions.set_action import Set
    import kirby_combat.loop.resolvers  # noqa: F401  (registers the kinds)
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.models import AttackPower
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    gun = AttackPower(
        xmlid="RKA", name="Colt revolver", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, beam=True,
    )
    shot = LegalAction(
        action_id="attack:wyatt:src1", kind="attack", target_id="wyatt",
        power_xmlid="RKA", power_name="Colt revolver",
        summary="Shoot Wyatt", _attack_view=gun,
    )

    def _ocv_of(session) -> int:
        out = resolve_chosen(
            session, session.combatants["frank"], shot,
            template=CombatTemplate.default_6e_superheroic(),
            roller=RandomRoller(seed=7))
        # `effective_ocv`, not a parsed audit line. The first draft read
        # `audit` and took `split()[2]`, which is the BASE OCV -- the
        # audit reads "Effective OCV: 8 +1 (mod) -2 (range)" -- so the
        # assertion compared a number the Set cannot change and reported
        # the wiring as dead when it was working.
        assert out.result is not None
        return int(out.result.to_hit.effective_ocv)

    plain = _ocv_of(_session())
    aimed = _ocv_of(Set.declare(_session(), "frank", target_id="wyatt")[0])
    assert aimed == plain + 1, f"Set bought nothing: {plain} -> {aimed}"
