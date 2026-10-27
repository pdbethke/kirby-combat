"""An offer the engine makes is an offer the engine can carry out.

Each of these was on the menu and then raised (or resolved as something the
book does not say) --- under `run_phase(on_unresolvable="raise")` a stopped
fight, on kirby-api a /run 500:

* `force_wall` was offered on `has_scene` alone and WITHOUT its power on the
  offer, so its resolver refused every one (99 of 99 in a 20-fight sweep).
* `rapid_fire` / `attack_construct` held at a wall that fell before the Held
  Action went off (6E2 p.22) looked the wall up, found rubble, and raised.
* a one-target Flash and Entangle made no Attack Roll (6E1 p.228, p.217),
  and the Flash summed its pips for BODY.
"""
from __future__ import annotations

from conftest import fighter                             # tests/loop/conftest.py
from shaped import TEMPLATE, Dice, Picks, encounter_on, scene_with

from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.loop.run import _situation_for
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


class _Power:
    """A build power in the shape the loader gives enumeration."""

    def __init__(self, xmlid: str, levels: int, *, id: str):
        self.xmlid = xmlid
        self.name = self.alias = xmlid.title()
        self.id = id
        self.levels = levels
        self.level_value = 1.0
        self.range = "Yes"
        self.range_value = 10 * levels * 10
        self.active_cost = levels * 10
        self.option_id = None
        self.assigned_adders: list = []
        self.assigned_modifiers: list = []
        self.sub_powers: list = []


def _caster(xmlid: str, levels: int):
    c = fighter("caster", side=VILLAINS, dex=30)
    c.hero.powers.append(_Power(xmlid, levels, id=f"src-{xmlid}"))
    return c


def _on_map(*cast, positions):
    return encounter_on(scene_with(positions), *cast)


def _kinds(enc, who="caster"):
    return {a.kind for a in _situation_for(enc.sessions[0], who).menu}


# ── force_wall ───────────────────────────────────────────────────────────────

def test_a_force_wall_is_raised_when_it_is_offered():
    """Seam: offered, chosen, resolved --- the wall is on the board."""
    enc = _on_map(_caster("FORCEWALL", 6), fighter("mark", side=HEROES),
                  positions={"caster": (0, 0, 0), "mark": (20, 0, 0)})
    assert "force_wall" in _kinds(enc)
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "force_wall"),
                       roller=Dice(face=3), on_unresolvable="raise")
    assert result.kind == "force_wall"
    raised = [e for e in result.encounter.sessions[0].event_log
              if e.kind == "BarrierRaised"]
    assert len(raised) == 1 and raised[0].body == 6


def test_no_force_wall_is_offered_where_it_cannot_be_placed():
    """The caster is off the map: the resolver could not say where the wall
    goes, so the menu does not promise one. Same for every enemy off it."""
    off_me = _on_map(_caster("FORCEWALL", 6), fighter("mark", side=HEROES),
                     positions={"mark": (20, 0, 0)})
    assert "force_wall" not in _kinds(off_me)
    off_them = _on_map(_caster("FORCEWALL", 6), fighter("mark", side=HEROES),
                       positions={"caster": (0, 0, 0)})
    assert "force_wall" not in _kinds(off_them)


def test_darkness_and_images_ask_the_same_question():
    """They place the force wall's way (`_point_near_nearest_enemy`), so the
    same gate binds them."""
    for xmlid, kind in (("DARKNESS", "darkness_zone"), ("IMAGES", "image_decoy")):
        enc = _on_map(_caster(xmlid, 4), fighter("mark", side=HEROES),
                      positions={"mark": (20, 0, 0)})
        assert kind not in _kinds(enc), kind


# ── a shot at a wall that has come down ──────────────────────────────────────

def _wall_fight():
    from kirby_combat.scene import Construct, Position

    shed = Construct(obj_id="shed", kind="wall",
                     segment=(Position(5, -2, 0), Position(5, 2, 0)),
                     blocks_los=True, blocks_movement=True, def_value=1, body=2)
    scene = scene_with({"caster": (0, 0, 0), "mark": (20, 0, 0)}, constructs=[shed])
    session = CombatSession.create(
        id="s", combatants=[fighter("caster", side=VILLAINS, dex=30),
                            fighter("mark", side=HEROES)],
        scene=scene, template=TEMPLATE, dice_roller=Dice(face=6),
    ).start()
    return session


def test_a_burst_at_a_fallen_wall_is_fired_into_the_rubble():
    """The Held Action case (6E2 p.22): the menu offered `rapid_fire` at the
    shed, somebody else's attack brings it down, then his burst goes off.
    It resolves --- shots at where it stood, no damage --- instead of
    raising."""
    from kirby_combat.loop.registry import resolve_chosen

    session = _wall_fight()
    menu = _situation_for(session, "caster").menu
    burst = next(a for a in menu if a.kind == "rapid_fire" and a.target_id == "shed")
    smash = next(a for a in menu if a.kind == "attack_construct" and a.target_id == "shed")
    down = resolve_chosen(session, session.combatants["caster"], smash,
                          template=TEMPLATE, roller=Dice(face=6)).session
    assert down.event_log[-1].result_payload["destroyed"] is True
    after = resolve_chosen(down, down.combatants["caster"], burst,
                           template=TEMPLATE, roller=Dice(face=6))
    payload = after.session.event_log[-1].result_payload
    assert payload["already_destroyed"] is True and payload["body_dealt"] == 0
    again = resolve_chosen(after.session, after.session.combatants["caster"], smash,
                           template=TEMPLATE, roller=Dice(face=6))
    assert again.session.event_log[-1].result_payload["already_destroyed"] is True


def test_a_wall_that_was_never_there_still_raises():
    """Rubble is not a licence to accept any id: an offer at a wall the place
    never had was never true."""
    import pytest
    from dataclasses import replace

    from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen

    session = _wall_fight()
    burst = next(a for a in _situation_for(session, "caster").menu
                 if a.kind == "rapid_fire" and a.target_id == "shed")
    with pytest.raises(UnresolvableAction):
        resolve_chosen(session, session.combatants["caster"],
                       replace(burst, target_id="no-such-wall"),
                       template=TEMPLATE, roller=Dice(face=6))


# ── a one-target Flash and Entangle roll to hit ──────────────────────────────

def _effect_fight(xmlid: str, levels: int):
    enc = Encounter(id="e", turn=1, segment=12, sessions=[CombatSession.create(
        id="s", combatants=[_caster(xmlid, levels), fighter("mark", side=HEROES)],
        scene=None, template=TEMPLATE, dice_roller=Dice(face=3),
    ).start()])
    return enc


def _run(enc, kind, face):
    return run_phase(enc, Picks(lambda a, _s: a.kind == kind),
                     roller=Dice(face=face), on_unresolvable="raise")


def test_a_flash_that_misses_blinds_nobody():
    """6E1 p.228: "a character must make an Attack Roll". 3d6 of 6s is 18,
    which always misses (6E2 p.37); no Flash dice are rolled for it."""
    from kirby_combat.actions.flash import Flash

    result = _run(_effect_fight("FLASH", 6), "flash", 6)
    out = result.encounter.sessions[0]
    assert not Flash.is_flashed(out, "mark", "sight")[0]
    miss = next(e.result_payload for e in reversed(out.event_log)
                if e.kind == "ActionResolved")
    assert miss["type"] == "flash_attack" and miss["hit"] is False and miss["roll"] == 18


def test_a_flash_counts_body_not_pips():
    """6E1 p.228: "rolls the Flash dice and counts the Normal Damage BODY".
    6d6 of 2s is 6 BODY (12 pips): 6 Segments against Flash Defense 0. The
    roll (6) hit OCV 9 against DCV 5 and is on the row."""
    from kirby_combat.actions.flash import Flash

    result = _run(_effect_fight("FLASH", 6), "flash", 2)
    out = result.encounter.sessions[0]
    flashed, remaining = Flash.is_flashed(out, "mark", "sight")
    assert flashed
    applied = next(e for e in out.event_log if e.kind == "FlashApplied")
    assert applied.segments == 6
    row = next(e.result_payload for e in out.event_log if e.kind == "ActionResolved"
               and (e.result_payload or {}).get("type") == "flash_attack")
    assert row["hit"] is True and row["roll"] == 6


def test_an_entangle_that_misses_binds_nobody():
    """6E1 p.217: "To use Entangle, a character must make an Attack Roll"."""
    from kirby_combat.session.effects import entangle_state

    result = _run(_effect_fight("ENTANGLE", 4), "entangle", 6)
    out = result.encounter.sessions[0]
    assert not entangle_state(out, "mark").is_entangled
    row = next(e.result_payload for e in reversed(out.event_log)
               if e.kind == "ActionResolved")
    assert row["type"] == "entangle_attack" and row["hit"] is False


def test_an_entangle_that_hits_binds_with_its_counted_body():
    from kirby_combat.session.effects import entangle_state

    result = _run(_effect_fight("ENTANGLE", 4), "entangle", 2)
    st = entangle_state(result.encounter.sessions[0], "mark")
    assert st.is_entangled and st.body_remaining == 4


def test_a_dodge_reaches_the_flash_roll():
    """The roll is folded at the one door (`_fold_session_cvs`): a Dodging
    target's +3 DCV turns a roll that would hit into a miss: a 13 hits OCV 9
    against DCV 5 (needs 15 or less), not against DCV 8 (12 or less)."""
    from kirby_combat.actions.reactive.dodge import Dodge
    from kirby_combat.actions.targeted_effects import effect_attack_roll

    enc = _effect_fight("FLASH", 6)
    s = enc.sessions[0]
    flash = s.combatants["caster"].hero.powers[-1]
    plain = effect_attack_roll(s, s.combatants["caster"], s.combatants["mark"],
                               flash, Dice(queue=[[5, 4, 4]]), TEMPLATE)
    assert plain.hit
    dodging, _ = Dodge.declare(s, "mark")
    folded = effect_attack_roll(dodging, dodging.combatants["caster"],
                                dodging.combatants["mark"], flash,
                                Dice(queue=[[5, 4, 4]]), TEMPLATE)
    assert not folded.hit


# ── shaped powers at constructs ──────────────────────────────────────────────

def test_a_shaped_power_is_never_aimed_at_a_construct():
    """The construct doors (`_resolve_attack_construct`,
    `_rapid_fire_at_construct`) make no Attack Roll and land the power
    unshaped: an Area would hit one wall and nobody beside it, a Constant one
    would hit once. So a shaped power is not offered at a construct at all
    (`attack_shapes.offer_is_buildable`), while the same power at a man is."""
    from dataclasses import replace as _replace

    from shaped import armed, shaped_blast
    from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
    from kirby_combat.scene import Construct, Position

    storm = shaped_blast("storm", 6, area=AreaSpec(
        shape=AreaShape.RADIUS, size_m=2.0, targeting=AreaTargeting.STANDARD,
        explosion=False, personal_immunity=False, width_m=2.0, height_m=2.0,
        thin_cone=False, unbuilt=()))
    shed = Construct(obj_id="shed", kind="wall",
                     segment=(Position(5, -2, 0), Position(5, 2, 0)),
                     blocks_los=False, blocks_movement=True, def_value=1, body=8)
    control = encounter_on(
        scene_with({"caster": (0, 0, 0), "mark": (8, 3, 0)}, constructs=[shed]),
        armed("caster", shaped_blast("plain", 6), side=VILLAINS, dex=30),
        armed("mark", None, side=HEROES))
    assert [a for a in _situation_for(control.sessions[0], "caster").menu
            if a.target_id == "shed"], "an unshaped Blast is offered at the shed"
    for power in (storm, _replace(shaped_blast("beam", 6), constant=True)):
        enc = encounter_on(
            scene_with({"caster": (0, 0, 0), "mark": (8, 3, 0)}, constructs=[shed]),
            armed("caster", power, side=VILLAINS, dex=30),
            armed("mark", None, side=HEROES))
        menu = _situation_for(enc.sessions[0], "caster").menu
        assert not [a for a in menu if a.target_id == "shed"
                    and a._attack_view is power], power.name
        assert [a for a in menu if a.kind == "attack" and a.target_id == "mark"]
