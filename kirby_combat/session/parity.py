"""Replay parity: a fight rebuilt from its own log is the fight that ran.

Two-databases spec §6 R1: the Danger Room (Peter, 2026-11-24: "the goal is
not to re-fight a fight. the goal is to replay it accurately"). A replay
folds the log from the opening state through `apply_event`, so ANY state
the engine changes without an event `apply_event` folds is lost from the
replay. That is a recurring defect class, until now found one live fight at
a time (the Darkness field that vanished on 2026-11-11; the Force Wall; the
recoveries that emitted nothing).

`divergence(live)` rebuilds the session from its log and names every place
the two differ. It compares what a viewer of the replay would see: each
combatant's vitals, position and conditions, the clock and acting order,
the board's constructs and walls, and the fight's status. An empty list is
parity. The comparison is by `to_dict`, the engine's own wire form, so it
reads exactly what a consumer persists and replays.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


@dataclass(frozen=True)
class Difference:
    """One place the replay differs from the live fight."""

    where: str
    live: Any
    replayed: Any

    def __str__(self) -> str:
        return f"{self.where}: live {self.live!r}, replayed {self.replayed!r}"


def rebuilt(session: "CombatSession") -> "CombatSession":
    """The session folded from its opening state through its whole log."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.combat_session import CombatSession

    fresh = CombatSession.create(
        id=session.id,
        combatants=list(session.initial_combatants.values()),
        scene=(session.initial_scene.snapshot()
               if session.initial_scene is not None else None),
        template=session.template,
        dice_roller=session.dice_roller,
    )
    for event in session.event_log:
        fresh = apply_event(fresh, event)
    return fresh


def _view(session: "CombatSession") -> dict[str, Any]:
    """What a replay viewer sees, in the engine's wire form."""
    from kirby_combat.serialization import to_dict

    scene = session.scene
    return {
        "status": session.status,
        "timeline": to_dict(session.timeline),
        "statuses": {k: sorted(v) for k, v in session.statuses.items()},
        "combatants": {cid: to_dict(c) for cid, c in session.combatants.items()},
        "positions": (to_dict(dict(scene.combatant_positions))
                      if scene is not None else None),
        "constructs": (to_dict(list(getattr(scene, "constructs", []) or []))
                       if scene is not None else None),
        "walls": (to_dict(list(getattr(scene, "walls", []) or []))
                  if scene is not None else None),
    }


def _diff(path: str, live: Any, replayed: Any, out: list[Difference]) -> None:
    if isinstance(live, dict) and isinstance(replayed, dict):
        for key in sorted(set(live) | set(replayed), key=str):
            _diff(f"{path}.{key}", live.get(key, "<absent>"),
                  replayed.get(key, "<absent>"), out)
        return
    if (isinstance(live, list) and isinstance(replayed, list)
            and len(live) == len(replayed)):
        for i, (a, b) in enumerate(zip(live, replayed)):
            _diff(f"{path}[{i}]", a, b, out)
        return
    if live != replayed:
        out.append(Difference(path, live, replayed))


def divergence(live: "CombatSession") -> list[Difference]:
    """Every place the fight rebuilt from ``live``'s log differs from
    ``live``. Empty is parity."""
    out: list[Difference] = []
    _diff("session", _view(live), _view(rebuilt(live)), out)
    return out


__all__ = ["Difference", "divergence", "rebuilt"]
