"""Brief — one Phase, written down.

WHAT THIS IS FOR. A chooser that reads text needs the Phase described:
who is acting, what shape they are in, who is standing where, and what
they may legally do. That description was the last thing keeping a fight
inside the parked kirby-api wrapper, where the equivalent builder is
160-odd lines that --- measured 2026-09-06 --- touch the database **zero**
times. It was already a pure function of engine state; only its location
was wrong.

WHY THIS IS NOT A VIOLATION OF THE ENGINE'S BOUNDARIES, which is worth
saying because two other homes were considered and rejected:

* The engine already renders itself to text and always has ---
  ``LegalAction.summary`` is a readable label, ``Tactic.narrative_summary``
  is "the one-liner shown to whatever picks one". A Brief is those, gathered
  into a page. It describes combat state and knows nothing about what reads
  it.
* ``kirby-ai`` was the obvious candidate and is the wrong one by its own
  charter, which says it owns the network hop and the policy around it ---
  and explicitly not content, rules, or rows. A description of a Phase is
  content, not transport.
* A module of its own would be one class with no second occupant.

**No word here names anything that reads a Brief**, and
``tests/test_vocabulary.py`` enforces that. The engine writes the page; who
reads it is somebody else's business. That is the same seam as ``Chooser``
--- the engine asks, and never learns what answered.

THE GROUND IS PART OF THE PHASE. A Brief that lists combatants and offers
and says nothing about where anyone is standing describes a fight in a
void. Measured 2026-09-07 on the O.K. Corral: the page mentioned no wall,
no cover and no range, so a reader could see that melee had vanished from
the menu and `move_strike` had appeared, and never know WHY --- it could
not prefer a target two metres away over one five metres off, because both
read identically, and it could not take cover behind a wagon it had no way
to know existed.

Everything needed was already computed elsewhere for the rules to use:
`distance_3d` for range, `compute_cover_level` and `cover_ocv_modifier`
for cover, `has_line_of_sight` for whether a shot is even possible. The
terrain section states those, and derives nothing of its own.

STABLE AND PARSEABLE, NOT PRETTY. Each action is listed with its
``action_id`` in brackets, because that token is what a chooser returns and
what ``validate_choice`` checks. The rest is a state line per combatant.
Formatting choices here are a view, not a rule --- a caller who wants a
different page builds one from the same objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kirby_combat.enumeration import is_down
from kirby_combat.roles import classify_role
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.chooser import PhaseSituation


def _stat(combatant, name: str, default: int = 0) -> int:
    stats = combatant.combat_stats()
    return int(getattr(stats, name, default) or default)


@dataclass(frozen=True)
class CombatantLine:
    """One combatant as a reader sees them.

    Enemy stats are shown as freely as the actor's. That is DELIBERATE and
    worth naming: the anti-metagaming line in this system is drawn by
    PERCEPTION --- an actor cannot target what it cannot perceive --- not by
    hiding numbers from whoever is choosing. Showing STUN and DCV but
    withholding, say, power names would be inconsistent rather than
    principled.
    """

    combatant: object

    @property
    def name(self) -> str:
        return getattr(self.combatant, "name", None) or self.combatant.id

    @property
    def side(self) -> Side:
        return Side.of(self.combatant)

    @property
    def is_down(self) -> bool:
        return is_down(self.combatant)

    @property
    def role(self) -> str:
        return classify_role(self.combatant)

    def render(self) -> str:
        state = self.combatant.state
        bits = [
            f"STUN {state.current_stun}/{_stat(self.combatant, 'max_stun')}",
            f"BODY {state.current_body}/{_stat(self.combatant, 'max_body')}",
            f"END {state.current_end}/{_stat(self.combatant, 'max_end')}",
            f"OCV {_stat(self.combatant, 'ocv')}",
            f"DCV {_stat(self.combatant, 'dcv')}",
        ]
        line = f"{self.name} [{self.side}] {', '.join(bits)}, role={self.role}"
        return f"{line} -- DOWN" if self.is_down else line

    def __str__(self) -> str:
        return self.render()


@dataclass(frozen=True)
class EnemyBearing:
    """Where one enemy stands, relative to the actor.

    Every figure here is the SAME one the rules use --- the range that gates
    melee, the cover level that penalises a shot, the line of sight that
    decides whether the shot is possible at all. A reader weighing an offer
    and the engine resolving it quote the same numbers.
    """

    enemy_id: str
    name: str
    range_m: float | None = None
    cover_level: int = 0
    cover_ocv: int = 0
    in_line_of_sight: bool = True

    def render(self) -> str:
        if self.range_m is None:
            return f"{self.name}: position unknown"
        bits = [f"{self.range_m:.1f}m"]
        if self.cover_level:
            bits.append(f"cover {self.cover_level}/4 ({self.cover_ocv:+d} OCV to hit)")
        if not self.in_line_of_sight:
            bits.append("NO line of sight")
        return f"{self.name}: {', '.join(bits)}"


class Terrain:
    """The ground, as it bears on this Phase.

    Reads the Scene and reports; computes no rule of its own. A fight with
    no Scene has no terrain, and ``present`` is False --- which is a real
    answer, not an empty one: it says this fight happens nowhere in
    particular, and nothing on the page should imply otherwise.
    """

    def __init__(self, session, actor, enemies) -> None:
        self._session = session
        self._actor = actor
        self._enemies = list(enemies)

    @property
    def scene(self):
        return getattr(self._session, "scene", None) if self._session else None

    @property
    def present(self) -> bool:
        return self.scene is not None and self.position_of(self._actor.id) is not None

    def position_of(self, combatant_id: str):
        from kirby_combat.scene.placement import position_of

        return position_of(self.scene, combatant_id)

    @property
    def features(self) -> list:
        """Walls and obstacles, nearest first. A named thing a reader can
        aim for, hide behind, or shoot through."""
        return list(getattr(self.scene, "walls", None) or [])

    @property
    def bearings(self) -> list[EnemyBearing]:
        from kirby_combat.resolution.line_of_sight import has_line_of_sight
        from kirby_combat.scene.cover import compute_cover_level, cover_ocv_modifier
        from kirby_combat.scene.geometry import distance_3d

        here = self.position_of(self._actor.id)
        out: list[EnemyBearing] = []
        for enemy in self._enemies:
            name = getattr(enemy, "name", None) or enemy.id
            there = self.position_of(enemy.id)
            if here is None or there is None:
                out.append(EnemyBearing(enemy.id, name))
                continue
            cover = compute_cover_level(
                shooter_pos=here, target_pos=there,
                target_is_prone_or_diving=False, scene=self.scene,
            )
            out.append(EnemyBearing(
                enemy_id=enemy.id, name=name,
                range_m=distance_3d(here, there),
                cover_level=cover,
                # The cover LEVEL is 0-4; the OCV table is keyed on percent
                # covered, so the level is converted the way the rules do
                # rather than by a second table invented here.
                cover_ocv=cover_ocv_modifier(cover * 25),
                in_line_of_sight=has_line_of_sight(self.scene, here, there),
            ))
        return sorted(out, key=lambda b: (b.range_m is None, b.range_m or 0.0))

    def render(self) -> str:
        if not self.present:
            return "Ground: open, featureless — no positions are being tracked."
        lines = [f"Ground: {getattr(self.scene, 'name', None) or 'unnamed'}"]
        for feature in self.features:
            fname = getattr(feature, "name", None) or getattr(feature, "id", "?")
            cover = getattr(feature, "cover_level", 0)
            body = getattr(feature, "body", None)
            blocks = "blocks sight" if getattr(feature, "blocks_los", False) else "does not block sight"
            lines.append(
                f"  {fname}: cover {cover}/4, {blocks}"
                + (f", BODY {body} to break through" if body is not None else "")
            )
        lines.append("Enemy bearings:")
        lines.extend(f"  {b.render()}" for b in self.bearings)
        return "\n".join(lines)


class Brief:
    """A written description of one Phase.

    Built from the engine's own ``PhaseSituation``, so it carries exactly
    what the actor was offered --- no more, and nothing re-derived.
    """

    def __init__(self, situation: "PhaseSituation") -> None:
        self._situation = situation

    @property
    def actor(self) -> CombatantLine:
        return CombatantLine(self._situation.actor)

    @property
    def allies(self) -> list[CombatantLine]:
        return [CombatantLine(c) for c in self._situation.allies]

    @property
    def enemies(self) -> list[CombatantLine]:
        return [CombatantLine(c) for c in self._situation.enemies]

    @property
    def terrain(self) -> Terrain:
        """The ground, as it bears on this Phase."""
        return Terrain(self._situation.session, self._situation.actor,
                       self._situation.enemies)

    @property
    def menu(self) -> list["LegalAction"]:
        return list(self._situation.menu)

    @property
    def action_ids(self) -> list[str]:
        """The tokens a chooser may return. ``validate_choice`` checks
        against exactly this list."""
        return [a.action_id for a in self.menu]

    def render(self) -> str:
        situation = self._situation
        lines = [
            f"Turn {situation.turn}, Segment {situation.segment}.",
            "",
            f"YOU control: {self.actor.render()}",
        ]

        if self.allies:
            lines.append("")
            lines.append("Allies:")
            lines.extend(f"  {line.render()}" for line in self.allies)

        lines.append("")
        lines.append("Enemies:" if self.enemies else "Enemies: none standing.")
        lines.extend(f"  {line.render()}" for line in self.enemies)

        lines.append("")
        lines.append(self.terrain.render())

        lines.append("")
        lines.append(f"Legal actions this Phase ({len(self.menu)}):")
        # The action_id is bracketed because it is the token a chooser
        # returns; the summary is for the reader, the id is the contract.
        lines.extend(f"  [{a.action_id}] {a.summary}" for a in self.menu)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()

    def __len__(self) -> int:
        """How many actions were offered."""
        return len(self.menu)
