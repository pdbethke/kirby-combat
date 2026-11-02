"""Every STUN, BODY and END change names who caused it.

`VitalsChanged` said what happened to a man and never by whom. Asked "who
knocked Talisman out", the only answer was to line the rows up by sequence
number and guess which `ActionResolved` each one belonged to: the Destroid's
57 STUN and the knockback's 29 more were two anonymous rows. `caused_by` is
the combatant whose act caused the change: the attacker for a hit and for
the knockback and fall it brings, the man himself for a cost he paid.
"""
from __future__ import annotations

from shaped import Dice, Picks, armed, encounter_on, scene_with, shaped_blast

from kirby_combat.loop import run_phase
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _shot():
    enc = encounter_on(
        scene_with({"shooter": (0, 0, 0), "mark": (5, 0, 0)}),
        armed("shooter", shaped_blast("blast", 8), side=VILLAINS, dex=30),
        armed("mark", None, side=HEROES))
    # 3d6 of 2s is 6: it hits. Every damage die a 2 as well.
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "attack" and a.target_id == "mark"),
                       roller=Dice(face=2), on_unresolvable="raise")
    return [e for e in result.encounter.sessions[0].event_log if e.kind == "VitalsChanged"]


def test_the_damage_names_the_attacker():
    hurt = [e for e in _shot() if e.combatant_id == "mark" and e.reason == "damage"]
    assert hurt, "the shot did no damage to record"
    assert {e.caused_by for e in hurt} == {"shooter"}


def test_the_end_he_spent_is_his_own_doing():
    spent = [e for e in _shot() if e.reason == "end_spent"]
    assert spent and all(e.caused_by == e.combatant_id == "shooter" for e in spent)


def test_the_knockback_names_the_man_who_hit_him():
    from kirby_combat.impact import impact_damage
    from shaped import TEMPLATE, session_on

    s = session_on(scene_with({"a": (0, 0, 0), "b": (1, 0, 0)}),
                   armed("a", None, side=VILLAINS), armed("b", None, side=HEROES))
    s, _ = impact_damage(s, "b", 4, roller=Dice(face=6), template=TEMPLATE,
                         reason="knockback", double_stun=False, halved=False,
                         caused_by="a")
    (row,) = [e for e in s.event_log if e.kind == "VitalsChanged"]
    assert (row.combatant_id, row.reason, row.caused_by) == ("b", "knockback", "a")
