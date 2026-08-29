"""Images — a perceivable thing that is not a combatant (6E1 p.238-239).

**The rule, in our own words** (this project ships no rules text; open your
own copy). A character with Images creates something other characters
perceive with the appropriate Senses. To project one he decides what it is,
where it is, and what it does, then makes a normal Attack Roll against DCV
3 to place it on the target point. Everyone with Line Of Sight perceives
it — the page is explicit that observers need neither to be within Reach
nor inside the affected Area, and gives a ball of light that might be seen
miles off. Observers who perceive an Image may make a PER Roll to spot it
as an Image rather than the real thing, modified by the realism its creator
paid for (+3 Character Points per -1 to observers' rolls) and by bonuses
for the Image's complexity. Failing that roll, an observer believes it is
real. Succeeding, he still perceives it but detects a flaw — and **the
Image does not disappear**; he simply knows and acts accordingly. Images is
a Constant Power and lasts while its creator pays END. An Image of
something that would have a DCV has whatever DCV its creator chose.

**Why this lives in kirby-combat and not kirby-api.** It was built in
kirby-api first, and that was a mistake — PeterB, 2026-08-28: *"images need
to live in -combat, not -api"*, *"-api is a wrapper around -combat to allow
us to run -combat on the web"*, *"there should be no mechanics or rules in
-api really."* Each of this module's three parts is rules math: an Attack
Roll, a Line-Of-Sight perception test, a modified PER Roll. kirby-api keeps
what it is genuinely for — the rows (`CombatSessionImageDecoyRow` and the
per-observer disbelief rows), the WebSocket payloads, the turn loop. The
distinction worth holding onto is that WHERE THE RULE LIVES is not WHERE
THE ROWS LIVE; `session/apply.py`'s "entity state lives in the driver" is a
log-replay argument about state and says nothing about who owns the rule.
Darkness is the same split done right: occlusion rule here, zone rows there.

**The structural problem this module solves, and how.** The engine's
perception layer answers "can A perceive B" where B is a COMBATANT — it
reads `target.hero` for Invisibility and `target.id` for a position. An
Image is perceivable and is not a combatant. Rather than widen `perceive()`
(and with it every caller's idea of what a target is), an Image is a POINT
plus the Sense Groups it affects, and `perceived_by` composes the existing
primitives against that point: line of sight, the observer's Flash state,
and the Darkness gate. Composing rather than widening is what makes 6E1
p.188's rule that a Sight Image cannot be perceived inside a Sight Darkness
field fall out for free instead of needing its own branch.

**Per-observer, everywhere.** Disbelief is one observer's knowledge. The
obvious wrong shape is a single ``disbelieved`` flag on the Image, which
lets the first character to make his roll spoil the illusion for the room.
State here is keyed by (image, observer) and derived from the event log,
matching ``Flash.is_flashed`` and ``NontargetingPerception.holds``.

**One assumption, stated rather than buried: every combatant is taken to
possess the ordinary human Sense Groups.** An Image bought against the
Hearing Group is heard by anyone who has ears, and this module does not
check that they do. It cannot: ``perception._sense_capabilities`` returns
only TARGETING senses by documented design, so the engine has no record of
a character's Hearing or Smell at all and asking it would answer "no ears"
for everyone. The assumption is right for the overwhelmingly common case
(6E2 p.9 describes Sight, Hearing and Smell as what a normal human has) and
wrong for a character who bought a Physical Limitation like Deafness, which
this engine does not model either. What IS checked is the thing that
actually varies in play: whether that Group has been taken away by a Flash
or a Darkness field. Revisit if and when non-Targeting senses become real.

**Not modelled, deliberately.** The INT Roll to copy a specific person
(6E1 p.239) and the "special knowledge" case where an observer knows the
real Defender is elsewhere are GM adjudication, not mechanics the engine
can decide; both feed the same net PER modifier this module already takes.
Scatter on a missed placement is likewise absent, matching
``actions/darkness.py`` — see that module's note.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession

#: 6E1 p.238 places an Image with an Attack Roll against DCV 3 — the same
#: target point DCV ``actions/darkness.py`` documents from 6E2 p.45/p.63.
#: Imported from there rather than restated so the two cannot drift.
from kirby_combat.actions.darkness import AREA_DCV


@dataclass(frozen=True)
class ProjectedImage:
    """One Image standing in the scene."""
    image_id: str
    caster_id: str
    position: tuple[float, float, float]
    sense_groups: tuple[str, ...]
    #: Net modifier to an observer's PER Roll to spot it as fake. NEGATIVE
    #: for realism the creator bought (6E1 p.238's +3 CP per -1), POSITIVE
    #: for a complexity bonus that helps the observer (6E1 p.239). One
    #: signed number because the page applies both to the same roll.
    per_modifier: int = 0
    #: 6E1 p.238 — whatever DCV the creator chose, or None for an Image of
    #: something that would not have one. The engine records it and never
    #: invents one.
    apparent_dcv: int | None = None


@dataclass(frozen=True)
class ImagePlacement:
    caster_id: str
    hit: bool
    roll: int
    target_number: int
    target_dcv: int
    image_id: str | None = None


@dataclass(frozen=True)
class DisbeliefResult:
    image_id: str
    observer_id: str
    succeeded: bool
    roll: int
    target_number: int
    #: ``""`` on a real attempt; ``"not_perceived"`` when the observer could
    #: not perceive the Image at all, which 6E1 p.239 makes a precondition
    #: of the roll (it gives it to characters WHO PERCEIVE the Image).
    reason: str = ""


class Images:
    name: str = "images"

    # ------------------------------------------------------------------ place
    @staticmethod
    def place(
        session: CombatSession,
        *,
        caster_id: str,
        position: tuple[float, float, float],
        sense_groups: list[str],
        per_modifier: int = 0,
        apparent_dcv: int | None = None,
        ocv_modifier: int = 0,
        roller=None,
    ) -> tuple[CombatSession, ImagePlacement]:
        """Make the placement Attack Roll and, on a hit, project the Image.

        ``ocv_modifier`` carries whatever the caller already worked out (the
        Range Modifier, Skill Levels); this action has no distance and does
        not re-derive any of it, matching ``Darkness.place``.
        """
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import (
            ActionDeclared, ActionResolved, make_author_combatant,
        )

        if roller is None:
            roller = session.dice_roller

        caster = session.combatants.get(caster_id)
        base_ocv = caster.combat_stats().ocv if caster is not None else 0
        # The standard HERO to-hit formula (resolution/to_hit.py): 3d6 <=
        # OCV + 11 - DCV.
        target_number = base_ocv + int(ocv_modifier) + 11 - AREA_DCV

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(caster_id),
            combatant_id=caster_id,
            action_type=Images.name,
            targets=[],                    # a target point, not a combatant
            parameters={
                "position": tuple(float(v) for v in position),
                "sense_groups": list(sense_groups),
                "per_modifier": int(per_modifier),
                "apparent_dcv": apparent_dcv,
                "target_dcv": AREA_DCV,
                "ocv_modifier": int(ocv_modifier),
            },
        )
        s = apply_event(session, declared)

        roll = sum(roller.roll_dice(3))
        hit = roll <= target_number
        image_id = f"image-{uuid.uuid4().hex[:8]}" if hit else None

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(caster_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "image_projected",
                "image_id": image_id,
                "caster_id": caster_id,
                "position": tuple(float(v) for v in position),
                "sense_groups": list(sense_groups),
                "per_modifier": int(per_modifier),
                "apparent_dcv": apparent_dcv,
                "hit": hit,
                "roll": roll,
                "target_number": target_number,
                "target_dcv": AREA_DCV,
            },
        )
        s = apply_event(s, resolved)

        return s, ImagePlacement(
            caster_id=caster_id, hit=hit, roll=roll,
            target_number=target_number, target_dcv=AREA_DCV,
            image_id=image_id,
        )

    # ------------------------------------------------------------------ dismiss
    @staticmethod
    def dismiss(session: CombatSession, *, image_id: str) -> CombatSession:
        """End an Image — its creator stopped paying END, or chose to drop it.

        Images is a Constant Power, so ceasing to pay ends it. The engine
        does not meter END on the caller's behalf here; a driver that tracks
        the upkeep calls this when it lapses.
        """
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import ActionResolved, make_author_engine

        evt = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            declaration_event_id="",
            result_payload={"type": "image_ended", "image_id": image_id},
        )
        return apply_event(session, evt)

    # ------------------------------------------------------------------ active
    @staticmethod
    def active(session: CombatSession) -> tuple[ProjectedImage, ...]:
        """Every Image currently standing, oldest first.

        Derived from the log rather than held as mutable state, matching
        every other effect in this engine (``Flash.is_flashed``,
        ``is_entangled``). A dismissed Image drops out; a missed placement
        never enters.
        """
        live: dict[str, ProjectedImage] = {}
        for evt in session.event_log:
            payload = getattr(evt, "result_payload", None)
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "image_projected" and payload.get("hit"):
                image_id = payload.get("image_id")
                if not image_id:
                    continue
                live[image_id] = ProjectedImage(
                    image_id=image_id,
                    caster_id=payload.get("caster_id", ""),
                    position=tuple(payload.get("position") or (0.0, 0.0, 0.0)),
                    sense_groups=tuple(payload.get("sense_groups") or ()),
                    per_modifier=int(payload.get("per_modifier") or 0),
                    apparent_dcv=payload.get("apparent_dcv"),
                )
            elif payload.get("type") == "image_ended":
                live.pop(payload.get("image_id"), None)
        return tuple(live.values())

    @staticmethod
    def get(session: CombatSession, image_id: str) -> ProjectedImage | None:
        for img in Images.active(session):
            if img.image_id == image_id:
                return img
        return None

    # ------------------------------------------------------------------ perception
    @staticmethod
    def perceived_by(
        session: CombatSession, image_id: str, observer_id: str,
        sense_group: str | None = None,
    ) -> bool:
        """Can ``observer_id`` perceive this Image?

        6E1 p.238 makes the test Line Of Sight and nothing else — no Reach
        requirement, no need to stand inside the affected Area, and so no
        distance check here. What CAN stop it is anything that takes away
        the Sense the Image speaks to: the observer being Flashed in that
        Sense Group, or a Darkness field covering that Group lying on the
        line. Both are the existing primitives, composed rather than
        reimplemented, which is why 6E1 p.188's rule that a Sight Image is
        not perceived inside a Sight Darkness needs no branch of its own.

        ``sense_group`` narrows the question to one Group ("does he HEAR
        it"); by default any Group the Image affects will do.
        """
        from kirby_combat.actions.flash import Flash
        from kirby_combat.perception import SenseCapability, _darkness_blocks
        from kirby_combat.resolution.line_of_sight import has_line_of_sight
        from kirby_combat.scene.scene import Position

        image = Images.get(session, image_id)
        if image is None:
            return False

        groups = [sense_group] if sense_group else list(image.sense_groups)
        groups = [g for g in groups if g in image.sense_groups]
        if not groups:
            return False

        observer = session.combatants.get(observer_id)
        if observer is None:
            return False

        scene = getattr(session, "scene", None)
        positions = getattr(scene, "combatant_positions", None) or {}
        eye = positions.get(observer_id)
        point = Position(*image.position)

        # Line Of Sight. A scene-less call or an unplaced observer fails
        # open, the same direction every other perception gate here takes.
        if scene is not None and eye is not None:
            if not has_line_of_sight(scene, eye, point):
                return False

        _, flashed = Flash.is_flashed(session, observer_id)

        # A stand-in target so the Darkness gate — which reads `.id` and a
        # position — can be asked about a point rather than a combatant.
        class _PointTarget:
            id = f"__image__{image_id}"

        target = _PointTarget()
        if scene is not None and eye is not None:
            positions = dict(positions)
            positions[target.id] = point
            scene = _ScenePositionsView(scene, positions)

        for group in groups:
            if group in flashed:
                continue
            sense = SenseCapability(xmlid="IMAGE_SENSE", name="Image", group=group)
            if scene is not None and eye is not None and _darkness_blocks(
                    observer, target, scene, sense):
                continue
            return True
        return False

    @staticmethod
    def believers(session: CombatSession, image_id: str) -> tuple[str, ...]:
        """Everyone who perceives this Image and has not seen through it.

        Excludes the caster: 6E1 p.238 has him decide what the Image is and
        where, so he is never fooled by it. That is not a rule the page
        states, because it does not need to.
        """
        image = Images.get(session, image_id)
        if image is None:
            return ()
        return tuple(
            cid for cid in session.combatants
            if cid != image.caster_id
            and Images.perceived_by(session, image_id, cid)
            and not Images.disbelieved_by(session, image_id, cid)
        )

    @staticmethod
    def believed_by(session: CombatSession, image_id: str, observer_id: str) -> bool:
        return observer_id in Images.believers(session, image_id)

    # ------------------------------------------------------------------ disbelief
    @staticmethod
    def disbelieved_by(
        session: CombatSession, image_id: str, observer_id: str,
    ) -> bool:
        """Has this ONE observer seen through this Image?

        Per (image, observer), derived from the log. A single flag on the
        Image would let the first character to make his roll spoil the
        illusion for everyone.
        """
        seen = False
        for evt in session.event_log:
            payload = getattr(evt, "result_payload", None)
            if not isinstance(payload, dict):
                continue
            if (payload.get("type") == "image_disbelief"
                    and payload.get("image_id") == image_id
                    and payload.get("observer_id") == observer_id):
                seen = seen or bool(payload.get("succeeded"))
        return seen

    @staticmethod
    def disbelieve(
        session: CombatSession,
        *,
        image_id: str,
        observer_id: str,
        extra_modifier: int = 0,
        roller=None,
    ) -> tuple[CombatSession, DisbeliefResult]:
        """One observer's PER Roll to spot the Image as an Image.

        The roll is 3d6 against the observer's own PER target, shifted by
        the Image's net ``per_modifier`` (negative for bought realism,
        positive for a complexity bonus) plus ``extra_modifier`` — which is
        where a caller puts the things 6E1 p.239 leaves to the GM: the
        imperfect-copy bonus from a failed INT Roll, the "being on the
        outside looking in" adjustment, or an observer's special knowledge.

        **A success does not remove the Image** (6E1 p.239 says so in as
        many words): the observer keeps perceiving it and now knows it is
        false. Only ``believed_by`` changes.

        An observer who cannot perceive the Image cannot roll at all — the
        page gives the roll to characters who perceive it — and gets back
        ``reason="not_perceived"`` rather than a silent failure.
        """
        from kirby_combat.perception import per_roll_target
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import ActionResolved, make_author_combatant

        if roller is None:
            roller = session.dice_roller

        image = Images.get(session, image_id)
        observer = session.combatants.get(observer_id)
        if image is None or observer is None or not Images.perceived_by(
                session, image_id, observer_id):
            return session, DisbeliefResult(
                image_id=image_id, observer_id=observer_id, succeeded=False,
                roll=0, target_number=0, reason="not_perceived",
            )

        target_number = (per_roll_target(observer)
                         + int(image.per_modifier) + int(extra_modifier))
        roll = sum(roller.roll_dice(3))
        succeeded = roll <= target_number

        evt = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(observer_id),
            declaration_event_id="",
            result_payload={
                "type": "image_disbelief",
                "image_id": image_id,
                "observer_id": observer_id,
                "roll": roll,
                "target_number": target_number,
                "succeeded": succeeded,
            },
        )
        s = apply_event(session, evt)

        return s, DisbeliefResult(
            image_id=image_id, observer_id=observer_id, succeeded=succeeded,
            roll=roll, target_number=target_number,
        )


class _ScenePositionsView:
    """A read-only Scene proxy with one extra entry in
    ``combatant_positions`` — the Image's point, under a synthetic id.

    ``perception._darkness_blocks`` looks its two endpoints up in the
    scene's position map, so asking it about a POINT means the point has to
    appear there. Wrapping rather than mutating keeps ``Images`` free of
    side effects on a shared Scene, and keeps ``_darkness_blocks`` unaware
    that anything but combatants exists.
    """

    __slots__ = ("_scene", "combatant_positions")

    def __init__(self, scene, positions):
        self._scene = scene
        self.combatant_positions = positions

    def __getattr__(self, name):
        return getattr(self._scene, name)
