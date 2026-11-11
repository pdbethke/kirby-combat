"""A Darkness field lasts as long as its caster keeps it up (6E1 p.188).

0.33.3 made a field outlive the Phase it was cast in, and so made it
immortal: nothing ever took one down. The pages:

  * 6E1 p.188: Darkness is Constant and costs END; "a Darkness field
    remains in existence as long as the character pays the END for it".
  * 6E1 p.129-130: a Constant power's END is paid "when the character's
    Phase begins, before he does anything else", and he "must maintain a
    Line Of Sight to the location of the Power".
  * 6E1 p.347 / 6E2 p.107: a Constant power "turns off at the end of the
    Segment whenever the character is asleep, Stunned, or Knocked Out" ---
    not at his next Phase.
  * 6E2 p.131: a man who takes a Recovery "cannot even maintain a Constant
    Power".
  * 6E2 p.20: "turning off a Power" is a Zero Phase Action.

Scene: the caster (villain, DEX 30) at the origin, the mark (hero) 20m out.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC

from conftest import fighter  # tests/loop/conftest.py
from shaped import TEMPLATE, Dice, Picks, encounter_on, scene_with
from test_offered_means_resolves import _Power

from kirby_combat.darkness_fields import DarknessEnd, darkness_fields
from kirby_combat.loop import run_phase
from kirby_combat.loop.run import _situation_for
from kirby_combat.session.apply import apply_event
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"caster": (0, 0, 0), "mark": (20, 0, 0)}
#: A campaign that counts END (6E2 p.133); the superheroic default does not.
COUNTED = replace(TEMPLATE, manage_endurance=True, manage_endurance_npc=True)


def _fight(*, template=TEMPLATE, current_end=40, rec=6):
    """`conftest.fighter`'s stat block, carrying a 4-level Darkness."""
    from fixtures.synthetic_hero import synthetic_combatant

    caster = synthetic_combatant(
        id="caster", name="caster", ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=30, ego=15, str_=15, con=18, pre=15, rec=rec,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=current_end,
        side=VILLAINS, attacks=[],
    )
    caster.hero.powers.append(_Power("DARKNESS", 4, id="src-DARKNESS"))
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


def _until(enc, chooser, who="caster", *, skip=0):
    for _ in range(40):
        r = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
        enc = r.encounter
        if r.actor_id == who:
            if skip == 0:
                return enc, r
            skip -= 1
    raise AssertionError(f"{who} never acted")


def _ended(enc):
    return [e.reason for e in enc.sessions[0].event_log if e.kind == "DarknessEnded"]


def _zones(enc):
    return [c for c in enc.sessions[0].scene.constructs if c.kind == "darkness_zone"]


def _cast(enc, chooser):
    enc, r = _until(enc, chooser)
    assert r.kind == "darkness_zone" and _zones(enc), "the field went up"
    return enc


def test_the_field_stays_up_while_he_pays():
    # REC 0: the Post-Segment 12 Recovery would otherwise refill what the
    # upkeep takes.
    enc = _fight(template=COUNTED, rec=0)
    chooser = _then("darkness_zone")
    enc = _cast(enc, chooser)
    end_before = enc.sessions[0].combatants["caster"].state.current_end
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == []
    assert len(_zones(enc)) == 1
    paid = end_before - enc.sessions[0].combatants["caster"].state.current_end
    assert paid > 0, "keeping it up cost END at the top of his Phase"


def test_casting_it_costs_its_end():
    """6E1 p.188: Darkness "Costs END" --- the use, not only the upkeep."""
    enc = _cast(_fight(template=COUNTED), _then("darkness_zone"))
    assert enc.sessions[0].combatants["caster"].state.current_end < 40


def test_it_goes_down_when_he_cannot_pay():
    """6E1 p.188: it lasts as long as he pays. The cast takes his last END,
    and with no REC he has none at his next Phase."""
    enc = _fight(template=COUNTED, current_end=1, rec=0)
    chooser = _then("darkness_zone")
    enc = _cast(enc, chooser)
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [DarknessEnd.NO_END.value]
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
    assert _ended(enc) == [DarknessEnd.LOST_LINE_OF_SIGHT.value]


def test_it_goes_down_at_the_end_of_the_segment_he_is_stunned_in():
    """6E2 p.107 / 6E1 p.347: off at the end of the Segment, so nobody else
    acts behind a field whose caster is lying Stunned."""
    import uuid
    from datetime import datetime

    from kirby_combat.darkness_fields import darkness_at_segment_end
    from kirby_combat.session.events import ActionResolved, make_author_engine

    enc = _fight()
    enc = _cast(enc, _then("darkness_zone"))
    s = enc.sessions[0]
    # The mark's blow Stuns him: the status's own SET edge (statuses.py).
    s = apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        declaration_event_id="blow",
        result_payload={"target_id": "caster", "status_changes": ["Stunned"]},
    ))
    s = darkness_at_segment_end(s)
    ended = [e.reason for e in s.event_log if e.kind == "DarknessEnded"]
    assert ended == [DarknessEnd.OWNER_STUNNED.value]
    assert [c for c in s.scene.constructs if c.kind == "darkness_zone"] == []


def test_a_caster_on_his_feet_keeps_it_through_the_segment_end():
    from kirby_combat.darkness_fields import darkness_at_segment_end

    enc = _cast(_fight(), _then("darkness_zone"))
    s = darkness_at_segment_end(enc.sessions[0])
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
    assert _ended(enc) == [DarknessEnd.RECOVERED.value]


def test_he_can_drop_it_and_cast_it_again():
    """6E2 p.20: turning a power off is a Zero Phase Action. While his field
    is up a second is not offered; dropping it puts the offer back."""
    enc = _cast(_fight(), _then("darkness_zone"))
    kinds = {a.kind for a in _situation_for(enc.sessions[0], "caster").menu}
    assert "drop_darkness" in kinds and "darkness_zone" not in kinds

    chooser = _then("drop_darkness")
    enc, _ = _until(enc, chooser)
    assert _ended(enc) == [DarknessEnd.DROPPED.value]
    assert _zones(enc) == []
    kinds = {a.kind for a in _situation_for(enc.sessions[0], "caster").menu}
    assert "darkness_zone" in kinds and "drop_darkness" not in kinds


def test_an_ended_field_stays_ended_on_a_replay():
    enc = _cast(_fight(), _then("darkness_zone"))
    enc, _ = _until(enc, _then("drop_darkness"))
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
