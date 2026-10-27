"""The Autofire offers: a burst at one man, a spray along several.

Built from the menu's own `attack` offers, AFTER the perception gate, so a
burst is offered only at a man the same power could be fired at once ---
in range, perceived, with ammunition --- and no gate is written twice. The
resolvers are `loop/autofire_resolvers.py`; the rules, cited, are there.

* `autofire:<target>:<power>:<shots>` --- the whole burst at one man (6E2
  p.44), or at his spot for an Autofire Area (6E2 p.45). Offered for shots
  of 2 or more: one shot is the plain `attack` offer already on the menu.
* `autofire_spray:line:<power>:<shots>` with `target_ids` --- one shot at
  each man along a line, nearest first, as many as the shots reach (one
  per 2m of line, never fewer than one a man). Not for an Area.

NOT OFFERED: hand-to-hand Autofire, Autofire at objects, an Area spray (see
`loop/autofire_resolvers.py`), a power `power_modifiers.unbuilt_reasons`
refuses (the loop filter drops those anyway).
"""
from __future__ import annotations

import math
from typing import Any


def _shots_available(power: Any, spent_charges: dict[str, int] | None) -> int:
    """The burst's shots: the power's maximum, cut to the Charges left
    (6E1 p.329: "pay Endurance (or use up Charges) for each shot")."""
    shots = int(power.autofire.shots)
    capacity = getattr(power, "charges", None)
    if capacity is not None:
        used = (spent_charges or {}).get(str(getattr(power, "source_id", "")), 0)
        shots = min(shots, int(capacity) - int(used))
    return shots


def _is_burst_power(power: Any) -> bool:
    return (getattr(power, "autofire", None) is not None
            and bool(getattr(power, "is_ranged", False))
            and int(getattr(power, "damage_dice", 0) or 0) > 0)


def _chain(here, positions: dict, ids: list[str]) -> list[str]:
    """Nearest to the shooter first, then nearest to the last man (RULING,
    labelled in `loop/autofire_resolvers.py`). Ties go to the lower id."""
    def d(a, b):
        return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))

    left = sorted(ids)
    out: list[str] = []
    at = here
    while left:
        nxt = min(left, key=lambda t: (d(at, positions[t]), t))
        out.append(nxt)
        left.remove(nxt)
        at = positions[nxt]
    return out


def _line_m(positions: dict, ids: list[str]) -> float:
    return sum(math.dist((positions[a].x, positions[a].y, positions[a].z),
                         (positions[b].x, positions[b].y, positions[b].z))
               for a, b in zip(ids, ids[1:]))


def autofire_offers(actor: Any, menu: list, *, enemies: list, scene: Any,
                    spent_charges: dict[str, int] | None) -> list:
    """The bursts this menu's `attack` offers make possible."""
    from kirby_combat.actions.autofire import shots_for_line
    from kirby_combat.enumeration import LegalAction, _friendly, _power_action_id

    named = {e.id: _friendly(e) for e in enemies}
    enemy_ids = set(named)

    by_power: dict[str, tuple[Any, list[str]]] = {}
    for a in menu:
        power = getattr(a, "_attack_view", None)
        if (a.kind != "attack" or a.target_id not in enemy_ids
                or getattr(a, "targets_construct", False) or power is None
                or not _is_burst_power(power)):
            continue
        key = str(getattr(power, "source_id", "") or "")
        entry = by_power.setdefault(key, (power, []))
        if a.target_id not in entry[1]:
            entry[1].append(a.target_id)

    out: list = []
    positions = getattr(scene, "combatant_positions", None) or {}
    for power, targets in by_power.values():
        shots = _shots_available(power, spent_charges)
        if shots < 2:
            continue
        pname = power.name or power.xmlid.lower()
        area = getattr(power, "area", None) is not None
        for tid in targets:
            out.append(LegalAction(
                action_id=f"{_power_action_id('autofire', tid, power)}:{shots}",
                kind="autofire", target_id=tid,
                power_xmlid=power.xmlid, power_name=power.name or None,
                summary=(
                    f"AUTOFIRE {pname} at {named[tid]}: {shots} shots, ONE Attack "
                    f"Roll{' against the target point (DCV 3)' if area else ''}; "
                    f"hits once, +1 hit per 2 points it makes the roll by "
                    f"(6E2 p.44{'-45' if area else ''}); END for every shot"
                ),
                _attack_view=power,
            ))
        here = positions.get(actor.id)
        placed = [t for t in targets if positions.get(t) is not None]
        if area or here is None or len(placed) < 2:
            continue
        chain = _chain(here, positions, placed)
        line: list[str] = []
        for tid in chain:
            trial = line + [tid]
            if shots_for_line(len(trial), _line_m(positions, trial)) > shots:
                break
            line = trial
        if len(line) < 2:
            continue
        need = shots_for_line(len(line), _line_m(positions, line))
        metres = _line_m(positions, line)
        out.append(LegalAction(
            action_id=f"{_power_action_id('autofire_spray', 'line', power)}:{need}",
            kind="autofire_spray", target_id=None,
            power_xmlid=power.xmlid, power_name=power.name or None,
            summary=(
                f"AUTOFIRE SPRAY {pname} along {', '.join(named[t] for t in line)}: "
                f"{need} shots "
                f"over {metres:.0f}m, -{int(metres) // 2} OCV on each man's own "
                f"roll, one hit each (6E2 p.44)"
            ),
            _attack_view=power,
            target_ids=tuple(line),
        ))
    return out
