"""CombatSession — the stateful combat state machine.

Per combatant-redesign step 3 (2026-05-02), the ``combatants`` dict
accepts either the flat ``StatBlockCombatant`` or the HD-shaped
``HeroCombatant``. The session machinery itself only reads ``.id``
on each combatant; per-combatant stat reads happen in ``actions/``
when AttackInput is built (step 4 migration).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.timeline import Timeline
from kirby_combat.session.events import (
    CombatEvent, SessionStarted, SessionEnded,
    make_author_engine,
)

if TYPE_CHECKING:
    from kirby_combat.scene.scene import Scene
    from kirby_combat.template import CombatTemplate
    from kirby_dice import DiceRoller


# Every kind of thing that can be in a fight. CombatParticipant in
# kirby_combat.participant is the ancestor; this union is what the session
# actually stores until the ABC is the only annotation needed.
CombatantLike = Union[StatBlockCombatant, HeroCombatant]


@dataclass
class CombatSession:
    """Stateful combat session. Hybrid mutable snapshot + append-only event log."""
    id: str
    combatants: dict[str, CombatantLike]
    #: The place this fight happens in. Typed as of 2026-08-26; it was `object`
    #: for no structural reason -- nothing in scene/ imports from session/, and
    #: session/ does not import scene at runtime, so no cycle ever forced it.
    #: Its partner field `combatants` was properly typed the whole time, so one
    #: half of the pair described itself and the other did not, and readers were
    #: left with `getattr(self.scene, "id", "")` standing in for a type.
    scene: "Scene | None"
    template: "CombatTemplate"
    timeline: Timeline
    event_log: list[CombatEvent] = field(default_factory=list)
    #: THE MEN AS THE FIGHT FOUND THEM --- what `combatants` was before
    #: the first event. `rewind_to_sequence` rebuilds a session by
    #: replaying the kept prefix of the log into a fresh one, and now that
    #: `apply_event` folds vitals there is no fresh one to be had from
    #: `combatants`: those are the men as the fight LEFT them, and a
    #: rewind seeded with them would replay the fight's damage on top of
    #: itself. There is no inverse to walk back to --- STUN is clamped
    #: nowhere but a Recovery is bounded by the maximum, so the fold is
    #: not injective.
    #:
    #: Filled in by `__post_init__` from `combatants` when it is not
    #: given AND the log is empty --- a session with no events has not
    #: been in a fight, so its combatants ARE the men it started with.
    #: Carried forward untouched by the `dataclasses.replace` every state
    #: change here goes through.
    #:
    #: A session constructed with events already on it and no
    #: `initial_combatants` RAISES. The men it holds are the men the
    #: fight left, inferring the start from them is a guess, and the
    #: guess is silent: every later `rewind_to_sequence` would replay the
    #: fight's damage on top of itself and return a session more hurt
    #: than the fight ever got, with nothing saying so. A consumer
    #: rebuilding a session from a snapshot has the starting combatants
    #: and must pass them.
    initial_combatants: dict[str, CombatantLike] | None = None
    #: THE BOARD AS THE FIGHT FOUND IT --- the Scene before the first
    #: event, positions and all. Exactly the same reason as
    #: `initial_combatants` above, one field over: `apply_event` folds
    #: `MovementResolved` now, so `rewind_to_sequence` seeded with
    #: `scene` would replay every step of the fight on top of the
    #: placement the fight ENDED in. Measured before it was fixed: a
    #: rewind to sequence 1 --- before anybody had taken a step --- put
    #: all three fighters on the spot they were standing on when it was
    #: over.
    #:
    #: A SNAPSHOT, not the same object. `Scene.combatant_positions` is a
    #: mutable dict by the Scene's own design, so holding the live Scene
    #: here would be holding a reference that moves with the fight.
    #: `Scene.snapshot()` copies it.
    initial_scene: "Scene | None" = None
    #: EVERY CONDITION EVERY MAN IS IN, folded from the log by
    #: `apply_event` out of `StatusEffectsChanged` --- knocked out,
    #: stunned, prone, held, entangled, flashed. Keyed by combatant id,
    #: one frozenset each, and every combatant has an entry (an empty one
    #: is "no conditions", which is a fact; a missing one would be a
    #: question).
    #:
    #: `kirby_combat.statuses.statuses_for` is the RULE --- what makes a
    #: condition true. This is the RECORD of it, and
    #: `session/state_view.py` reads this rather than deriving a second
    #: answer. `status_emission.record_status_changes` is the one door
    #: between them.
    statuses: dict[str, frozenset[str]] = field(default_factory=dict)
    status: str = "setup"
    dice_roller: Optional["DiceRoller"] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # EVERY COMBATANT HAS AN ENTRY. A missing key is a question
        # ("has he no conditions, or has nobody asked?"); an empty
        # frozenset is an answer. Seeded here so no reader needs a
        # default; anything already supplied wins, so a session
        # rehydrated from a snapshot carries its own conditions.
        self.statuses = {
            **{combatant_id: frozenset() for combatant_id in self.combatants},
            **self.statuses,
        }
        if self.initial_combatants is not None:
            if self.initial_scene is None and self.scene is not None:
                if self.event_log:
                    raise ValueError(
                        f"session {self.id!r} was built with "
                        f"{len(self.event_log)} events already on it, a "
                        f"Scene, and no `initial_scene`: the Scene it "
                        f"holds has the men where the fight LEFT them, "
                        f"and `rewind_to_sequence` replays into where it "
                        f"FOUND them. Pass the starting Scene."
                    )
                self.initial_scene = self.scene.snapshot()
            return
        if self.event_log:
            raise ValueError(
                f"session {self.id!r} was built with "
                f"{len(self.event_log)} events already on it and no "
                f"`initial_combatants`: the combatants it holds are the "
                f"men the fight LEFT, and `rewind_to_sequence` replays "
                f"into the men it FOUND. Pass the starting combatants."
            )
        self.initial_combatants = dict(self.combatants)
        if self.initial_scene is None and self.scene is not None:
            self.initial_scene = self.scene.snapshot()

    @classmethod
    def create(
        cls,
        id: str,
        combatants: list[CombatantLike],
        scene: "Scene | None",
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
