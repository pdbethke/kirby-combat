"""The page a man reads outside his own Phase says why he is reading it.

`loop/reactions.py` asks a chooser two questions out of turn: Abort to a
defence against an incoming attack (6E2 p.23-24), or use a Held Action before
somebody else's Phase (6E2 p.22). The Brief said neither: the defender saw a
Turn and Segment and a menu of Dodge and Block, with no attack, no attacker,
and nothing to say an Abort costs his next Phase.

Every page here is the one `run_phase` hands the defender's chooser.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import encounter_of, fighter          # tests/loop/conftest.py
from kirby_combat.actions.flash import Flash
from kirby_combat.brief import Brief
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_dice import RandomRoller

HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


class _Reads:
    """``a`` shoots ``d`` (or holds, when ``hold``); everybody else waits.
    Keeps every out-of-turn page, rendered."""

    def __init__(self, *, hold: bool = False):
        self.hold = hold
        self.pages: list[tuple[str, str, str]] = []

    def choose(self, situation):
        why = situation.out_of_turn
        if why is not None:
            self.pages.append((situation.actor.id, why.reason.value,
                               Brief(situation).render()))
            return situation.menu[0].action_id
        kind = "hold" if (self.hold and situation.actor.id == "a") else (
            "attack" if situation.actor.id == "a" else "dodge")
        return next(a for a in situation.menu if a.kind == kind).action_id


def _duel():
    # A SHEET page: "Incoming: ..., OCV 9" is the attacker's sheet, which a
    # judged page leaves off (see test_the_page_judges_enemies).
    enc = encounter_of(fighter("a", side=HEROES, dex=30),
                       fighter("d", side=VILLAINS, dex=10))
    session = enc.sessions[0]
    return replace(enc, sessions=[replace(session, template=replace(
        session.template, page_knowledge="sheet"))])


def _abort_page(encounter) -> str:
    chooser = _Reads()
    run_phase(encounter, chooser, roller=RandomRoller(seed=3),
              on_unresolvable="raise")
    pages = [p for who, why, p in chooser.pages if who == "d" and why == "abort"]
    assert pages, "the defender was never asked"
    return pages[0]


def test_the_abort_page_names_the_attack_the_attacker_and_the_cost():
    page = _abort_page(_duel())
    assert "OUT OF TURN: this is not your Phase. An attack is coming at you" in page
    assert "Incoming: a, Blast (attack, ranged, OCV 9)." in page
    assert "You can perceive a with a Targeting Sense." in page
    assert "An Abort costs your next Phase (6E2 p.23-24)." in page


def test_the_abort_page_says_when_he_cannot_perceive_the_attacker():
    enc = _duel()
    s, _ = Flash.apply(enc.sessions[0], attacker_id="a", target_id="d",
                       sense_group="sight", body_dealt=6, flash_defense=0)
    from dataclasses import replace
    page = _abort_page(replace(enc, sessions=[s]))
    assert "You cannot perceive a with a Targeting Sense." in page


def test_the_held_action_page_says_what_he_is_holding_for():
    chooser = _Reads(hold=True)
    roller = RandomRoller(seed=3)
    first = run_phase(_duel(), chooser, roller=roller, on_unresolvable="raise")
    assert first.kind == "hold"
    run_phase(first.encounter, chooser, roller=roller, on_unresolvable="raise")
    pages = [p for who, why, p in chooser.pages if who == "a" and why == "held_action"]
    assert pages, "the holder was never asked"
    assert ("OUT OF TURN: this is not your Phase. d's Phase is about to start "
            "and you are Holding an Action") in pages[0]
    assert "You are holding for: " in pages[0]


def test_an_ordinary_phase_says_nothing_of_the_kind():
    class _Own:
        page = None

        def choose(self, situation):
            if situation.out_of_turn is None and self.page is None:
                self.page = Brief(situation).render()
            return next(a for a in situation.menu if a.kind == "dodge").action_id

    own = _Own()
    run_phase(_duel(), own, roller=RandomRoller(seed=3), on_unresolvable="raise")
    assert "OUT OF TURN" not in own.page
