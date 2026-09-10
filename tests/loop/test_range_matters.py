"""A shot across the lot is harder than one at point-blank.

6E2's Range Modifier table is in `tables.RANGE_MODIFIER_TABLE`, correct:
nothing to 8m, then -2 OCV per doubling. `range_penalty()` reads it.
`resolution/to_hit.py` applies it. And EVERY attack resolver in the loop
passed `distance_m=None`, so it has never once been charged:

    Range penalty: 0 (HTH or distance not specified)

That line is in the audit trail of every ranged attack this engine has
ever resolved. A revolver at twenty metres hit exactly as easily as one
pressed against a man's coat.

THE DISTANCE WAS ALREADY BEING MEASURED, twice over. `distances_from`
computes it for the MENU -- which is how range-dependent offers are gated
-- and `Brief.bearings` prints it for whatever is choosing, so a model
reading the page could see "5.2m away" and then take a shot the rules
scored as point-blank. Only resolution never asked.

The same shape as `MovementResolved`, `end_spent` and the hit-location
multipliers: computed, correct, delivered nowhere.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _session(apart_m: float):
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-5.0, -5.0, 0.0, 300.0, 300.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-5, -5), (300, -5), (300, 300), (-5, 300)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"tom": Position(0.0, 0.0, 0.0),
                             "virgil": Position(apart_m, 0.0, 0.0)},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=3),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()


def _shoot(apart_m: float):
    """Resolve one ranged attack at that separation; return the audit."""
    import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.loop.run import distances_from

    session = _session(apart_m)
    actor = session.combatants["tom"]
    target = session.combatants["virgil"]
    menu = enumerate_actions(
        actor, [target], has_scene=True, scene=session.scene,
        distances=distances_from(session.scene, actor, [target]),
    )
    attack = next((m for m in menu if m.kind == "attack"), None)
    assert attack is not None, f"no attack offered at {apart_m}m"
    out = resolve_chosen(session, actor, attack, template=TEMPLATE,
                         roller=RandomRoller(seed=3))
    return out.result.audit_trail


def _penalty(audit) -> int:
    for line in audit:
        if line.startswith("Range penalty"):
            if "not specified" in line:
                return 0
            return int(line.split(":")[1].strip().split()[0])
    raise AssertionError(f"no range line in {audit}")


def test_point_blank_costs_nothing():
    """6E2: no penalty inside 8m."""
    assert _penalty(_shoot(4.0)) == 0


def test_across_the_lot_costs_two():
    """8m to 16m is the first doubling: -2 OCV."""
    assert _penalty(_shoot(12.0)) == -2


def test_down_the_street_costs_more():
    """The table is read by BAND, not by doubling from the distance: the
    first band whose ceiling the distance fits under. 40m is inside the
    33-64m band, so it is -6, not the -4 of the 17-32m band."""
    assert _penalty(_shoot(40.0)) == -6
    assert _penalty(_shoot(100.0)) == -8


def test_the_audit_says_the_distance():
    """A to-hit that moved silently is indistinguishable from a bad roll,
    both to a reader and to anything learning from the log."""
    line = next(l for l in _shoot(12.0) if l.startswith("Range penalty"))
    assert "12" in line


def test_a_fight_with_no_map_is_unchanged():
    """Most fights have no Scene, and an unknown distance must stay
    unknown rather than becoming zero -- `distances_from` returns None for
    exactly that reason."""
    import kirby_combat.loop.resolvers  # noqa: F401
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen

    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=3),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()
    actor = session.combatants["tom"]
    menu = enumerate_actions(actor, [session.combatants["virgil"]])
    attack = next(m for m in menu if m.kind == "attack")
    out = resolve_chosen(session, actor, attack, template=TEMPLATE,
                         roller=RandomRoller(seed=3))
    assert _penalty(out.result.audit_trail) == 0


# ---------------------------------------------------------------------------
# The Advantage that buys the penalty away
# ---------------------------------------------------------------------------
def _to_hit_at(distance_m: float, *, bought_off: bool):
    """One to-hit with a made-up ranged power, with and without the +1/2."""
    from kirby_combat.models import AttackInput, AttackPower, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit

    session = _session(distance_m)
    power = AttackPower(
        xmlid="BLAST", name="beam", damage_dice=4, half_die=False,
        plus_one=False, damage_type="normal", defense_type="pd",
        range_m=200.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        no_range_modifier=bought_off,
    )
    return resolve_to_hit(
        AttackInput(
            attacker=session.combatants["tom"],
            target=session.combatants["virgil"],
            power=power, distance_m=distance_m, aim=None,
            dice=DiceValues(to_hit=[3, 3, 3]),
        ),
        template=TEMPLATE,
    )


def test_no_range_modifier_ignores_the_penalty():
    """6E1 p.346: a power with this +1/2 Advantage "ignores the Range
    Modifier when making Attack Rolls", hitting as well at maximum range
    as at point blank. The penalty is not reduced -- it does not apply."""
    assert _to_hit_at(100.0, bought_off=False).range_penalty == -8
    assert _to_hit_at(100.0, bought_off=True).range_penalty == 0


def test_no_range_modifier_says_so_in_the_audit():
    """A zero that came from an Advantage must not read like the zero
    that came from nobody measuring -- that was the bug this whole file
    was written for."""
    audit = _to_hit_at(100.0, bought_off=True).audit
    line = next(l for l in audit if l.startswith("Range penalty"))
    assert "No Range Modifier" in line


def test_the_advantage_is_read_off_the_build():
    """HD writes it as NORANGEMODIFIER; nothing downstream can honour a
    modifier the view never carries."""
    import inspect
    from kirby_combat import hero_view
    assert "NORANGEMODIFIER" in inspect.getsource(hero_view)
