"""A tripped man with Acrobatics may keep his feet.

Trip itself is 6E2 p.67 (-1 OCV, no damage, target knocked prone). The SAVE
is not in the book: it is a house rule carried in from the consuming
application's Spec C section 3, and it is labelled as one in the resolver so
that deleting it is a one-line decision.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import FakeRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: `resolvers._attack_dice` draws to-hit 3d6, then damage (none, for a
#: maneuver that does none), then Hit Location 3d6 and the STUN Multiplier.
#: The save's 3d6 comes after all of them.
_LOCATION = [3, 3, 3]
_STUN_MULT = [1]


def _blast(source_id: str) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id, is_ranged=True,
    )


def _man(id: str, *, side, skills: dict[str, int] | None = None):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40,
        side=side, attacks=[_blast(f"{id}-eb")], skills=skills or {},
    )


def _fight(*, target_skills: dict[str, int] | None) -> CombatSession:
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=FakeRoller([]),
        combatants=[
            _man("brute", side=Side.named("villains")),
            _man("mark", side=Side.named("heroes"), skills=target_skills),
        ],
    ).start()


def _trip() -> LegalAction:
    return LegalAction(
        action_id="trip:mark", kind="trip", target_id="mark",
        power_xmlid=None, power_name=None, summary="trip",
        _attack_view=_blast("brute-eb"),
    )


def _resolve(session, roller):
    return resolve_chosen(
        session, session.combatants["brute"], _trip(),
        template=TEMPLATE, roller=roller,
    )


def _roller(to_hit: list[int], save: list[int] | None) -> FakeRoller:
    pool = [to_hit, _LOCATION, _STUN_MULT]
    if save is not None:
        pool.append(save)
    return FakeRoller(pool)


def test_a_successful_acrobatics_roll_keeps_feet():
    """Hit by a small margin, then make the roll: the man stays standing."""
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [1, 1, 1]))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    save = payload["acrobatics_save"]
    assert save is not None
    assert save["rolled"] is True
    assert save["roll"] == 3
    assert save["kept_feet"] is True
    # The penalty is the margin by which the Trip landed, never a bonus.
    assert save["target"] == 15 - max(0, resolved.result.to_hit.margin)
    assert payload["is_prone_after"] is False
    assert PRONE not in statuses_for(resolved.session, "mark")


def test_a_failed_roll_falls():
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [6, 6, 6]))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    assert payload["acrobatics_save"]["kept_feet"] is False
    assert payload["is_prone_after"] is True
    assert PRONE in statuses_for(resolved.session, "mark")


def test_a_man_without_acrobatics_simply_falls():
    """No skill, no roll: the payload says so rather than inventing a save."""
    session = _fight(target_skills=None)
    resolved = _resolve(session, _roller([4, 4, 4], None))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    assert payload["acrobatics_save"] is None
    assert payload["is_prone_after"] is True
    assert PRONE in statuses_for(resolved.session, "mark")


def test_a_missed_trip_rolls_no_save_at_all():
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([6, 6, 6], None))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is False
    assert payload["acrobatics_save"] is None
    assert payload["is_prone_after"] is False
    assert PRONE not in statuses_for(resolved.session, "mark")
