"""Mental Paralysis binds (6E1 p.217-219), and so does a physical Entangle.

Mental Entangle made its MCV Attack Roll, wrote `entangle_body` into the log
and applied nothing: the victim acted as if free. RAW it is an Entangle
(6E1 p.219: "Characters can use Entangle to create a type of power called
Mental Paralysis") with three differences, all on p.219:

* it has "Resistant Mental Defense instead of PD/ED";
* "The victim uses EGO, not STR, to escape ... He rolls 1d6 per 5 points of
  EGO", and "Mental Defense neither adds to the character's EGO for purposes
  of breaking out of, nor offers any other protection against, Mental
  Paralysis";
* "Attacks with a physical manifestation ... cannot damage a Mental
  Paralysis" --- Mental Blasts can --- and Teleporting out leaves him
  "subject to the Mental Paralysis when he appears at his destination".

Building it on the physical Entangle found that the physical one was never
wired into the loop either: `run_phase` passed no `physical_entangle`, so
an Entangled man got his whole menu, and nothing put him at DCV 0.
"""
from __future__ import annotations

from test_mental_combat_bites import (
    TEMPLATE, _Dice, _Power, _Records, _brainchild, _fight, _offer, _person,
)

from kirby_combat.actions.entangle import Entangle
from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.effects import entangle_state
from kirby_dice import RandomRoller


def _paralyst(levels: int = 4):
    psi = _brainchild()
    power = _Power("ENTANGLE", levels, mods=("VERSUSEGO", "ACV", "TAKESNODAMAGE"))
    psi.hero.powers.append(power)
    return psi, power


def _paralysed(*, levels: int = 4, effect: int = 4, md: int = 5, ego: int = 10,
               mark_is_mentalist: bool = False):
    psi, power = _paralyst(levels)
    mark = _person("mark", "gang", dex=30, md=md, ego=ego, mentalist=mark_is_mentalist)
    session = _fight(psi, mark)
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mental_entangle", "mark", power),
                              template=TEMPLATE, roller=_Dice((1, 1, 1), effect=effect))
    return resolved.session


def _menu_of_mark(session):
    chooser = _Records()
    result = run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]),
                       chooser, roller=RandomRoller(seed=21))
    assert result.actor_id == "mark"
    return chooser.menu


# ── applying it ─────────────────────────────────────────────────────────────

def test_mental_paralysis_is_a_real_entangle_with_mental_defense_not_pd_ed():
    """6E1 p.217: "he rolls his Entangle dice and counts the Normal Damage
    BODY" --- four 4s are 4 BODY, not 16. p.219: Mental Defense "offers no
    other protection against" it, so mark's MD 5 takes nothing off."""
    session = _paralysed()
    applied = [e for e in session.event_log if e.kind == "EntangleApplied"]
    assert len(applied) == 1
    a = applied[0]
    assert (a.target_id, a.mental_paralysis, a.entangle_body, a.entangle_md) == (
        "mark", True, 4, 4)
    assert (a.entangle_pd, a.entangle_ed) == (0, 0)
    assert Entangle.is_entangled(session, "mark") == (True, 4)


def test_a_missed_mcv_roll_binds_nobody():
    psi, power = _paralyst()
    session = _fight(psi, _person("mark", "gang", dex=30))
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mental_entangle", "mark", power),
                              template=TEMPLATE, roller=_Dice((6, 6, 6), effect=4))
    assert not [e for e in resolved.session.event_log if e.kind == "EntangleApplied"]


def test_a_mental_paralysis_is_not_a_physical_entangle():
    """p.219: "physical Entangles don't add to Mental Paralysis Entangles,
    and vice-versa" --- the physical fold does not see it."""
    session = _paralysed()
    assert entangle_state(session, "mark").is_entangled is False


# ── what it does to him ─────────────────────────────────────────────────────

def test_the_paralysed_man_is_at_dcv_zero():
    """6E1 p.217: "his arms and legs are restrained, giving him a DCV of 0"."""
    assert effective_dcv_for(_paralysed(), "mark") == 0


def test_his_menu_is_the_ego_escape_and_nothing_else():
    """p.217: "an Entangled character must escape the Entangle before
    attacking other characters". No STR escape (p.219: EGO, not STR), no
    Teleport out (he remains subject to it)."""
    menu = _menu_of_mark(_paralysed())
    assert {a.kind for a in menu} == {"escape_ego"}


def test_a_mentalist_may_mental_blast_his_way_out_but_not_shoot():
    """p.219: Mental Blasts can affect a Mental Paralysis; "Attacks with a
    physical manifestation ... cannot damage" it."""
    menu = _menu_of_mark(_paralysed(mark_is_mentalist=True))
    attacks = [a for a in menu if a.kind == "escape_attack"]
    assert [a.power_xmlid for a in attacks] == ["MENTALBLAST"]


# ── escaping it ─────────────────────────────────────────────────────────────

def _escape(session, kind: str, effect: int, power=None):
    offer = next(a for a in _menu_of_mark_offers(session) if a.kind == kind
                 and (power is None or a.power_xmlid == power))
    return resolve_chosen(session, session.combatants["mark"], offer,
                          template=TEMPLATE, roller=_Dice((effect,) * 3, effect=effect)).session


def _menu_of_mark_offers(session):
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.run import _entangle_holds

    physical, paralysis = _entangle_holds(session, "mark")
    mark = session.combatants["mark"]
    return enumerate_actions(mark, [session.combatants["psi"]],
                             physical_entangle=physical, mental_paralysis=paralysis)


def test_ego_escape_rolls_ego_over_five_dice_against_its_mental_defense():
    """EGO 10: 2d6. Two 6s are 4 BODY of Normal Damage (6E2 p.100: a 6 is 2 BODY),
    less the paralysis's MD 4 --- nothing; it holds at 4 BODY."""
    session = _escape(_paralysed(), "escape_ego", effect=6)
    assert Entangle.is_entangled(session, "mark") == (True, 4)


def test_a_strong_mind_breaks_it():
    """EGO 30: 6d6 of 6s, 12 BODY - MD 4 = 8, at least twice the 4 BODY left,
    so he is free (6E2 p.126's breakout margin)."""
    session = _escape(_paralysed(ego=30), "escape_ego", effect=6)
    assert Entangle.is_entangled(session, "mark") == (False, None)
    escapes = [e for e in session.event_log if e.kind == "EntangleEscape"]
    assert [(e.mental_paralysis, e.escaped) for e in escapes] == [(True, True)]


def test_his_own_mental_defense_does_not_help_him_escape():
    """p.219: MD does not add to EGO for breaking out. EGO 10 with MD 50 is
    still 2d6."""
    weak = _escape(_paralysed(md=50), "escape_ego", effect=6)
    assert Entangle.is_entangled(weak, "mark") == (True, 4)


def test_a_mental_blast_counts_its_body_as_normal_damage():
    """p.219: "if it's a STUN-only attack, count the 'BODY' as if it were a
    Normal Damage attack". 6d6 of 6s = 12 BODY - MD 4 = 8: free."""
    session = _escape(_paralysed(mark_is_mentalist=True), "escape_attack",
                      effect=6, power="MENTALBLAST")
    assert Entangle.is_entangled(session, "mark") == (False, None)


# ── the physical Entangle, wired at last ────────────────────────────────────

def _physically_entangled():
    psi = _brainchild()
    mark = _person("mark", "gang", dex=30)
    session = _fight(psi, mark)
    session, _ = Entangle.apply(session, attacker_id="psi", target_id="mark",
                                entangle_body=5, entangle_pd=5, entangle_ed=5)
    return session


def test_a_physically_entangled_man_is_offered_only_his_escapes():
    menu = _menu_of_mark(_physically_entangled())
    assert menu and {a.kind for a in menu} <= {"escape_str", "escape_attack", "escape_teleport"}


def test_a_physically_entangled_man_is_at_dcv_zero():
    assert effective_dcv_for(_physically_entangled(), "mark") == 0


def test_a_str_escape_counts_body_and_soaks_against_the_entangles_pd():
    """6E1 p.218: escape BODY must "exceed the Entangle's defenses". STR 15 is
    3d6; three 6s are 6 BODY, less PD 5 = 1 off a 5 BODY Entangle."""
    session = _escape(_physically_entangled(), "escape_str", effect=6)
    assert Entangle.is_entangled(session, "mark") == (True, 4)
