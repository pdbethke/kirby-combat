"""What terrain is made of, and how hard it is to break — 6E2 p172-173.

6E2 p172 states the rule: an object has a PD, an ED and a BODY total; an
attack's BODY less the object's appropriate defense reduces the object's
BODY; objects have no STUN. Defenses are Resistant unless the table prints
them in parentheses, which marks Normal Defense -- it does not apply
against Killing damage.

The table on p173 is keyed by OBJECT KIND, not by material: it prints
"Brick wall", not "brick". That is the right shape for terrain, because an
imported map has walls and doors rather than materials.

CITATION WARNING. Three places in this codebase have cited this rule
wrongly, in two different ways: `MATERIAL_DEFAULTS` said 6E2 p152 (which is
electricity and chemicals) and the destructible-terrain spec said 6E2
p176-177 (improvised weapons). If you are checking these numbers, p173 is
the page.

Rows whose BODY the book gives as a range or open-ended ("City gates,
large/heavy, BODY 20+") are deliberately omitted rather than pinned to an
invented value.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectDurability:
    """One row of the Objects Table.

    `resistant` False reproduces the book's parenthesised defenses: the
    value applies against Normal damage and not against Killing.
    """
    pd: int
    ed: int
    body: int
    resistant: bool = True


#: 6E2 p173, Objects Table -- the walls and doors a map import needs.
OBJECT_DURABILITY: dict[str, ObjectDurability] = {
    # Walls
    "armored wall":             ObjectDurability(13, 18, 7),
    "brick wall":               ObjectDurability(5, 10, 3),
    "concrete wall":            ObjectDurability(6, 10, 5),
    "home inside wall":         ObjectDurability(3, 3, 3),
    "home outside wall":        ObjectDurability(4, 6, 3),
    "reinforced concrete wall": ObjectDurability(8, 10, 5),
    "spaceship interior wall":  ObjectDurability(8, 8, 6),
    "wooden wall":              ObjectDurability(4, 3, 3),
    # Doors
    "airlock door":             ObjectDurability(8, 12, 7),
    "city gates, small":        ObjectDurability(5, 8, 10),
    "exterior wood door":       ObjectDurability(4, 4, 3),
    "interior spaceship door":  ObjectDurability(6, 6, 4),
    "interior wood door":       ObjectDurability(2, 2, 3),
    "large vault door":         ObjectDurability(16, 24, 9),
    "metal fire door":          ObjectDurability(5, 5, 5),
    "safe door":                ObjectDurability(10, 15, 9),
    # Glazing -- parenthesised in the book, so Normal Defense.
    "glass":                    ObjectDurability(1, 1, 1, resistant=False),
    "reinforced glass":         ObjectDurability(2, 2, 1, resistant=False),
}
