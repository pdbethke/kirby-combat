"""ObjectCombatant — objects (doors, walls, vases) as Combatants with BODY/DEF.

6E2 p152: Inanimate objects have BODY and DEF (rPD/rED). They take Normal or
Killing damage like characters but have no STUN, cannot Dodge or Abort, and
cannot use powers. Some materials are vulnerable to specific damage types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from kirby_combat.models import StatBlockCombatant
from kirby_combat.participant import Breakable


# Material -> typical (DEF, BODY) ranges per 6E2 p152.
MATERIAL_DEFAULTS: dict[str, tuple[int, int]] = {
    "paper":   (0, 1),
    "glass":   (1, 1),
    "wood":    (3, 4),
    "stone":   (5, 7),
    "metal":   (7, 10),
    "steel":   (8, 12),
    "concrete": (6, 8),
}


@dataclass
class ObjectCombatant(Breakable, StatBlockCombatant):
    """An inanimate object as a StatBlockCombatant. BODY/DEF, no STUN behavior.

    ``Breakable`` supplies ``is_destroyed()``. This class used to carry its
    own identical copy (``self.current_body <= 0``), which made four
    statements of the same rule across the package. Inheriting it was a
    no-op: ``Breakable.is_destroyed`` is a plain METHOD (deliberately matched
    to the call convention here), and ``Breakable.state.current_body`` reads
    through ``StatBlockCombatant.state``, which returns ``self`` — so it sees
    the same ``current_body`` field the old copy read directly.
    """
    material: str = "wood"
    # Round-trip: HDC sometimes encodes equipment/object as raw XML; we store
    # the source string so a future serializer can re-emit it byte-for-byte.
    hdc_source_xml: str | None = None

    kind: ClassVar[str] = "object"

    @classmethod
    def make(
        cls,
        id: str, name: str,
        material: str,
        body: int | None = None,
        def_: int | None = None,
        hdc_source_xml: str | None = None,
    ) -> "ObjectCombatant":
        if material not in MATERIAL_DEFAULTS:
            raise ValueError(f"unknown material: {material}")
        default_def, default_body = MATERIAL_DEFAULTS[material]
        actual_def = def_ if def_ is not None else default_def
        actual_body = body if body is not None else default_body
        return cls(
            id=id, name=name,
            ocv=0, dcv=0, omcv=0, dmcv=0,
            spd=0, dex=0, ego=0, int_=0, str_=0, con=0,
            pre=0, rec=0,
            pd=0, ed=0, rpd=actual_def, red=actual_def, md=0,
            power_defense=0, flash_defense=0,
            max_stun=0, max_body=actual_body, max_end=0,
            current_stun=0, current_body=actual_body, current_end=0,
            is_mentalist=False, is_npc=True,
            material=material,
            hdc_source_xml=hdc_source_xml,
        )

    # ── objects have no STUN behaviour at all (6E2 p152) ──────────────
    #
    # ``StatBlockCombatant`` mixes in ``Stunnable``; an object inherits from
    # it for the stat-block fields, not for the STUN track. ``make()`` above
    # hardcodes ``current_stun=0`` because there is no track -- so the
    # inherited ``current_stun <= 0`` rule read an undamaged object as
    # unconscious. Measured 2026-08-25, before this opt-out::
    #
    #     ObjectCombatant.make(material='wood')   # an intact door
    #     -> current_stun=0  is_ko=True  is_conscious=False  is_destroyed=False
    #
    # Raising AttributeError (rather than returning False) is what actually
    # removes the member: ``hasattr(door, "is_ko")`` is then False and
    # ``getattr(door, "is_ko", default)`` takes the default, so shape-dispatch
    # code cannot be fooled into treating a door as a knock-out-able thing.
    # ``is_destroyed()`` is the question to ask an object.

    _NO_STUN = (
        "ObjectCombatant has no STUN track (6E2 p152: objects take BODY and "
        "break, they are never knocked out) -- ask is_destroyed() instead"
    )

    @property
    def is_ko(self) -> bool:
        raise AttributeError(self._NO_STUN)

    @property
    def is_conscious(self) -> bool:
        raise AttributeError(self._NO_STUN)

    def can_dodge(self) -> bool:
        return False

    def can_abort(self) -> bool:
        return False

    def takes_damage_type(self, damage_type: str) -> bool:
        """Glass takes killing damage extra well (-2 DEF vs killing).

        We expose this as a simple boolean for now; the damage adjustment
        is computed by a subsequent helper.
        """
        # All objects can be damaged in theory; vulnerabilities are tracked
        # via material defaults rather than blanket exclusions.
        return True
