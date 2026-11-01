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
* MIND LOCK ONLY. `Sighting.perceived` is also true for a mind he reaches
  only through a Mind Scan lock, which gives no looks: he is named and
  "his mind is in reach" and nothing else. What a lock does reveal is 3b's
  Mind Scan facts, not this module's.
* CAPS. A long fight must not grow the page without bound (a hero in a
  3-vs-20 fight takes a hit every Phase): `seen` keeps the first
  `MAX_SEEN` uses and counts the rest, `how_hits_landed` keeps the most
  recent `MAX_HITS_LISTED` and counts the earlier ones. Same reason and
  same pattern as `brief_detail.MAX_POWER_NAMES` / `MAX_LISTED`: a page
  something pays by the token to read.
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


#: Powers he has been seen to use that are listed before the rest are
#: counted. The page-size reason `brief_detail.MAX_POWER_NAMES` gives.
MAX_SEEN = 8

#: How many of the most recent hits on him are listed before the earlier
#: ones are counted; `brief_detail.MAX_LISTED`'s reason, and the newest
#: blows are the ones that say how he is doing.
MAX_HITS_LISTED = 6


@dataclass(frozen=True)
class EnemyJudgement:
    enemy_id: str
    name: str
    side: str
    perceived: bool
    looks: str
    #: Power/maneuver names he has USED this fight, first-use order, no
    #: repeats, at most `MAX_SEEN`.
    seen: tuple[str, ...]
    #: One line per hit he TOOK this fight: the most recent `MAX_HITS_LISTED`.
    how_hits_landed: tuple[str, ...]
    #: "a machine", "a mook", "down".
    features: tuple[str, ...]
    distance_m: float | None
    #: Has he taken any action this fight.
    acted: bool
    #: A Targeting Sense reaches him. False with `perceived` True is a mind
    #: reached through a Mind Scan lock alone.
    physical: bool
    #: Uses past `MAX_SEEN` that are not listed.
    seen_more: int
    #: Hits earlier than the `MAX_HITS_LISTED` listed.
    hits_earlier: int


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
            features=(), distance_m=None, acted=False, physical=False,
            seen_more=0, hits_earlier=0)

    if not sight.physical:
        return EnemyJudgement(
            enemy_id=enemy.id, name=enemy.name, side=enemy.side,
            perceived=True, looks="", seen=(), how_hits_landed=(),
            features=(), distance_m=None, acted=False, physical=False,
            seen_more=0, hits_earlier=0)

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
        looks=classify_health(enemy), seen=tuple(seen[:MAX_SEEN]),
        how_hits_landed=tuple(landed[-MAX_HITS_LISTED:]), features=tuple(features),
        distance_m=situation.distances_m.get(enemy.id), acted=acted, physical=True,
        seen_more=max(0, len(seen) - MAX_SEEN),
        hits_earlier=max(0, len(landed) - MAX_HITS_LISTED))


def render_judgement(j: EnemyJudgement) -> list[str]:
    """The Brief's lines for this enemy.

    RULING: an enemy he cannot perceive keeps the Brief's one line from
    before judgement existed ("Name [side]: you cannot perceive him"; see
    `Brief._combatant_block`), so there is one wording for it, not two.
    """
    head = f"{j.name} [{j.side}]"
    if not j.perceived:
        return [f"{head}: you cannot perceive him"]
    if not j.physical:
        return [f"{head}: his mind is in reach"]
    if j.distance_m is not None:
        head += f", {j.distance_m:.0f}m away"
    head += f": looks {j.looks}"
    if j.features:
        head += "; " + "; ".join(j.features)
    lines = [head]
    if j.seen:
        more = f" (and {j.seen_more} more)" if j.seen_more else ""
        lines.append("  seen: " + ", ".join(j.seen) + more)
    elif not j.acted:
        lines.append("  has not acted yet")
    else:
        lines.append("  seen: none yet")
    if j.how_hits_landed:
        earlier = f"(and {j.hits_earlier} earlier) | " if j.hits_earlier else ""
        lines.append("  hits taken: " + earlier + " | ".join(j.how_hits_landed))
    return lines
