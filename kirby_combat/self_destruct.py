"""When a man sets off a power he bought Self Only (squad tactics spec, 7).

A damaging power bought with the custom limitation "Self Only"
(`power_modifiers.CustomLimitation`; the Destroid's "Self Destruct System",
RKA 8d6, 1 Charge which Never Recovers) affects only its user. It is not
offered as an ordinary attack (`power_modifiers.unbuilt_reasons`, since
0.31.0); it is offered as `self_destruct`, and only as a last resort, in one
of two cases. A Self Only Aid or Healing is not a self-destruct and is not
touched: only a damaging attack power (`AttackPower.self_only`) is read.

(a) CAPTURE IS IMMINENT: he is Entangled (physically or by Mental Paralysis,
    both Entangles, 6E1 p.219) or Grabbed (6E2 p.64). He was told to avoid
    capture, and a man held is a man about to be taken.

(b) HE JUDGES THE SQUAD IS LOST: he fights in a squad (`squads.py`) whose
    casualty fraction, counted the way `morale.side_morale` counts a side
    (`morale.casualty_fraction`), is above one half, and he makes an INT
    Roll. PeterB: "thats an int role". The roll is a Characteristic Roll,
    9 + INT/5 or less on 3d6 (6E1 p.14, `kirby_cost.engine.rolls`), made at
    the top of his own Phase, at most once a Phase, and only when it could
    matter: the squad is lost and he has a Self Only damaging power with a
    use left. It is recorded as `SelfDestructRolled`; a made roll puts the
    offer on his menu for that Phase. A man in no squad has only (a). There
    is no fallback to his side. RULING: one half is our threshold (the
    spec's call, not the book's), the same line at which `morale` calls a
    side ROUTING.

RULING, the third clause of the spec's capture trigger ("at or under 0 STUN
with an enemy in reach") is NOT built. A man at or under 0 STUN is Knocked
Out (6E1 p.421) and takes no Action, so an offer to him could never be
taken; `enumerate_actions` already offers a downed man nothing.

The offer is spent from the power's Charges like any other use
(`charges.spent_charges`), so a used-up Self Destruct System is not offered
again; it resolves through `actions/self_destruct.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession

SELF_DESTRUCT = "self_destruct"

#: The squad is lost when more than this fraction of it is down or gone.
#: RULING (the spec's call, see above): half.
SQUAD_LOST_ABOVE = 0.5


def self_destruct_powers(actor: Any, spent: dict[str, int]) -> list[Any]:
    """His Self Only damaging powers with a use left, in the order he has them."""
    from kirby_combat.charges import has_charges_left
    from kirby_combat.enumeration import source_power_of

    return [
        ap for ap in actor.attacks
        if getattr(ap, "self_only", False) and int(ap.damage_dice) > 0
        and has_charges_left(source_power_of(actor, ap), spent)
    ]


def capture_is_imminent(session: "CombatSession", actor_id: str) -> bool:
    """Is he Entangled or Grabbed (trigger a)?"""
    from kirby_combat.actions.entangle import Entangle
    from kirby_combat.actions.grab import Grab

    return (Entangle.is_entangled(session, actor_id)[0]
            or Grab.is_grabbed(session, actor_id)[0])


def _squad_of(session: "CombatSession", actor_id: str):
    from kirby_combat.side import Side
    from kirby_combat.squads import squads_of

    me = session.combatants[actor_id]
    for squad in squads_of(session):
        if squad.side == Side.of(me).id and actor_id in squad.member_ids:
            return squad
    return None


def squad_casualty_fraction(session: "CombatSession", actor_id: str) -> float | None:
    """The casualty fraction of his squad, or None for a man in no squad."""
    from kirby_combat.morale import casualty_fraction

    squad = _squad_of(session, actor_id)
    if squad is None:
        return None
    return casualty_fraction([session.combatants[i] for i in squad.member_ids])


def squad_is_lost(session: "CombatSession", actor_id: str) -> bool:
    """Is he in a squad whose casualty fraction is above one half?"""
    fraction = squad_casualty_fraction(session, actor_id)
    return fraction is not None and fraction > SQUAD_LOST_ABOVE


def _rolled_this_phase(session: "CombatSession", actor_id: str) -> list:
    from kirby_combat.pre_attacks.in_the_phase import _in_this_phase

    return [e for e in _in_this_phase(session, actor_id)
            if getattr(e, "kind", None) == "SelfDestructRolled"
            and e.combatant_id == actor_id]


def judge_the_squad(session: "CombatSession", actor_id: str, roller) -> "CombatSession":
    """Make his INT Roll for the squad being lost, if one is owed this Phase.

    Owed when the squad is lost, he has a Self Only damaging power with a
    use left, and he has not rolled this Phase. Returns the session
    unchanged when no roll is owed: nothing is rolled for a man who could
    not use the answer.
    """
    from kirby_combat.charges import spent_charges
    from kirby_combat.enumeration import is_down
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import SelfDestructRolled, make_author_engine
    from kirby_cost.engine.rolls import characteristic_roll

    actor = session.combatants[actor_id]
    if is_down(actor) or not squad_is_lost(session, actor_id):
        return session
    if not self_destruct_powers(actor, spent_charges(session, actor_id)):
        return session
    if _rolled_this_phase(session, actor_id):
        return session
    squad = _squad_of(session, actor_id)
    number = characteristic_roll(int(actor.int_))
    rolled = sum(roller.roll_dice(3))
    return apply_event(session, SelfDestructRolled(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=actor_id, squad=squad.name, side=squad.side,
        casualty_fraction=squad_casualty_fraction(session, actor_id),
        roll=rolled, target_number=number, succeeded=rolled <= number,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


def judged_the_squad_lost(session: "CombatSession", actor_id: str) -> bool:
    """Did he make this Phase's INT Roll, with his squad still lost?"""
    return any(e.succeeded for e in _rolled_this_phase(session, actor_id)) \
        and squad_is_lost(session, actor_id)


def self_destruct_offers(session: "CombatSession", actor: Any) -> list["LegalAction"]:
    """The `self_destruct` offers on his menu: one per Self Only damaging
    power with a use left, when capture is imminent or he judged the squad
    lost. Empty otherwise."""
    from kirby_combat.charges import spent_charges
    from kirby_combat.enumeration import LegalAction, _power_action_id, is_down

    if is_down(actor):
        return []
    powers = self_destruct_powers(actor, spent_charges(session, actor.id))
    if not powers:
        return []
    if capture_is_imminent(session, actor.id):
        why = "he is about to be captured"
    elif judged_the_squad_lost(session, actor.id):
        why = "he judges the squad is lost"
    else:
        return []
    return [
        LegalAction(
            action_id=_power_action_id(SELF_DESTRUCT, actor.id, ap),
            kind=SELF_DESTRUCT, target_id=None,
            power_xmlid=ap.xmlid, power_name=ap.name,
            summary=(f"Set off {ap.name} ({int(ap.damage_dice)}d6): it hurts "
                     f"only you, and you may not survive it; {why}"),
            _attack_view=ap,
        )
        for ap in powers
    ]
