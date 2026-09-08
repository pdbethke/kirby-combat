"""When a side breaks.

Spec: `kirby/docs/superpowers/specs/2026-09-08-side-morale-design.md`.

Power Lad killed seven armed men in twenty-eight Phases and nobody left.
Three things built the same day failed to produce that: `threat` says WHO
to shoot, not when to stop; violence-as-Presence scales with the
terrifier's PRE and his is 10; and `break_off_when_nothing_works` needs
landed blows, which at OCV 5 against DCV 6 arrive far slower than Power
Lad kills. **They die faster than they can learn.**

CASUALTIES ARE THE FAST SIGNAL. Watching half your side torn apart in two
Turns is what actually breaks a group, and nothing read it.

A SIDE, NOT A MAN. HERO gives an individual no morale stat --- PRE is the
stat, and 6E2 p.140 says so outright: Howler's "demoralized henchmen are
about to run" is fixed with a Presence Attack, not a morale roll. A side
is the thing that routs, and the book has no opinion about it because a
side is not a character. So this is judgement throughout, and the tiers
are the ones `masscombat.UnitMorale` already names rather than a sixth
vocabulary invented here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.masscombat import UnitMorale
from kirby_combat.morale import holds_fast, side_morale
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_engine,
)
from kirby_combat.side import Side


class _Log:
    def __init__(self, events=()):
        self.event_log = list(events)


def _base() -> dict:
    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _futile(who: str, at: str) -> list:
    d = ActionDeclared(**_base(), combatant_id=who, action_type="attack",
                       targets=[at])
    r = ActionResolved(**_base(), declaration_event_id=d.id,
                       result_payload={"hit": True, "body_dealt": 0,
                                       "stun_dealt": 0, "target_id": at})
    return [d, r]


def _man(id_, *, down=False):
    c = fighter(id_, side=Side.named("law"), armed=True,
                stun=0 if down else 40)
    return c


# ---- Casualties, the fast signal ----

def test_a_side_that_has_lost_nobody_is_fresh():
    men = [_man("a"), _man("b"), _man("c"), _man("d")]
    assert side_morale(_Log(), men) is UnitMorale.FRESH


def test_one_loss_in_four_is_steady():
    """Men die in fights. One is not a rout."""
    men = [_man("a", down=True), _man("b"), _man("c"), _man("d")]
    assert side_morale(_Log(), men) is UnitMorale.STEADY


def test_a_third_down_is_shaken():
    men = [_man("a", down=True), _man("b", down=True), _man("c"), _man("d"),
           _man("e"), _man("f")]
    assert side_morale(_Log(), men) is UnitMorale.SHAKEN


def test_half_the_side_down_is_routing():
    """The Earps at Turn 2: Virgil and Wyatt gone of four. That is the
    moment they should have left the lot, and did not."""
    men = [_man("virgil", down=True), _man("wyatt", down=True),
           _man("morgan"), _man("doc")]
    assert side_morale(_Log(), men) is UnitMorale.ROUTING


def test_almost_everyone_down_is_broken():
    men = [_man("a", down=True), _man("b", down=True), _man("c", down=True),
           _man("d")]
    assert side_morale(_Log(), men) is UnitMorale.BROKEN


# ---- Futility, the slow signal, stacking on top ----

def test_futility_costs_a_side_one_tier():
    """Losing a man is bad; losing a man to something your bullets bounce
    off is worse, and the side has watched both."""
    men = [_man("a", down=True), _man("b"), _man("c"), _man("d")]
    events = _futile("b", "monster") + _futile("c", "monster") + _futile("d", "monster")
    assert side_morale(_Log(), men) is UnitMorale.STEADY
    assert side_morale(_Log(events), men) is UnitMorale.SHAKEN


def test_futility_alone_does_not_rout_an_unhurt_side():
    """A side that has lost nobody is not routing because one enemy is
    armoured. It has a problem, not a crisis."""
    men = [_man("a"), _man("b"), _man("c"), _man("d")]
    events = _futile("a", "monster") + _futile("b", "monster") + _futile("c", "monster")
    assert side_morale(_Log(events), men) is UnitMorale.STEADY


def test_morale_never_falls_below_broken():
    men = [_man("a", down=True), _man("b", down=True), _man("c", down=True)]
    events = _futile("a", "m") + _futile("b", "m") + _futile("c", "m")
    assert side_morale(_Log(events), men) is UnitMorale.BROKEN


# ---- Who breaks with it ----

def test_overconfidence_keeps_a_man_in_a_fight_his_side_has_lost():
    """PeterB: morale "can also be mitigated by psych comps -- like
    overconfidence". The side breaks; WHICH men break with it depends on
    who they are, and a man who cannot conceive of losing is still
    standing there.

    Our judgement, and the reverse of the book's: 6E2 p.138 prices a
    psychological complication as a BONUS to an attack that plays to it.
    Nothing in HERO says Overconfidence resists a rout; it follows from
    what the complication MEANS.
    """
    proud = _man("frank")
    proud.hero.complications = [_Raw("PSYCHOLOGICALLIMITATION", "Overconfidence")]
    assert holds_fast(proud)


def test_an_ordinary_man_does_not_hold_fast():
    assert not holds_fast(_man("tom"))


def test_an_unrelated_complication_does_not_keep_him():
    plain = _man("doc")
    plain.hero.complications = [_Raw("HUNTED", "Hunted by the Clantons")]
    assert not holds_fast(plain)


class _Raw:
    def __init__(self, xmlid, input_text=""):
        self.xmlid = xmlid
        self.input = input_text
        self.alias = "Psychological Complication"
        self.adder_string = ""
        self.adders = []
        self.name = ""
