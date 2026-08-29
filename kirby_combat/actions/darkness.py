"""Darkness — placing a field that senses cannot penetrate (6E1 p.188).

**The rule, in our own words** (this project ships no rules text; open
your own copy). Darkness fills an Area and makes it IMPENETRABLE to the
Sense Group(s) it was bought against. The page draws the contrast itself:
natural night imposes a PER penalty and Nightvision counteracts it, while
Darkness against the Sight Group cannot be seen into, out of, or through
even by someone with Nightvision. It does not make those PER Rolls
harder; it makes them impossible. Creating a field does not let you
perceive through it — that takes an Enhanced Sense or the Personal
Immunity Advantage. And a character who cannot perceive his opponent from
inside one takes the same DCV/OCV penalties as any other character who
cannot perceive an opponent with a Targeting Sense, which the page sends
the reader to 6E2 for.

**Three consequences, and each is a place an implementation goes wrong:**

1. **Not a PER modifier.** There is no roll to make, so nothing here
   touches ``per_roll_target`` or the PER machinery. The occlusion lives
   in ``perception._darkness_blocks``, which drops the sense entirely.
2. **Into, out of, AND through.** Three claims, and doing only the
   "through" one (a ray-polygon crossing test) looks right until two
   characters stand inside the same field and see each other perfectly.
   ``perception._darkness_blocks`` tests the crossing OR either endpoint
   being inside, which covers all four arrangements.
3. **The CV consequence is shared with Flash, not duplicated.** 6E1 p.188
   and 6E2 p.9/p.127 are one rule about being unable to perceive with a
   Targeting Sense, whatever took the Sense away. So Darkness reaches the
   CV seam through ``sense_penalties._targeting_senses_blocked`` — the
   same predicate Flash reaches it through. A second implementation would
   drift, and this engine has watched that happen before.

**Placement.** 6E1 p.188 requires an Attack Roll against a target Area to
put the field where the character wants it. It does not restate the
target number there; 6E2 p.45 does, naming Darkness explicitly while
setting an area-effecting attack against DCV 3, and 6E2 p.63 gives the
same number for the target point of an Area Of Effect attack. So DCV 3 is
grounded on a page that names this Power, not inferred from Barrier or
Images (which happen to agree).

**Scatter on a miss is deliberately NOT implemented.** 6E2's rules for an
attack that misses a target point scatter it to a nearby location rather
than making it vanish. Modelling that needs a scatter direction and
distance this action has no way to choose deterministically, and guessing
would put a field somewhere the book did not. A miss here places nothing
and says so in the result; a driver that wants scatter can place a second
field at the scattered point. Recorded as a known incompleteness rather
than hidden.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from kirby_combat.session.combat_session import CombatSession


#: 6E2 p.45 — an area-effecting attack (Darkness is named) rolls against
#: DCV 3. 6E2 p.63 gives the same number for an Area Of Effect target
#: point, which is why a target's own DCV and any Dodge are irrelevant.
AREA_DCV = 3


@dataclass(frozen=True)
class DarknessResult:
    attacker_id: str
    hit: bool
    roll: int
    target_number: int
    target_dcv: int
    #: Ids of the zones placed — one per Sense Group. Empty on a miss.
    construct_ids: tuple[str, ...] = ()


class Darkness:
    name: str = "darkness"

    @staticmethod
    def place(
        session: CombatSession,
        *,
        attacker_id: str,
        polygon_xy: list[tuple[float, float]],
        elevation_range_m: tuple[float, float],
        sense_groups: list[str],
        personal_immunity: bool = False,
        ocv_modifier: int = 0,
        roller=None,
    ) -> tuple[CombatSession, DarknessResult]:
        """Make the Attack Roll and, on a hit, put the field on the scene.

        **One zone per Sense Group, not one zone with a list.** The engine's
        ``Construct`` carries a single ``sense_group``, and
        ``perception._darkness_blocks`` matches on it. A Darkness bought
        against two Groups therefore becomes two Constructs sharing a
        footprint; folding them into one field with a list would have meant
        changing the Construct shape and every reader of it, for no gain —
        the geometry is identical and the gate is per-sense anyway.

        ``ocv_modifier`` carries whatever the caller has already worked out
        (the Range Modifier, Combat Skill Levels, a maneuver) rather than
        this action re-deriving any of it; it has no distance and no
        knowledge of the attacker's intent.

        The placed zones go onto the returned session's ``scene``. The
        engine's scene is what ``perception`` reads, so a placement that
        only emitted an event would leave the field invisible to the rule
        it exists to trigger. ``ConstructSpawned`` is still emitted for the
        log, matching how every other construct announces itself.
        """
        from kirby_combat.scene.construct import construct_from_spawn_spec
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.events import (
            ActionDeclared, ActionResolved, ConstructSpawned,
            make_author_combatant,
        )

        if roller is None:
            roller = session.dice_roller

        attacker = session.combatants.get(attacker_id)
        base_ocv = attacker.combat_stats().ocv if attacker is not None else 0
        effective_ocv = base_ocv + int(ocv_modifier)
        # The standard HERO to-hit formula, the same one
        # ``resolution/to_hit.py`` documents: roll 3d6 <= OCV + 11 - DCV.
        target_number = effective_ocv + 11 - AREA_DCV

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type=Darkness.name,
            targets=[],                       # an Area, not a combatant
            parameters={
                "polygon_xy": [tuple(p) for p in polygon_xy],
                "elevation_range_m": tuple(elevation_range_m),
                "sense_groups": list(sense_groups),
                "personal_immunity": bool(personal_immunity),
                "target_dcv": AREA_DCV,
                "ocv_modifier": int(ocv_modifier),
            },
        )
        s = apply_event(session, declared)

        roll = sum(roller.roll_dice(3))
        hit = roll <= target_number

        construct_ids: list[str] = []
        if hit:
            new_constructs = list(s.scene.constructs or []) if s.scene else []
            for group in sense_groups:
                obj_id = f"darkness-{uuid.uuid4().hex[:8]}"
                new_constructs.append(construct_from_spawn_spec(
                    obj_id=obj_id,
                    kind="darkness_zone",
                    segment=s.timeline.segment,
                    polygon_xy=[tuple(p) for p in polygon_xy],
                    elevation_range_m=tuple(elevation_range_m),
                    source_combatant_id=attacker_id,
                    created_at_seq=len(s.event_log),
                    sense_group=group,
                    creator_immune=bool(personal_immunity),
                ))
                construct_ids.append(obj_id)
            s = replace(s, scene=replace(s.scene, constructs=new_constructs))

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "darkness",
                "attacker_id": attacker_id,
                "hit": hit,
                "roll": roll,
                "target_number": target_number,
                "target_dcv": AREA_DCV,
                "construct_ids": list(construct_ids),
                # No scatter on a miss -- see this module's docstring.
                "scattered": False,
            },
        )
        s = apply_event(s, resolved)

        for obj_id in construct_ids:
            spawned = ConstructSpawned(
                id=str(uuid.uuid4()),
                session_id=s.id,
                sequence=len(s.event_log) + 1,
                timestamp=now,
                author=make_author_combatant(attacker_id),
                construct_id=obj_id,
                construct_kind="darkness_zone",
                source_combatant=attacker_id,
            )
            s = apply_event(s, spawned)

        return s, DarknessResult(
            attacker_id=attacker_id,
            hit=hit,
            roll=roll,
            target_number=target_number,
            target_dcv=AREA_DCV,
            construct_ids=tuple(construct_ids),
        )
