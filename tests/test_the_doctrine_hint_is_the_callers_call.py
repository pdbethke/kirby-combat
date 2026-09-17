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


# ---------------------------------------------------------------------------
# The caller's own plan, on the same page and under the same gate
# ---------------------------------------------------------------------------
#
# A caller with advice of its own -- a plan for this fight, written
# outside the engine -- used to have two choices: render the page and
# staple its lines on afterwards, or build a second page. Both make a
# second renderer, and a second renderer agrees with this one only until
# somebody edits one of them. `extra_doctrine` is the door: the lines go
# in where the page is built, under the heading that is already there.
#
# And they are advice, so they are under the same gate. An arm that
# removes the engine's doctrine and keeps somebody else's plan has not
# removed the doctrine.

PLAN = ["Fall back to the wagon and make them come to you  -> disengage"]


class _BriefWithNoDoctrineOfItsOwn(_Brief):
    @property
    def doctrine(self):
        return []


def _lines_under_the_heading(page: str) -> list[str]:
    body = page.split(HEADING + ", best first:")[1]
    out = []
    for line in body.splitlines()[1:]:
        if not line.strip():
            break
        out.append(line)
    return out


def test_the_extra_lines_come_after_the_engines_own():
    page = _brief().render(extra_doctrine=PLAN)
    assert _lines_under_the_heading(page) == [
        "  Get behind cover NOW  -> move_to_cover",
        f"  {PLAN[0]}",
    ]


def test_extras_alone_open_the_section():
    """No doctrine of its own is not a reason to drop the caller's."""
    page = _BriefWithNoDoctrineOfItsOwn(
        _brief()._situation).render(extra_doctrine=PLAN)
    assert HEADING in page
    assert _lines_under_the_heading(page) == [f"  {PLAN[0]}"]


def test_no_extras_and_no_doctrine_is_still_silence():
    page = _BriefWithNoDoctrineOfItsOwn(_brief()._situation).render()
    assert HEADING not in page


def test_a_caller_that_asked_for_no_doctrine_gets_no_extras_either():
    assert HEADING not in _brief().render(doctrine=False, extra_doctrine=PLAN)
    assert PLAN[0] not in _brief().render(doctrine=False, extra_doctrine=PLAN)


def test_the_env_override_removes_the_extras_too(monkeypatch):
    monkeypatch.setenv("KIRBY_BRIEF_NO_DOCTRINE", "1")
    page = _brief().render(doctrine=True, extra_doctrine=PLAN)
    assert HEADING not in page
    assert PLAN[0] not in page


def test_the_heading_appears_at_most_once():
    page = _brief().render(extra_doctrine=PLAN)
    assert page.count(HEADING) == 1
    assert _BriefWithNoDoctrineOfItsOwn(
        _brief()._situation).render(extra_doctrine=PLAN).count(HEADING) == 1


def test_nothing_else_on_the_page_changes():
    """The extras are the ONLY difference -- not a re-laid-out page."""
    plain = _brief().render().splitlines()
    with_plan = _brief().render(extra_doctrine=PLAN).splitlines()
    assert [line for line in with_plan if line != f"  {PLAN[0]}"] == plain
