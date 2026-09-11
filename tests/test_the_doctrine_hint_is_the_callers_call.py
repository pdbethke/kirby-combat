"""Who gets the doctrine hint is a property of the READER, not a global.

The page ends with "What your doctrine says, best first:" --- TacticChooser's
own ranked answer, eleven lines above the menu. Measured across three models
on the same five situations, removing it does NOT do one thing:

    corral, 6 fights        with hint    without
      a frontier model      4 kinds      5 kinds
      its small sibling     5 kinds      8 kinds
      a local 35B           5 kinds      5 kinds, but collapsed onto
                                         `attack` (4 -> 10 of 15) with
                                         `hide`, `disengage` and
                                         `move_to_cover` gone entirely,
                                         and `attack_construct` chosen
                                         twice by a side whose stated
                                         objective is to shoot the men
                                         and NOT the buildings.

So the hint narrows a capable model and holds a local one together. There is
no default that is right for both, which is exactly the shape of `Seat.vision`
--- ask the seat, not the environment.

`KIRBY_BRIEF_NO_DOCTRINE` stays, and stays able only to REMOVE: it is the
measurement harness's global override, and a switch that could also turn the
section back ON would make every A/B arm depend on which seat answered.
"""
from __future__ import annotations

from kirby_combat.brief import Brief
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation


class _Stats:
    ocv = dcv = 8
    omcv = dmcv = 5
    max_stun = max_body = max_end = 20
    str_ = con = 15
    dex = ego = int_ = 10
    pre = 15
    spd = 4
    pd = ed = 10
    rpd = red = 2


class _Actor:
    id = "virgil_earp"
    name = "Virgil Earp"
    max_stun = current_stun = 20
    max_body = current_body = 20
    max_end = current_end = 20
    hero = None
    side = None

    class state:
        current_stun = current_body = current_end = 20

    def combat_stats(self):
        return _Stats()


class _Brief(Brief):
    """The advice itself is `Brief.doctrine`'s business and has its own
    tests. This file is about the GATE, so the section is stubbed to a
    fixed line -- otherwise the test passes or fails on whether the
    tactics library happens to advise this stub actor."""

    @property
    def doctrine(self):
        return ["Get behind cover NOW  -> move_to_cover"]


def _brief():
    menu = [LegalAction(action_id="dodge", kind="dodge", target_id=None,
                        power_xmlid=None, power_name=None, summary="Dodge"),
            LegalAction(action_id="recover", kind="recover", target_id=None,
                        power_xmlid=None, power_name=None, summary="Recover")]
    return _Brief(PhaseSituation(actor=_Actor(), menu=menu, segment=12, turn=1))


HEADING = "What your doctrine says"


def test_the_hint_is_there_when_nobody_says_otherwise():
    assert HEADING in _brief().render()


def test_a_caller_can_ask_for_the_page_without_it():
    assert HEADING not in _brief().render(doctrine=False)


def test_a_caller_can_ask_for_it_explicitly():
    assert HEADING in _brief().render(doctrine=True)


def test_the_env_override_can_only_ever_remove(monkeypatch):
    """A seat that wants the hint must not be able to put it back while a
    measurement arm is running without it --- otherwise every arm depends
    on which seat answered."""
    monkeypatch.setenv("KIRBY_BRIEF_NO_DOCTRINE", "1")
    assert HEADING not in _brief().render()
    assert HEADING not in _brief().render(doctrine=True)


def test_the_menu_still_follows(monkeypatch):
    """Removing the hint must not take the actions with it."""
    page = _brief().render(doctrine=False)
    assert "[dodge]" in page and "[recover]" in page
