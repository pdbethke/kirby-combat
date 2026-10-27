"""When a Recovery gives back less than REC, or nothing at all.

Two rules the book writes and the engine did not keep; Batch C listed both
as missing.

  * HOLDING HIS BREATH. 6E2 p.132: "A character who holds his breath does
    not get to Recover, even on Post-Segment 12." The engine has drowned
    men since Batch C (`zone_effects._drown`), and every one of them took
    his free Post-Segment 12 Recovery under water.
  * DAMAGE OVER TIME. 6E1 p.333: "In most cases, the victim of a Damage
    Over Time attack cannot Recover any of the damage sustained until the
    Damage Over Time has entirely run its course. He can still Recover STUN
    or BODY lost to other means". So the STUN a running Damage Over Time
    has taken from him is held back from every Recovery until it ends; the
    rest comes back as usual.

Both are asked of the man as the log has him now, by the two Recovery
doors: the free Post-Segment 12 Recovery (`encounter._apply_post_12_recovery`)
and the Recovery he takes as an Action (`loop/resolvers._resolve_recover`).
END is not held back by a Damage Over Time: it takes none.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def holding_breath(session: "CombatSession", combatant_id: str) -> bool:
    """Is he in water he cannot breathe, now?

    The same question `zone_effects` asks before it drowns him: an
    ``every_segment`` suffocation zone around him that he neither breathes
    in (Life Support) nor swims in (`construct_effects`).
    """
    from kirby_combat.construct_effects import resolve_construct_effect
    from kirby_world.construct import constructs_containing

    scene = getattr(session, "scene", None)
    combatant = session.combatants.get(combatant_id)
    if scene is None or combatant is None:
        return False
    here = (getattr(scene, "combatant_positions", None) or {}).get(combatant_id)
    if here is None:
        return False
    zones = [c for c in (getattr(scene, "constructs", None) or [])
             if getattr(getattr(c, "effect", None), "kind", None) == "suffocation"]
    for construct in constructs_containing(here, zones):
        res = resolve_construct_effect(construct, combatant, segment_tick=True)
        if res is not None and res.outcome == "suffocating":
            return True
    return False


def stun_held_by_damage_over_time(session: "CombatSession",
                                  combatant_id: str) -> int:
    """STUN that running Damage Over Time has taken from him (6E1 p.333).

    Every dose of a one-target Damage Over Time still running
    (`lingering.py`), and of a Damage Over Time zone still standing
    (`standing_areas.py`), whose row names him.
    """
    from kirby_combat.lingering import LingeringMode, active_lingering
    from kirby_combat.standing_areas import StandingMode, active_standing_areas

    running = {e.id for e in active_lingering(
        session, target_id=combatant_id, mode=LingeringMode.DAMAGE_OVER_TIME)}
    running |= {a.id for a in active_standing_areas(
        session, mode=StandingMode.DAMAGE_OVER_TIME)}
    if not running:
        return 0
    held = 0
    for event in session.event_log:
        if getattr(event, "kind", "") != "ActionResolved":
            continue
        p = event.result_payload or {}
        if p.get("target_id") != combatant_id:
            continue
        if p.get("lingering_id") in running or p.get("standing_area_id") in running:
            held += int(p.get("stun_dealt", 0) or 0)
    return held


def allowed_recovery(session: "CombatSession", combatant,
                     stun: int, end: int) -> tuple[int, int]:
    """``(stun, end)`` of a Recovery worth ``(stun, end)``, as the rules
    above let him have it."""
    if holding_breath(session, combatant.id):
        return 0, 0
    held = stun_held_by_damage_over_time(session, combatant.id)
    if held:
        ceiling = int(combatant.combat_stats().max_stun) - held
        room = max(0, ceiling - int(combatant.state.current_stun))
        stun = min(stun, room)
    return stun, end


def without_futile_recovery(session: "CombatSession", actor_id: str,
                            menu: list) -> list:
    """A man holding his breath "does not get to Recover" (6E2 p.132), so a
    Recovery is not offered to him: it would spend his Phase on nothing."""
    if not any(a.kind == "recover" for a in menu):
        return menu
    if not holding_breath(session, actor_id):
        return menu
    return [a for a in menu if a.kind != "recover"]
