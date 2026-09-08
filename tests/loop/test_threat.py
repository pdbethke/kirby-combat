"""How dangerous is that one? --- threat, and why the lot ignored a monster.

Power Lad killed seven men in the O.K. Corral. Once `target_id` was
actually delivered to the chooser the Cowboys concentrated on him, and
the Earps started shooting the two UNARMED men who were running away ---
because `keep_range` names the enemy you most outrange, and being
harmless is exactly what makes you easy to outrange. Coherent doctrine,
and no notion of danger anywhere in it.

PeterB, 2026-09-08: *"there needs to be some kind of threat awareness"*
/ *"a high PRE would also draw attention"* / *"as well as PRE attacks"*.

TWO HALVES, WEIGHTED, because a fighter knows two different things.

WHAT HE CAN SEE STANDING THERE --- the menace floor. A seven-foot horror
with claws IS visibly dangerous before it does anything, and pretending
otherwise would make every fight start stupid. Read as damage classes
(6E1 p.97: a Killing die is worth three DCs against a Normal die's one)
plus PRE, which is the characteristic for exactly this and nothing else.

WHAT HE HAS WATCHED HIM DO --- observed harm, folded from the session's
own event log. This is the half that respects the anti-metagaming rule
perception already enforces: it counts what happened in front of him, not
what the character sheet says. A Presence Attack landing counts here too;
it is the loudest thing anybody in that lot could witness.

The floor means the men react in Phase 1. The observed half means they
react MORE once he has torn somebody apart, which is the behaviour the
benchmark was missing.
"""
from __future__ import annotations

from conftest import blast, fighter              # tests/loop/conftest.py
from kirby_combat.models import AttackPower
from kirby_combat.side import Side
from kirby_combat.tactics.base import Situation


def _claws(dice: int = 6) -> AttackPower:
    return AttackPower(
        xmlid="HKA", name="Rending and Tearing", damage_dice=dice,
        half_die=False, plus_one=False, damage_type="killing",
        defense_type="pd", range_m=0.0, uses_str=True, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=False, reach_m=1.0, source_id="hka",
    )


def _monster(id_="power_lad", pre: int = 40):
    from fixtures.synthetic_hero import synthetic_combatant
    c = synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=6, omcv=5, dmcv=5, spd=4, dex=20,
        ego=15, str_=40, con=20, pre=pre, rec=8, pd=2, ed=2, rpd=25, red=20,
        md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=10, max_end=40,
        current_stun=40, current_body=10, current_end=40,
        side=Side.solo(id_), attacks=[_claws()],
    )
    return c


def _gunman(id_="wyatt"):
    return fighter(id_, side=Side.named("law"), armed=True)


def _unarmed(id_="ike"):
    return fighter(id_, side=Side.named("cow"), armed=False)


def _threat(actor, enemies, session=None):
    return Situation(actor=actor, allies=[], enemies=list(enemies),
                     current_segment=12, turn=1, session=session).threat


# ---- The menace floor: what you can see before anything happens ----

def test_a_monster_reads_as_more_dangerous_than_a_gunman():
    """Phase 1, nothing has happened yet, and the men can still see him."""
    threat = _threat(_gunman("doc"), [_monster(), _gunman("frank")])
    assert threat["power_lad"] > threat["frank"]


def test_an_unarmed_man_is_the_least_dangerous_thing_in_the_lot():
    """The defect this exists to stop: Ike Clanton, running away, was the
    preferred target of three armed lawmen."""
    threat = _threat(_gunman("doc"), [_monster(), _gunman("frank"), _unarmed()])
    assert threat["ike"] == min(threat.values())
    assert threat["ike"] < threat["frank"]


def test_a_killing_attack_outweighs_a_normal_one_of_the_same_dice():
    """6E1 p.97: a Killing die is three damage classes, a Normal die one.
    Counting dice alone would call a 6d6 blast and 6d6 of claws equal."""
    killer = fighter("killer", side=Side.named("x"), armed=False)
    killer.attacks.append(_claws(3))
    blaster = fighter("blaster", side=Side.named("x"), armed=False)
    blaster.attacks.append(blast("b", dice=3))
    threat = _threat(_gunman(), [killer, blaster])
    assert threat["killer"] > threat["blaster"]


def test_presence_draws_attention_on_its_own():
    """PRE is the characteristic for being imposing, and nothing else."""
    loud = _monster("loud", pre=40)
    quiet = _monster("quiet", pre=10)
    threat = _threat(_gunman(), [loud, quiet])
    assert threat["loud"] > threat["quiet"]


# ---- Observed harm: what you watched him do ----

def test_a_man_who_has_killed_someone_reads_as_worse_than_one_who_has_not():
    """The half that makes the lot LEARN. Two identical monsters; one of
    them has already torn a man apart in front of you.

    Built as the real DECLARED + RESOLVED pair the resolvers emit, joined
    by `declaration_event_id`, because that join is the thing being
    tested: the resolution carries the damage and the declaration carries
    who did it, and reading only resolutions gives a log full of harm
    nobody committed."""
    a, b = _monster("seen"), _monster("unseen")
    threat = _threat(_gunman(), [a, b],
                     session=_FakeSession(_did_harm("seen", body=19, stun=30)))
    assert threat["seen"] > threat["unseen"]


def test_a_landed_presence_attack_counts_as_harm_witnessed():
    """PeterB: PRE attacks draw attention. 6E2 p.137 makes one an attack
    on everybody who can hear it, and the engine already records it."""
    from kirby_combat.session.events import PresenceApplied

    a, b = _monster("roarer"), _monster("silent")
    log = [PresenceApplied(**_base(), attacker_id="roarer",
                           target_id="wyatt", tier="PRE+30", segments=4)]
    threat = _threat(_gunman(), [a, b], session=_FakeSession(log))
    assert threat["roarer"] > threat["silent"]


def test_no_session_means_the_floor_alone_and_no_crash():
    """Most fights are driven without a session in hand. Threat must still
    be answerable from what is visible."""
    threat = _threat(_gunman(), [_monster(), _unarmed()])
    assert threat["power_lad"] > threat["ike"]


def _base() -> dict:
    """The five fields every event carries."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.events import make_author_engine

    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _did_harm(who: str, *, body: int, stun: int) -> list:
    """The pair a resolver emits when somebody hurts somebody."""
    from kirby_combat.session.events import ActionDeclared, ActionResolved

    declared = ActionDeclared(**_base(), combatant_id=who,
                              action_type="attack", targets=["virgil"])
    resolved = ActionResolved(**_base(), declaration_event_id=declared.id,
                              result_payload={"body_dealt": body,
                                              "stun_dealt": stun})
    return [declared, resolved]


class _FakeSession:
    def __init__(self, event_log):
        self.event_log = event_log


# ---- The doctrine that was gunning down fleeing unarmed men ----

def test_keep_range_picks_the_dangerous_melee_enemy_not_the_first_one():
    """`keep_range` is "deny the melee threat their attack" -- and it took
    `melee_enemies[0]`, first in roster order.

    Both Ike Clanton and Power Lad are melee-only, so at the O.K. Corral
    the Earps kept their distance from the UNARMED man running away while
    a monster closed on them. Being harmless is exactly what makes you
    easy to outrange; the tactic needs to know which melee enemy is worth
    denying.
    """
    from kirby_combat.tactics.library import all_tactics

    tactic = next(t for t in all_tactics() if t.name == "keep_range")
    # Ike first, deliberately: roster order is what used to decide.
    situation = Situation(actor=_gunman("doc"), allies=[],
                          enemies=[_unarmed("ike"), _monster("power_lad")],
                          current_segment=12, turn=1)
    assert tactic.applicable(situation)
    assert tactic.execute(situation).steps[0].target_id == "power_lad"
