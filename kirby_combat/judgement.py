"""What a fighter can JUDGE of one enemy, instead of his sheet.

A man across a street does not know another man's STUN, PD or SPD. He sees
how hurt the other looks, what he has been seen to do, how the blows that
landed on him visibly landed, and what kind of thing he is. This module
builds exactly that, from the fight's record and the combatant, and nothing
else: no characteristic, no defence value and no vital reaches it.

PURE. It reads the situation, the session's event log and the combatant; it
rolls nothing (perception comes from `brief_detail.sightings`, which never
rolls) and writes nothing. Wiring it into the Brief is not done here.

RULINGS
* UNPERCEIVED, REVEALS NOTHING. An enemy `sightings` says the actor cannot
  perceive is named and sided and nothing more: no looks, no powers, no
  hits, no features, no distance. What you cannot perceive you cannot judge.
* SEEN POWERS. The log does not record who saw what, so v1 counts every
  power he has used this fight while he is perceived NOW. A use that
  happened while he was hidden is therefore read back once he is in view.
  Accepted: the alternative is a per-observer perception history the engine
  does not keep.
* HOW HITS LANDED. One line per `ActionResolved` that hit him: the power's
  name and what visibly followed (`status_changes`, else "kept fighting").
  No STUN or BODY numbers: a visible consequence, or its absence, is what
  anyone watching sees.
* LOOKS. `health.classify_health`'s word ("healthy" / "wounded" /
  "critical"), the rung the rest of the engine already cuts from. It is how
  hurt he LOOKS; the percentage behind it stays on his sheet.
* A MOOK only when `minor_hits` is set AND the template has any of the
  minor-NPC rules on (6E2 p.121-122; `mooks.py`): in cinematic play extras
  look like extras, and under RAW rules `minor_hits` changes nothing, so it
  is not shown either.
* A MACHINE when his build in play has an AUTOMATON power. A robot looks
  like a robot; the engine has no machine concept yet, and this asserts
  nothing about what affects him.
* DOWN when `enumeration.is_down`.
* NO "flying" FEATURE. The engine tracks a position (z), not a current
  movement mode; a man at height is not necessarily flying (a ledge, a
  roof). Omitted until a mode is tracked, rather than guessed from z.
* ACTED. He has authored any `ActionDeclared` or `ActionResolved` this
  fight; turn one reads "has not acted yet".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kirby_combat.brief_detail import sightings
from kirby_combat.enumeration import is_down
from kirby_combat.health import classify_health
from kirby_combat.identity import build_in_play

if TYPE_CHECKING:
    from kirby_combat.loop.chooser import PhaseSituation


@dataclass(frozen=True)
class EnemyJudgement:
    enemy_id: str
    name: str
    side: str
    perceived: bool
    looks: str
    #: Power/maneuver names he has USED this fight, first-use order, no repeats.
    seen: tuple[str, ...]
    #: One line per hit he TOOK this fight.
    how_hits_landed: tuple[str, ...]
    #: "a machine", "a mook", "down".
    features: tuple[str, ...]
    distance_m: float | None
    #: Has he taken any action this fight.
    acted: bool


def _used_name(payload: dict) -> str | None:
    return payload.get("power_name") or payload.get("maneuver_name") \
        or payload.get("power_xmlid") or None


def _is_mook(session: Any, enemy: Any) -> bool:
    if getattr(enemy, "minor_hits", None) is None:
        return False
    t = session.template
    return bool(t.minor_dead_at_zero_body or t.minor_stunned_is_dead
                or t.minor_hit_counting)


def _is_machine(enemy: Any) -> bool:
    powers = build_in_play(enemy).powers or []
    return any((getattr(p, "xmlid", "") or "").upper() == "AUTOMATON"
               for p in powers)


#: What an observer sees for each status a blow can leave (resolution/status.py).
_SEEN_STATUS = {
    "Stunned": "he staggered",
    "Knocked Out": "he dropped",
    "Dying": "he went down and stayed down",
    "Dead": "he went down and stayed down",
}


def _landed_line(payload: dict, enemy_id: str) -> str:
    """The visible consequences of one hit on him, in what an onlooker sees.

    RULING: knockback is visible as it happens, so its distance is shown
    ("knocked back 4m"); a fall (`statuses.FELL` lists the ids who went down)
    reads "he went down" only if HE is on that list (it names everyone a
    resolution put on the ground, the attacker of a block-throw included),
    and not again when knockback already
    put him on the ground or moved him. A status with no mapped sight is
    shown by name.
    """
    from kirby_combat.statuses import FELL

    name = _used_name(payload) or "An attack"
    seen: list[str] = []
    knocked = False
    for c in payload.get("status_changes") or []:
        seen.append(_SEEN_STATUS.get(str(c), f"he was {c}"))
    kb = payload.get("knockback")
    if kb and (kb.get("distance_m", 0) > 0 or kb.get("prone")):
        d = kb.get("distance_m", 0)
        knocked = True
        if d > 0:
            seen.append(f"he was knocked back {d:.0f}m")
        else:
            seen.append("he was knocked down")
    if enemy_id in (payload.get(FELL) or ()) and not knocked:
        seen.append("he went down")
    seen = list(dict.fromkeys(seen))
    return f"{name} hit him; " + (", ".join(seen) if seen else "he kept fighting")


def judge_enemy(situation: "PhaseSituation", enemy: Any) -> EnemyJudgement:
    """What the actor can judge of `enemy` right now. See the module docstring."""
    sight = sightings(situation)[enemy.id]
    if not sight.perceived:
        return EnemyJudgement(
            enemy_id=enemy.id, name=enemy.name, side=enemy.side,
            perceived=False, looks="", seen=(), how_hits_landed=(),
            features=(), distance_m=None, acted=False)

    session = situation.session
    seen: list[str] = []
    landed: list[str] = []
    acted = False
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        author = evt.author
        by_him = author.type == "combatant" and author.id == enemy.id
        if kind == "ActionDeclared" and by_him:
            acted = True
        elif kind == "ActionResolved":
            payload = evt.result_payload
            if by_him:
                acted = True
                name = _used_name(payload)
                if name and name not in seen:
                    seen.append(name)
            if payload.get("target_id") == enemy.id and payload.get("hit"):
                landed.append(_landed_line(payload, enemy.id))

    features: list[str] = []
    if _is_machine(enemy):
        features.append("a machine")
    if _is_mook(session, enemy):
        features.append("a mook")
    if is_down(enemy):
        features.append("down")

    return EnemyJudgement(
        enemy_id=enemy.id, name=enemy.name, side=enemy.side, perceived=True,
        looks=classify_health(enemy), seen=tuple(seen),
        how_hits_landed=tuple(landed), features=tuple(features),
        distance_m=situation.distances_m.get(enemy.id), acted=acted)


def render_judgement(j: EnemyJudgement) -> list[str]:
    """The Brief's lines for this enemy."""
    head = f"{j.name} [{j.side}]"
    if not j.perceived:
        return [f"{head}: out of sight"]
    if j.distance_m is not None:
        head += f", {j.distance_m:.0f}m away"
    head += f": looks {j.looks}"
    if j.features:
        head += "; " + "; ".join(j.features)
    lines = [head]
    if j.seen:
        lines.append("  seen: " + ", ".join(j.seen))
    elif not j.acted:
        lines.append("  has not acted yet")
    else:
        lines.append("  seen: none yet")
    if j.how_hits_landed:
        lines.append("  hits taken: " + " | ".join(j.how_hits_landed))
    return lines
