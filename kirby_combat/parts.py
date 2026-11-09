"""The parts of a purchase: the one place that knows where they are kept.

kirby-cost keeps a purchase's nested purchases in one of THREE lists,
depending on what the container is:

- ``sub_powers``: a framework's slots (Multipower, VPP, Elemental Control)
- ``objects``: a List's contents
- ``powers``: a Compound Power's parts
  (``kirby_cost/objects/powers/compound_power.py``)

Every walk over a build reads its children through ``parts_of``. Before
2026-11-09 eight walks read ``sub_powers`` alone, so anything bought inside a
Compound Power was invisible in combat. The corpus Agent of UNTIL's Blaster
Carbine is a Compound Power (Blast plus Combat Skill Levels), and the agent
fought with no attack at all. ``tests/test_compound_power_parts.py`` holds a
ratchet that fails on any new single-list walk.

``hero.powers`` (a build's SECTION) is not a part list; walks start there
and descend with ``parts_of``.
"""
from __future__ import annotations

from typing import Any

PART_LISTS: tuple[str, ...] = ("sub_powers", "objects", "powers")


def parts_of(purchase: Any) -> list[Any]:
    """The purchases directly inside ``purchase``, in list order: framework
    slots, then List contents, then Compound Power parts. Empty for a leaf.
    Not recursive; callers recurse and keep their own ``seen`` guard."""
    out: list[Any] = []
    for attr in PART_LISTS:
        nested = getattr(purchase, attr, None)
        if isinstance(nested, list):
            out.extend(nested)
    return out
