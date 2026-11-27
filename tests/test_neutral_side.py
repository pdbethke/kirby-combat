"""A neutral side: nobody's enemy, and not a side in the fight (`Side.neutral`).

The Cowboys' horses at the O.K. Corral (Peter, 2026-11-27): not targeted by
anybody's doctrine, and a fight is neither won nor kept going by them.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.roster import Roster
from kirby_combat.session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC
from kirby_dice import FakeRoller

LAW, COW = Side.named("law"), Side.named("cow")
HORSES = Side.named("horses", neutral=True)


def _session(*men):
    return CombatSession.create(id="s", combatants=list(men), scene=None,
                                template=RAW_HEROIC, dice_roller=FakeRoller([])).start()


def _man(id_, side, **kw):
    return synthetic_combatant(id=id_, name=id_, spd=2, side=side, **kw)


def test_neutral_is_hostile_to_nobody():
    assert not HORSES.hostile_to(LAW) and not LAW.hostile_to(HORSES)
    assert LAW.hostile_to(COW)


def test_nobody_is_offered_the_horse_as_an_enemy():
    session = _session(_man("wyatt", LAW), _man("frank", COW), _man("horse", HORSES))
    enemies = [c.id for c in Roster(session).enemies_of(session.combatants["wyatt"])]
    assert enemies == ["frank"]


def test_the_horses_do_not_keep_a_fight_going():
    """The Cowboys down: one side stands, whatever the horses are doing."""
    session = _session(_man("wyatt", LAW), _man("frank", COW, current_body=0),
                       _man("horse", HORSES))
    assert list(Roster(session).standing) == [LAW]


def test_a_neutral_body_is_asked_nothing_until_it_spooks():
    """Seam: the loop spends a standing horse's Phase without asking the
    chooser; a horse that bolted is asked, and offered only breaking off."""
    from fixtures.terms import terms_stated
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop.run import run_phase
    from kirby_combat.squads import KEEP_ORDERS

    asked: list = []

    class _Watch:
        def give_orders(self, page):
            return KEEP_ORDERS

        def choose(self, situation):
            asked.append(situation.actor.id)
            return situation.menu[0].action_id

    session = terms_stated(_session(_man("wyatt", LAW, dex=10), _man("frank", COW, dex=10),
                                    _man("horse", HORSES, dex=30)))
    encounter = Encounter(id="e", turn=1, segment=11, sessions=[session],
                          template=RAW_HEROIC).run_segment(roller=lambda: [3, 3, 3])
    class _Threes:
        def roll_dice(self, count, sides):
            return [3] * count

    result = run_phase(encounter, _Watch(), roller=_Threes(), on_unresolvable="skip")
    spent = [e for e in result.encounter.sessions[0].event_log
             if e.kind == "PhaseSpent" and e.combatant_id == "horse"]
    assert "horse" not in asked
    assert spent and spent[0].reason == "stands"
