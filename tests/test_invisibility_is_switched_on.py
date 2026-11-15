"""Invisibility is on only when he turns it on (or it is Persistent).

`concealment.is_invisible` read the BUILD, so anyone who owned Invisibility
was unseen all fight. Ravel's "Active Camoflage" is a 35-point slot in his
Multipower; recorded 2026-11-15 against Bokor with the slot EMPTY, Bokor
could perceive him only at arm's length and was offered nothing but Grab and
Trip --- no Mojo Hand, no powder, no Presence Attack --- for the whole fight.

6E2 p.20: turning a power on is a Zero Phase Action, once a Phase; 6E1
p.129-130: a Constant power is kept up on END each Phase (`kept_up`).
"""
from __future__ import annotations

from kirby_combat.concealment import is_invisible
from kirby_combat.switched_powers import Switched

from tests.test_desolidification import _menu, _ravel, _session, _take

CAMOFLAGE = "1669688064786"      # Invisibility, 35 points
STRING_STORM = "1648350992201"


def _bokor_kinds_at_ravel(s):
    return {a.kind for a in _menu(s, "bokor") if a.target_id == "ravel"}


def test_owning_it_in_an_empty_slot_hides_nobody():
    s, _ = _session(_ravel(**{STRING_STORM: 45}))
    assert not is_invisible(s, s.combatants["ravel"])
    assert "presence_attack" in _bokor_kinds_at_ravel(s)


def test_a_slot_holding_it_offers_to_turn_it_on_and_nothing_hides_him_yet():
    s, _ = _session(_ravel(**{CAMOFLAGE: 35}))
    assert not is_invisible(s, s.combatants["ravel"])
    assert Switched.INVISIBLE.terms.on_kind in {a.kind for a in _menu(s, "ravel")}


def test_turned_on_he_is_invisible_and_can_turn_it_off():
    s, template = _session(_ravel(**{CAMOFLAGE: 35}))
    s = _take(s, template, "ravel", Switched.INVISIBLE.terms.on_kind)
    assert is_invisible(s, s.combatants["ravel"])
    assert Switched.INVISIBLE.terms.off_kind in {a.kind for a in _menu(s, "ravel")}
    s = _take(s, template, "ravel", Switched.INVISIBLE.terms.off_kind)
    assert not is_invisible(s, s.combatants["ravel"])
