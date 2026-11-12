"""What the menu offers a Multipower: one re-split, and its presets.

6E1 p.404-406: the reserve is divided among the slots, a FIXED slot at its
full Active Points or not at all (p.404-405), a VARIABLE slot in any share
from 0 to its Active Points (p.405), all of them together within the reserve
(p.406). p.410: re-dividing it is a Zero Phase Action, once a Phase. A
variable share is unbounded, so the menu makes ONE offer per Multipower that
has a variable slot (`framework.SplitChoice`), answered with the points; and
a short list of PRESETS a person at the table can read and pick (spec §5.3):

1. the player's own standing splits (spec §5.5a), by position;
2. **All in <slot>**: one per variable slot, as high as it goes, the rest to
   the other variable slots in slot order;
3. **Even**: the reserve shared among the variable slots as evenly as their
   steps allow;
4. **<fixed slot> + remainder**: one per fixed slot that fits, the rest to
   the variable slots in slot order.

A Multipower with ONLY fixed slots has no share to suggest: its neutral
presets are the whole sets its reserve can carry (`whole_sets`), the same
sets its re-split offers name.

THE OPENING (spec §5.2, decision 7) is the same offer with nothing in force:
`opening_offer`. The fight does not start until each Multipower's seat has
stated one.

Duplicates collapse (the first name wins, so a player's own split beats a
neutral one that happens to equal it) and a preset equal to the split in
force is dropped: answering with it changes nothing (`SplitChoice.parse`).

NEUTRAL BY CONSTRUCTION: nothing here reads the board, a threat or an
enemy. Which split suits the fight is the seat's call; the menu only lists
splits worth naming.

"Best fitting step": the highest rung of a slot's priced ladder at or under
the points left. A share that falls between rungs is legal (6E1 p.406:
Kerendor's 9-point Resistant Protection) but buys no more than the rung
below it, so a remainder may leave a few points unspent.

Every word of an effect is kirby-cost's (`SlotStep.display`, from
`kirby_cost.engine.allocation.step_display`); this module only joins them.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.framework import (
    Preset, ReserveExceeded, SplitChoice, StandingSplit, split_choice_of,
    validate_split,
)

if TYPE_CHECKING:
    from kirby_combat.models import FrameworkView, PricedSlotView

#: What an effect reads as when no slot holds a point.
NOTHING_ON = "nothing switched on"


def _rung(slot: "PricedSlotView", points: int):
    """The rung a slot holding ``points`` stands on: the highest at or under
    them (6E1 p.406)."""
    return [st for st in slot.steps if st.points <= points][-1]


def slot_display(slot: "PricedSlotView", points: int) -> str:
    """What a slot holding ``points`` does, in kirby-cost's words ("" at
    0): the display of the rung it stands on."""
    return _rung(slot, points).display


def _best_fit(slot: "PricedSlotView", points: int) -> int:
    """The most a variable slot can usefully take out of ``points``."""
    return _rung(slot, min(points, slot.active_points)).points


def effect_text(view: "FrameworkView", points: dict[str, int], *,
                lead: str | None) -> str:
    """What ``points`` buys, in words: each slot holding a point, its rung's
    display, joined. ``lead`` (a slot id) is named first, the rest in slot
    order; with nothing on, `NOTHING_ON`."""
    order = sorted(view.slots, key=lambda s: s.slot_id != lead)
    words = [slot_display(s, points[s.slot_id]) for s in order
             if points.get(s.slot_id, 0) > 0]
    return ", ".join(words) if words else NOTHING_ON


def _fill(view: "FrameworkView", split: dict[str, int], left: int) -> dict[str, int]:
    """Give ``left`` points to the variable slots still at 0, in slot order,
    each at its best fitting step."""
    out = dict(split)
    for slot in view.slots:
        if slot.variable and out[slot.slot_id] == 0 and left > 0:
            out[slot.slot_id] = _best_fit(slot, left)
            left -= out[slot.slot_id]
    return out


def _even(view: "FrameworkView", reserve: int) -> dict[str, int]:
    """The reserve shared among the variable slots as evenly as their steps
    allow: an equal share each, then what the steps left over, in slot
    order."""
    split = {s.slot_id: 0 for s in view.slots}
    variables = [s for s in view.slots if s.variable]
    share = reserve // len(variables)
    for slot in variables:
        split[slot.slot_id] = _best_fit(slot, share)
    left = reserve - sum(split.values())
    for slot in variables:
        if left <= 0:
            break
        held = split[slot.slot_id]
        split[slot.slot_id] = _best_fit(slot, held + left)
        left -= split[slot.slot_id] - held
    return split


def _neutral(view: "FrameworkView") -> list[tuple[str, dict[str, int], str]]:
    """``(name, split, lead slot)`` for the neutral presets, in menu order."""
    reserve = int(view.reserve_or_pool)
    off = {s.slot_id: 0 for s in view.slots}
    out = []
    for slot in view.slots:
        if slot.variable:
            top = _best_fit(slot, reserve)
            out.append((f"All in {slot.name}",
                        _fill(view, {**off, slot.slot_id: top}, reserve - top),
                        slot.slot_id))
    out.append(("Even", _even(view, reserve), None))
    for slot in view.slots:
        if not slot.variable and slot.active_points <= reserve:
            out.append((f"{slot.name} + remainder",
                        _fill(view, {**off, slot.slot_id: slot.active_points},
                              reserve - slot.active_points),
                        slot.slot_id))
    return out


def whole_sets(view: "FrameworkView") -> list[tuple[str, ...]]:
    """The sets of slots a FIXED-only Multipower can have on at once (6E1
    p.404-405: each at its full Active Points or off; p.404: within the
    reserve). Everything when the reserve carries it all, no reason to make
    him switch one at a time; otherwise each slot that fits by itself. A
    slot bigger than the whole reserve can never be on.

    Power Lad's five 44-45 point slots against a 45-point reserve draw 224
    together: offering them as one set is the menu offering what the engine
    refuses, which he chose 152 times in one fight.
    """
    reserve = int(view.reserve_or_pool or 0)
    points = {s.slot_id: int(s.active_points) for s in view.slots}
    if reserve and sum(points.values()) <= reserve:
        return [tuple(points)]
    return [(sid,) for sid, cost in points.items() if reserve and cost <= reserve]


def _whole_set_presets(view: "FrameworkView") -> list[tuple[str, dict[str, int], str | None]]:
    """``(name, split, lead slot)`` for each of `whole_sets`: a single slot
    by its own name, everything as "Everything on"."""
    names = {s.slot_id: s.name for s in view.slots}
    off = {s.slot_id: 0 for s in view.slots}
    full = {s.slot_id: int(s.active_points) for s in view.slots}
    out = []
    for slots in whole_sets(view):
        points = {**off, **{sid: full[sid] for sid in slots}}
        if len(slots) == 1:
            out.append((names[slots[0]], points, slots[0]))
        else:
            out.append(("Everything on", points, None))
    return out


def standing_refusals(view: "FrameworkView",
                      standing: tuple[StandingSplit, ...]) -> list[tuple[StandingSplit, str]]:
    """Each standing split that no longer fits the build in play, with the
    rule it breaks (6E1 p.404-406). Left off the menu, never trimmed to fit
    (spec §5.5a)."""
    out = []
    for sp in sorted(standing, key=lambda sp: sp.position):
        try:
            validate_split(view, dict(sp.points))
        except ReserveExceeded as exc:
            out.append((sp, f"it draws {exc.requested} Active Points from a "
                            f"{exc.reserve}-point reserve (6E1 p.404)"))
        except KeyError:
            out.append((sp, f"it names a slot {view.name} no longer has"))
        except ValueError as exc:      # the slot's kind forbids the share
            out.append((sp, str(exc)))
    return out


def presets_for(view: "FrameworkView", current: dict[str, int],
                standing: tuple[StandingSplit, ...]) -> tuple[Preset, ...]:
    """The presets for ``view`` (a PRICED view) given the split in force and
    the player's standing splits; see the module docstring for the order."""
    refused = [sp for sp, _ in standing_refusals(view, standing)]
    off = {s.slot_id: 0 for s in view.slots}
    named: list[Preset] = []
    for sp in sorted(standing, key=lambda sp: sp.position):
        if sp in refused:
            continue
        points = {**off, **sp.points}
        named.append(Preset(sp.name, points,
                            effect_text(view, points, lead=None),
                            standing=True, standard=sp.standard))
    neutral = (_neutral(view) if any(sl.variable for sl in view.slots)
               else _whole_set_presets(view))
    for name, points, lead in neutral:
        named.append(Preset(name, points, effect_text(view, points, lead=lead),
                            standing=False, standard=False))
    # Before the opening ({}) nothing is in force, so nothing is "as is".
    seen: list[dict[str, int]] = [{**off, **current}] if current else []
    out = []
    for preset in named:
        if preset.points in seen:
            continue
        seen.append(preset.points)
        out.append(preset)
    return tuple(out)


def split_offer(view: "FrameworkView", current: dict[str, int],
                standing: tuple[StandingSplit, ...]) -> tuple[SplitChoice, str]:
    """The re-split offer's choice and its words, for a PRICED view of a
    Multipower with a variable slot and the split in force:
    "Re-split Magical Powers (60 reserve): now Blast 12d6"."""
    choice = split_choice_of(view, current, presets_for(view, current, standing))
    in_force = {**{s.slot_id: 0 for s in view.slots}, **current}
    summary = (f"Re-split {view.name} ({int(view.reserve_or_pool)} reserve): "
               f"now {effect_text(view, in_force, lead=None)}")
    return choice, summary


def opening_offer(view: "FrameworkView",
                  standing: tuple[StandingSplit, ...]) -> tuple[SplitChoice, str]:
    """The opening split's choice and its words, for a PRICED view of any
    Multipower, variable slots or not (spec §5.2, decision 7).

    6E1 p.404-406: the reserve is divided among the slots before the fight
    begins. Nothing is in force yet (``current`` is {}), so no preset is
    dropped as "as is", and every legal split, nothing-on included, is an
    answer (`SplitChoice.parse`). The player's standing splits come first and his standard combat
    set is marked (`SplitChoice.standard`); none is applied without an
    answer.
    """
    choice = split_choice_of(view, {}, presets_for(view, {}, standing))
    summary = (f"Open {view.name} ({int(view.reserve_or_pool)} reserve): state "
               f"the split it starts the fight with")
    return choice, summary
