"""Which offers the engine can carry out for a shaped power.

`power_modifiers` reads Area Of Effect, Constant, Damage Over Time, Side
Effects and Increased Endurance Cost off the build, and the attack door
(`actions/recording.resolve_attack_in_session`) resolves them. Only the
kinds that reach that door with the offered power can honour them, so an
offer of any other kind built from such a power would resolve as something
the build does not say --- an Area Flash blinding one man, a Constant
Mental Blast hitting once. The standing rule for this engine: what it
cannot build is not offered.

The filter runs over the finished menu in `loop/run.py` rather than inside
`enumerate_actions`, because one of its questions (Lock Out) needs the
fight's log and enumeration holds no session.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kirby_combat.power_modifiers import unbuilt_reasons

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction


#: The kinds whose resolver hands the offered power, unchanged in shape, to
#: the attack door (`loop/resolvers.py`: `_resolve_attack`, `_resolve_push`
#: and `_reposition`; and, once per shot, `_resolve_shots` for the
#: multi-shot kinds).
#:
#: THE MULTI-SHOT KINDS ARE IN, and Batch C's reason for leaving them out
#: was wrong. It read 6E1 p.321 as requiring Autofire for a multi-shot
#: Area; that page prices Autofire ON an Area, and 6E2 p.76 lists, among
#: the Multiple Attacks a character may make, "use a Blast and an RKA, Area
#: Of Effect against a single target or multiple targets". And a Constant
#: power used again is another maintained use (6E1 p.129, "affect him with
#: the power twice"). Each shot reaches the door, which shapes it.
#:
#: NOT IN: `spread` --- "Characters cannot Spread Area Of Effect attacks"
#: (6E1 p.321), and a Spread of a Constant or Damage Over Time power is not
#: a rule the book writes.
SHAPED_DOOR_KINDS = frozenset({
    "attack", "strike", "push", "move_strike", "reposition_strike",
    "multiple_attack", "rapid_fire", "sweep",
    # An Autofire Area's landings are Area uses through the door (6E2 p.45,
    # `loop/autofire_resolvers.py`). A spray of one is never offered.
    "autofire",
})

#: Kinds whose resolver places a shaped power's AREA itself, on its own
#: path (`actions/area_effects.py`): an Area Flash blinds everyone in it
#: (6E1 p.228, p.326's Kasdrevan), an Area Entangle binds everyone in it
#: (6E1 p.220). Instant only: a Constant or Damage Over Time one is not
#: built.
AREA_EFFECT_KINDS = frozenset({"flash", "entangle"})

#: Kinds whose power IS an area by nature, and whose resolver places that
#: area itself (Darkness's field, a Barrier, an Image). Their AOE modifier
#: is the size of the thing they make, not an attack on an area.
_INHERENTLY_PLACED = frozenset({"darkness_zone", "force_wall", "image_decoy"})


def shape_of(power: Any) -> tuple[Any, bool, Any]:
    """``(area, constant, damage_over_time)`` of an offered power.

    An attack view (`models.AttackPower`) carries them. A Flash, Entangle,
    Drain or Mind Control offer carries the BUILD's power itself
    (`enumeration.py` reads those straight off ``hero.powers``), which has
    no such fields --- so Batch C's filter, reading only the view's fields,
    passed every Area Flash, Area Entangle and Damage Over Time Drain
    through as a one-target power: 27 Area Flashes blinding one man. Read
    them off the build here, with the same readers `hero_view` uses.
    """
    if hasattr(power, "area") or hasattr(power, "damage_over_time"):
        return (getattr(power, "area", None),
                bool(getattr(power, "constant", False)),
                getattr(power, "damage_over_time", None))
    from kirby_combat.power_modifiers import (
        area_spec_of, damage_over_time_of, is_constant,
    )

    return area_spec_of(power), is_constant(power), damage_over_time_of(power)


def _shaped(power: Any) -> bool:
    area, constant, dot = shape_of(power)
    return area is not None or constant or dot is not None


def offer_is_buildable(session, actor_id: str, action: "LegalAction") -> bool:
    """Can the engine carry this offer out as the build describes it?"""
    from kirby_combat.lingering import locked_out

    power = getattr(action, "_attack_view", None)
    if power is None or action.kind in _INHERENTLY_PLACED:
        return True
    if unbuilt_reasons(power):
        return False
    if action.kind in AREA_EFFECT_KINDS and _shaped(power):
        from kirby_combat.actions.area_effects import area_effect_unbuilt

        return not area_effect_unbuilt(power)
    if _shaped(power) and action.kind not in SHAPED_DOOR_KINDS:
        return False
    if _shaped(power) and getattr(action, "targets_construct", False):
        # A burst at a wall is rolled off the attack door
        # (`_rapid_fire_at_construct`); it would land unshaped.
        return False
    if (getattr(power, "side_effects", None) is not None
            and action.kind not in SHAPED_DOOR_KINDS):
        # Side Effects land at the attack door (`apply_side_effects`); the
        # other resolvers never reach it.
        return False
    if action.target_id and locked_out(session, actor_id, power, action.target_id):
        return False
    return True


def offers_the_engine_can_keep(session, actor_id: str, menu: list) -> list:
    """The menu, less every offer `offer_is_buildable` refuses."""
    return [a for a in menu if offer_is_buildable(session, actor_id, a)]
