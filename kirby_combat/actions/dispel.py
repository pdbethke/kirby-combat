"""Dispel turns a power off, and its owner turns it back on (6E1 p.195).

"To use Dispel, the character must declare what power or ability he's trying
to Dispel, then make an Attack Roll. If he succeeds, he rolls and totals the
Dispel dice and subtracts the target's Power Defense (if any). If the
remaining total exceeds the Active Point total of the target power, the
target power is Dispelled - that is, it stops working. Dispel is an all or
nothing attack ... The victim of a Dispel may 'restart' the Dispelled power,
but he has to start from scratch - he must perform any preparations again."

origin/main rolled the dice, recorded the total and turned nothing off.

OFF, FOR EVERY READER. A `PowerDispelled` is folded by `apply_event` into the
target's ``hero``: it is swapped for a `HeroWithPowersOff` whose ``powers``
leave the dispelled one out. Everything that reads a power off the build ---
the defences `combat_stats()` totals, `defense_view`, `attacks`, movement,
Invisibility in `perception` --- reads the build without it, without being
told about Dispel at all.

BACK ON. "Activating a Power" is a Zero Phase Action at the start of a Phase
(6E2 p.20), so `restart_dispelled` turns it back on at the top of its
owner's next Phase in which he can act at all (a Stunned man takes no
Actions, 6E2 p.106). RULING: he always does --- nothing in a fight is served
by leaving your Force Field off --- and "any preparations" are not modelled:
a power bought with Extra Time to start comes back as quickly as any other.

NOT BUILT, so not offered:
- a Dispel whose INPUT names a special-effect group ("Fire", "Magic",
  "Technological Object" --- most of the corpus): which of the target's
  powers are Fire is not something a build records. HD has a per-power
  ``SFX`` attribute, and in the local corpus 67,417 of its 67,488 values are
  "Default"; the 71 others are Light, Ice/Cold, Mutant, Electricity,
  Darkness, Vibration, Water, Miscellaneous, Magic/Mystic, Light or Radio
  and Botany. Not one is Fire or Magic, the groups most Dispels name, and
  matching "Electricity Powers" to "Electricity" would be a string guess.
  (Checked 2026-10-27; the same holds for Drain/Aid inputs like "Magic
  Powers" and "Energy Powers");
- a Dispel on a combatant rebuilt from a snapshot, whose views were
  recorded rather than derived and cannot leave a power out;
- Dispelling an incoming attack with a Held Action (6E1 p.195). "Assuming
  the Dispel applies to the attack" --- and no corpus Dispel names an attack
  power: the 13 INPUTs are Magic, Magic Powers, Technological Object,
  Summon, Invisibility, Fire, Fire Powers, Holy Powers, Electronic Devices,
  Electricity Powers, Electrical Device Powers, EM Spectrum-Based Powers and
  Desolidification. With nothing that could ever be offered, the door is
  not built.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: "Dispel cannot affect Characteristics; use Drain for that sort of effect"
#: (6E1 p.195). A characteristic bought as a power is still one.
_CHARACTERISTICS = frozenset({
    "STR", "DEX", "CON", "INT", "EGO", "PRE", "OCV", "DCV", "OMCV", "DMCV",
    "SPD", "PD", "ED", "REC", "END", "BODY", "STUN", "RUNNING", "SWIMMING",
    "LEAPING",
})


class HeroWithPowersOff:
    """A build with some of its powers switched off.

    Everything is the build's own except ``powers`` and ``equipment``, which
    leave the dispelled ones out. ``original`` is the build itself, which
    is what a restart and a snapshot go back to.
    """

    def __init__(self, original, off: frozenset[str]):
        self.original = original
        self.off = frozenset(off)

    def _on(self, items):
        return _without(items, self.off)

    @property
    def powers(self):
        return self._on(self.original.powers)

    @property
    def equipment(self):
        return self._on(getattr(self.original, "equipment", None))

    def __getattr__(self, name):
        # Only reached for what this class does not define; `original` is
        # always set in __init__, so asking for it here means a half-built
        # object (copy/pickle), and recursing into it would never end.
        if name == "original":
            raise AttributeError(name)
        return getattr(self.original, name)


class _PurchaseWithPartsOff:
    """A framework (or List, or Compound Power) with some of its parts off.

    A Disarm takes ONE object, and a slot bought with its own Accessible
    Focus inside a framework that is not is one (`kirby_combat.weapons`), so
    switching off only top-level purchases could not take it. Everything is
    the purchase's own except the part lists, which leave the off ones out.
    """

    def __init__(self, original, off: frozenset[str]):
        self.original = original
        self.off = frozenset(off)

    @property
    def sub_powers(self):
        return _without(getattr(self.original, "sub_powers", None), self.off)

    @property
    def objects(self):
        return _without(getattr(self.original, "objects", None), self.off)

    @property
    def powers(self):
        return _without(getattr(self.original, "powers", None), self.off)

    def __getattr__(self, name):
        if name == "original":
            raise AttributeError(name)
        return getattr(self.original, name)


_PART_LISTS = ("sub_powers", "objects", "powers")


def _without(items, off: frozenset[str]):
    """``items`` less the purchases in ``off``, at any depth."""
    out = []
    for p in items or []:
        if str(getattr(p, "id", "")) in off:
            continue
        if any(str(getattr(c, "id", "")) in off
               for c in _parts(p)):
            p = _PurchaseWithPartsOff(p, off)
        out.append(p)
    return out


def _parts(purchase):
    """Every part under a purchase, at any depth."""
    stack = []
    for attr in _PART_LISTS:
        nested = getattr(purchase, attr, None)
        if isinstance(nested, list):
            stack.extend(nested)
    seen: set[int] = set()
    while stack:
        p = stack.pop()
        if id(p) in seen:
            continue
        seen.add(id(p))
        yield p
        for attr in _PART_LISTS:
            nested = getattr(p, attr, None)
            if isinstance(nested, list):
                stack.extend(nested)


def original_hero(hero):
    return hero.original if isinstance(hero, HeroWithPowersOff) else hero


def dispelled_ids(session: "CombatSession", combatant_id: str) -> frozenset[str]:
    """The powers of his that are off now, folded from the log."""
    off: set[str] = set()
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if kind == "PowerDispelled" and evt.target_id == combatant_id:
            off.add(evt.power_id)
        elif kind == "PowerRestarted" and evt.combatant_id == combatant_id:
            off.discard(evt.power_id)
    return frozenset(off)


def fold_dispel(session: "CombatSession", combatant_id: str) -> "CombatSession":
    """Swap the combatant's build for one with his dispelled powers off (or
    back to the build when none are). What `apply_event` calls."""
    from dataclasses import replace

    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        raise ValueError(
            f"{combatant_id!r} is not a combatant in session {session.id!r}")
    # A weapon out of his hand is off the same way (`kirby_combat.weapons`).
    from kirby_combat.weapons import out_of_hand_ids

    off = dispelled_ids(session, combatant_id) | out_of_hand_ids(session, combatant_id)
    base = original_hero(combatant.hero)
    hero = HeroWithPowersOff(base, off) if off else base
    combatants = {**session.combatants, combatant_id: replace(combatant, hero=hero)}
    return replace(session, combatants=combatants)


# ---------------------------------------------------------------------------
# What a Dispel can be aimed at
# ---------------------------------------------------------------------------

def _key(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def dispellable_on(dispel, target) -> list:
    """The target's powers this Dispel is bought against, by power type.

    INPUT names the power (6E1 p.195: "must declare what power or ability
    he's trying to Dispel"); it matches a power whose xmlid it spells
    ("Invisibility", "Force Field"). Empty for a special-effect group and
    for a snapshot-rebuilt target --- see the module docstring.
    """
    if getattr(target, "snapshot", None) is not None:
        return []
    wanted = _key(getattr(dispel, "input", None) or "")
    if not wanted or wanted in _CHARACTERISTICS:
        return []
    from kirby_combat.identity import in_play

    # A power he bought Only In Alternate Identity is not running while he
    # is out of it (6E1 p.388), so there is nothing there to Dispel.
    return [
        p for p in (original_hero(target.hero).powers or [])
        if _key(getattr(p, "xmlid", "")) == wanted and getattr(p, "id", None)
        and in_play(p, in_hero_id=target.state.in_hero_id)
    ]


def resistance(power) -> int:
    """The Active Points a Dispel must exceed: the power's own, doubled for
    each level of Difficult To Dispel (6E1 p.335: "it doubles the Active
    Points in that power (not including the points spent on this Advantage)
    for purposes of determining the effects of Dispel")."""
    from kirby_combat.hero_view import _modifier_levels

    active = int(float(getattr(power, "active_cost", 0) or 0))
    return active * (2 ** _modifier_levels(power, "DIFFICULTTODISPEL"))


# ---------------------------------------------------------------------------
# Using it
# ---------------------------------------------------------------------------

def resolve_dispel(session, actor, action, *, roller, template):
    """Returns (session, payload). The offer names the target power at the
    end of its action_id (``...:power=<id>``)."""
    from kirby_combat.actions.adjust import _record, attack_roll
    from kirby_combat.adjustments import roll_effect
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import PowerDispelled, make_author_combatant

    if action.target_id is None:
        raise ValueError(f"{action.action_id!r}: a Dispel names its target")
    dispel = action._attack_view
    target = session.combatants[action.target_id]
    tail = action.action_id.rsplit(":", 1)[-1]
    wanted = tail[len("power="):] if tail.startswith("power=") else None
    power = next((p for p in dispellable_on(dispel, target)
                  if str(p.id) == wanted), None)
    if power is None:
        raise ValueError(
            f"{action.action_id!r} names no power of {target.id!r} this Dispel reaches")

    payload: dict = {
        "kind": action.kind, "target_id": target.id,
        "power_source_id": str(getattr(dispel, "id", "") or ""),
        "target_power_id": str(power.id),
        "target_power_xmlid": (power.xmlid or "").upper(),
    }
    to_hit = attack_roll(session, actor, target, dispel, roller, template)
    payload.update(hit=to_hit.hit, roll=to_hit.roll, target_number=to_hit.target_number)
    if not to_hit.hit:
        payload["dispelled"] = False
        return _record(session, actor, action, payload), payload

    rolled = roll_effect(dispel, roller)
    power_defense = int(target.combat_stats().power_defense)
    total = max(0, rolled - power_defense)
    needed = resistance(power)
    # "If the remaining total EXCEEDS the Active Point total" --- the
    # driver this replaces dispelled on a tie (>=), which the page does not.
    success = total > needed
    payload.update(active_points_rolled=rolled, power_defense=power_defense,
                   total=total, target_active_points=needed, dispelled=success)
    session = _record(session, actor, action, dict(payload))
    if success:
        session = apply_event(session, PowerDispelled(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(actor.id),
            target_id=target.id, power_id=str(power.id),
            power_xmlid=(power.xmlid or "").upper(), source_combatant=actor.id,
        ))
    return session, payload


def restart_dispelled(session: "CombatSession", combatant_id: str) -> "CombatSession":
    """Turn his dispelled powers back on, at the start of his Phase.

    6E2 p.20: "Other Zero Phase Actions include activating a Power". Called
    by `run_phase` once it knows he can act this Phase.
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import PowerRestarted, make_author_combatant

    for power_id in sorted(dispelled_ids(session, combatant_id)):
        session = apply_event(session, PowerRestarted(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id, power_id=power_id,
        ))
    return session
