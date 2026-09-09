"""Doctrine plans against the men the menu will actually let it act on.

MEASURED. Over 25 seeded O.K. Corral runs, 142 of 638 decisions (22%) fell
through the whole tactic catalogue to `FirstLegalChooser`; Virgil Earp's
own rate was 51%, the worst in the fight. The probe:

    tom_mclaury fell through, then took attack:morgan_earp:1289203311469
      dodge_under_fire   wants wait            at None          on menu: False
      fight_from_cover   wants move_to_cover   at None          on menu: False
      fight_from_cover   wants attack          at virgil_earp   on menu: False
      sustained_fire     wants attack          at virgil_earp   on menu: False
      smash_cover        wants attack_construct at virgil_earp  on menu: False
      push_when_winning  wants attack          at virgil_earp   on menu: False

Every tactic named `virgil_earp`, and no offer against Virgil was on the
menu --- he is behind Fly's Studio, a LOS-blocking wall, and the perception
gate correctly drops every offer against a man you cannot see. Doctrine
planned six times against somebody it had no business knowing the position
of, produced six unexecutable plans, and fell through.

The engine already decided this question ON THE MENU: perception governs
combat, an AI cannot target an enemy it cannot perceive. The `Situation`
handed to the catalogue never learned it. So this does not re-derive
perception --- it reads the menu, which has already applied it, along with
range, reach, ammunition and everything else.

That also keeps the ONE case where an unperceived enemy is still fair game:
an adjacent HtH offer survives the gate marked `blind`, stays on the menu,
and so stays a man you may plan against.

`Situation.enemies` is the list; `PhaseSituation.enemies` (the brief, the
roster, morale, the count of who is still standing) is untouched, because
those are asking a different question --- who is in this fight, not who can
I hit.
"""
from __future__ import annotations

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation


class _Guy:
    def __init__(self, ident):
        self.id = ident
        self.hero = None


def _offer(action_id, kind, target_id, **kw):
    return LegalAction(action_id=action_id, kind=kind, target_id=target_id,
                       power_xmlid=None, power_name=None, summary=action_id, **kw)


def _situation(menu, enemies):
    return PhaseSituation(actor=_Guy("tom"), menu=menu,
                          enemies=[_Guy(e) for e in enemies])


def test_a_man_no_offer_names_is_not_planned_against():
    """Virgil is behind the studio wall: nothing on the menu touches him."""
    menu = [_offer("attack:morgan:99", "attack", "morgan"),
            _offer("wait", "wait", None)]
    tactical = _situation(menu, ["morgan", "virgil"]).tactical_situation()
    assert [e.id for e in tactical.enemies] == ["morgan"]


def test_an_unseen_man_you_can_still_swing_at_is_planned_against():
    """The blind-HtH carve-out: the gate keeps an adjacent HtH offer against
    an enemy the actor cannot perceive, so he stays a target."""
    blind = _offer("strike:virgil", "strike", "virgil")
    blind.blind = True
    tactical = _situation([blind], ["virgil"]).tactical_situation()
    assert [e.id for e in tactical.enemies] == ["virgil"]


def test_scenery_does_not_make_a_man_a_target():
    """`attack_construct` offers are keyed by WALL id. If a wall were ever
    named the same as a fighter, it must not put him back on the list."""
    menu = [_offer("attack_construct:virgil", "attack_construct", "virgil",
                   targets_construct=True)]
    tactical = _situation(menu, ["virgil"]).tactical_situation()
    assert tactical.enemies == []


def test_complications_follow_the_same_list():
    """`enemy_complications` is keyed off the same enemies; a man who is not
    a target should not be carried there either."""
    menu = [_offer("attack:morgan:99", "attack", "morgan")]
    tactical = _situation(menu, ["morgan", "virgil"]).tactical_situation()
    assert set(tactical.enemy_complications) == {"morgan"}


def test_an_empty_menu_leaves_the_enemies_alone():
    """A caller that builds a Situation with no menu at all --- the tests
    and `a_phase_written_down` both do --- is not asserting that nobody is
    targetable. Filtering there would silently blank every enemy list."""
    tactical = _situation([], ["morgan", "virgil"]).tactical_situation()
    assert {e.id for e in tactical.enemies} == {"morgan", "virgil"}
