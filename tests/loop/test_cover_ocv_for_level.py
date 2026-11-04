"""One reading of a cover level as an OCV penalty (6E2 p.45), shared by the
attack door, the menu, the Brief and the seats."""
from __future__ import annotations

from kirby_world.cover import cover_ocv_modifier

from kirby_combat.actions.recording import cover_ocv_for_level
from kirby_combat.threat_picture import view_named


def test_a_level_is_a_quarter_of_him():
    assert [cover_ocv_for_level(n) for n in range(5)] == [
        cover_ocv_modifier(0), cover_ocv_modifier(25), cover_ocv_modifier(50),
        cover_ocv_modifier(75), cover_ocv_modifier(100)]
    assert cover_ocv_for_level(2) == -2


def test_view_named_finds_by_name_or_xmlid():
    class P:
        def __init__(self, name, xmlid):
            self.name, self.xmlid = name, xmlid

    class E:
        attacks = [P("Storm", "ENERGYBLAST")]

    assert view_named(E(), "Storm") is E.attacks[0]
    assert view_named(E(), "ENERGYBLAST") is E.attacks[0]
    assert view_named(E(), "Flash") is None
