"""Which hand holds each of a man's weapons.

6E2 p.113: an Impairing wound to the hands, arms or shoulders is "-3 OCV for
any attacks using that arm". `weapons` already knows WHO holds a weapon;
this knows WHICH HAND, because a wound to the left arm does not spoil a gun
in the right.

RULINGS (Peter, 2026-11-27):
  * Stated per weapon at the start of the fight (`GripsStated`, in the same
    window as `RulingsStated` and the fight's terms), never assumed. A
    weapon of his whose grip was never stated is refused when asked
    (`GripsMissing`), not given a hand.
  * A weapon its owner picks back up goes to a free hand, the right if both
    are free.
  * A weapon bought Two-Handed --- HD's ``REQUIREDHANDS`` option ``TWO``, the
    Required Hands Limitation (6E1 Limitations) --- needs both. Read off the
    build: the Corral's Winchesters carry it, its Colts and coach gun do not.

A weapon out of its owner's hands (`weapons.holder_of` someone else, or on
the ground) has no grip: nothing he does with his arms touches it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

RIGHT, LEFT, BOTH = "right", "left", "both"
HANDS = (RIGHT, LEFT, BOTH)


class GripsMissing(LookupError):
    """A weapon in his hands whose grip the fight never stated."""


class GripsWrong(ValueError):
    """A stated grip the weapons cannot have: one hand, two guns."""


@dataclass(frozen=True)
class Grip:
    """One weapon, and the hand (or hands) holding it."""

    weapon_id: str
    hands: str

    def __post_init__(self) -> None:
        if self.hands not in HANDS:
            raise GripsWrong(f"{self.weapon_id!r}: hands {self.hands!r} is not "
                             f"one of {HANDS}")


def hands_needed(purchase: Any) -> int:
    """2 when the purchase carries Required Hands: Two-Handed, else 1."""
    from kirby_cost.model.modifiers import find_modifier

    from kirby_combat.power_modifiers import _option

    required = find_modifier(purchase, "REQUIREDHANDS", inherited=True)
    return 2 if required is not None and _option(required) == "TWO" else 1


def _sides(hands: str) -> frozenset[str]:
    return frozenset({RIGHT, LEFT}) if hands == BOTH else frozenset({hands})


def _purchase(combatant: Any, weapon_id: str) -> Any:
    from kirby_combat.actions.dispel import original_hero
    from kirby_combat.parts import parts_of

    stack = list(getattr(original_hero(combatant.hero), "powers", None) or [])
    stack += list(getattr(original_hero(combatant.hero), "equipment", None) or [])
    while stack:
        p = stack.pop()
        if str(getattr(p, "id", "")) == weapon_id:
            return p
        stack.extend(parts_of(p))
    raise GripsWrong(f"{combatant.id!r} has no weapon {weapon_id!r}")


def check_grips(combatant: Any, grips: Iterable[Grip]) -> None:
    """Refuse grips his weapons cannot have. Raises `GripsWrong`."""
    from kirby_combat.weapons import accessible_foci

    owned = {w.weapon_id for w in accessible_foci(combatant)}
    used: set[str] = set()
    for grip in grips:
        if grip.weapon_id not in owned:
            raise GripsWrong(f"{combatant.id!r} owns no weapon {grip.weapon_id!r}")
        need = hands_needed(_purchase(combatant, grip.weapon_id))
        if need == 2 and grip.hands != BOTH:
            raise GripsWrong(f"{combatant.id!r}'s {grip.weapon_id!r} needs two "
                             f"hands (Required Hands: Two-Handed)")
        clash = _sides(grip.hands) & used
        if clash:
            raise GripsWrong(f"{combatant.id!r}: two weapons in the "
                             f"{'/'.join(sorted(clash))} hand")
        used |= _sides(grip.hands)


def state_grips(session: "CombatSession", combatant_id: str,
                grips: Iterable[Grip]) -> "CombatSession":
    """Put one fighter's grips on the log (`GripsStated`), as the fight starts."""
    from datetime import UTC, datetime
    import uuid

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import GripsStated, make_author_engine

    return apply_event(session, GripsStated(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_engine(), combatant_id=combatant_id,
        grips=tuple(grips)))


def stated_grips(session: "CombatSession", combatant_id: str) -> dict[str, str]:
    """weapon id -> hands, as stated for him at the start of the fight."""
    for event in session.event_log:
        if (getattr(event, "kind", None) == "GripsStated"
                and event.combatant_id == combatant_id):
            return {g.weapon_id: g.hands for g in event.grips}
    return {}


def grip_of(session: "CombatSession", owner_id: str, weapon_id: str) -> str | None:
    """The hand(s) holding his weapon, or None when it is out of his hands.

    The stated grip until a `WeaponMoved` takes it; a pickup by its owner
    goes to a free hand, the right if both are free (ruling above).
    """
    from kirby_combat.weapons import PICKED_UP

    grips = dict(stated_grips(session, owner_id))
    held: dict[str, str | None] = dict(grips)
    for event in session.event_log:
        if getattr(event, "kind", None) != "WeaponMoved" or event.owner_id != owner_id:
            continue
        if event.cause == PICKED_UP and event.holder_id == owner_id:
            busy = set().union(*(_sides(h) for w, h in held.items()
                                 if h is not None and w != event.weapon_id))
            need = hands_needed(_purchase(_owner(session, owner_id), event.weapon_id))
            if need == 2:
                held[event.weapon_id] = BOTH
            else:
                free = [h for h in (RIGHT, LEFT) if h not in busy]
                held[event.weapon_id] = free[0] if free else None
        else:
            held[event.weapon_id] = None
    if weapon_id not in held:
        raise GripsMissing(
            f"{owner_id!r}'s weapon {weapon_id!r} has no stated grip: state it "
            "with grips.state_grips as the fight starts")
    return held[weapon_id]


def _owner(session: "CombatSession", owner_id: str) -> Any:
    return session.combatants[owner_id]
