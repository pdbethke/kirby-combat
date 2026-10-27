"""Which identity a character is in, and what he owns in it.

THE RULE. 6E1 p.388: "A character can only use a power with Only In
Alternate Identity ('OIAID') while he's in an alternate identity." HD's xmlid
for that Limitation is ``OIHID``. And p.389: "the change must take at least a
Full Phase, if not longer (during which the character can do nothing else)".
6E1 p.133 says the same from the other side: activating a Power is a Zero
Phase Action, "In some cases - such as when a Power has the Limitations Extra
Time or Only In Alternate Identity - activating a Power may take longer
(typically a Full Phase ...)".

THE DEFECT THIS CLOSES. ``HeroCombatState.in_hero_id`` gated the
CHARACTERISTICS bought that way (kirby-cost's ``ActivationContext``) and
nothing else. A civilian Ravel had his base DEX and SPD and still fired the
costumed Blast, wore the costumed Force Field, flew, and was offered every
power on his sheet. And nothing ever flipped the flag, so the change of
identity the Limitation is priced on never happened in a fight.

ONE DOOR. ``build_in_play(combatant)`` is the character's build as it
stands in his current identity: the same object in his Hero identity (so the
common case costs nothing and changes nothing), and otherwise a view whose
purchase sections leave out everything bound to the other identity. Every
reader that walks a character's purchases --- ``hero_view``'s views, the
menu, perception, the resolvers --- reads it, so one predicate decides what a
man owns this Phase. A nested purchase (one part of a Compound Power) is
checked with the same predicate, ``in_play``, by the walks that descend.

THE CHANGE. ``identity_change_offer`` builds the menu's offer and
``change_identity`` records it as an ``IdentityChanged`` event, which
``apply_event`` folds onto the combatant --- so a fight rebuilt from its log
is in the same identity as the fight that ran.

RULING (6E1 p.389 leaves it to the GM). The Limitation requires that "the
change must take at least a Full Phase ... and/or there must be other
difficulties". This engine rules the change a Full Phase Action, and a
Zero Phase Action for a character who has bought the means to change
instantly: the Instant Change Adder on Shape Shift or Multiform (6E1 p.272,
p.281: "can shift shape as a Zero Phase Action"), or the Cosmetic Transform
the book names Instant Change (6E1 p.133 points to it at 6E1 p.307 for
"Characters who want to alter their clothing"). Such a character's OIAID is
justified by the "other difficulties" branch, which is the GM's to enforce
outside the fight.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

from kirby_cost.model.modifiers import has_modifier

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession

#: HD's xmlid for the Only In Alternate Identity Limitation (6E1 p.388).
OIHID = "OIHID"

#: The menu kinds. Two, because the loop reads the TIME a change takes off
#: the kind, exactly as it reads a Presence Attack's: a Full Phase change
#: spends the Phase and is excluded from a Half Phase (6E2 p.139's very
#: impressed man); a Zero Phase one leaves the Phase his (6E1 p.272).
CHANGE_IDENTITY = "change_identity"
CHANGE_IDENTITY_INSTANT = "change_identity_instant"
IDENTITY_KINDS = frozenset({CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT})

#: The sections of a build that hold purchases. Characteristics are not
#: among them: a characteristic bought OIAID is a ``Contribution`` kirby-cost
#: already conditions on ``ActivationContext`` (``combat_stats``).
_PURCHASE_SECTIONS = frozenset({
    "powers", "equipment", "martial_arts", "skills", "talents", "perks",
})

#: The Adder that makes a change of form a Zero Phase Action (6E1 p.272
#: Multiform, p.281 Shape Shift).
_INSTANT_CHANGE_ADDER = "INSTANTCHANGE"

#: The book's own name for the clothing-changing Cosmetic Transform (6E1
#: p.133, p.307). Matched on the Transform's name or alias because the build
#: carries nothing else that says what a Cosmetic Transform changes; a
#: TRANSFORM of another option never matches.
_INSTANT_CHANGE_NAME = "instant change"


def in_play(purchase: Any, *, in_hero_id: bool) -> bool:
    """Does this purchase work in the identity he is in?

    ``has_modifier`` inherits from enclosing purchases (kirby-cost
    ``model/modifiers.py``), so a slot of an OIAID Multipower is bound with
    its pool, and the predicate is the one kirby-cost's characteristic walk
    asks.
    """
    if in_hero_id:
        return True
    return not has_modifier(purchase, OIHID)


class BuildInIdentity:
    """A build, seen from outside its Hero identity.

    Delegates everything to the build, except that each purchase section
    leaves out what only works in the Hero identity. Bound methods
    (``characteristic_value``, ``characteristic_states``) are the build's
    own, so characteristics keep kirby-cost's conditioning and are not
    filtered twice.
    """

    __slots__ = ("_build",)

    def __init__(self, build: Any) -> None:
        object.__setattr__(self, "_build", build)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._build, name)
        if name in _PURCHASE_SECTIONS and value is not None:
            return [p for p in value if in_play(p, in_hero_id=False)]
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "a build seen in an identity is read-only; change the build "
            "itself (HeroCombatant.hero)")


def build_in_play(combatant: Any) -> Any:
    """The combatant's build as it stands in his current identity.

    The build itself in his Hero identity, so the usual case is the object
    every reader already had. A combatant with no ``state`` (a flat stat
    block) has no identity and no build to filter; asking is a mistake and
    raises naming the type.
    """
    state = getattr(combatant, "state", None)
    hero = getattr(combatant, "hero", None)
    if state is None or hero is None:
        raise TypeError(
            f"{type(combatant).__name__} {getattr(combatant, 'id', '?')!r} "
            "has no build and no identity; build_in_play reads a "
            "HeroCombatant")
    if state.in_hero_id:
        return hero
    return BuildInIdentity(hero)


def _purchases(build: Any) -> Iterable[Any]:
    """Every purchase on a build, nested ones included."""
    stack: list[Any] = []
    for section in _PURCHASE_SECTIONS | {"characteristics"}:
        stack.extend(getattr(build, section, None) or [])
    seen: set[int] = set()
    while stack:
        p = stack.pop()
        if id(p) in seen:
            continue
        seen.add(id(p))
        yield p
        for child in ("sub_powers", "objects", "powers"):
            nested = getattr(p, child, None)
            if isinstance(nested, list):
                stack.extend(nested)


def build_has_alternate_identity(build: Any) -> bool:
    """Does anything on this build depend on which identity he is in?

    6E1 p.388: "only characters who maintain two distinct identities can
    use this Limitation" --- so a build carrying it has two, and one
    without it has nothing a change would alter.
    """
    return any(has_modifier(p, OIHID, inherited=False)
               for p in _purchases(build))


def build_has_instant_change(build: Any) -> bool:
    """Has he bought the means to change in no time? See the module ruling."""
    for p in _purchases(build):
        adders = (getattr(p, "assigned_adders", None)
                  or getattr(p, "adders", None) or [])
        if any((getattr(a, "xmlid", "") or "").upper() == _INSTANT_CHANGE_ADDER
               for a in adders):
            return True
        if ((getattr(p, "xmlid", "") or "").upper() == "TRANSFORM"
                and (getattr(p, "option_id", "") or "").upper() == "COSMETIC"
                and _INSTANT_CHANGE_NAME in {
                    (getattr(p, "name", "") or "").strip().lower(),
                    (getattr(p, "alias", "") or "").strip().lower()}):
            return True
    return False


def identity_change_offer(actor: Any) -> "LegalAction | None":
    """The menu's change-of-identity offer, or None when there is none.

    None for a character with one identity, and for a combatant rebuilt
    from a snapshot that recorded only one (``has_alternate_identity`` says
    which). The offer goes both ways: into the costume and out of it.
    """
    from kirby_combat.enumeration import LegalAction

    if not actor.has_alternate_identity():
        return None
    instant = actor.has_instant_change()
    kind = CHANGE_IDENTITY_INSTANT if instant else CHANGE_IDENTITY
    going_to_hero = not actor.state.in_hero_id
    where = "into his Hero identity" if going_to_hero else "out of his Hero identity"
    cost = ("a Zero Phase Action with Instant Change (6E1 p.272); his Phase "
            "goes on" if instant else
            "a Full Phase Action, and he can do nothing else (6E1 p.389)")
    return LegalAction(
        action_id=f"{kind}:{'hero' if going_to_hero else 'civilian'}",
        kind=kind,
        target_id=None,
        power_xmlid=None,
        power_name=None,
        summary=(f"Change {where}: {cost}. What he bought Only In "
                 f"Alternate Identity works only in it (6E1 p.388)."),
    )


def change_identity(
    session: "CombatSession", combatant_id: str, *, zero_phase: bool,
) -> "CombatSession":
    """Record the change. ``apply_event`` folds it onto the combatant."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        IdentityChanged, make_author_combatant,
    )

    combatant = session.combatants[combatant_id]
    return apply_event(session, IdentityChanged(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id,
        in_hero_id=not combatant.state.in_hero_id,
        zero_phase=zero_phase,
    ))


def identity_changed_this_phase(
    session: "CombatSession", combatant_id: str,
) -> bool:
    """Has he already changed identity in this Phase?

    Read by the loop after a Zero Phase change, so the same Phase coming
    back to him does not offer the change again.
    """
    from kirby_combat.pre_attacks.in_the_phase import _since_his_last_phase

    return any(
        getattr(evt, "kind", None) == "IdentityChanged"
        and getattr(evt, "combatant_id", None) == combatant_id
        for evt in _since_his_last_phase(session, combatant_id)
    )
