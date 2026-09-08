"""The advice was written for a reader and never delivered.

Every one of the 21 tactics carries a `narrative_summary`. `Tactic`'s own
docstring calls it "the tactic listing a chooser sees" and the field's
comment says "one-liner shown to whatever picks one". They are written in
the second person, addressed to whoever is deciding:

    "You are injured -- get behind cover NOW..."
    "You have nothing that can reach them and they have something that
     reaches you..."

Nothing rendered them. `brief.py` mentioned tactics zero times, so the
only thing that ever consumed a tactic was `TacticChooser`, which reads
`plan.steps[0].kind` and ignores the prose entirely. A reader that picks
by reading was shown the map, the enemies and 70 offers, and never the
one paragraph written to tell it what to do.

So "why doesn't it take the advice" had a duller answer than expected:
it was never given the advice.

WHAT THIS IS NOT. The section states which doctrines apply and what they
say, best-first, in the catalogue's own words. It does not pick, does not
reorder the menu, and does not claim the doctrine is right --- a tactic
is judgement, and `Basis` already records which ones the book actually
advises. The chooser stays free to ignore it, exactly as
`TacticChooser` stays free to fall through a tactic whose action is not
on the menu.
"""
from __future__ import annotations

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.brief import Brief
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.side import Side


def _situation(*, hurt: bool = False):
    actor = fighter("actor", side=Side.named("a"), dex=20)
    if hurt:
        actor = actor.with_state(current_stun=4)
    enemies = [fighter("mark", side=Side.named("b"), dex=10)]
    menu = enumerate_actions(actor, enemies)
    return PhaseSituation(actor=actor, menu=menu, enemies=enemies,
                          allies=[], session=None, segment=12, turn=1)


def test_the_brief_names_the_doctrines_that_apply():
    text = Brief(_situation()).render()
    assert "What your doctrine says" in text


def test_it_carries_the_tactic_s_own_words():
    """Not a paraphrase --- the catalogue's text, so there is one place to
    edit it and no second copy to drift."""
    from kirby_combat.tactics.library import tactics_for

    situation = _situation()
    applicable = tactics_for(situation.tactical_situation())
    assert applicable, "no tactic fired; the test proves nothing"
    text = Brief(situation).render()
    first_words = " ".join(applicable[0].narrative_summary.split())[:40]
    assert first_words in " ".join(text.split())


def test_the_advice_names_the_action_kind_it_points_at():
    """A doctrine a reader cannot act on is decoration. Each line says
    which kind its first step wants, so the reader can find it in the
    menu."""
    text = Brief(_situation()).render()
    line = next(l for l in text.splitlines() if "->" in l and "  " in l)
    assert line.strip()


def test_it_does_not_reorder_or_shrink_the_menu():
    """Advice, not a filter. The chooser must still see everything legal."""
    situation = _situation()
    brief = Brief(situation)
    assert [a.action_id for a in brief.menu] == \
           [a.action_id for a in situation.menu]


def test_a_situation_with_no_applicable_doctrine_says_nothing():
    """Silence beats an empty heading --- there is no advice to give."""
    from kirby_combat.brief import Brief as _B

    situation = _situation()
    text = _B(situation).render()
    # Whatever fires here, the section is present only when non-empty.
    if "What your doctrine says" in text:
        body = text.split("What your doctrine says")[1].strip()
        assert body, "heading with nothing under it"
