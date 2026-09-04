"""Darkness — a scene occluder, not a PER penalty (6E1 p.188).

The page is emphatic that Darkness does not make PER Rolls with the
affected Senses harder, it makes them IMPOSSIBLE, and that the covered
area is impenetrable to those Senses even for someone with Nightvision.
It also states the occlusion three ways -- a Sense cannot reach INTO the
field, OUT OF it, or THROUGH it -- and the easy half-implementation is to
do one of the three. All three are pinned here.

The convergence tests at the bottom are the point of the file: 6E1 p.188
sends a character who cannot perceive an opponent from inside a Darkness
field to the same DCV/OCV penalties 6E2 p.9 gives a Flashed one. Two
implementations of one rule would drift, so Darkness reaches the CV seam
through `sense_penalties`, exactly as Flash does.
"""

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.darkness import Darkness
from kirby_combat.cv_modifiers import effective_dcv_for, effective_ocv_for
from kirby_dice import FakeRoller
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


# A box spanning x 8..12, y 0..10, elevations 0..3.
def _zone(*, sense_group="sight", creator_immune=False, source=None,
          obj_id="dz1") -> Construct:
    return Construct(
        obj_id=obj_id, kind="darkness_zone",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_group=sense_group, creator_immune=creator_immune,
        source_combatant_id=source,
    )


def _c(id_):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _scene(positions, constructs) -> Scene:
    return Scene(
        id="sdark", name="Darkness",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=list(constructs),
        combatant_positions=positions,
    )


#: Positions used by the into/out-of/through trio. INSIDE lies within the
#: polygon; WEST and EAST are outside it, on opposite sides.
WEST = Position(0.0, 5.0, 1.5)
INSIDE = Position(10.0, 5.0, 1.5)
INSIDE_2 = Position(11.0, 6.0, 1.5)
EAST = Position(20.0, 5.0, 1.5)


def _session(a_pos, b_pos, constructs, roller=None) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_c("ana"), _c("boz")],
        scene=_scene({"ana": a_pos, "boz": b_pos}, constructs),
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller or FakeRoller([]),
    ).start()


def _blocked(session, observer="ana", opponent="boz") -> bool:
    from kirby_combat.sense_penalties import _targeting_senses_blocked
    return _targeting_senses_blocked(session, observer, opponent)


# ---------------------------------------------------------------------------
# Into, out of, and through — 6E1 p.188 states all three
# ---------------------------------------------------------------------------
#
# Measured rather than assumed: of these four, only the both-inside case
# distinguishes a correct implementation from the crossing-only one. Deleting
# the endpoint test from `perception._darkness_blocks` leaves into, out-of and
# through all still passing -- a ray with exactly one endpoint inside a polygon
# necessarily crosses its boundary, so those three are one mechanism wearing
# three names. They are kept anyway because the page states three claims and a
# reader checking the engine against it will look for three, but the note is
# here so nobody mistakes them for three independent guards.

def test_a_sense_cannot_reach_into_the_field():
    """Observer outside, target inside."""
    s = _session(WEST, INSIDE, [_zone()])
    assert _blocked(s) is True


def test_a_sense_cannot_reach_out_of_the_field():
    """Observer inside, target outside."""
    s = _session(INSIDE, EAST, [_zone()])
    assert _blocked(s) is True


def test_a_sense_cannot_reach_through_the_field():
    """Both outside, on opposite sides -- the ray crosses the polygon."""
    s = _session(WEST, EAST, [_zone()])
    assert _blocked(s) is True


def test_two_characters_inside_the_same_field_cannot_see_each_other():
    """Neither endpoint is outside and the ray never crosses the boundary --
    the case a crossing-only implementation silently gets wrong."""
    s = _session(INSIDE, INSIDE_2, [_zone()])
    assert _blocked(s) is True


def test_a_ray_that_misses_the_field_is_unaffected():
    """The gate must be geometric, not "a Darkness exists somewhere"."""
    s = _session(Position(0.0, 40.0, 1.5), Position(20.0, 40.0, 1.5), [_zone()])
    assert _blocked(s) is False


def test_darkness_against_another_sense_group_does_not_blind_sight():
    s = _session(WEST, EAST, [_zone(sense_group="hearing")])
    assert _blocked(s) is False


def test_nightvision_does_not_help():
    """6E1 p.188 says so by name: Darkness versus the Sight Group is
    impenetrable by Sight Group Senses, even for someone with Nightvision.
    Natural darkness is the thing Nightvision counteracts; this is not
    natural darkness.
    """
    s = _session(WEST, EAST, [_zone()])
    ana = s.combatants["ana"]
    assert any(sense.group == "sight" for sense in ana.senses())
    assert _blocked(s) is True


def test_the_creator_is_blind_in_his_own_field_without_personal_immunity():
    """6E1 p.188: creating the field does not let you perceive through it."""
    s = _session(WEST, EAST, [_zone(source="ana", creator_immune=False)])
    assert _blocked(s) is True


def test_the_creator_with_personal_immunity_sees_through():
    s = _session(WEST, EAST, [_zone(source="ana", creator_immune=True)])
    assert _blocked(s) is False


# ---------------------------------------------------------------------------
# Convergence — the same code path as Flash (6E1 p.188 -> 6E2 p.9)
# ---------------------------------------------------------------------------

def test_darkness_blinding_costs_the_same_cv_as_flash_blinding():
    """6E1 p.188 hands a character who cannot perceive his opponent from
    inside a Darkness field straight to 6E2 p.9's DCV/OCV penalties. Same
    rule, so it must be the same code path -- two implementations drift.
    """
    s = _session(WEST, EAST, [_zone()])
    assert effective_ocv_for(s, "ana", against="boz", combat_type="hth") == 4
    assert effective_dcv_for(s, "ana", against="boz", combat_type="hth") == 4
    assert effective_ocv_for(s, "ana", against="boz", combat_type="ranged") == 0
    assert effective_dcv_for(s, "ana", against="boz", combat_type="ranged") == 4


def test_a_nontargeting_per_roll_mitigates_darkness_too():
    """The mitigation belongs to the CV rule, not to Flash, so it has to
    work identically for a character blinded by Darkness."""
    from kirby_combat.sense_penalties import NontargetingPerception

    s = _session(WEST, EAST, [_zone()])
    s, result = NontargetingPerception.acquire(
        s, observer_id="ana", target_id="boz", sense_group="hearing",
        roller=FakeRoller([[2, 2, 2]]),
    )
    assert result.succeeded
    assert effective_dcv_for(s, "ana", against="boz", combat_type="hth") == 7
    assert effective_dcv_for(s, "ana", against="boz", combat_type="ranged") == 8


def test_darkness_blinds_the_pair_symmetrically():
    """Nothing about the geometry favours one end of the ray."""
    s = _session(WEST, EAST, [_zone()])
    assert effective_dcv_for(s, "ana", against="boz", combat_type="hth") == 4
    assert effective_dcv_for(s, "boz", against="ana", combat_type="hth") == 4


# ---------------------------------------------------------------------------
# Placing the field — 6E1 p.188 makes it an Attack Roll against an Area
# ---------------------------------------------------------------------------

def test_placing_darkness_hits_an_area_at_dcv_3():
    """6E1 p.188 requires an Attack Roll against a target Area to place the
    field. 6E2 p.45 names Darkness while stating that an area-effecting
    attack rolls against DCV 3, and 6E2 p.63 gives the same number for the
    target point of an Area Of Effect attack.

    OCV 8 vs DCV 3 needs 3d6 <= 8 + 11 - 3 = 16. A 9 makes it comfortably.
    """
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    s, result = Darkness.place(
        s, attacker_id="ana",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight"],
    )
    assert result.hit is True
    assert result.target_dcv == 3
    assert result.construct_ids


def test_a_missed_attack_roll_places_no_field():
    """OCV 8 vs DCV 3 misses only on 17 or 18 -- rolled here as 18."""
    s = _session(WEST, EAST, [], roller=FakeRoller([[6, 6, 6]]))
    s, result = Darkness.place(
        s, attacker_id="ana",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight"],
    )
    assert result.hit is False
    assert result.construct_ids == ()
    assert not [c for c in (s.scene.constructs or []) if c.kind == "darkness_zone"]


def test_a_placed_field_blinds_immediately():
    """Placement and occlusion are one system, not two -- the field the
    action puts on the scene is the one perception reads."""
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    assert _blocked(s) is False
    s, result = Darkness.place(
        s, attacker_id="boz",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight"],
    )
    assert result.hit
    assert _blocked(s) is True
    assert effective_dcv_for(s, "ana", against="boz", combat_type="hth") == 4


def test_one_field_per_sense_group():
    """A Darkness bought against two Sense Groups occludes both, and the
    engine's zone Construct is keyed by ONE group -- so placing it has to
    produce one zone per group rather than silently dropping the second.
    """
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    s, result = Darkness.place(
        s, attacker_id="ana",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight", "hearing"],
    )
    assert result.hit
    zones = [c for c in s.scene.constructs if c.kind == "darkness_zone"]
    assert {z.sense_group for z in zones} == {"sight", "hearing"}


def test_placement_records_the_attack_on_the_log():
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    s, _ = Darkness.place(
        s, attacker_id="ana",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight"],
    )
    declared = [e for e in s.event_log
                if e.kind == "ActionDeclared" and e.action_type == "darkness"]
    spawned = [e for e in s.event_log if e.kind == "ConstructSpawned"]
    assert len(declared) == 1
    assert len(spawned) == 1


def test_personal_immunity_is_threaded_through_placement():
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    s, _ = Darkness.place(
        s, attacker_id="ana",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_groups=["sight"], personal_immunity=True,
    )
    assert _blocked(s, observer="ana", opponent="boz") is False
    assert _blocked(s, observer="boz", opponent="ana") is True


# ---------------------------------------------------------------------------
# Repositioning around a Darkness field (scene/visibility.py)
# ---------------------------------------------------------------------------

def test_nearest_visible_point_will_not_shoot_through_darkness():
    """`nearest_visible_point` short-circuits on a clear wall LoS. Without
    a darkness gate it answers "you can already see him" from inside a smoke
    cloud, and an AI holding that answer never moves.
    """
    from kirby_combat.scene.visibility import nearest_visible_point

    scene = _scene({}, [_zone()])
    assert nearest_visible_point(WEST, EAST, scene, radius=30.0,
                                 sense_group="sight") != WEST


def test_nearest_visible_point_ignores_darkness_of_another_group():
    from kirby_combat.scene.visibility import nearest_visible_point

    scene = _scene({}, [_zone(sense_group="hearing")])
    assert nearest_visible_point(WEST, EAST, scene, radius=30.0,
                                 sense_group="sight") == WEST


def test_nearest_visible_point_without_a_sense_group_is_unchanged():
    """The parameter is opt-in; every existing caller keeps wall geometry."""
    from kirby_combat.scene.visibility import nearest_visible_point

    scene = _scene({}, [_zone()])
    assert nearest_visible_point(WEST, EAST, scene, radius=30.0) == WEST


def test_a_vantage_point_around_the_field_is_found():
    """The field spans y 0..10; a point north of it has a clear ray."""
    from kirby_combat.scene.visibility import nearest_visible_point

    scene = _scene({}, [_zone()])
    found = nearest_visible_point(WEST, EAST, scene, radius=40.0,
                                  sense_group="sight")
    assert found is not None and found != WEST
