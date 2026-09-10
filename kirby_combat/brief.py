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

    @property
    def range_ocv(self) -> int:
        """What this distance costs to hit, 6E2's Range Modifier table.

        DERIVED, never stored: it is a function of the range and nothing
        else, so it cannot drift from `range_m` the way a second field
        would. Zero when the position is unknown -- an unknown distance
        must stay unknown rather than reading as point blank.

        Quoted for the same reason `cover_ocv` is: a page that prints
        cover's price and leaves range as a bare distance asks its reader
        to know the table by heart to tell a free shot from a -6, and
        every fight this engine has run has had a reader who did not.
        A power bought with No Range Modifier (6E1 p.346) pays none of
        this; that is a property of the POWER, and the offer to use it
        says so.
        """
        from kirby_combat.tables import range_penalty

        return 0 if self.range_m is None else range_penalty(self.range_m)

    def render(self) -> str:
        if self.range_m is None:
            return f"{self.name}: position unknown"
        bits = [f"{self.range_m:.1f}m"]
        if self.range_ocv:
            bits.append(f"{self.range_ocv:+d} OCV at that range")
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
    def sightings(self) -> list[str]:
        """Each feature as this actor sees it: how far, and what cover it
        would give THEM against the enemies actually present.

        A FIELD OF VIEW, NOT AN INVENTORY. Listing a wall's own
        `cover_level` says what the wall is; it does not say what it is
        worth from where you stand. A building behind you shields you from
        nobody, and its cover_level is 4 either way. So the number quoted
        is the one `cover_available` computes for the spot beside it
        against the current threats -- the same figure the offer to move
        there quotes, and the same one the rules apply once you are behind
        it.
        """
        import math

        from kirby_combat.scene.cover import cover_available

        here = self.position_of(self._actor.id)
        if here is None:
            return []
        threats = [
            p for p in (self.position_of(e.id) for e in self._enemies)
            if p is not None
        ]
        out = []
        for wall in self.features:
            name = getattr(wall, "name", None) or getattr(wall, "id", "?")
            a, b = wall.segment
            mid = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
            distance = math.dist((here.x, here.y), mid)
            spot, level = cover_available(wall, here, threats, self.scene)
            worth = (
                f"would give you cover {level}/4" if level > 0
                else "would not shield you from where they are"
            )
            # HOW HARD, AND HOW MUCH. BODY alone says how much there is to
            # chew through and nothing about whether you can bite: under
            # 6E2 p.172 an object takes BODY damage reduced by its DEF, so
            # an attack that does not beat DEF never touches it. A DEF 4
            # boarding house falls to a pistol in three Phases; a DEF 8
            # bank never does, and on the old page the two read
            # IDENTICALLY. Measured at the O.K. Corral: 127 of 781
            # decisions were spent shooting buildings and nothing a reader
            # could see told them whether it was working.
            body = getattr(wall, "body", None)
            defense = getattr(wall, "def_value", None)
            hardness = ""
            if defense is not None and body is not None:
                hardness = f"; DEF {defense}, BODY {body} to break through"
            elif body is not None:
                hardness = f"; BODY {body} to break through"
            elif defense is not None:
                hardness = f"; DEF {defense}"
            out.append(f"{name}: {distance:.1f}m away, {worth}{hardness}")
        return out

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
        lines.append("Where they are:")
        lines.extend(f"  {b.render()}" for b in self.bearings)
        if self.sightings:
            lines.append("What is around you:")
            lines.extend(f"  {sighting}" for sighting in self.sightings)
        return "\n".join(lines)


#: How each complication reads on the page. HD's xmlids, in the book's
#: own vocabulary (6E1 Complications).
_KINDS = {
    "PSYCHOLOGICALLIMITATION": "Psychological",
    "SOCIALLIMITATION": "Social",
    "PHYSICALLIMITATION": "Physical",
    "HUNTED": "Hunted by",
    "SUSCEPTIBILITY": "Susceptible to",
    "VULNERABILITY": "Vulnerable to",
    "DEPENDENTNPC": "Dependent NPC",
    "DEPENDENCE": "Dependent on",
    "ENRAGED": "Enraged",
    "BERSERK": "Berserk",
    "RIVALRY": "Rivalry",
    "DISTINCTIVEFEATURES": "Distinctive",
    "ACCIDENTALCHANGE": "Accidental change",
    "UNLUCK": "Unluck",
    "REPUTATION": "Reputation",
}


def _readable(xmlid: str) -> str:
    """A label for a complication this mapping has never seen.

    Never a bare string: an unlabelled line under "What drives you" reads
    as a motive whatever it actually is, which is the defect this exists
    to prevent.
    """
    return (xmlid or "Complication").replace("_", " ").title()


class Brief:
    """A written description of one Phase.

    Built from the engine's own ``PhaseSituation``, so it carries exactly
    what the actor was offered --- no more, and nothing re-derived.
    """

    def __init__(self, situation: "PhaseSituation") -> None:
        self._situation = situation

    @property
    def doctrine(self) -> list[str]:
        """The tactics that apply here, best first, in their own words.

        THE ADVICE WAS WRITTEN AND NEVER DELIVERED. Every tactic carries a
        `narrative_summary`; `Tactic`'s docstring calls it "the tactic
        listing a chooser sees" and the field's own comment says
        "one-liner shown to whatever picks one". They are written in the
        second person, addressed to whoever is deciding --- "You are
        injured, get behind cover NOW". Nothing rendered them. The only
        consumer a tactic ever had was `TacticChooser`, which reads
        `plan.steps[0].kind` and throws the prose away.

        So a reader that decides by reading was shown the map, the enemies
        and seventy offers, and never the paragraph written to tell it
        what to do.

        THIS ADVISES; IT DOES NOT DECIDE. The menu is not reordered, not
        filtered, and nothing here says the doctrine is correct --- a
        tactic is judgement, and `Basis` already records which ones the
        book actually advises. Each line names the action kind its first
        step wants, so the advice can be acted on rather than admired.
        """
        from kirby_combat.tactics.library import tactics_for

        try:
            situation = self._situation.tactical_situation()
        except Exception:
            return []

        # ONLY WHAT IS ON THE MENU. Advice pointing at an action the
        # actor cannot take this Phase is worse than no advice: it reads
        # as an instruction and cannot be followed. `dodge_under_fire`
        # and `abort_to_block` both name `kind="wait"`, which is not an
        # action kind at all, so both would otherwise head this list with
        # something unfindable. `TacticChooser` applies the same rule by
        # falling through such a tactic; this is that rule, said in prose.
        offered = {a.kind for a in self.menu}

        out: list[str] = []
        for tactic in tactics_for(situation):
            try:
                plan = tactic.execute(situation)
            except Exception:
                continue
            if not plan.steps:
                continue
            kind = plan.steps[0].kind
            if kind not in offered:
                continue
            summary = " ".join((tactic.narrative_summary or "").split())
            if not summary:
                continue
            out.append(f"{tactic.name} -> {kind}: {summary}")
        return out

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
    def drives(self) -> list[str]:
        """What this fighter will and will not do.

        A Brief listed the actor, the allies, the enemies, the ground, the
        doctrine and the menu, and never once said what the man WANTED. A
        reader got a complete tactical picture with the motive cut out of
        it and was then asked to choose --- so "sensible" could only ever
        mean "legal". That is the whole of Virgil Earp shooting the
        Harwood House: nothing on his page said he was a marshal whose
        business was the Cowboys, and the house was the first thing he was
        allowed to hit.

        HERO ALREADY HAS THIS AND IT IS NOT A NEW SUBSYSTEM. Psychological
        Complications are exactly a character's standing goals and
        refusals --- "Code Against Killing", "Overconfidence", "Protective
        Of Innocents" --- bought on the sheet and, per 6E2 p.138, severe
        enough that an attack playing to one is worth Presence dice.
        `complications_of` has read them since the loop learned to fill
        `Situation.actor_complications`; two tactics look at them and the
        page showed them to nobody.

        Severity travels with the text, because "Code Against Killing
        (Total)" and a Moderate reluctance are different instructions and
        the book already grades them on these rungs.
        """
        from kirby_combat.complications import complications_of

        out = []
        # A HUNTER IS NOT A MOTIVE. Measured on the corral: Billy
        # Clanton's page read "What drives you: Gunfighter / Law
        # Enforcement". "Law Enforcement" is who HUNTS him, and a reader
        # told that was a drive would conclude the Cowboy is motivated by
        # the marshals. `complications_of` returns every kind there is, so
        # each line says which kind it is.
        for comp in complications_of(self._situation.actor) or []:
            # `name` FIRST: `complications_of` fills it with the raw's
            # `input` -- the text a player actually wrote ("Code Against
            # Killing") -- and falls back to the alias only when there is
            # none. The alias alone is the generic "Psychological
            # Complication", which says nothing to anybody.
            text = (getattr(comp, "name", "") or getattr(comp, "alias", "")
                    or getattr(comp, "notes", "")).strip()
            if not text:
                continue
            severity = (getattr(comp, "adders", None) or {}).get("INTENSITY")
            if severity:
                text = f"{text} ({severity.title()})"
            out.append(f"{_KINDS.get(comp.xmlid, _readable(comp.xmlid))}: {text}")
        return out

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

        # WHAT THE SIDE WANTS, which is not the same as what the man
        # wants. See `Side.objective`.
        objective = getattr(getattr(self._situation.actor, "side", None),
                            "objective", None)
        if objective:
            lines.append("")
            lines.append(f"What your side is trying to do: {objective}")

        # NO HEADING OVER NOTHING. Most combatants carry no complications,
        # and an empty section is noise on a page something pays by the
        # token to read.
        if self.drives:
            lines.append("")
            lines.append("What drives you:")
            lines.extend(f"  {drive}" for drive in self.drives)

        import os as _os

        # An escape hatch for measuring the section's effect, not a
        # feature: set KIRBY_BRIEF_NO_DOCTRINE=1 to render the page
        # without it and compare the same fight both ways.
        doctrine = ([] if _os.environ.get("KIRBY_BRIEF_NO_DOCTRINE")
                    else self.doctrine)
        if doctrine:
            lines.append("")
            lines.append("What your doctrine says, best first:")
            lines.extend(f"  {line}" for line in doctrine)

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
