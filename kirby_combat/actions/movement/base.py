"""MovementAction — base for all movement powers.

Subclasses: Running, Leaping, Flight, Swimming, Teleportation, Tunneling.
Each subclass sets `name`, `base_inches`, and overrides `noncombat_multiplier`
or `end_per_10m` if the power deviates from defaults.

Movement modes per HERO 6E2:
  half-move:   distance ≤ base_inches × 1m;   DCV factor 1.0; OCV factor 1.0
  full-move:   distance ≤ base_inches × 2m;   DCV factor 0.5; OCV factor 1.0
  noncombat:   distance ≤ base_inches × 2m × noncombat_multiplier; DCV/OCV 0

(Note: in HERO, 1 inch = 2 meters. Half-move covers half the inches; the
half-move distance cap in meters is therefore base_inches × 1m.)

END cost: ceil(distance_m / 10) × end_per_10m. 1 END per 10m is the 6E default
for Running; some powers (e.g., Teleportation) may cost more.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import MovementResolved, make_author_combatant


def _decrement_end(combatant, cost: int):
    """Subtract ``cost`` from ``combatant.current_end`` and return the
    updated combatant. Handles both the flat ``StatBlockCombatant`` (END is
    a dataclass field) and ``HeroCombatant`` (END lives on a separate
    ``state`` dataclass via ``state.current_end``).

    Detection: ``StatBlockCombatant.state`` returns ``self`` (its flat
    ``current_*`` fields ARE its state), so ``combatant.state is combatant``
    distinguishes the two shapes. That identity is load-bearing here -- see
    the comment on ``StatBlockCombatant.state`` in models.py; making it
    return a copy would route every stat-block END spend into the
    HeroCombatant branch below, which ``dataclasses.replace``s a nonexistent
    ``state`` field.
    """
    from dataclasses import replace as _replace
    if combatant.state is not combatant:
        # HeroCombatant: state is a separate HeroCombatState dataclass
        new_state = _replace(combatant.state, current_end=combatant.current_end - cost)
        return _replace(combatant, state=new_state)
    # StatBlockCombatant: current_end is a field on the combatant itself.
    return _replace(combatant, current_end=combatant.current_end - cost)


_VALID_MOVE_TYPES = frozenset({"half", "full", "noncombat"})


@dataclass
class MovementAction:
    """A single movement instance: power × mode × distance.

    Construct directly for ad-hoc movement, or use a subclass (Running etc.)
    that pre-sets `name`, `base_inches`, and power-specific overrides.
    """
    name: str                        # "running", "flight", ...
    distance_m: float                # meters to move this phase
    move_type: Literal["half", "full", "noncombat"]
    base_inches: int                 # inches of movement the power provides
    noncombat_multiplier: int = 4    # default per 6E
    end_per_10m: int = 1             # default per 6E (Running)

    # ---- Mode factors -----------------------------------------------------

    def dcv_factor(self) -> float | int:
        return {"half": 1.0, "full": 0.5, "noncombat": 0}.get(self.move_type, 1.0)

    def ocv_factor(self) -> float | int:
        return {"half": 1.0, "full": 1.0, "noncombat": 0}.get(self.move_type, 1.0)

    # ---- END cost ---------------------------------------------------------

    def end_cost(self) -> int:
        if self.distance_m <= 0:
            return 0
        return math.ceil(self.distance_m / 10) * self.end_per_10m

    # ---- Validation -------------------------------------------------------

    def _max_distance_m(self) -> float:
        if self.move_type == "half":
            return self.base_inches * 1.0           # half of (inches × 2m) = inches × 1m
        if self.move_type == "full":
            return self.base_inches * 2.0
        if self.move_type == "noncombat":
            return self.base_inches * 2.0 * self.noncombat_multiplier
        return 0.0

    def validate(self, combatant: StatBlockCombatant) -> list[str]:
        """Return list of validation errors. Empty list = valid."""
        errors: list[str] = []
        if self.move_type not in _VALID_MOVE_TYPES:
            errors.append(
                f"unknown move_type {self.move_type!r}; must be one of {sorted(_VALID_MOVE_TYPES)}"
            )
            return errors    # other checks moot

        cap = self._max_distance_m()
        if self.distance_m > cap:
            errors.append(
                f"distance {self.distance_m}m exceeds {self.move_type} cap of {cap}m "
                f"(base_inches={self.base_inches})"
            )
        cost = self.end_cost()
        if combatant.current_end < cost:
            errors.append(
                f"insufficient END for {self.name}: have {combatant.current_end}, need {cost}"
            )
        return errors

    # ---- Resolve ----------------------------------------------------------

    def resolve(
        self,
        session: CombatSession,
        combatant_id: str,
    ) -> tuple[CombatSession, MovementResolved]:
        """Apply the movement: validate, emit MovementResolved, decrement END.

        Returns (new_session, event). Raises ValueError on validation failure.
        """
        from kirby_combat.session.apply import apply_event
        from dataclasses import replace

        combatant = session.combatants.get(combatant_id)
        if combatant is None:
            raise ValueError(f"combatant {combatant_id!r} not in session")
        errors = self.validate(combatant)
        if errors:
            raise ValueError(f"movement validation failed: {'; '.join(errors)}")

        cost = self.end_cost()
        # Decrement END on the combatant first (apply_event won't do it for us).
        # Both legacy Combatant (flat field) and HeroCombatant (state.current_end
        # property) need a different update path; helper handles both.
        new_combatants = dict(session.combatants)
        new_combatants[combatant_id] = _decrement_end(combatant, cost)
        session = replace(session, combatants=new_combatants)

        evt = MovementResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            from_pos=None,
            to_pos=None,
            velocity_mps=float(self.distance_m),
            move_type=self.move_type,
        )
        return apply_event(session, evt), evt
