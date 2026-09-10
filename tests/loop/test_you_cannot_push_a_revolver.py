"""6E2 p.135: a Power on Charges cannot be Pushed.

    "Generally, characters can only Push Powers that cost END. They
    cannot Push powers that never cost END, that are bought to 0 END, or
    that have Charges (but can Push powers bought to 1/2 END)."

`enumeration._pushable` already knows this and asks the SOURCE power's
`uses_end`, which is the engine's Java-parity answer. But when the source
cannot be found it returns True unconditionally, and an AUTHORED attack
-- every combatant in the publishable shootout, and most of this suite --
has no source power at all. So a Colt Peacemaker with six charges was
offered as a Push, and Pushing it charged 5 END (6E2 p.133) out of a
gunfighter who should never have been able to spend it.

The fallback is not wrong to be permissive: the bare STR strike has no
source either, and STR does cost END. The fix is to fall back to what the
VIEW carries -- `charges` and `reduced_end`, both read off the build --
rather than to a blanket yes.
"""
from __future__ import annotations

from kirby_combat.endurance import costs_end
from kirby_combat.enumeration import enumerate_actions


def test_costs_end_is_the_books_own_test():
    """The three cases p.135 names, and the one it allows."""
    from kirby_combat.models import AttackPower

    def gun(**kw):
        return AttackPower(
            xmlid="RKA", name="colt", damage_dice=2, half_die=False,
            plus_one=False, damage_type="killing", defense_type="pd",
            range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
            penetrating=0, increased_stun_mult=0, is_ranged=True, **kw)

    assert costs_end(gun()) is True,                 "a plain power can be Pushed"
    assert costs_end(gun(charges=6)) is False,       "Charges cannot"
    assert costs_end(gun(reduced_end=True)) is False, "0 END cannot"


def test_a_charged_weapon_is_never_offered_as_a_push():
    """Through the real menu, with the real cast. The shootout's cast is
    authored, so nothing here has a source power to consult."""
    from examples.the_shootout_we_can_publish import the_cast, the_scene
    from kirby_combat.loop.run import distances_from
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import RAW_HEROIC
    from kirby_dice import RandomRoller

    session = CombatSession.create(
        id="push", combatants=the_cast(), scene=the_scene(),
        template=RAW_HEROIC, dice_roller=RandomRoller(seed=1)).start()

    offered = []
    for actor in session.combatants.values():
        enemies = [c for c in session.combatants.values()
                   if c.side != actor.side]
        menu = enumerate_actions(
            actor, enemies, has_scene=True, scene=session.scene,
            distances=distances_from(session.scene, actor, enemies),
        )
        offered += [(actor.name, m.summary) for m in menu if m.kind == "push"]

    assert offered == [], (
        "every weapon at the O.K. Corral runs on Charges and none of them "
        f"can be Pushed, but the menu offered: {offered}"
    )
