"""The stat block is priced from one walk, and reads the same as many.

``characteristic_state`` walks the whole purchase tree to answer for a single
xmlid, so pricing a stat block walked it once per characteristic — about
eighteen times, with ``contribution_from_purchase`` running ~1,500 times per
read on a medium character. That is the combat AI's inner loop.

Caching is the wrong fix and both callers' docstrings say so: Drains, Aids and
identity flips have to compose live. Walking once for all of them keeps every
read fresh.

These pin the EQUIVALENCE, not the speed — a timing assertion would be flaky on
a shared machine, and the risk in this change was never that it stayed slow, it
was that the one-walk form answered differently.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import _STAT_XMLIDS, HeroCombatant
from tests.corpus import require_authored


@pytest.fixture(scope="module")
def hero():
    """Ravel: frameworks, duplicate xmlids, and a conditional purchase — the
    character whose walk this change is about. Resolved through
    ``tests.corpus`` and SKIPPED when unset: this suite commits no .hdc files,
    and a path into a maintainer's home is not shippable."""
    return HeroCombatant.from_hdc(require_authored("Ravel")).hero


def test_one_walk_answers_exactly_as_many_walks(hero):
    many = {x: hero.characteristic_state(x) for x in _STAT_XMLIDS}
    once = hero.characteristic_states(_STAT_XMLIDS)
    assert set(once) == set(many)
    for xmlid, state in many.items():
        assert once[xmlid].base == state.base
        assert ([(c.xmlid, c.delta, c.source_label, c.requires_hero_id)
                 for c in once[xmlid].contributions]
                == [(c.xmlid, c.delta, c.source_label, c.requires_hero_id)
                    for c in state.contributions])


def test_asking_for_one_is_the_same_call(hero):
    """``characteristic_state`` is the batch form with a single xmlid, so
    there is one walk to keep correct rather than two to keep in step."""
    assert hero.characteristic_states(["DEX"])["DEX"].contributions == \
        hero.characteristic_state("DEX").contributions


def test_a_characteristic_nobody_bought_still_gets_a_state(hero):
    state = hero.characteristic_states(["BODY"])["BODY"]
    assert state.xmlid == "BODY"
    assert state.base == hero.characteristic_value("BODY")


def test_the_stat_list_covers_what_the_block_reads():
    """A characteristic missing from _STAT_XMLIDS falls back to the per-xmlid
    walk — slower, never wrong — but the two drifting should still be visible."""
    from kirby_combat.hero_view import _CHARACTERISTIC_FOR_STAT

    assert set(_CHARACTERISTIC_FOR_STAT.values()) <= set(_STAT_XMLIDS)
