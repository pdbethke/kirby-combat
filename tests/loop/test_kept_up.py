"""What a man keeps up on the board lasts as long as the book says (`kept_up`).

Darkness (6E1 p.188) and Images (p.238) are Constant powers that leave
something in the scene. The pages:

  * p.129-130: a Constant power's END is paid "when the character's Phase
    begins, before he does anything else", and he "must maintain a Line Of
    Sight to the location of the Power".
  * p.129 (Sapphire) and p.188: he may keep several up, each paying for
    itself --- "provided he pays the END cost for all fields".
  * p.369 / p.403: a Charge on a Constant power lasts one Phase.
  * p.402: a Framework slot that loses the reserve stops working.
  * p.347 / 6E2 p.107: off at the end of the Segment he is Stunned in.
  * 6E2 p.131: a Recovery keeps no Constant power up.
  * 6E2 p.20: turning one off is a Zero Phase Action.

Scene: the caster (villain, DEX 30) at the origin, the mark (hero) 20m out.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace as NS

from conftest import fighter  # tests/loop/conftest.py
from shaped import TEMPLATE, Dice, Picks, encounter_on, scene_with
from test_offered_means_resolves import _Power

from kirby_combat.darkness_fields import darkness_fields
from kirby_combat.kept_up import (
    KeptKind,
    kept_up,
    kept_up_at_segment_end,
    maintain_kept_up,
)
from kirby_combat.loop import run_phase
from kirby_combat.loop.run import _situation_for
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_engine
from kirby_combat.side import Side
from kirby_combat.upkeep import UpkeepEnd

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"caster": (0, 0, 0), "mark": (20, 0, 0)}
#: A campaign that counts END (6E2 p.133); the superheroic default does not.
COUNTED = replace(TEMPLATE, manage_endurance=True, manage_endurance_npc=True)


def _charges(n: int, *adders: str):
    word = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR"}[n]
    return NS(xmlid="CHARGES", option_id=word, alias_for_vector=f"{n} Charges",
              assigned_adders=[NS(xmlid=a) for a in adders], private=False)


def _fight(*powers, template=TEMPLATE, current_end=40, rec=6):
    """`conftest.fighter`'s stat block, carrying ``powers`` (default: a
    4-level Darkness)."""
    from fixtures.synthetic_hero import synthetic_combatant

    caster = synthetic_combatant(
        id="caster", name="caster", ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=30, ego=15, str_=15, con=18, pre=15, rec=rec,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=current_end,
        side=VILLAINS, attacks=[],
    )
    caster.hero.powers.extend(powers or [_Power("DARKNESS", 4, id="src-DARKNESS")])
    # The mark is unarmed, so the caster is never asked to Abort and every
    # Phase `_until` stops on is his own.
    return encounter_on(scene_with(POSITIONS), caster,
                        fighter("mark", side=HEROES, armed=False), template=template)


def _then(*steps):
    """The caster takes each kind in ``steps`` once, in order; everyone
    else, and the caster afterwards, Dodges."""
    left = list(steps)

    def want(action, situation):
        if situation.actor.id != "caster" or not left:
            return False
        if action.kind == left[0]:
            left.pop(0)
            return True
        return False
    return Picks(want)


def _until(enc, chooser, who="caster", *, roller=None):
    for _ in range(40):
        r = run_phase(enc, chooser, roller=roller or Dice(face=3),
                      on_unresolvable="raise")
        enc = r.encounter
        if r.actor_id == who:
            return enc, r
    raise AssertionError(f"{who} never acted")


def _ended(enc):
    """Every reason anything kept up came down, in order."""
    out = []
    for e in enc.sessions[0].event_log:
        if e.kind == "DarknessEnded":
            out.append(e.reason)
        payload = getattr(e, "result_payload", None) or {}
        if payload.get("type") == "image_ended":
            out.append(payload["reason"])
    return out


def _zones(enc):
    return [c for c in enc.sessions[0].scene.constructs if c.kind == "darkness_zone"]


def _end(enc):
    return enc.sessions[0].combatants["caster"].state.current_end


def _menu(enc):
    return _situation_for(enc.sessions[0], "caster").menu


def _cast(enc, chooser, kind="darkness_zone"):
    enc, r = _until(enc, chooser)
    assert r.kind == kind and kept_up(enc.sessions[0]), "it went up"
    return enc


def _stun_him(s):
    """The mark's blow Stuns him: the status's own SET edge (statuses.py)."""
    return apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        declaration_event_id="blow",
        result_payload={"target_id": "caster", "status_changes": ["Stunned"]},
    ))


# ---------------------------------------------------------------- upkeep

def test_the_field_stays_up_while_he_pays():
    # REC 0: the Post-Segment 12 Recovery would otherwise refill what the
    # upkeep takes.
    enc = _fight(template=COUNTED, rec=0)
    chooser = _then("darkness_zone")
    enc = _cast(enc, chooser)
    end_before = _end(enc)
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == []
    assert len(_zones(enc)) == 1
    assert end_before - _end(enc) > 0, "keeping it up cost END at the top of his Phase"


def test_casting_it_costs_its_end():
    """6E1 p.188: Darkness "Costs END" --- the use, not only the upkeep."""
    enc = _cast(_fight(template=COUNTED), _then("darkness_zone"))
    assert _end(enc) < 40


def test_a_zero_end_field_costs_nothing():
    """The sheet's own END column (`end_usage`): a 0 END Darkness costs 0
    to cast and 0 to keep up. It was priced off its Active Points."""
    power = _Power("DARKNESS", 4, id="src-DARKNESS")
    power.end_usage = 0
    chooser = _then("darkness_zone")
    enc = _cast(_fight(power, template=COUNTED, rec=0), chooser)
    enc, _ = _until(enc, chooser)
    assert _end(enc) == 40 and len(_zones(enc)) == 1


def test_it_goes_down_when_he_cannot_pay():
    """6E1 p.188: it lasts as long as he pays. The cast takes his last END,
    and with no REC he has none at his next Phase."""
    enc = _fight(template=COUNTED, current_end=1, rec=0)
    chooser = _then("darkness_zone")
    enc = _cast(enc, chooser)
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [UpkeepEnd.NO_END.value]
    assert _zones(enc) == []


def test_it_goes_down_when_he_loses_sight_of_it():
    """6E1 p.129: "maintain a Line Of Sight to the location of the Power"."""
    from kirby_world.scene import Position, Wall

    enc = _fight()
    chooser = _then("darkness_zone")
    enc = _cast(enc, chooser)
    s = enc.sessions[0]
    wall = Wall(id="w", name="w",
                segment=(Position(3.0, -5.0, 0.0), Position(3.0, 5.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True, cover_level=4)
    enc = replace(enc, sessions=[replace(s, scene=replace(s.scene, walls=[wall]))])
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [UpkeepEnd.LOST_LINE_OF_SIGHT.value]


# ------------------------------------------------------- several at once

def test_he_keeps_two_fields_and_pays_for_each():
    """6E1 p.188: "A character may maintain more than one Darkness field at
    once, provided he pays the END cost for all fields"; p.129's Sapphire
    pays "END to maintain each use ... 20 END per Phase"."""
    power = _Power("DARKNESS", 4, id="src-DARKNESS")
    power.end_usage = 3
    chooser = _then("darkness_zone", "darkness_zone")
    enc = _fight(power, template=COUNTED, rec=0)
    enc = _cast(enc, chooser)
    assert "darkness_zone" in {a.kind for a in _menu(enc)}, \
        "a second field is offered while the first is up"
    enc = _cast(enc, chooser)
    assert len(darkness_fields(enc.sessions[0])) == 2
    before = _end(enc)
    enc, _ = _until(enc, chooser)
    assert before - _end(enc) == 6, "two fields, 3 END each, at the top of his Phase"
    assert _ended(enc) == []


def test_he_turns_off_the_one_he_chooses():
    """6E2 p.20: one Zero Phase turn-off offer per field, naming it."""
    chooser = _then("darkness_zone", "darkness_zone")
    enc = _cast(_fight(), chooser)
    enc = _cast(enc, chooser)
    first, second = darkness_fields(enc.sessions[0])
    drops = sorted(a.action_id for a in _menu(enc) if a.kind == "drop_darkness")
    assert drops == sorted([f"drop_darkness:{first.id}", f"drop_darkness:{second.id}"])

    pick = Picks(lambda a, s: s.actor.id == "caster"
                 and a.action_id == f"drop_darkness:{first.id}")
    enc, _ = _until(enc, pick)
    assert _ended(enc) == [UpkeepEnd.DROPPED.value]
    assert [f.id for f in darkness_fields(enc.sessions[0])] == [second.id]


# ------------------------------------------------------ Stun, Recovery

def test_it_goes_down_at_the_end_of_the_segment_he_is_stunned_in():
    """6E2 p.107 / 6E1 p.347: off at the end of the Segment, so nobody else
    acts behind a field whose caster is lying Stunned."""
    enc = _cast(_fight(), _then("darkness_zone"))
    s = kept_up_at_segment_end(_stun_him(enc.sessions[0]))
    assert [e.reason for e in s.event_log if e.kind == "DarknessEnded"] == [
        UpkeepEnd.OWNER_STUNNED.value]
    assert [c for c in s.scene.constructs if c.kind == "darkness_zone"] == []


def test_a_caster_on_his_feet_keeps_it_through_the_segment_end():
    enc = _cast(_fight(), _then("darkness_zone"))
    s = kept_up_at_segment_end(enc.sessions[0])
    assert [e for e in s.event_log if e.kind == "DarknessEnded"] == []


def test_a_recovery_lets_it_go():
    """6E2 p.131: a man who Recovers "cannot even maintain a Constant Power"."""
    # Low END and no REC, so a Recovery is on his menu (`enumeration`: under
    # a third of his END).
    enc = _fight(current_end=6, rec=0)
    chooser = _then("darkness_zone", "recover")
    enc = _cast(enc, chooser)
    enc, r = _until(enc, chooser)
    assert r.kind == "recover"
    assert _ended(enc) == [UpkeepEnd.RECOVERED.value]


def test_an_ended_field_stays_ended_on_a_replay():
    chooser = _then("darkness_zone")
    enc = _cast(_fight(), chooser)
    field = darkness_fields(enc.sessions[0])[0]
    enc, _ = _until(enc, Picks(lambda a, s: s.actor.id == "caster"
                               and a.action_id == f"drop_darkness:{field.id}"))
    s = enc.sessions[0]
    fresh = s.__class__.create(
        id=s.id, combatants=list(s.initial_combatants.values()),
        scene=s.initial_scene.snapshot(), template=s.template,
        dice_roller=s.dice_roller,
    )
    for event in s.event_log:
        fresh = apply_event(fresh, event)
    assert [c for c in fresh.scene.constructs if c.kind == "darkness_zone"] == []
    assert darkness_fields(fresh) == []


# ---------------------------------------------------------------- Charges

def test_a_charged_field_runs_a_charge_a_phase_and_goes_down_when_empty():
    """6E1 p.369: "Each Charge normally only lasts for one Phase"; p.403:
    "Constant Powers require one Charge per Phase". Two Charges: one to
    cast, one to keep it up a Phase, and none for the Phase after."""
    power = _Power("DARKNESS", 4, id="src-DARKNESS")
    power.end_usage = 0
    power.assigned_modifiers = [_charges(2)]
    chooser = _then("darkness_zone")
    enc = _cast(_fight(power), chooser)
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [], "the second Charge kept it up"
    assert "darkness_zone" not in {a.kind for a in _menu(enc)}, \
        "no Charge left, so no new field is offered"
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [UpkeepEnd.NO_CHARGES.value]


def test_continuing_uncontrolled_and_fuel_are_not_offered():
    """6E1 p.402 names Uncontrolled and Continuing Charges as the exceptions
    to the slot rule; with Fuel Charges (p.373) each ends a power in its own
    way, which nothing here carries out --- so it is not offered rather
    than kept up by the wrong rule."""
    for mods in ([_charges(2, "CONTINUING")], [_charges(2, "FUEL")],
                 [NS(xmlid="UNCONTROLLED", option_id=None, assigned_adders=[],
                     private=False)]):
        power = _Power("DARKNESS", 4, id="src-DARKNESS")
        power.assigned_modifiers = mods
        enc = _fight(power)
        assert "darkness_zone" not in {a.kind for a in _menu(enc)}, mods[0].xmlid


# ---------------------------------------------------------- the reserve

def test_switching_the_slot_off_takes_it_down():
    """6E1 p.402: "If he changes the reserve/Pool allocation to another slot
    while that Constant or Persistent Power is in use, the power immediately
    ceases to operate"."""
    power = _Power("DARKNESS", 4, id="src-DARKNESS")
    power.framework_id, power.slot_id = "mp", "src-DARKNESS"
    enc = _cast(_fight(power), _then("darkness_zone"))
    s = enc.sessions[0]
    s = apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        declaration_event_id="realloc",
        result_payload={"kind": "reallocate", "combatant_id": "caster",
                        "framework_id": "mp", "active_slot_ids": ["blast"]},
    ))
    s = maintain_kept_up(s, "caster", template=TEMPLATE, roller=Dice(face=3))
    assert [e.reason for e in s.event_log if e.kind == "DarknessEnded"] == [
        UpkeepEnd.SLOT_SWITCHED.value]


def test_a_slot_without_the_reserve_is_not_offered():
    """p.402: allocating the reserve comes before turning the power on."""
    from kirby_combat.upkeep import slot_on

    power = _Power("DARKNESS", 4, id="src-DARKNESS")
    power.framework_id, power.slot_id = "mp", "src-DARKNESS"
    caster = _fight(power).sessions[0].combatants["caster"]
    on_blast = {"mp": (60, 60, {"blast"}, {"blast": 60, "src-DARKNESS": 40})}
    on_dark = {"mp": (60, 40, {"src-DARKNESS"}, {"blast": 60, "src-DARKNESS": 40})}
    never = {"mp": (60, 0, set(), {"blast": 60, "src-DARKNESS": 40})}
    assert not slot_on(caster, power, on_blast)
    assert slot_on(caster, power, on_dark)
    assert slot_on(caster, power, never), "never reallocated: as he brought it in"


# ----------------------------------------------------------------- Images

def _images():
    return _Power("IMAGES", 4, id="src-IMAGES")


def test_an_image_costs_end_and_is_kept_up_like_darkness():
    """6E1 p.238: Images is "Duration: constant ... Costs END: yes"."""
    chooser = _then("image_decoy")
    enc = _cast(_fight(_images(), template=COUNTED, rec=0), chooser, "image_decoy")
    cast_cost = 40 - _end(enc)
    assert cast_cost > 0
    enc, _ = _until(enc, chooser)
    assert _end(enc) < 40 - cast_cost, "kept up at the top of his Phase"
    assert [i.kind for i in kept_up(enc.sessions[0])] == [KeptKind.IMAGE]


def test_he_keeps_two_images_and_drops_one():
    chooser = _then("image_decoy", "image_decoy")
    enc = _cast(_fight(_images()), chooser, "image_decoy")
    enc = _cast(enc, chooser, "image_decoy")
    first, second = kept_up(enc.sessions[0])
    enc, _ = _until(enc, Picks(lambda a, s: s.actor.id == "caster"
                               and a.action_id == f"drop_image:{first.id}"))
    assert _ended(enc) == [UpkeepEnd.DROPPED.value]
    assert [i.id for i in kept_up(enc.sessions[0])] == [second.id]


def test_an_image_goes_down_when_he_is_stunned_or_recovers():
    enc = _cast(_fight(_images()), _then("image_decoy"), "image_decoy")
    s = kept_up_at_segment_end(_stun_him(enc.sessions[0]))
    assert kept_up(s) == []

    enc = _fight(_images(), current_end=6, rec=0)
    chooser = _then("image_decoy", "recover")
    enc = _cast(enc, chooser, "image_decoy")
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [UpkeepEnd.RECOVERED.value]
