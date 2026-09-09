"""Men before buildings. The menu puts scenery at the bottom.

MEASURED at the O.K. Corral. Virgil Earp takes cover behind Fly's Studio,
where no Cowboy can be seen and so no offer against a Cowboy survives the
perception gate. Doctrine correctly declines, the fallback takes the first
legal offer --- and the first legal offer is `attack:construct:harwood-
interior`. The marshal of Tombstone spends his Phase shooting a house.

`LegalAction.targets_construct` was added for exactly this and says so:
"Terrain offers led the action list --- six of the first six entries in a
21-action menu --- while 'Flight toward <enemy>' sat at #18, so the picker
spent 8 of 19 real actions demolishing scenery. Used for PRESENTATION
ORDER only; the legal set is unchanged."

It was set in three places and read by the resolver to route damage. NOTHING
EVER ORDERED ON IT. The field described a fix that was never applied ---
the same shape as `compute_cover_level`, `PlanStep.target_id` and the rest.

So the `PhaseSituation` --- which IS the presentation, where enumeration is
the legal set --- offers the same actions with scenery last. The legal set is
untouched, which is the whole claim --- a wagon is still a thing you may
throw and a wall is still a thing you may break, and `throw_something_heavy`
and `smash_cover` still find them. They are simply no longer what a fighter
does by default when he cannot think of anything better.
"""
from __future__ import annotations

import pytest

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import FirstLegalChooser, PhaseSituation


def _offer(action_id, kind, target_id, *, construct=False):
    return LegalAction(action_id=action_id, kind=kind, target_id=target_id,
                       power_xmlid=None, power_name=None, summary=action_id,
                       targets_construct=construct)


class _Guy:
    id = "virgil"
    hero = None


def test_the_fallback_shoots_a_man_before_a_house():
    """Virgil's actual menu, in its actual order."""
    menu = [_offer("attack:construct:harwood", "attack", "harwood", construct=True),
            _offer("attack:construct:flys", "attack", "flys", construct=True),
            _offer("attack:billy:9", "attack", "billy")]
    situation = PhaseSituation(actor=_Guy(), menu=menu)
    assert FirstLegalChooser().choose(situation) == "attack:billy:9"


def test_a_menu_of_nothing_but_scenery_still_offers_it():
    """The legal set is unchanged --- when a wall is all there is, a wall
    is what he hits. This is Virgil behind Fly's Studio with the Cowboys
    unseen, and breaking the wall he is hiding behind is a real option."""
    menu = [_offer("attack:construct:harwood", "attack", "harwood", construct=True)]
    situation = PhaseSituation(actor=_Guy(), menu=menu)
    assert FirstLegalChooser().choose(situation) == "attack:construct:harwood"


def test_order_among_scenery_is_untouched():
    menu = [_offer("attack:construct:a", "attack", "a", construct=True),
            _offer("attack:construct:b", "attack", "b", construct=True)]
    assert [a.action_id for a in PhaseSituation(actor=_Guy(), menu=menu).ordered_menu] == \
        ["attack:construct:a", "attack:construct:b"]


def test_order_among_people_is_untouched():
    """A stable partition, not a sort. Everything the enumerator decided
    about relative order among real offers survives."""
    menu = [_offer("dodge", "dodge", None),
            _offer("attack:construct:a", "attack", "a", construct=True),
            _offer("attack:billy:9", "attack", "billy"),
            _offer("disengage", "disengage", None)]
    assert [a.action_id for a in PhaseSituation(actor=_Guy(), menu=menu).ordered_menu] == \
        ["dodge", "attack:billy:9", "disengage", "attack:construct:a"]


def test_an_empty_menu_is_still_refused():
    with pytest.raises(Exception):
        FirstLegalChooser().choose(PhaseSituation(actor=_Guy(), menu=[]))
