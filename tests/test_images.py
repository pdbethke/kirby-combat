"""Images — a perceivable thing that is not a combatant (6E1 p.238-239).

The rule has three moving parts and the engine owns all three:

  1. **Placement** is a normal Attack Roll against DCV 3.
  2. **Perception** is Line Of Sight, and nothing else. The page is explicit
     that an observer needs neither Reach nor to be inside the Image's Area.
  3. **Disbelief** is a PER Roll made PER OBSERVER, modified by the realism
     bought for the Image and by bonuses for its complexity. Success does
     not remove the Image -- the observer perceives it and knows it is
     false; everyone else still believes it.

Point 3 is the one an implementation gets wrong by storing a single
`disbelieved` flag on the Image. One observer seeing through an illusion
must not spoil it for the room.
"""

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.images import Images
from kirby_combat.dice import FakeRoller
from kirby_combat.scene.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


def _c(id_):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


CASTER = Position(0.0, 0.0, 1.5)
NEAR = Position(5.0, 0.0, 1.5)
FAR = Position(120.0, 0.0, 1.5)      # miles away in spirit: LoS is LoS
IMAGE_AT = (10.0, 0.0, 1.5)


def _session(positions=None, walls=None, constructs=None, roller=None):
    positions = positions or {"mirage": CASTER, "ana": NEAR, "boz": FAR}
    scene = Scene(
        id="s", name="Images",
        bounds=SceneBounds(0, 0, 0, 200, 200, 20),
        surfaces=[], walls=list(walls or []), hazards=[],
        ambient=AmbientConditions(),
        constructs=list(constructs or []),
        combatant_positions=positions,
    )
    return CombatSession.create(
        id="s1", combatants=[_c("mirage"), _c("ana"), _c("boz")],
        scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller or FakeRoller([]),
    ).start()


def _place(session, *, roller=None, **kw):
    params = dict(
        caster_id="mirage", position=IMAGE_AT, sense_groups=["sight"],
        per_modifier=0,
    )
    params.update(kw)
    return Images.place(session, roller=roller or FakeRoller([[3, 3, 3]]), **params)


# ---------------------------------------------------------------------------
# Placement — an Attack Roll against DCV 3 (6E1 p.238)
# ---------------------------------------------------------------------------

def test_placing_an_image_rolls_against_dcv_3():
    """OCV 8 vs DCV 3 needs 3d6 <= 8 + 11 - 3 = 16; a 9 makes it."""
    s = _session()
    s, result = _place(s)
    assert result.hit is True
    assert result.target_dcv == 3
    assert result.image_id


def test_a_missed_roll_places_no_image():
    s = _session()
    s, result = _place(s, roller=FakeRoller([[6, 6, 6]]))
    assert result.hit is False
    assert result.image_id is None
    assert Images.active(s) == ()


def test_a_placed_image_is_listed_and_addressable():
    s = _session()
    s, result = _place(s)
    images = Images.active(s)
    assert len(images) == 1
    assert images[0].image_id == result.image_id
    assert images[0].caster_id == "mirage"
    assert images[0].sense_groups == ("sight",)


def test_placement_is_recorded_on_the_log():
    s = _session()
    s, _ = _place(s)
    declared = [e for e in s.event_log
                if e.kind == "ActionDeclared" and e.action_type == "images"]
    assert len(declared) == 1
    assert declared[0].parameters["target_dcv"] == 3


def test_an_image_can_be_given_a_dcv_of_the_casters_choosing():
    """6E1 p.238: an Image of something that should have a DCV has whatever
    DCV its creator wants. The engine records it; it does not invent one."""
    s = _session()
    s, result = _place(s, apparent_dcv=6)
    assert Images.active(s)[0].apparent_dcv == 6


def test_an_image_ends_when_the_caster_stops_paying():
    """Images is a Constant Power -- it lasts as long as END is paid."""
    s = _session()
    s, result = _place(s)
    s = Images.dismiss(s, image_id=result.image_id)
    assert Images.active(s) == ()


# ---------------------------------------------------------------------------
# Perception — Line Of Sight, and nothing else (6E1 p.238)
# ---------------------------------------------------------------------------

def test_everyone_with_line_of_sight_perceives_the_image():
    s = _session()
    s, r = _place(s)
    assert Images.perceived_by(s, r.image_id, "ana") is True
    assert Images.perceived_by(s, r.image_id, "boz") is True


def test_distance_alone_does_not_prevent_perception():
    """6E1 p.238 is explicit: observers need not be within Reach of the
    Image, nor inside its area of effect. A ball of light might be seen
    miles off."""
    s = _session()
    s, r = _place(s)
    assert Images.perceived_by(s, r.image_id, "boz") is True


def test_a_wall_between_observer_and_image_blocks_it():
    from kirby_combat.scene.scene import Wall

    wall = Wall(id="w1", name="wall", height_m=5.0,
                segment=(Position(7.0, -5.0, 0.0), Position(7.0, 5.0, 0.0)))
    s = _session(walls=[wall])
    s, r = _place(s)
    assert Images.perceived_by(s, r.image_id, "ana") is False


def test_asking_about_a_group_the_image_does_not_affect_is_false():
    """A Sight Image is not heard. Narrowing the question to a Group the
    Image was never bought against answers no, whatever the observer has."""
    s = _session()
    s, r = _place(s, sense_groups=["sight"])
    assert Images.perceived_by(s, r.image_id, "ana", sense_group="hearing") is False
    assert Images.perceived_by(s, r.image_id, "ana", sense_group="sight") is True


def test_a_hearing_image_survives_a_sight_flash():
    """The Group keying has to be real in both directions: blinding an
    observer must not stop him HEARING an Image. A gate that only asked
    "is this observer flashed at all" would fail this.
    """
    from kirby_combat.actions.flash import Flash

    s = _session()
    s, r = _place(s, sense_groups=["hearing"])
    s, _ = Flash.apply(s, attacker_id="mirage", target_id="ana",
                       sense_group="sight", body_dealt=8, flash_defense=0)
    assert Images.perceived_by(s, r.image_id, "ana") is True


def test_a_hearing_image_survives_a_sight_darkness():
    """Same keying, on the Darkness gate rather than the Flash one."""
    from kirby_combat.scene.construct import Construct

    zone = Construct(
        obj_id="dz", kind="darkness_zone",
        polygon_xy=[(7.0, -5.0), (9.0, -5.0), (9.0, 5.0), (7.0, 5.0)],
        elevation_range_m=(0.0, 3.0), sense_group="sight",
    )
    s = _session(constructs=[zone])
    s, r = _place(s, sense_groups=["hearing"])
    assert Images.perceived_by(s, r.image_id, "ana") is True


def test_a_flashed_observer_does_not_perceive_a_sight_image():
    """The Image is a sense effect; a blinded observer misses it."""
    from kirby_combat.actions.flash import Flash

    s = _session()
    s, r = _place(s)
    s, _ = Flash.apply(s, attacker_id="mirage", target_id="ana",
                       sense_group="sight", body_dealt=8, flash_defense=0)
    assert Images.perceived_by(s, r.image_id, "ana") is False


def test_a_sight_image_is_not_perceived_through_a_sight_darkness():
    """6E1 p.188 says so directly: light created by Sight Group Images has
    no effect in a Darkness to Sight Group field. Falls out of routing
    Image perception through the same occlusion gate as everything else --
    which is the point of routing it there.
    """
    from kirby_combat.scene.construct import Construct

    zone = Construct(
        obj_id="dz", kind="darkness_zone",
        polygon_xy=[(7.0, -5.0), (9.0, -5.0), (9.0, 5.0), (7.0, 5.0)],
        elevation_range_m=(0.0, 3.0), sense_group="sight",
    )
    s = _session(constructs=[zone])
    s, r = _place(s)
    assert Images.perceived_by(s, r.image_id, "ana") is False


# ---------------------------------------------------------------------------
# Disbelief — PER OBSERVER (6E1 p.239)
# ---------------------------------------------------------------------------

def test_a_successful_per_roll_lets_one_observer_see_through_it():
    s = _session()
    s, r = _place(s)
    s, d = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    assert d.succeeded is True
    assert Images.disbelieved_by(s, r.image_id, "ana") is True


def test_disbelief_does_not_leak_to_other_observers():
    """The defect this test exists to catch: one `disbelieved` flag on the
    Image instead of per-observer state."""
    s = _session()
    s, r = _place(s)
    s, _ = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    assert Images.disbelieved_by(s, r.image_id, "ana") is True
    assert Images.disbelieved_by(s, r.image_id, "boz") is False


def test_a_failed_roll_leaves_the_observer_believing():
    s = _session()
    s, r = _place(s)
    s, d = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[6, 6, 6]]))
    assert d.succeeded is False
    assert Images.disbelieved_by(s, r.image_id, "ana") is False


def test_a_spotted_image_does_not_disappear():
    """6E1 p.239: Images spotted as fake do NOT vanish -- the observer can
    tell it is fake and acts accordingly. So it is still perceived, and it
    is still there for everyone else."""
    s = _session()
    s, r = _place(s)
    s, _ = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    assert Images.active(s)                                   # still there
    assert Images.perceived_by(s, r.image_id, "ana") is True  # still seen
    assert Images.believed_by(s, r.image_id, "ana") is False  # but not believed
    assert Images.believed_by(s, r.image_id, "boz") is True


def test_realism_bought_for_the_image_penalises_the_per_roll():
    """6E1 p.238: +3 Character Points buys -1 to observers' PER Rolls.
    INT 15 rolls 12-; at -3 the roll is 9-, so a 10 that would have made
    the unmodified roll now fails."""
    s = _session()
    s, r = _place(s, per_modifier=-3)
    s, d = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[4, 3, 3]]))   # 3d6 = 10
    assert d.target_number == 9
    assert d.succeeded is False


def test_complexity_can_help_the_observer_instead():
    """6E1 p.239 modifies the roll by penalties paid for AND bonuses for
    complexity -- the net modifier runs in both directions, so a positive
    one has to work too."""
    s = _session()
    s, r = _place(s, per_modifier=+2)
    s, d = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[5, 4, 5]]))   # 3d6 = 14
    assert d.target_number == 14
    assert d.succeeded is True


def test_an_observer_who_cannot_perceive_the_image_cannot_disbelieve_it():
    """6E1 p.239 gives the roll to characters WHO PERCEIVE the Image."""
    from kirby_combat.scene.scene import Wall

    wall = Wall(id="w1", name="wall", height_m=5.0,
                segment=(Position(7.0, -5.0, 0.0), Position(7.0, 5.0, 0.0)))
    s = _session(walls=[wall])
    s, r = _place(s)
    s, d = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    assert d.succeeded is False
    assert d.reason == "not_perceived"


def test_disbelief_is_recorded_on_the_log():
    s = _session()
    s, r = _place(s)
    s, _ = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    payloads = [e.result_payload for e in s.event_log
                if getattr(e, "result_payload", None)
                and e.result_payload.get("type") == "image_disbelief"]
    assert len(payloads) == 1
    assert payloads[0]["observer_id"] == "ana"


def test_believers_lists_who_is_still_fooled():
    """The surface a driver needs to decide who may target the decoy."""
    s = _session()
    s, r = _place(s)
    assert Images.believers(s, r.image_id) == ("ana", "boz")
    s, _ = Images.disbelieve(s, image_id=r.image_id, observer_id="ana",
                             roller=FakeRoller([[2, 2, 2]]))
    assert Images.believers(s, r.image_id) == ("boz",)


def test_the_caster_is_never_fooled_by_his_own_image():
    s = _session()
    s, r = _place(s)
    assert "mirage" not in Images.believers(s, r.image_id)


def test_a_hearing_image_is_blocked_by_a_hearing_darkness():
    """The companion to the two "survives a Sight-Darkness/Flash" tests: it
    proves the gate is consulted for Hearing at all, rather than the Group
    keying passing by never being asked."""
    from kirby_combat.scene.construct import Construct

    zone = Construct(
        obj_id="dz", kind="darkness_zone",
        polygon_xy=[(7.0, -5.0), (9.0, -5.0), (9.0, 5.0), (7.0, 5.0)],
        elevation_range_m=(0.0, 3.0), sense_group="hearing",
    )
    s = _session(constructs=[zone])
    s, r = _place(s, sense_groups=["hearing"])
    assert Images.perceived_by(s, r.image_id, "ana") is False


def test_a_hearing_image_is_blocked_by_a_hearing_flash():
    from kirby_combat.actions.flash import Flash

    s = _session()
    s, r = _place(s, sense_groups=["hearing"])
    s, _ = Flash.apply(s, attacker_id="mirage", target_id="ana",
                       sense_group="hearing", body_dealt=8, flash_defense=0)
    assert Images.perceived_by(s, r.image_id, "ana") is False


def test_an_image_affecting_two_groups_survives_losing_one():
    """Perception needs ONE surviving Group, not all of them."""
    from kirby_combat.actions.flash import Flash

    s = _session()
    s, r = _place(s, sense_groups=["sight", "hearing"])
    s, _ = Flash.apply(s, attacker_id="mirage", target_id="ana",
                       sense_group="sight", body_dealt=8, flash_defense=0)
    assert Images.perceived_by(s, r.image_id, "ana") is True
    assert Images.perceived_by(s, r.image_id, "ana", sense_group="sight") is False
