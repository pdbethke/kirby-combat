"""Somebody can kneel down and stop a man dying.

6E2 p.109: "This unpleasant fate is not inevitable. Another character can
stabilize a character at 0 or negative BODY with a successful Paramedics
roll (at -1 for every negative 2 BODY). This doesn't give the wounded
character back any BODY, it just stabilizes his condition so he doesn't
lose any more BODY."

6E2 p.115 adds that the roll is available to anyone: "Characters with
Paramedics (even just the Everyman 8- roll) may attempt to stop
Bleeding."

Until the bleed-out existed there was nothing to stabilize, so this is
the other half of the same rule rather than a separate feature: a fight
where men bleed and cannot be saved is not the rule, it is half of it.
Doc Holliday was a dentist.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_HEROIC
from kirby_combat.vitals import apply_vitals_delta
from kirby_dice import FakeRoller, RandomRoller

LAW = Side.named("law")
COW = Side.named("cow")


def _medic(paramedics: int | None = 11):
    return synthetic_combatant(
        id="doc", name="Doc", ocv=7, dcv=5, spd=3, dex=15,
        max_stun=20, max_body=9, max_end=25, side=LAW,
        skills={"PARAMEDICS": paramedics} if paramedics else None,
    )


def _fight(*, wounded_body: int, paramedics: int | None = 11):
    session = CombatSession.create(
        id="doc", scene=None, template=RAW_HEROIC,
        dice_roller=RandomRoller(seed=2),
        combatants=[_medic(paramedics),
                    synthetic_combatant(id="hurt", name="Hurt", spd=3,
                                        max_stun=20, max_body=10,
                                        max_end=25, side=LAW),
                    fighter("foe", side=COW)],
    ).start()
    hurt = session.combatants["hurt"]
    session.combatants["hurt"] = apply_vitals_delta(
        hurt, body=wounded_body - hurt.state.current_body)
    return session


def _offers(session):
    actor = session.combatants["doc"]
    enemies = [session.combatants["foe"]]
    allies = [session.combatants["hurt"]]
    return [m for m in enumerate_actions(actor, enemies, allies=allies)
            if m.kind == "stabilize"]


# ---- The offer -----------------------------------------------------------

def test_a_dying_ally_can_be_stabilized():
    assert [m.target_id for m in _offers(_fight(wounded_body=-2))] == ["hurt"]


def test_nobody_offers_to_stabilize_a_man_who_is_fine():
    assert _offers(_fight(wounded_body=6)) == []


def test_the_offer_says_what_the_roll_is():
    """-2 BODY is -1 on an 11- Paramedics, so 10-. A page that does not
    say the number is a page nothing can reason from."""
    offer = _offers(_fight(wounded_body=-2))[0]
    assert "10-" in offer.summary, offer.summary


def test_everyman_paramedics_is_enough_to_try():
    """p.115: "even just the Everyman 8- roll"."""
    assert _offers(_fight(wounded_body=-2, paramedics=None))


# ---- The roll ------------------------------------------------------------

def _stabilize(session, roll):
    offer = _offers(session)[0]
    return resolve_chosen(session, session.combatants["doc"], offer,
                          template=RAW_HEROIC, roller=FakeRoller([roll]))


def test_a_made_roll_stops_the_bleeding():
    session = _fight(wounded_body=-2)
    after = _stabilize(session, [1, 1, 1]).session       # 3 on 3d6
    assert after.event_log[-1].result_payload["stabilized"] is True

    ended = Encounter(id="e", turn=1, segment=12, sessions=[after],
                      template=RAW_HEROIC).advance_segment().sessions[0]
    assert ended.combatants["hurt"].state.current_body == -2, (
        "a stabilized man stops losing BODY (6E2 p109)")


def test_a_missed_roll_leaves_him_bleeding():
    session = _fight(wounded_body=-2)
    after = _stabilize(session, [6, 6, 6]).session       # 18 on 3d6
    assert after.event_log[-1].result_payload["stabilized"] is False

    ended = Encounter(id="e", turn=1, segment=12, sessions=[after],
                      template=RAW_HEROIC).advance_segment().sessions[0]
    assert ended.combatants["hurt"].state.current_body == -3


def test_stabilizing_gives_back_no_body():
    """p.109 is explicit: "This doesn't give the wounded character back
    any BODY"."""
    session = _fight(wounded_body=-4)
    after = _stabilize(session, [1, 1, 1]).session
    assert after.combatants["hurt"].state.current_body == -4


def test_the_driver_tells_enumeration_who_is_on_his_side():
    """Enumeration knowing how is worth nothing if the loop never says
    who the actor's allies are -- and `Roster.allies_of` excludes the
    DOWN, which is right for "who can help me fight" and exactly wrong
    for the man on the ground who needs somebody to kneel beside him."""
    from kirby_combat.encounter import Encounter
    import kirby_combat.loop.run as run

    session = _fight(wounded_body=-2)
    ties = RandomRoller(seed=11)
    session = Encounter(id="e", turn=1, segment=12, sessions=[session],
                        template=RAW_HEROIC).run_segment(
        roller=lambda: ties.roll_dice(3)).sessions[0]

    handed: list = []
    original = run.enumerate_actions

    def spy(actor, enemies, **kwargs):
        handed.append((actor.id, [a.id for a in kwargs.get("allies") or []]))
        return original(actor, enemies, **kwargs)

    class _First:
        def choose(self, situation):
            return situation.menu[0].action_id

    run.enumerate_actions = spy
    try:
        run.run_phase(session, _First(), template=RAW_HEROIC,
                      roller=RandomRoller(seed=2), on_unresolvable="skip")
    finally:
        run.enumerate_actions = original

    assert handed, "nobody was enumerated at all"
    # Whoever acted, the dying man is on somebody's list -- either as an
    # ally to save or, for the enemy, not at all.
    for actor_id, ally_ids in handed:
        if actor_id == "doc":
            assert "hurt" in ally_ids, (
                "Doc was not told his friend was on the ground")


def test_a_fallen_ally_is_still_an_ally():
    """`Roster.fallen_allies_of` is the seam: a dying man is nobody's
    fighting ally and very much somebody's patient."""
    from kirby_combat.roster import Roster

    session = _fight(wounded_body=-2)
    roster = Roster(session)
    doc = session.combatants["doc"]
    assert [c.id for c in roster.allies_of(doc)] == []
    assert [c.id for c in roster.fallen_allies_of(doc)] == ["hurt"]
