"""Unit — aggregation of identical combatants for mass combat."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class UnitMorale(Enum):
    FRESH = "fresh"                           # +1 to checks
    STEADY = "steady"                         # no modifier
    SHAKEN = "shaken"                         # -2 to checks
    ROUTING = "routing"                       # forced to flee
    BROKEN = "broken"                         # destroyed / surrendered


@dataclass
class Unit:
    """A pack of N identical combatants resolved in aggregate."""
    id: str
    name: str
    archetype_combatant_id: str
    count: int
    initial_count: int
    aggregate_body_pool: int                  # total BODY across unit members
    morale: UnitMorale
    archetype_body_per: int
    archetype_stun_per: int
    archetype_dex: int

    @classmethod
    def from_archetype(
        cls, id: str, name: str, archetype_combatant_id: str,
        count: int, morale: UnitMorale,
        body_per: int = 10, stun_per: int = 15, dex: int = 10,
    ) -> "Unit":
        return cls(
            id=id, name=name,
            archetype_combatant_id=archetype_combatant_id,
            count=count, initial_count=count,
            aggregate_body_pool=body_per * count,
            morale=morale,
            archetype_body_per=body_per,
            archetype_stun_per=stun_per,
            archetype_dex=dex,
        )

    def take_aggregate_damage(self, body: int) -> "Unit":
        """Apply damage across the unit; count drops proportionally."""
        new_pool = max(0, self.aggregate_body_pool - body)
        per = self.archetype_body_per or 1
        new_count = max(0, new_pool // per)
        return replace(self, count=new_count, aggregate_body_pool=new_pool)

    @property
    def needs_morale_check(self) -> bool:
        """True when unit has lost 25%+ of initial count."""
        if self.initial_count == 0:
            return False
        loss_pct = (self.initial_count - self.count) / self.initial_count
        return loss_pct >= 0.25 and self.morale != UnitMorale.ROUTING

    def fail_morale_check(self) -> "Unit":
        """Drop morale one tier. BROKEN -> stays BROKEN."""
        order = [
            UnitMorale.FRESH, UnitMorale.STEADY, UnitMorale.SHAKEN,
            UnitMorale.ROUTING, UnitMorale.BROKEN,
        ]
        idx = order.index(self.morale)
        new_morale = order[min(idx + 1, len(order) - 1)]
        return replace(self, morale=new_morale)

    def can_act_offensively(self) -> bool:
        return self.morale in (UnitMorale.FRESH, UnitMorale.STEADY, UnitMorale.SHAKEN)

    def is_destroyed(self) -> bool:
        return self.count == 0 or self.morale == UnitMorale.BROKEN
