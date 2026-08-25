"""ObjectCombatant — objects (doors, walls, vases) as Combatants with BODY/DEF.

6E2 p152: Inanimate objects have BODY and DEF (rPD/rED). They take Normal or
Killing damage like characters but have no STUN, cannot Dodge or Abort, and
cannot use powers. Some materials are vulnerable to specific damage types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from kirby_combat.models import StatBlockCombatant


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
class ObjectCombatant(StatBlockCombatant):
    """An inanimate object as a StatBlockCombatant. BODY/DEF, no STUN behavior."""
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
            spd=0, dex=0, ego=0, str_=0, con=0,
            pre=0, rec=0,
            pd=0, ed=0, rpd=actual_def, red=actual_def, md=0,
            power_defense=0, flash_defense=0,
            max_stun=0, max_body=actual_body, max_end=0,
            current_stun=0, current_body=actual_body, current_end=0,
            is_mentalist=False, is_npc=True,
            material=material,
            hdc_source_xml=hdc_source_xml,
        )

    def is_destroyed(self) -> bool:
        return self.current_body <= 0

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
