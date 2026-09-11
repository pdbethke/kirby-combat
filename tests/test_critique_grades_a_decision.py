"""A decision can be WRONG, and until now nothing here said so.

`docs/gaps.md` ends on the admission: "It does not settle that the choices
are GOOD ... nothing here grades a decision as right or wrong." Every
measurement so far counts VARIETY -- how many of 62 kinds get chosen, which
rule paths fire -- which scores a fighter who shoots the buildings as
pleasing breadth.

These graders are DETERMINISTIC and they only ever say "wrong", never
"right". A Phase with no finding is not endorsed; it is merely not
indictable. That asymmetry is deliberate: whether an attack was the BEST
choice is judgement, and this file has none. Whether it could not possibly
have worked is arithmetic.

They grade doctrine too. If `TacticChooser` ever picks a futile attack,
that is an engine finding, not a chooser finding.

NO RE-DERIVATION. Futility asks the engine's own `compute_defense` and
`hit_location.killing_damage` / `normal_damage` what a BEST-POSSIBLE roll
would get through. A second damage calculation here would drift from the
resolver, and would do it silently, in the direction of whatever the rules
last looked like.
"""
from __future__ import annotations

from kirby_combat.critique import critique
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.models import AttackPower, StatBlockCombatant


def _power(dice: int, *, killing: bool = False) -> AttackPower:
    return AttackPower(
        xmlid="RKA" if killing else "EB", name="Colt" if killing else "Blast",
        damage_dice=dice, half_die=False, plus_one=False,
        damage_type="killing" if killing else "normal",
        defense_type="pd", range_m=100.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=True,
    )


def _fighter(id: str, *, pd: int = 10, rpd: int = 2,
             stun: int = 20, body: int = 20, end: int = 20):
    """A REAL `StatBlockCombatant`, not a stub.

    `compute_defense` reads `.defenses`, `.pd` and `.knockback_resistance`
    off the combatant itself. A hand-rolled double carrying only
    `combat_stats()` satisfied the grader's own code and then failed
    inside the engine -- which is the whole argument for building the
    real type here.
    """
    return StatBlockCombatant(
        id=id, name=id.title(), ocv=8, dcv=8, omcv=5, dmcv=5, spd=4,
        dex=10, ego=10, str_=15, con=15, pre=15, rec=5,
        pd=pd, ed=pd, rpd=rpd, red=rpd, md=0, power_defense=0,
        flash_defense=0, max_stun=20, max_body=20, max_end=20,
        current_stun=stun, current_body=body, current_end=end,
    )


def _attack(target_id: str, power: AttackPower, *, construct: bool = False):
    return LegalAction(
        action_id=f"attack:{target_id}:src1", kind="attack", target_id=target_id,
        power_xmlid=power.xmlid, power_name=power.name,
        summary=f"Shoot {target_id}", _attack_view=power,
        targets_construct=construct,
    )


def _situation(menu, enemies):
    return PhaseSituation(actor=_fighter("virgil"), menu=menu,
                          enemies=enemies, segment=12, turn=1)


def _kinds(situation, action_id) -> set[str]:
    return {f.kind for f in critique(situation, action_id)}


# ---- futility -------------------------------------------------------

def test_a_blast_that_cannot_scratch_him_is_futile():
    """1d6 normal, best roll 6: 6 STUN and 2 BODY, against 30 PD. Zero
    gets through on the best roll the dice can produce -- so zero gets
    through on every roll, forever. This is the "futile 1d6 blast" the
    Krackle defect list has carried as an open item."""
    mark = _fighter("mark", pd=30, rpd=30)
    a = _attack("mark", _power(1))
    assert "futile" in _kinds(_situation([a], [mark]), a.action_id)


def test_an_attack_that_can_get_through_is_not_futile():
    mark = _fighter("mark")          # 10 PD
    a = _attack("mark", _power(12))
    assert "futile" not in _kinds(_situation([a], [mark]), a.action_id)


def test_a_killing_attack_is_judged_against_RESISTANT_defense_only():
    """6E: a Killing Attack's BODY is stopped by resistant defense alone.
    2 rPD against 2d6 killing is not futile even though 30 total PD would
    be -- grading it on total defense would call a lethal shot harmless."""
    mark = _fighter("mark")          # pd 10 / rpd 2
    a = _attack("mark", _power(2, killing=True))
    assert "futile" not in _kinds(_situation([a], [mark]), a.action_id)


def test_a_borderline_attack_is_not_futile():
    """Exactly enough to get one point through on a perfect roll is a bad
    bet, not an impossible one. The grader says WRONG, never UNWISE."""
    mark = _fighter("mark")          # 10 PD; 2d6 normal maxes at 12 STUN
    a = _attack("mark", _power(2))
    assert "futile" not in _kinds(_situation([a], [mark]), a.action_id)


# ---- scenery --------------------------------------------------------

def test_shooting_a_wall_while_a_man_is_on_the_menu_is_a_finding():
    """`PhaseSituation.ordered_menu` already puts MEN BEFORE BUILDINGS and
    names the case: "the marshal of Tombstone spends his Phase shooting a
    house". Ordering made it less likely; nothing recorded it when it
    happened anyway."""
    mark = _fighter("mark")
    wall = _attack("harwood-interior", _power(6), construct=True)
    man = _attack("mark", _power(6))
    assert "scenery" in _kinds(_situation([wall, man], [mark]), wall.action_id)


def test_shooting_a_wall_when_a_wall_is_all_there_is_is_not_a_finding():
    """The engine's own words: "when a wall is all there is, a wall is
    what he hits". Flagging that would indict the actor for the menu."""
    wall = _attack("harwood-interior", _power(6), construct=True)
    assert "scenery" not in _kinds(_situation([wall], []), wall.action_id)


def test_a_targetless_maneuver_is_not_a_man():
    """REGRESSION, and the grader's first false positive.

    Pointed at doctrine on the street benchmark this reported three
    Phases of "shooting a house while a man was on the menu". The trace
    said otherwise: the only non-scenery attack offer was
    `haymaker` with `target_id=None` -- a maneuver naming nobody -- and
    the tactic that fired was `smash_cover`, whose whole basis is that
    "cover the enemy is using is worth more destroyed than ignored".

    Doctrine was right and the grader was wrong. An offer only counts as
    a man if it NAMES one.
    """
    hay = LegalAction(action_id="haymaker", kind="haymaker", target_id=None,
                      power_xmlid=None, power_name=None, summary="Haymaker")
    wall = _attack("harwood-interior", _power(6), construct=True)
    assert "scenery" not in _kinds(_situation([wall, hay], []), wall.action_id)


def test_an_offer_naming_someone_not_in_the_fight_is_not_a_man():
    """A target_id that matches no combatant is not evidence a man was
    available -- the same failure one step further on."""
    ghost = _attack("nobody-here", _power(6))
    wall = _attack("harwood-interior", _power(6), construct=True)
    assert "scenery" not in _kinds(_situation([wall, ghost], []), wall.action_id)


def test_shooting_the_man_is_never_scenery():
    mark = _fighter("mark")
    man = _attack("mark", _power(6))
    assert _kinds(_situation([man], [mark]), man.action_id) == set()


# ---- wasted Phase ---------------------------------------------------

def test_recovering_at_full_health_wastes_the_phase():
    """A Recover takes the whole Phase (6E2 p.58) and a man at 20/20/20
    buys nothing with it."""
    rec = LegalAction(action_id="recover", kind="recover", target_id=None,
                      power_xmlid=None, power_name=None, summary="Recover")
    assert "wasted" in _kinds(_situation([rec], []), rec.action_id)


def test_recovering_when_hurt_is_not_wasted():
    hurt = PhaseSituation(actor=_fighter("virgil", stun=4, body=12, end=2),
                          menu=[], segment=12, turn=1)
    rec = LegalAction(action_id="recover", kind="recover", target_id=None,
                      power_xmlid=None, power_name=None, summary="Recover")
    hurt.menu = [rec]
    assert "wasted" not in _kinds(hurt, rec.action_id)


# ---- the contract ---------------------------------------------------

def test_an_action_not_on_the_menu_is_refused():
    """A grader that silently returns "no findings" for an id it never saw
    would report a clean sweep for a run whose ids it could not match."""
    import pytest

    with pytest.raises(KeyError):
        critique(_situation([], []), "attack:nobody:src1")
