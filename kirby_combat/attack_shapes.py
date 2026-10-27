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
#: and `_reposition`). Multi-shot kinds (`rapid_fire`, `sweep`, `spread`,
#: `multiple_attack`) also reach the door, once per shot, which is wrong for
#: all three shapes: 6E1 p.321 requires Autofire for a multi-shot Area
#: (unbuilt), and a Constant or Damage Over Time power used several times in
#: a Phase is not a rule the book writes.
SHAPED_DOOR_KINDS = frozenset({
    "attack", "strike", "push", "move_strike", "reposition_strike",
})

#: Kinds whose power IS an area by nature, and whose resolver places that
#: area itself (Darkness's field, a Barrier, an Image). Their AOE modifier
#: is the size of the thing they make, not an attack on an area.
_INHERENTLY_PLACED = frozenset({"darkness_zone", "force_wall", "image_decoy"})


def _shaped(power: Any) -> bool:
    return (getattr(power, "area", None) is not None
            or bool(getattr(power, "constant", False))
            or getattr(power, "damage_over_time", None) is not None)


def offer_is_buildable(session, actor_id: str, action: "LegalAction") -> bool:
    """Can the engine carry this offer out as the build describes it?"""
    from kirby_combat.lingering import locked_out

    power = getattr(action, "_attack_view", None)
    if power is None or action.kind in _INHERENTLY_PLACED:
        return True
    if unbuilt_reasons(power):
        return False
    if _shaped(power) and action.kind not in SHAPED_DOOR_KINDS:
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
