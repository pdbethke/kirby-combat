"""CombatSession — the stateful combat state machine.

Per combatant-redesign step 3 (2026-05-02), the ``combatants`` dict
accepts either the legacy flat ``Combatant`` or the HD-shaped
``HeroCombatant``. The session machinery itself only reads ``.id``
on each combatant; per-combatant stat reads happen in ``actions/``
when AttackInput is built (step 4 migration).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import Combatant
from kirby_combat.session.timeline import Timeline
from kirby_combat.session.events import (
    CombatEvent, SessionStarted, SessionEnded,
    make_author_engine,
)

if TYPE_CHECKING:
    from kirby_combat.template import CombatTemplate
    from kirby_combat.dice.roller import DiceRoller


# Either flat or HD-shaped — both implement ``.id``. Live alongside
# until the migration retires LegacyCombatant in step 6.
CombatantLike = Union[Combatant, HeroCombatant]


@dataclass
class CombatSession:
    """Stateful combat session. Hybrid mutable snapshot + append-only event log."""
    id: str
    combatants: dict[str, CombatantLike]
    scene: object | None
    template: "CombatTemplate"
    timeline: Timeline
    event_log: list[CombatEvent] = field(default_factory=list)
    status: str = "setup"
    dice_roller: Optional["DiceRoller"] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        id: str,
        combatants: list[CombatantLike],
        scene: object | None,
        template: "CombatTemplate",
        dice_roller: Optional["DiceRoller"] = None,
    ) -> "CombatSession":
        return cls(
            id=id,
            combatants={c.id: c for c in combatants},
            scene=scene,
            template=template,
            timeline=Timeline(
                turn=1, segment=12,
                acting_order=[], current_slot_index=0,
            ),
            event_log=[],
            status="setup",
            dice_roller=dice_roller,
        )

    def start(self) -> "CombatSession":
        """setup → active. Emits SessionStarted. Returns new session."""
        if self.status != "setup":
            return self
        from kirby_combat.session.apply import apply_event
        evt = SessionStarted(
            id=f"{self.id}-evt-{self._next_sequence()}",
            session_id=self.id,
            sequence=self._next_sequence(),
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            scene_id=getattr(self.scene, "id", "") if self.scene else "",
            combatant_ids=list(self.combatants.keys()),
        )
        return apply_event(self, evt)

    def pause(self) -> "CombatSession":
        if self.status == "active":
            return replace(self, status="paused", updated_at=datetime.now(timezone.utc))
        return self

    def resume(self) -> "CombatSession":
        if self.status == "paused":
            return replace(self, status="active", updated_at=datetime.now(timezone.utc))
        return self

    def end(self, reason: str = "") -> "CombatSession":
        if self.status == "ended":
            return self
        from kirby_combat.session.apply import apply_event
        seq = self._next_sequence()
        evt = SessionEnded(
            id=f"{self.id}-evt-{seq}",
            session_id=self.id,
            sequence=seq,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            reason=reason,
        )
        return apply_event(self, evt)

    def _next_sequence(self) -> int:
        return len(self.event_log) + 1
