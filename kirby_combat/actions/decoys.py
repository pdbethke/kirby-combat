"""An Image of a man, drawing the fire meant for him (6E1 p.238-239).

`actions/images.py` has known for a long time who perceives an Image
(`perceived_by`), who still believes it (`believers`) and how a PER Roll sees
through it (`disbelieve`). Nothing outside its own tests asked any of it:
`enumerate_actions` takes ``decoy_targets`` and ``own_decoy_live`` and
`loop/run.py` passed neither, so an Image conjured in a fight was never
something anybody could shoot, and a caster could conjure a second, a third,
a tenth. This module is the two halves the parked kirby-api driver carried
(``_decoy_targets_for``, ``_resolve_attack_decoy``), moved onto the engine's
own Image model.

WHO SEES A DECOY AS A TARGET. Everyone who perceives the Image and has not
seen through it (`Images.believers`), except its caster, and only an Image
cast by one of his enemies: it is an Image of an enemy standing there.

WHAT AN IMAGE LOOKS LIKE --- a JUDGEMENT carried from the driver. 6E1 p.238
has the caster decide "what Image to produce"; a ``image_decoy`` offer does
not ask, and the offer's own promise is a decoy that draws fire, so the Image
is of the caster himself. The offer against it reads exactly as an offer
against him would ("the full fool", in the driver's words), apart from its id.

ATTACKING ONE. 6E1 p.239: "Images cannot cause any physical effects and are
totally intangible", and "Normally, Images react in an appropriate manner to
outside phenomena ... However, this may make it easier for observers to detect
that the Image is, in fact, just an Image." So the attack is made and spent ---
declared, its END paid, its Charge counted --- and lands on nothing; and the
attacker, who has just interacted with it, makes the PER Roll 6E1 p.239 gives
"characters who perceive an Image", at the Image's own modifier. A success is
the observer's alone (`Images.disbelieved_by` is keyed per observer), and the
Image does not vanish: it drops off HIS menu and keeps fooling everyone else.

NOT MODELLED: a Touch-Group Image (6E1 p.239's "feels, to the touch, like what
it seems to be") and the complexity bonus for an Image reacting to being hit.
The offer carries no description of what the Image does, so the roll is at the
modifier the Image was projected with.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.actions.images import Images

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


def decoy_targets_for(
    session: "CombatSession", observer_id: str, enemy_ids: set[str],
) -> list[tuple[str, str]]:
    """``(image_id, apparent_name)`` for every Image this observer may shoot.

    The shape `enumerate_actions(decoy_targets=)` has always taken.
    """
    out: list[tuple[str, str]] = []
    for image in Images.active(session):
        if image.caster_id not in enemy_ids:
            continue
        if observer_id not in Images.believers(session, image.image_id):
            continue
        caster = session.combatants[image.caster_id]
        out.append((image.image_id, str(getattr(caster, "name", None) or caster.id)))
    return out


def own_decoy_live(session: "CombatSession", caster_id: str) -> bool:
    """Whether this caster already has an Image standing (one at a time)."""
    return any(img.caster_id == caster_id for img in Images.active(session))


def is_decoy(session: "CombatSession", target_id: str | None) -> bool:
    """Whether an offer's target is a standing Image rather than a man."""
    return (target_id is not None and target_id not in session.combatants
            and Images.get(session, target_id) is not None)


def attack_decoy(
    session: "CombatSession", actor, *, image_id: str, power: Any,
    action_kind: str, template: "CombatTemplate", roller,
) -> tuple["CombatSession", dict[str, Any]]:
    """Spend an attack on an Image, and roll the attacker's disbelief.

    Returns the new session and the payload recorded for the attack.
    """
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_cost
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    image = Images.get(session, image_id)
    if image is None:
        raise ValueError(f"no standing Image {image_id!r} to attack")

    now = datetime.now(timezone.utc)
    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=action_kind, targets=[image_id],
        parameters={"power_xmlid": getattr(power, "xmlid", None)},
    )
    s = apply_event(session, declared)
    s = _spend_attack_end(s, s.combatants[actor.id], int(end_cost(power)), template,
                          power=power)
    payload: dict[str, Any] = {
        "kind": action_kind,
        "target_id": image_id,
        "image_id": image_id,
        "into_the_void": True,
        "hit": False,
        "stun_dealt": 0,
        "body_dealt": 0,
        "status_changes": [],
        "power_xmlid": getattr(power, "xmlid", None),
        "power_source_id": getattr(power, "source_id", None),
        "power_name": getattr(power, "name", None),
        "segment": s.timeline.segment,
        "effective_ocv": None,
        "target_dcv": None,
        "margin": None,
    }
    resolved = ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id),
        declaration_event_id=declared.id, result_payload=payload,
    )
    s = apply_event(s, resolved)
    s, _disbelief = Images.disbelieve(
        s, image_id=image_id, observer_id=actor.id, roller=roller,
    )
    return s, payload
