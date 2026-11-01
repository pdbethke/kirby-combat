"""The Brief carries what the deleted page carried (lift and shift).

The consumer-side page builder deleted in the 2026-09-17 harness refactor
showed, per combatant, SPD, PD/ED and their resistant halves, PRE, EGO,
OMCV/DMCV, MD and INT, powers by name, a health and status rung, held
actions, attacks taken this Turn, Mind Control / Mental Illusion / Entangle
state, Drains, Damage Reduction, Trigger and Limited Power texts and
complications; then reach and elevation per enemy, the matchup, the
mental-lock line, the Flashed and can't-swim warnings and the frameworks
block. The engine's Brief kept STUN, BODY, END, OCV, DCV, role and DOWN.

Every test here reads a page rendered INSIDE `run_phase`, from the
situation the loop itself built --- the page a chooser is actually shown
--- and fails on the engine as it was before the port.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from corpus import require_authored
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import LegalAction
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.mental.continuing import roll_breakouts
from kirby_combat.models import AttackPower
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionResolved, AdjustmentApplied, EntangleApplied, FlashApplied,
    HeldActionDeclared, make_author_engine,
)
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

# A SHEET page: these tests are about the numbers a page can carry of an
# enemy, which the named (judged) templates deliberately do not show.
TEMPLATE = replace(CombatTemplate.default_6e_superheroic(), page_knowledge="sheet")


# ── the harness ─────────────────────────────────────────────────────────────

class _Reads:
    """A chooser that reads the page it is given, then takes the first offer
    in reading order --- the page's own order."""

    def __init__(self):
        self.page = ""
        self.situation = None

    def choose(self, situation):
        # Out of turn (an Abort, a Held Action: `loop/reactions.py`) is not
        # the Phase page these tests read: decline, and do not keep it.
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.situation = situation
        self.page = situation.brief().render()
        return situation.ordered_menu[0].action_id


def _fight(*cast, scene=None, seed: int = 7) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(cast), scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=seed),
    ).start()


def _page(session: CombatSession, actor_id: str) -> _Reads:
    """Run the Phase of ``actor_id`` (the fastest man, so the first to act)
    and return what his chooser read."""
    reader = _Reads()
    result = run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]),
                       reader, roller=RandomRoller(seed=21))
    assert result.actor_id == actor_id, result.actor_id
    return reader


def _log(session: CombatSession, event_cls, **fields) -> CombatSession:
    return apply_event(session, event_cls(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        **fields,
    ))


def _floor(**positions) -> Scene:
    return Scene(
        id="lot", name="lot", bounds=SceneBounds(-5, -5, -5, 60, 60, 30),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-5, -5), (60, -5), (60, 60), (-5, 60)],
                          elevation_m=0.0, surface_type="ground", cover_level=0,
                          is_supporting=True)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v) for k, v in positions.items()},
    )


def _two(**actor_kw):
    hero = fighter("hero", side=Side.named("x"), dex=30, **actor_kw)
    goon = fighter("goon", side=Side.named("y"), dex=10)
    return hero, goon


def _block(page: str, name: str) -> str:
    """The lines of one combatant's entry: his head line and what is
    indented under it."""
    lines = page.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{name} [") or line.startswith(f"YOU control: {name} ["):
            out = [line]
            for nxt in lines[i + 1:]:
                if nxt.startswith("      ") or (line.startswith("YOU") and nxt.startswith("    ")):
                    out.append(nxt)
                else:
                    break
            return "\n".join(out)
    raise AssertionError(f"{name} has no entry on the page:\n{page}")


# ── the numbers ─────────────────────────────────────────────────────────────

def test_every_perceived_combatant_carries_the_numbers_the_rules_use():
    """SPD, both defenses with their resistant halves, PRE (the number a
    Presence Attack is measured against, 6E2 p.138), EGO / OMCV / DMCV / MD
    and INT --- for the actor and for the enemy he is looking at."""
    page = _page(_fight(*_two()), "hero").page
    for who in ("hero", "goon"):
        entry = _block(page, who)
        for fragment in ("SPD 4", "PD 4/2r", "ED 4/2r", "PRE 15", "EGO 15",
                         "OMCV 5/DMCV 5", "MD 3", "INT 10"):
            assert fragment in entry, f"{fragment!r} missing for {who}:\n{entry}"


def test_the_health_rung_is_the_engines_own():
    """`health.classify_health`: below half STUN is wounded, a quarter is
    critical. The page reads the one ladder every consumer reads."""
    hero, goon = _two(stun=15)
    page = _page(_fight(hero, goon), "hero").page
    assert "condition: wounded" in _block(page, "hero")
    assert "condition: healthy" in _block(page, "goon")


def test_a_stunned_enemy_is_said_to_be_stunned():
    session = _fight(*_two())
    session = _log(session, ActionResolved, declaration_event_id="", result_payload={
        "kind": "attack", "target_id": "goon", "hit": True, "status_changes": ["Stunned"]})
    page = _page(session, "hero").page
    entry = _block(page, "goon")
    assert "Stunned" in entry
    assert "attacked 1 time this Turn" in entry


def test_the_powers_are_on_the_page_by_their_authored_names():
    ravel = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    ravel.side = Side.named("x")
    goon = fighter("goon", side=Side.named("y"), dex=1)
    page = _page(_fight(ravel, goon), "ravel").page
    assert "powers: " in page and "Floating String Form" in page


def test_a_character_with_identity_bound_purchases_says_which_identity_he_is_in():
    """Ravel's Multipower is Only In Alternate Identity (6E1 p.388), and
    `combat_stats` reads such purchases through `state.in_hero_id`."""
    ravel = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    ravel.side = Side.named("x")
    goon = fighter("goon", side=Side.named("y"), dex=1)
    page = _page(_fight(ravel, goon), "ravel").page
    assert "in his Hero identity; " in page
    assert "work only in it (Only In Alternate Identity, 6E1 p.388)" in page
    assert "Hero identity" not in _block(page, "goon")


# ── what is being done to them ──────────────────────────────────────────────

def test_an_entangled_enemy_is_shown_held():
    session = _log(_fight(*_two()), EntangleApplied, target_id="goon",
                   entangle_body=4, entangle_pd=3, entangle_ed=3, mental_paralysis=False)
    page = _page(session, "hero").page
    assert "Entangled: BODY 4, DEF 3/3" in _block(page, "goon")


def test_a_drained_enemy_shows_the_drain():
    session = _log(_fight(*_two()), AdjustmentApplied, target_id="goon",
                   stat="STR", delta=-10, fade_rate_per_turn=5)
    page = _page(session, "hero").page
    assert "STR drained -10" in _block(page, "goon")


def test_a_held_action_is_visible():
    session = _log(_fight(*_two()), HeldActionDeclared, combatant_id="goon",
                   trigger_condition="the hero moves", for_action="attack")
    page = _page(session, "hero").page
    assert "holding an action (attack) until: the hero moves" in _block(page, "goon")


class _RawComp:
    xmlid = "PSYCHOLOGICALLIMITATION"
    alias = "Psychological Complication"
    notes = ""
    levels = 0
    adders = ()
    adder_string = "Intensity Is Total, Situation Is (Common)"
    input = "Code Against Killing"


def test_an_enemys_complications_are_on_his_line():
    hero, goon = _two()
    goon.hero.complications = [_RawComp()]
    page = _page(_fight(hero, goon), "hero").page
    assert "complications: Psychological: Code Against Killing (Total)" in _block(page, "goon")


# ── perception ──────────────────────────────────────────────────────────────

class _Invisibility:
    xmlid = "INVISIBILITY"
    alias = "Invisibility"
    name = "Invisibility"
    adders: list = []
    sub_powers: list = []


def test_an_enemy_you_cannot_perceive_is_named_and_nothing_more():
    """What you cannot perceive you cannot read: no STUN, no condition."""
    hero, goon = _two()
    goon.hero.powers.append(_Invisibility())
    page = _page(_fight(hero, goon, scene=_floor(hero=(0, 0, 0), goon=(10, 0, 0))), "hero").page
    entry = _block(page, "goon")
    assert entry == "  goon [y]: you cannot perceive him"
    assert "goon: you cannot perceive him; nothing that needs to perceive" in page


def _mentalist(id_: str, side: str, dex: int):
    c = synthetic_combatant(
        id=id_, name=id_, ocv=6, dcv=5, omcv=8, dmcv=5, spd=4, dex=dex, ego=15,
        str_=10, con=15, pre=10, rec=5, pd=5, ed=5, md=5,
        max_stun=40, max_body=12, max_end=40, side=Side.named(side),
        is_mentalist=True,
        attacks=[AttackPower(
            xmlid="MENTALBLAST", name="Mind Blast", damage_dice=6, half_die=False,
            plus_one=False, damage_type="normal", defense_type="md", range_m=None,
            uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
            increased_stun_mult=0, source_id=f"{id_}-mb", is_ranged=False)],
    )
    return c


def test_a_mind_behind_a_wall_is_in_reach_through_a_mind_scan_lock():
    """6E1 p.265: the lock is mental line of sight. The old page's
    "Mind Scan locked" line, now from the same fold the gate reads."""
    psi = _mentalist("psi", "psi", dex=30)
    mark = fighter("mark", side=Side.named("gang"), dex=10)
    scene = _floor(psi=(0, 5, 0), mark=(20, 5, 0))
    scene.walls.append(Wall(id="w", name="Brick", segment=(Position(10, -5, 0), Position(10, 30, 0)),
                            height_m=6.0, blocks_los=True, blocks_movement=True,
                            cover_level=4, body=6))
    session = _log(_fight(psi, mark, scene=scene), ActionResolved, declaration_event_id="",
                   result_payload={"kind": "mind_scan", "established": True,
                                   "attacker_id": "psi", "target_id": "mark",
                                   "reached": "mental_powers", "source_id": "psi-scan"})
    page = _page(session, "psi").page
    assert "mark: out of sight, so no physical attack reaches him; his mind is in reach " \
           "through your Mind Scan lock" in page


# ── the actor's own situation ───────────────────────────────────────────────

def test_a_flashed_actor_is_told_so():
    session = _log(_fight(*_two()), FlashApplied, target_id="hero",
                   sense_group="sight", segments=3)
    page = _page(session, "hero").page
    assert "You are Flashed in the Sight Group for 3 more Segments (6E1 p.228)" in page


def test_a_man_who_cannot_swim_is_told_about_the_water_he_stands_in():
    from kirby_world.construct import Construct, ConstructEffect

    hero, goon = _two()
    hero.state.statuses.add("cannot_swim")
    scene = _floor(hero=(2, 2, 0), goon=(30, 30, 0))
    scene.constructs.append(Construct(
        obj_id="the-quarry-pool", kind="hazard_zone",
        polygon_xy=[(0, 0), (5, 0), (5, 5), (0, 5)], elevation_range_m=(-3.0, 1.0),
        effect=ConstructEffect(kind="suffocation", gating="breathing_swimming",
                               trigger="every_segment"),
    ))
    page = _page(_fight(hero, goon, scene=scene), "hero").page
    assert "Deep water (the-quarry-pool): you are in it. You cannot swim" in page


# ── Mind Control: the victim's order, and the caster's view ────────────────

class _MindControl:
    xmlid = "MINDCONTROL"
    name = "Mind Control"
    alias = "Mind Control"
    levels = 12
    id = "src-MINDCONTROL"
    assigned_adders: list = []
    assigned_modifiers: list = []
    sub_powers: list = []


class _Dice(RandomRoller):
    def __init__(self, *three, effect=None):
        super().__init__(seed=11)
        self._three = [list(t) for t in three]
        self._effect = effect

    def roll_dice(self, count, sides=6):
        if count == 3 and self._three:
            return self._three.pop(0)
        if self._effect is not None and count != 3:
            return [self._effect] * count
        return super().roll_dice(count, sides)


def _controlled(order: str):
    """psi Mind Controls mark with ``order``; mark then FAILS his first
    Breakout Roll (6E1 p.258), so the order is obeyed."""
    psi = _mentalist("psi", "psi", dex=10)
    psi.hero.powers.append(_MindControl())
    mark = fighter("mark", side=Side.named("gang"), dex=30)
    rando = fighter("rando", side=Side.named("solo"), dex=20)
    session = _fight(psi, mark, rando)
    mc = psi.hero.powers[-1]
    offer = LegalAction(action_id=f"mind_control:mark:{order}", kind="mind_control",
                        target_id="mark", power_xmlid=mc.xmlid, power_name=mc.name,
                        summary="mind control", _attack_view=mc, order=order)
    resolved = resolve_chosen(session, session.combatants["psi"], offer,
                              template=TEMPLATE, roller=_Dice((1, 1, 1), effect=6))
    assert resolved.session.event_log[-1].result_payload["established"] is True
    return roll_breakouts(resolved.session, "mark", _Dice((6, 6, 6)))


@pytest.mark.parametrize("order,says", [
    ("spare", "leave psi and his side alone"),
    ("withdraw", "flee the combat. Nothing that attacks anybody is on your menu"),
    ("turn", "attack your own side"),
])
def test_the_victim_is_told_the_order_that_narrowed_his_menu(order, says):
    """`obey` bends his Phase to the order; the page says which and why."""
    page = _page(_controlled(order), "mark").page
    assert "You are under orders (Mind Control, 6E1 p.256)" in page
    assert says in page


def test_the_controller_sees_his_order_on_the_victims_line_and_nobody_else_does():
    """Mental Powers are invisible by default (6E1 p.151)."""
    session = _controlled("spare")
    from kirby_combat.brief import Brief
    from kirby_combat.loop.chooser import PhaseSituation
    from kirby_combat.roster import Roster

    def page_for(viewer_id):
        viewer = session.combatants[viewer_id]
        roster = Roster(session)
        return Brief(PhaseSituation(
            actor=viewer, menu=[LegalAction(action_id="dodge", kind="dodge", target_id=None,
                                            power_xmlid=None, power_name=None, summary="Dodge")],
            enemies=roster.enemies_of(viewer), allies=roster.allies_of(viewer),
            session=session, segment=12, turn=1,
        )).render()

    assert "under your Mind Control, order 'spare' (obeying" in page_for("psi")
    # rando sees psi's power by its name, "Mind Control" --- that is the
    # sheet --- and nothing about what psi has done to mark with it.
    assert "order 'spare'" not in page_for("rando")
    assert "under your Mind Control" not in page_for("rando")


# ── reach, elevation and movement ───────────────────────────────────────────

class _Flight:
    xmlid = "FLIGHT"
    name = "Flight"
    alias = "Flight"
    levels = 20
    active_cost = 20
    id = "src-FLIGHT"
    adders: list = []
    assigned_adders: list = []
    assigned_modifiers: list = []
    modifiers: list = []
    sub_powers: list = []


def test_each_enemy_says_how_far_how_high_and_what_movement_reaches_him():
    hero, goon = _two()
    hero.hero.powers.append(_Flight())
    page = _page(_fight(hero, goon, scene=_floor(hero=(0, 0, 0), goon=(15, 0, 8))), "hero").page
    section = page.split("Reaching them:\n", 1)[1]
    line = next(l for l in section.splitlines() if l.strip().startswith("goon: 17.0m"))
    assert "8m above you" in line
    assert "Running does not close, Flight (20m) reaches him this Phase" in line


def test_an_enemy_within_reach_is_said_to_be():
    page = _page(_fight(*_two(), scene=_floor(hero=(0, 0, 0), goon=(1, 0, 0))), "hero").page
    assert "goon: 1.0m, within your 1m reach" in page


# ── the matchup ─────────────────────────────────────────────────────────────

def test_the_matchup_states_the_numbers_and_gives_no_advice():
    """The old page's "close and trade" asymmetry, as facts only: who acts
    more often and what each side's heaviest attack averages through the
    other's defense."""
    tank = synthetic_combatant(
        id="tank", name="tank", ocv=8, dcv=5, spd=3, dex=30, str_=10, con=20,
        pd=20, ed=20, rpd=10, red=10, max_stun=60, max_body=15, max_end=40,
        side=Side.named("x"), attacks=[blast("tank-eb", dice=12)])
    pest = synthetic_combatant(
        id="pest", name="pest", ocv=8, dcv=5, spd=4, dex=10, str_=5, con=10,
        pd=3, ed=3, max_stun=25, max_body=10, max_end=30,
        side=Side.named("y"), attacks=[blast("pest-eb", dice=4)])
    page = _page(_fight(tank, pest), "tank").page
    assert "The matchup:" in page
    assert ("pest acts at least as often as you (SPD 4 to your 3); his heaviest attack "
            "averages about 0 of your 60 STUN through your defense, and yours about 39 "
            "through his.") in page
    for advice in ("Close and trade", "close and trade", "TACTIC"):
        assert advice not in page


# ── frameworks ──────────────────────────────────────────────────────────────

def test_the_frameworks_block_names_slots_dice_and_the_nnd_defense():
    bokor = HeroCombatant.from_build(require_authored("Bokor"), id="bokor")
    bokor.side = Side.named("x")
    goon = fighter("goon", side=Side.named("y"), dex=1)
    page = _page(_fight(bokor, goon), "bokor").page
    assert "Frameworks:" in page
    assert "Vodou Powers - gris gris bag powders (Multipower, 41-point reserve):" in page
    nnd = next(l for l in page.splitlines() if "Digitalis dust:" in l)
    assert "37 AP, fixed" in nnd and "NND, stopped only by" in nnd


# ── reading order ───────────────────────────────────────────────────────────

def test_the_page_lists_the_menu_scenery_last():
    """`PhaseSituation.ordered_menu`: the order both shipped choosers read,
    and now the order the page is printed in."""
    hero, goon = _two()
    scene = _floor(hero=(0, 5, 0), goon=(8, 5, 0))
    scene.walls.append(Wall(id="crate", name="Crate", segment=(Position(2, 0, 0), Position(2, 3, 0)),
                            height_m=1.0, blocks_los=False, blocks_movement=True,
                            cover_level=2, body=5, def_value=3))
    reader = _page(_fight(hero, goon, scene=scene), "hero")
    menu = reader.situation.menu
    assert any(getattr(a, "targets_construct", False) for a in menu)
    listed = [line.strip().split("]")[0][1:] for line in reader.page.splitlines()
              if line.startswith("  [")]
    assert listed == [a.action_id for a in reader.situation.ordered_menu]
    first_scenery = next(i for i, aid in enumerate(listed)
                         if any(a.action_id == aid and a.targets_construct for a in menu))
    assert all(not a.targets_construct for a in reader.situation.ordered_menu[:first_scenery])
    assert all(a.targets_construct for a in reader.situation.ordered_menu[first_scenery:])
