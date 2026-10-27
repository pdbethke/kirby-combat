"""Acting out of turn: Aborting to a defence, and using a Held Action.

Two things a man may do when it is NOT his Phase, both of which the parked
kirby-api driver did and the engine did not:

1. **ABORT TO A DEFENCE WHEN ATTACKED** (driver ``_maybe_abort``, deleted in
   70ad60f). 6E2 p.24: "Typically a character must declare an Abort when an
   attacker announces he's attacking that character, but before any rolls are
   made." Dodge and Block were offered only on the defender's OWN Phase, so
   the out-of-turn Abort --- the reason Abort exists --- never happened.

2. **USING A HELD ACTION** (driver ``_resolve_release_held``). 6E2 p.22: "A
   character can usually use a Held Action ... at any time". The engine let a
   man Hold and never asked him again: `run_phase` passed no
   ``open_held_action_ids``, so ``release_held`` was never offered, and a held
   Phase was simply a Phase thrown away.

THE DEFENDER'S OWN CHOOSER DECIDES. The driver decided an Abort with a
deterministic expected-damage picker (``sim_ai.maybe_abort_to_defense``)
gated on an INT Roll. Neither is a rule: 6E2 p.24 makes the Abort the
character's choice and asks no roll, so the INT Roll is dropped (a driver
error, corrected here) and the choice goes to the one seat the loop has,
`Chooser.choose`, with a `PhaseSituation` whose ``actor`` is the defender and
whose ``out_of_turn`` says why he is being asked. The FIRST offer is always
to do nothing --- keep the Phase, keep holding --- so a chooser that takes the
first legal offer behaves exactly as it did before this module existed.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Callable

from kirby_combat.enumeration import LegalAction, _friendly, is_down
from kirby_combat.pre_attacks.in_the_phase import PRESENCE_KINDS
from kirby_combat.loop.chooser import (
    Chooser, IncomingAttack, OutOfTurn, OutOfTurnReason, PhaseSituation,
    validate_choice,
)

if TYPE_CHECKING:
    from kirby_combat.actions.held_action import HeldActionDeclared
    from kirby_combat.session.combat_session import CombatSession


class Reaction(str, Enum):
    """The answers to "he is attacking you --- do you Abort?" (6E2 p.24)."""

    #: Take it on his ordinary DCV and keep his next Phase.
    NONE = "no_abort"
    #: 6E2 p.55 / p.93: +3 DCV against all attacks (a Martial Dodge's +5).
    DODGE = "dodge"
    #: 6E2 p.59: roll to stop this hand-to-hand attack outright.
    BLOCK = "block"


#: The answer to "his Phase is starting --- do you use your Held Action?".
KEEP_HOLDING = "keep_holding"

#: The kinds whose resolution reaches the attack door
#: (`actions/recording.resolve_attack_in_session`), where a Dodge's DCV and a
#: Block's roll are read. A defence against a kind that does not reach it
#: would be a Phase given up for nothing, so it is not offered: Grab,
#: Entangle, Flash, Move By and Move Through resolve elsewhere today.
#: Mental Powers are absent on purpose: they roll OMCV against DMCV, and
#: neither Dodge nor Block touches DMCV (6E1 p.150).
REACTABLE_KINDS = frozenset({
    "attack", "strike", "maneuver", "trip", "disarm", "push",
    "throw_object", "move_strike", "reposition_strike",
    "rapid_fire", "multiple_attack", "sweep",
})


def _is_hth(action: LegalAction) -> bool:
    power = action._attack_view
    if action.kind in ("strike", "maneuver", "trip", "disarm", "sweep"):
        return True
    if power is None:
        return False
    return not getattr(power, "is_ranged", (getattr(power, "range_m", 0) or 0) > 0)


def _killing(action: LegalAction) -> bool:
    """6E1 p.98: does this offer do Killing Damage? Read off the power or
    the maneuver it carries; an offer with neither does none."""
    for view in (action._attack_view, action._maneuver_view):
        if view is not None:
            return str(getattr(view, "damage_type", "")) == "killing"
    return False


def describe_incoming(attacker_id: str, incoming: LegalAction) -> IncomingAttack:
    """The attack ``incoming`` as a defender's seat is told about it.

    ``hand_to_hand`` is `_is_hth`, the same test that puts Block on the
    menu, so a seat reading it can never disagree with the menu it is
    shown."""
    return IncomingAttack(
        attacker_id=str(attacker_id),
        action_id=incoming.action_id,
        kind=incoming.kind,
        power_name=incoming.power_name,
        summary=incoming.summary,
        hand_to_hand=_is_hth(incoming),
        killing=_killing(incoming),
    )


def nameable_powers(combatant) -> tuple[str, ...]:
    """The names a Held Action order may name its action by, in sheet order.

    Peter, 2026-10-27: a held order names its action "by power (or
    maneuver) plus a target rule" and is matched to the live offer by
    `LegalAction.power_name` when it fires. These are the SHEET's names ---
    the attacks this combatant carries, every power of the build in play,
    every bought maneuver, his Interaction Skills (offered as social
    combat, APG p34), and the Strike and standard maneuvers (Grab, Trip,
    Move-By, Move-Through) everyone has --- a superset of
    what any menu can put on an offer (`tests/loop/test_nameable_powers.py`
    holds that on real builds). A name with no matching offer when the order
    fires matches nothing, and the question is asked.
    """
    from kirby_combat.identity import build_in_play

    names: list[str] = []

    def add(name) -> None:
        if name and str(name) not in names:
            names.append(str(name))

    for attack in getattr(combatant, "attacks", None) or []:
        add(getattr(attack, "name", None))
    if getattr(combatant, "state", None) is not None and getattr(combatant, "hero", None) is not None:
        for power in getattr(build_in_play(combatant), "powers", None) or []:
            add(getattr(power, "name", None))
    from kirby_combat.enumeration import INTERACTION_SKILLS, STANDARD_MANEUVER_NAMES

    has_build = (getattr(combatant, "state", None) is not None
                 and getattr(combatant, "hero", None) is not None)
    maneuvers = getattr(combatant, "maneuver_view", None)
    for maneuver in (maneuvers() if callable(maneuvers) else []):
        add(getattr(maneuver, "name", None))
    if has_build:
        skills = {(getattr(s, "xmlid", "") or "").upper()
                  for s in (getattr(build_in_play(combatant), "skills", None) or [])}
        for xmlid, (_kind, label) in INTERACTION_SKILLS.items():
            if xmlid in skills:
                add(label)
    add("Strike")
    for name in STANDARD_MANEUVER_NAMES:
        add(name)
    return tuple(names)


def _used_his_phase_this_segment(session: "CombatSession", combatant_id: str) -> bool:
    """6E2 p.24: "Once a character has performed an Attack Action or otherwise
    used his full Phase in a particular Segment, he cannot Abort to any
    Action until the next Segment.\""""
    timeline = session.timeline
    return any(
        slot.combatant_id == combatant_id and slot.has_acted
        and slot.segment == timeline.segment
        for slot in timeline.acting_order
    )


def may_abort(session: "CombatSession", defender_id: str, attacker) -> bool:
    """Whether the defender may Abort to a defence against this attacker now.

    Each refusal is a rule:

    * down (6E1 p.421) --- he is in no condition to;
    * already Aborted, inside the lockout (6E2 p.24);
    * Stunned or recovering (6E2 p.106: "he cannot even Abort");
    * used his Phase this Segment (6E2 p.24, quoted on the helper above);
    * Surprised (6E2 p.24: "Characters who are Surprised normally cannot
      Abort their next Phase; they have, after all, been taken unawares").
    """
    from kirby_combat.actions.reactive.abort import is_aborting
    from kirby_combat.actions.recording import _surprise_for
    from kirby_combat.statuses import stunned_or_recovering_for

    defender = session.combatants.get(defender_id)
    if defender is None or is_down(defender):
        return False
    if is_aborting(session, defender_id):
        return False
    if stunned_or_recovering_for(session, defender_id):
        return False
    if (_used_his_phase_this_segment(session, defender_id)
            and usable_hold(session, defender_id) is None):
        # A Held Action is the exception: Lazer, having made a Half Move
        # and Held the rest, "could Abort to Dodge and sacrifice his Held
        # Half Phase" (6E2 p.24).
        return False
    from kirby_combat.rage import rage_state

    if rage_state(session, defender_id).raging:
        # 6E1 p.424-425: an Enraged or Berserk man fights and does not
        # defend himself, and an Abort is only ever to a defensive Action
        # (6E2 p.23). `rage_menu` refuses it on his own Phase; this is the
        # same refusal out of turn.
        return False
    surprise = _surprise_for(session, attacker, defender)
    if surprise is not None and surprise.applies:
        return False
    return True


def reaction_menu(
    session: "CombatSession", attacker, incoming: LegalAction,
) -> list[LegalAction]:
    """What the target of ``incoming`` may Abort to, or [] when he may not.

    No Abort at all for a kind that is not an attack on a man
    (`REACTABLE_KINDS`), or for a target that is not a combatant (an Image).
    Block is offered only against hand-to-hand attacks (6E2 p.59: "Blocks
    only affect Ranged attacks with the GM's permission").
    """
    from kirby_combat.actions.reactive.martial import block_maneuver, dodge_maneuver

    defender_id = incoming.target_id
    if incoming.kind not in REACTABLE_KINDS or defender_id not in session.combatants:
        return []
    if not may_abort(session, defender_id, attacker):
        return []
    defender = session.combatants[defender_id]
    dodge = dodge_maneuver(defender)
    # His name, as the rest of the menu and the Brief name him: a player
    # reads these offers as his question (kirby-api), and an id is a uuid.
    who = _friendly(attacker)
    menu = [
        LegalAction(
            action_id=Reaction.NONE.value, kind=Reaction.NONE.value,
            target_id=None, power_xmlid=None, power_name=None,
            summary=(f"Don't Abort: take {who}'s attack on your "
                     "ordinary DCV and keep your next Phase"),
        ),
        LegalAction(
            action_id=Reaction.DODGE.value, kind=Reaction.DODGE.value,
            target_id=None, power_xmlid=None, power_name=None,
            summary=(f"Abort to {dodge.name or 'Dodge'}: +{dodge.dcv} DCV "
                     "against all attacks until your Phase after next; you "
                     "give up your next Phase (6E2 p24)"),
        ),
    ]
    if _is_hth(incoming):
        block = block_maneuver(defender)
        menu.append(LegalAction(
            action_id=Reaction.BLOCK.value, kind=Reaction.BLOCK.value,
            target_id=attacker.id, power_xmlid=None, power_name=None,
            summary=(f"Abort to {block.name or 'Block'}: roll OCV"
                     f"{block.ocv:+d} against {who}'s OCV; a success "
                     "stops the blow (6E2 p59). You give up your next Phase"),
        ))
    return menu


def _situation(session, actor, menu, *, reason, by_id, incoming) -> PhaseSituation:
    from kirby_combat.roster import Roster

    roster = Roster(session)
    return PhaseSituation(
        actor=actor, menu=menu,
        enemies=roster.enemies_of(actor),
        allies=roster.allies_of(actor),
        session=session,
        segment=session.timeline.segment, turn=session.timeline.turn,
        out_of_turn=OutOfTurn(
            reason=reason, by_id=by_id, incoming=incoming,
            attack=(describe_incoming(by_id, incoming)
                    if incoming is not None else None),
        ),
    )


def react_to_attack(
    session: "CombatSession", attacker, incoming: LegalAction, chooser: Chooser,
) -> tuple["CombatSession", Reaction | None]:
    """Ask the target of ``incoming`` whether he Aborts, and record it.

    Called by `run_phase` after the attacker has chosen and before anything
    is rolled --- the moment 6E2 p.24 fixes. Returns the new session and the
    reaction taken (None when he was not entitled to one).

    A man Holding his Action Aborts with it: 6E2 p.24, "If he's Holding a
    Phase or Half Phase, he may Abort to use his Held Action to perform a
    defensive Action; in that case he doesn't lose any more Phases."
    """
    menu = reaction_menu(session, attacker, incoming)
    if not menu:
        return session, None
    defender = session.combatants[incoming.target_id]
    situation = _situation(
        session, defender, menu, reason=OutOfTurnReason.ABORT,
        by_id=attacker.id, incoming=incoming,
    )
    chosen = Reaction(validate_choice(chooser.choose(situation), menu).kind)
    if chosen is Reaction.NONE:
        return session, chosen

    from kirby_combat.actions.reactive.abort import mark_aborting, mark_aborting_with_held

    from kirby_combat.actions.held_action import HeldAction

    held = usable_hold(session, defender.id)
    if held is not None:
        session, _ = HeldAction.release(
            session, held.id,
            trigger_observed=f"Aborted to {chosen.value} against {attacker.id}",
        )
        session, _ = mark_aborting_with_held(
            session, defender.id, to_action=chosen.value,
        )
    else:
        session, _ = mark_aborting(session, defender.id, to_action=chosen.value)
    return session, chosen


# ---------------------------------------------------------------------------
# Held Actions (6E2 p.22)
# ---------------------------------------------------------------------------


def _held_at(session: "CombatSession", held: "HeldActionDeclared") -> tuple[int, int] | None:
    """The (turn, segment) of the Phase he Held: the spend that followed it."""
    seen = False
    for event in session.event_log:
        if event is held or getattr(event, "id", None) == held.id:
            seen = True
            continue
        if (seen and getattr(event, "kind", "") == "PhaseSpent"
                and event.combatant_id == held.combatant_id):
            return (event.turn, event.segment)
    return None


def _lapsed(session: "CombatSession", held: "HeldActionDeclared") -> bool:
    """6E2 p.22: "he loses any Held Action when the next Segment in which he
    has a Phase begins, because he can only have one Phase at a time.\""""
    from kirby_combat.session.timeline import next_phase
    from kirby_combat.tables import segments_for_spd

    held_at = _held_at(session, held)
    if held_at is None:
        return False                    # being declared in this very Phase
    holder = session.combatants.get(held.combatant_id)
    if holder is None:
        return True
    phases = segments_for_spd(holder.combat_stats().spd)
    if not phases:
        return False
    following = next_phase(phases, *held_at, inclusive=False)
    now = (session.timeline.turn, session.timeline.segment)
    return now >= following


def expire_lapsed_holds(session: "CombatSession") -> "CombatSession":
    """Drop every Held Action whose holder's next Phase Segment has begun.

    Recorded through `HeldAction.expire_for_combatant_next_phase`, which
    existed for exactly this and had no caller.
    """
    from kirby_combat.actions.held_action import HeldAction

    lapsed = {h.combatant_id for h in HeldAction.get_pending_all(session)
              if _lapsed(session, h)}
    for combatant_id in sorted(lapsed):
        session, _ = HeldAction.expire_for_combatant_next_phase(session, combatant_id)
    return session


def usable_hold(session: "CombatSession", combatant_id: str) -> "HeldActionDeclared | None":
    """His Held Action, if he has one he can still use right now."""
    from kirby_combat.actions.held_action import HeldAction

    combatant = session.combatants.get(combatant_id)
    if combatant is None or is_down(combatant):
        return None
    for held in HeldAction.get_pending(session, combatant_id):
        if _held_at(session, held) is not None and not _lapsed(session, held):
            return held
    return None


#: What a released Held Action may NOT be. Holding again is not using it,
#: and `release_held` is the own-Phase offer this module replaces.
_NOT_FROM_A_HOLD = frozenset({"hold", "release_held"})


def _contest_dex(session, holder, actor, roller) -> tuple[bool, str]:
    """6E2 p.22's contested DEX Roll: does the holder act before the actor?

    "If two characters want to perform an Action at the same time, each
    character should make a DEX Roll ... the character whose DEX Roll
    succeeds by the most gets to act first. If both characters make the roll
    by the same amount, their Held Actions occur simultaneously."

    RULING: this engine resolves one action at a time, so "simultaneously"
    cannot be run as such; a tie goes to the man whose Phase it is, and the
    holder acts straight after him. Returns (holder first, the note).
    """
    from kirby_combat.session.tie_rule import dex_roll_target

    h_target = dex_roll_target(int(holder.combat_stats().dex))
    a_target = dex_roll_target(int(actor.combat_stats().dex))
    h_roll = sum(roller.roll_dice(3))
    a_roll = sum(roller.roll_dice(3))
    first = (h_target - h_roll) > (a_target - a_roll)
    note = (f"DEX Rolls (6E2 p22): {holder.id} {h_roll} vs {h_target}-, "
            f"{actor.id} {a_roll} vs {a_target}-")
    return first, note


def ask_holders(
    session: "CombatSession", actor_id: str, chooser: Chooser, *,
    situation_for: Callable[["CombatSession", str], PhaseSituation],
    roller,
) -> tuple["CombatSession", list[tuple[str, LegalAction, str]], list[tuple[str, LegalAction, str]]]:
    """Ask everyone Holding an Action whether he uses it before this Phase.

    ``situation_for`` builds a man's ordinary Phase situation --- the menu
    exactly as `run_phase` would offer it on his Phase --- so a released
    Held Action is any action he could have taken then, minus holding again.
    The first offer is `KEEP_HOLDING`.

    Returns the session and two lists of ``(holder_id, action, note)``: the
    releases that go BEFORE the actor's Phase and those that go straight
    AFTER it (a holder who lost 6E2 p.22's DEX contest). Defensive actions
    (anything he could Abort to) "occur first" without a roll (6E2 p.22).
    Nothing is resolved here; `run_phase` resolves each through the same
    registry as any other choice.
    """
    from kirby_combat.actions.held_action import HeldAction

    before: list[tuple[str, LegalAction, str]] = []
    after: list[tuple[str, LegalAction, str]] = []
    holders = sorted({h.combatant_id for h in HeldAction.get_pending_all(session)})
    for holder_id in holders:
        if holder_id == actor_id:
            continue
        held = usable_hold(session, holder_id)
        if held is None:
            continue
        base = situation_for(session, holder_id)
        menu = [LegalAction(
            action_id=KEEP_HOLDING, kind=KEEP_HOLDING,
            target_id=None, power_xmlid=None, power_name=None,
            summary=f"Keep holding: let {actor_id} take his Phase",
        )] + [a for a in base.menu if a.kind not in _NOT_FROM_A_HOLD]
        situation = PhaseSituation(
            actor=base.actor, menu=menu, enemies=base.enemies,
            allies=base.allies, fallen_allies=base.fallen_allies,
            distances_m=base.distances_m, reach_m=base.reach_m,
            session=session, segment=base.segment, turn=base.turn,
            out_of_turn=OutOfTurn(
                reason=OutOfTurnReason.HELD_ACTION, by_id=actor_id,
                incoming=None, attack=None,
            ),
        )
        chosen = validate_choice(chooser.choose(situation), menu)
        if chosen.kind == KEEP_HOLDING:
            continue
        # A PRESENCE ATTACK TAKES NO TIME (6E2 p.25), so it does not use the
        # Held Action: he makes it and is still Holding. One a Phase, as on
        # his own (`in_the_phase.presence_attack_made_this_phase` keeps the
        # offer off his menu once it is made).
        if chosen.kind not in PRESENCE_KINDS:
            session, _ = HeldAction.release(
                session, held.id,
                trigger_observed=f"used before {actor_id}'s Phase: {chosen.kind}",
            )
        if chosen.kind in (Reaction.DODGE.value, Reaction.BLOCK.value):
            before.append((holder_id, chosen, "a defensive Action goes first (6E2 p22)"))
            continue
        first, note = _contest_dex(
            session, session.combatants[holder_id], session.combatants[actor_id], roller,
        )
        (before if first else after).append((holder_id, chosen, note))
    return session, before, after
