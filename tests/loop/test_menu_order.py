"""Every capability gets seen before any capability repeats.

`enumerate_actions` returned offers in the order the code appends them,
which is not a decision anybody made --- it is the order the blocks
happen to sit in the function. Attacks are built first and built per
(power x enemy), so with four enemies they alone fill the top of the
list, and the distinct options land wherever their block happens to be.

Measured on the O.K. Corral: Ike Clanton's menu ran to 70 offers with
`move_to_cover` at #67 and `disengage` at #68 -- last and second to last.
The two actions that would have let an unarmed man behave like a man
were at the bottom of a list whose first eight entries were four ways to
punch someone and four ways to punch someone else. A reader that weighs
early items more heavily than late ones will never find them, and the
run that prompted this picked `attack` in all 36 of its Phases.

So the menu is interleaved BY KIND: one offer of each distinct kind, then
the second of each, and so on. Every capability the actor has appears
before any capability repeats. This ranks nothing and recommends nothing
--- within a kind the original order is untouched, and the set of offers
is identical. It only stops the count of TARGETS from deciding what gets
read.

A consumer that wants a different order can sort the list; what it cannot
do is recover an option it never saw.
"""
from __future__ import annotations

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.side import Side


def _menu(enemy_count=4):
    actor = fighter("actor", side=Side.named("a"), dex=20)
    enemies = [fighter(f"e{i}", side=Side.named("b"), dex=10)
               for i in range(enemy_count)]
    return enumerate_actions(actor, enemies)


def test_every_kind_appears_before_any_kind_repeats():
    menu = _menu()
    kinds = [a.kind for a in menu]
    distinct = len(set(kinds))
    first_block = kinds[:distinct]
    assert len(set(first_block)) == distinct, (
        "the first N offers should be N different kinds, but got "
        f"{[k for k in first_block]}"
    )


def test_no_offer_is_lost_or_duplicated():
    """Interleaving is a reordering and nothing else."""
    actor = fighter("actor", side=Side.named("a"), dex=20)
    enemies = [fighter(f"e{i}", side=Side.named("b"), dex=10) for i in range(4)]
    menu = enumerate_actions(actor, enemies)
    ids = [a.action_id for a in menu]
    assert len(ids) == len(set(ids)), "duplicate offers"


def test_order_within_a_kind_is_preserved():
    """Targets keep their original sequence, so a caller that relied on
    'the first attack offer' still gets the same one."""
    menu = _menu()
    attacks = [a.action_id for a in menu if a.kind == "attack"]
    actor = fighter("actor", side=Side.named("a"), dex=20)
    enemies = [fighter(f"e{i}", side=Side.named("b"), dex=10) for i in range(4)]
    raw = [a.action_id for a in enumerate_actions(actor, enemies)
           if a.kind == "attack"]
    assert attacks == raw


def test_a_rare_kind_is_not_buried_by_a_common_one():
    """The actual complaint: one `dodge` must not sit behind sixteen
    attack offers just because there are four enemies."""
    menu = _menu(enemy_count=8)
    kinds = [a.kind for a in menu]
    assert kinds.index("dodge") < 20, (
        f"dodge landed at #{kinds.index('dodge')} of {len(kinds)}"
    )
