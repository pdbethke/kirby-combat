"""Vehicle = Combatant subtype. HDC-shaped fields only.

HDC alignment note: HDC treats vehicles via the same `<CHARACTER>` XML
shape as PCs, with `<CHARACTER_INFO>` fields like CHARACTER_TYPE indicating
type. Fields here mirror the canonical HD vehicle fields:
NAME, SIZE, BODY, DEF (rPD/rED), PD, ED, STUN, SPD, DEX, STR, MOVEMENT.
Combat-only state (passengers, current STUN/BODY) lives on the Combatant
parent fields established in Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import ClassVar

from kirby_combat.models import Combatant


@dataclass(frozen=True)
class Passenger:
    combatant_id: str
    seat: str                               # "driver" | "gunner" | "shotgun" | ...
    is_firing_port: bool = False


# HDC Size -> passenger capacity (6E supplements Vehicles pg 24).
_SIZE_TO_CAPACITY: dict[int, int] = {
    1: 2, 2: 4, 3: 6, 4: 6, 5: 10, 6: 10, 7: 15, 8: 20, 9: 30, 10: 50,
}


def max_passengers_for_size(size: int) -> int:
    size = max(1, min(10, size))
    return _SIZE_TO_CAPACITY[size]


@dataclass
class Vehicle(Combatant):
    """A vehicle is a Combatant with additional HDC-shaped fields.

    New fields beyond Combatant:
        size               HDC SIZE (1-10)
        movement_inches    dict of movement mode -> inches (1" = 2m)
        passengers         list[Passenger]
    """
    size: int = 1
    movement_inches: dict[str, int] = field(default_factory=dict)
    passengers: list[Passenger] = field(default_factory=list)

    # Class-level marker so apply_event and serialization can distinguish
    # Vehicle from base Combatant.
    kind: ClassVar[str] = "vehicle"

    @classmethod
    def make(
        cls,
        id: str, name: str,
        size: int, body: int, def_: int, pd: int, ed: int,
        speed: int, dex: int, str_: int,
        max_stun: int, max_end: int,
        movement_inches: dict[str, int],
        passengers: list[Passenger],
    ) -> "Vehicle":
        """Factory building a Vehicle with Combatant-compatible defaults."""
        if len(passengers) > max_passengers_for_size(size):
            raise ValueError(
                f"Vehicle {id}: {len(passengers)} passengers exceeds capacity "
                f"{max_passengers_for_size(size)} for SIZE {size}"
            )
        return cls(
            id=id, name=name,
            ocv=0, dcv=max(0, 6 - size),   # bigger = easier to hit
            omcv=0, dmcv=0,
            spd=speed, dex=dex, ego=0, str_=str_, con=0,
            pre=0, rec=0,
            pd=pd, ed=ed, rpd=def_, red=def_, md=0,
            power_defense=0, flash_defense=0,
            max_stun=max_stun, max_body=body, max_end=max_end,
            current_stun=max_stun, current_body=body, current_end=max_end,
            is_mentalist=False, is_npc=True,
            size=size,
            movement_inches=movement_inches,
            passengers=list(passengers),
        )

    def add_passenger(self, passenger: "Passenger") -> "Vehicle":
        if len(self.passengers) >= max_passengers_for_size(self.size):
            raise ValueError(
                f"Vehicle {self.id}: passenger capacity reached "
                f"({max_passengers_for_size(self.size)})"
            )
        return replace(self, passengers=[*self.passengers, passenger])

    def remove_passenger(self, combatant_id: str) -> "Vehicle":
        return replace(
            self,
            passengers=[p for p in self.passengers if p.combatant_id != combatant_id],
        )
