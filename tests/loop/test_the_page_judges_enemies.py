"""Under a "judged" template the page describes ENEMIES as a fighter judges
them (`kirby_combat.judgement`) and not from their sheets.

What goes: an enemy's STUN/BODY/END, DCV, SPD, defences, characteristics and
complications; the matchup estimate (his damage through HIS defences); the
attacker's exact OCV on the out-of-turn Abort page. What stays: the actor and
his allies as today, and everything a "sheet" template printed.

Every page here is the one `run_phase` hands the chooser.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.brief import Brief
from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_dice import RandomRoller
from tests.templates import PLAIN

HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")
SHEET = PLAIN
JUDGED = replace(PLAIN, page_knowledge="judged")


class _Reads:
    """Keeps the first own-Phase page and every out-of-turn page; takes the
    first offer in reading order (an Abort is declined)."""

    def __init__(self, actor_id=None):
        self.actor_id = actor_id
        self.page = None
        self.aborts: list[tuple[str, str]] = []

    def choose(self, situation):
        why = situation.out_of_turn
        if why is not None:
            self.aborts.append((situation.actor.id, Brief(situation).render()))
            return situation.menu[0].action_id
        if self.page is None and (self.actor_id in (None, situation.actor.id)):
            self.page = Brief(situation).render(doctrine=False)
        return situation.ordered_menu[0].action_id


def _session(*cast, template, seed=7):
    return CombatSession.create(
        id="s", combatants=list(cast), scene=None, template=template,
        dice_roller=RandomRoller(seed=seed)).start()


def _play(session, actor_id=None) -> _Reads:
    reader = _Reads(actor_id)
    run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]),
              reader, roller=RandomRoller(seed=7), on_unresolvable="raise")
    return reader


def _small(template):
    return _session(
        fighter("hero", side=HEROES, dex=30), fighter("pal", side=HEROES, dex=20),
        fighter("goon", side=VILLAINS, dex=10), template=template)


def _slower_and_stronger(template):
    """A slow hero who hits hard against a fast man who cannot hurt him: one
    of the two shapes on which the sheet page prints "The matchup:"."""
    return _session(
        fighter("hero", side=HEROES, dex=30, spd=2, dice=8),
        fighter("goon", side=VILLAINS, dex=10, spd=6, dice=1), template=template)


GOLDEN_SHEET_PAGE = (
    "Turn 1, Segment 12.\n"
    "\n"
    "YOU control: hero [heroes] STUN 40/40, BODY 12/12, END 40/40, OCV 9, DCV 5, role=ranged_blaster\n"
    "    SPD 4, PD 4/2r, ED 4/2r, PRE 15, EGO 15, OMCV 5/DMCV 5, MD 3, INT 10\n"
    "    condition: healthy\n"
    "\n"
    "Allies:\n"
    "  pal [heroes] STUN 40/40, BODY 12/12, END 40/40, OCV 9, DCV 5, role=ranged_blaster\n"
    "      SPD 4, PD 4/2r, ED 4/2r, PRE 15, EGO 15, OMCV 5/DMCV 5, MD 3, INT 10\n"
    "      condition: healthy\n"
    "\n"
    "Enemies:\n"
    "  goon [villains] STUN 40/40, BODY 12/12, END 40/40, OCV 9, DCV 5, role=ranged_blaster\n"
    "      SPD 4, PD 4/2r, ED 4/2r, PRE 15, EGO 15, OMCV 5/DMCV 5, MD 3, INT 10\n"
    "      condition: healthy\n"
    "\n"
    "Ground: open, featureless \u2014 no positions are being tracked."
)


def test_a_judged_page_shows_no_enemy_sheet_numbers():
    page = _play(_small(JUDGED), "hero").page
    enemies = page.split("Enemies:")[1].split("Ground:")[0]
    assert "goon [villains]" in enemies and "looks healthy" in enemies
    for sheet in ("PD ", "ED ", "STUN ", "BODY ", "END ", "DCV", "OCV", "SPD ",
                  "PRE ", "EGO"):
        assert sheet not in enemies, (sheet, enemies)
    # The actor and his ally are as today.
    assert "YOU control: hero [heroes] STUN 40/40" in page
    assert "pal [heroes] STUN 40/40" in page.split("Allies:")[1].split("Enemies:")[0]


def test_the_matchup_estimate_is_gone_on_a_judged_page():
    sheet = _play(_slower_and_stronger(SHEET), "hero").page
    assert "The matchup:" in sheet, "the fixture no longer produces a matchup"
    judged = _play(_slower_and_stronger(JUDGED), "hero").page
    assert "The matchup:" not in judged


def test_the_abort_page_names_the_attack_but_not_his_ocv():
    def abort(template):
        s = _session(fighter("a", side=HEROES, dex=30),
                     fighter("d", side=VILLAINS, dex=10), template=template)
        pages = [p for who, p in _play(s).aborts if who == "d"]
        assert pages, "the defender was never asked"
        return pages[0]

    assert "Incoming: a, Blast (attack, ranged, OCV 9)." in abort(SHEET)
    judged = abort(JUDGED)
    assert "Incoming: a, Blast (attack, ranged)." in judged
    assert "OCV" not in judged.split("Incoming:")[1].split("\n")[0]


def test_an_enemy_he_cannot_perceive_keeps_todays_single_line():
    """A REALLY unperceived enemy (Invisible, through the real `sightings`
    and `perceive`, no stubs), who has fought in the open and been hit."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.loop.chooser import PhaseSituation
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant
    from tests.combat_fixtures import _InvisibilityPower

    floor = Scene(
        id="floor", name="Floor", bounds=SceneBounds(0, 0, 0, 40, 40, 40),
        surfaces=[Surface(id="g", name="g", polygon_xy=[(0, 0), (40, 0), (40, 40), (0, 40)],
                          elevation_m=0.0, surface_type="ground", cover_level=0,
                          is_supporting=True)],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={"hero": Position(0.0, 0.0, 0.0, 0.0),
                             "vex": Position(10.0, 0.0, 0.0, 3.14)})

    def fight(invisible):
        vex = fighter("vex", side=VILLAINS)
        if invisible:
            vex.hero.powers.append(_InvisibilityPower())
        s = CombatSession.create(
            id="s", combatants=[fighter("hero", side=HEROES), vex], scene=floor,
            template=JUDGED, dice_roller=RandomRoller(seed=1)).start()
        for author, payload in (
            ("vex", dict(kind="attack", power_name="Blast", target_id="hero",
                         hit=False, status_changes=[])),
            ("hero", dict(kind="attack", power_name="Strike", target_id="vex",
                          hit=True, status_changes=["Stunned"])),
        ):
            s = apply_event(s, ActionResolved(
                id=str(uuid.uuid4()), session_id=s.id,
                sequence=len(s.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_combatant(author),
                declaration_event_id="", result_payload=payload))
        sit = PhaseSituation(
            actor=s.combatants["hero"], menu=[], enemies=[s.combatants["vex"]],
            allies=[], session=s, distances_m={"vex": 10.0}, segment=12, turn=1)
        return Brief(sit).render(doctrine=False)

    def enemies_of(page):
        return page.split("Enemies:")[1].split("Ground:")[0].strip()

    # The control: in plain view the same log is read back as judgement.
    seen = enemies_of(fight(invisible=False))
    assert "seen: Blast" in seen and "he staggered" in seen

    page = fight(invisible=True)
    assert enemies_of(page) == "vex [villains]: you cannot perceive him"
    for leak in ("Blast", "Strike", "staggered", "10m", "looks", "acted"):
        assert leak not in page


def test_a_sheet_page_is_unchanged():
    """GOLDEN, captured from the engine before the judged page existed (same
    fight, `page_knowledge="sheet"`). Everything above the doctrine and menu."""
    page = _play(_small(SHEET), "hero").page
    assert page.split("\n\nLegal actions")[0] == GOLDEN_SHEET_PAGE
