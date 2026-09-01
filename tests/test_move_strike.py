"""The close-and-strike composite: close, then may the strike happen?

The defect this closes, observed in a live fight on 2026-08-31: Cheshire Cat
attempted a martial throw on GORGON while standing on a rooftop six metres
above him. The close was resolved scene-aware (and legally went nowhere, since
running is same-elevation only), and the strike resolved anyway.
"""
import pytest

from kirby_combat.actions.move_strike import (
    MoveStrikeOutcome, StrikePlan, resolve_move_strike,
)
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.dice import FakeRoller
from kirby_combat.hero_view import HeroCombatState, HeroCombatant
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate


def _rooftop_arena() -> Scene:
    """Ground at z=0 over the whole floor; a rooftop at z=6 over x in [10,20]."""
    return Scene(
        id="arena", name="Urban Rooftop",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
            Surface(id="roof", name="Roof",
                    polygon_xy=[(10, 0), (20, 0), (20, 20), (10, 20)],
                    elevation_m=6.0, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
        ],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


class _StubHero:
    """Minimal LoadedHero stand-in: enough for `senses()` (Normal Sight only)
    and for the PER roll target. INT 10 -> an 11- PER roll."""

    def __init__(self, name: str):
        self.name = name
        self.powers: list = []
        self.skills: list = []
        self.talents: list = []

    def characteristic_value(self, xmlid: str) -> int:
        return 10 if xmlid.upper() == "INT" else 0


def _combatant(cid: str) -> HeroCombatant:
    return HeroCombatant(
        id=cid,
        hero=_StubHero(cid),                # type: ignore[arg-type]
        state=HeroCombatState(
            current_stun=20, current_body=10, current_end=20,
        ),
    )


def _observer() -> HeroCombatant:
    """Sees by Normal Sight and nothing else."""
    return _combatant("cheshire")


def _unseeable_target() -> HeroCombatant:
    """Also sighted; the tests make it unperceivable with `target_invisible`
    rather than by giving it a build, so no character fixture is needed."""
    return _combatant("gorgon")


class _BlindRoller:
    """Every die a 6, so any 3d6 roll totals 18 and fails. Used to make the
    Fringe PER roll for an Invisible target lose deterministically."""

    def roll_dice(self, count: int) -> list[int]:
        return [6] * count


class _SharpRoller:
    """Every die a 1, so any 3d6 roll totals 3 and succeeds — the observer
    makes its PER roll."""

    def roll_dice(self, count: int) -> list[int]:
        return [1] * count


def _session_with_a_stunned_combatant() -> CombatSession:
    """A live session in which "bob" is Stunned and "attacker" is not --
    mirrors the recipe in `tests/test_stunned_enforcement.py`."""
    attacker = synthetic_combatant(
        id="attacker", name="Attacker",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[AttackPower(
            xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
            half_die=False, plus_one=False, damage_type="normal",
            defense_type="ed", range_m=200, uses_str=False, str_min=0,
            armor_piercing=0, penetrating=0, increased_stun_mult=0,
        )],
    )
    bob = synthetic_combatant(
        id="bob", name="bob",
        ocv=8, dcv=9, omcv=5, dmcv=7,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    session = CombatSession.create(
        id="s1", combatants=[attacker, bob], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()
    attack = AttackInput(
        attacker=attacker, target=bob, power=attacker.attacks[0],
        distance_m=0, aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
        ),
    )
    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Stunned" in result.status_changes    # the hit really qualifies
    return session


def test_an_attacker_on_a_roof_cannot_reach_the_street_below():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(15, 10, 6),      # on the rooftop
        target_pos=Position(15, 10, 0),     # directly below, on the street
        mode="running",
        half_move_m=6.0,                    # plenty, as the crow flies
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.reach.in_reach is False
    assert out.reach.shortfall_m == pytest.approx(5.0)   # 6m gap, 1m reach
    # Verified against movement_reach: running is same-elevation only, so the
    # actor does not move at all — landing == actor_pos.
    assert out.travelled_m == pytest.approx(0.0)


def test_a_legal_close_on_the_same_level_produces_a_strike():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(6, 10, 0),      # 4m away on the ground
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert isinstance(out.strike, StrikePlan)
    assert out.strike.blind is False
    assert out.reason == ""
    assert out.reach.in_reach is True
    assert out.travelled_m == pytest.approx(3.0)   # stops 1m short: reach


def test_a_close_that_runs_out_of_movement_lands_short_and_does_not_strike():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(18, 10, 0),     # 16m away
        mode="running",
        half_move_m=6.0,                    # not enough
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.travelled_m == pytest.approx(6.0)     # spent the whole budget
    assert out.distance_after_m == pytest.approx(10.0)


def test_reach_is_judged_before_perception():
    """An attacker who never got close has no attack to gate. Reporting
    "unperceived" for someone six metres below names the wrong failure.

    The target here is BOTH out of reach and unperceivable, and real
    observer/target combatants are supplied so the perception branch is
    genuinely live -- an implementation that consulted perception first would
    report the perception failure instead, and this assertion is what tells
    the two orderings apart.
    """
    scene = _rooftop_arena()
    observer, target = _observer(), _unseeable_target()
    scene.combatant_positions.update({
        observer.id: Position(15, 10, 6), target.id: Position(15, 10, 0),
    })
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(15, 10, 6),
        target_pos=Position(15, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id=observer.id,
        observer=observer,
        target=target,
        target_invisible=True,              # also unperceivable
        roller=_BlindRoller(),
    )
    assert out.reason == "out_of_reach"
    assert out.strike is None


def test_closing_on_an_unperceivable_target_strikes_blind():
    """6E2 p9 (restated p127): the close does not confer perception. An attacker who
    arrives beside an enemy it still cannot sense may swing, but at half CV --
    it does not get a clean full-CV blow out of walking into the dark."""
    scene = _rooftop_arena()
    observer, target = _observer(), _unseeable_target()
    scene.combatant_positions.update({
        observer.id: Position(2, 10, 0), target.id: Position(6, 10, 0),
    })
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(6, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id=observer.id,
        observer=observer,
        target=target,
        target_invisible=True,
        roller=_BlindRoller(),      # the Fringe PER roll fails
    )
    assert out.reason == ""
    assert out.strike == StrikePlan(blind=True)


def test_a_perceived_target_is_struck_at_full_cv():
    """The control for the test above: same close, nothing concealing the
    target, so the strike is not blind."""
    scene = _rooftop_arena()
    observer, target = _observer(), _unseeable_target()
    scene.combatant_positions.update({
        observer.id: Position(2, 10, 0), target.id: Position(6, 10, 0),
    })
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(6, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id=observer.id,
        observer=observer,
        target=target,
        roller=_BlindRoller(),
    )
    assert out.strike == StrikePlan(blind=False)


def test_an_already_adjacent_actor_does_not_move_onto_the_target():
    """Nothing to close. The actor should stand still rather than walk into
    the enemy's own square."""
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(5.8, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.travelled_m == pytest.approx(0.0)
    assert out.landing == Position(5, 10, 0)
    assert out.distance_after_m == pytest.approx(0.8)
    assert out.strike == StrikePlan(blind=False)


def test_a_refused_mode_gives_an_adjacent_actor_no_free_strike():
    """A mode the engine does not model is refused outright, and a refused
    close lands the actor back where it started. Standing next to the enemy
    already must not turn that refusal into a legal move-and-strike."""
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(5.8, 10, 0),
        mode="not_a_mode",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "move_refused"
    assert out.reach.in_reach is True        # in reach, and still no strike


def test_swimming_on_dry_land_gives_an_adjacent_actor_no_free_strike():
    scene = _rooftop_arena()      # no water anywhere
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(5.8, 10, 0),
        mode="swimming",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "move_refused"


def test_a_stunned_actor_gets_no_move_strike_even_standing_adjacent():
    """6E2 p106: a Stunned character cannot move. `movement_reach` reports
    that refusal the same way it reports any other -- unreachable, landing
    unchanged -- so an adjacent Stunned combatant would otherwise collect a
    free close-and-strike out of not moving at all."""
    scene = _rooftop_arena()
    session = _session_with_a_stunned_combatant()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(5.8, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="bob",             # the Stunned one
        session=session,
    )
    assert out.strike is None
    assert out.reason == "move_refused"

    # Control: the same close for an un-Stunned combatant in the same session
    # is a legal strike, so it is the condition doing the work here.
    ok = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(5.8, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="attacker",
        session=session,
    )
    assert ok.strike == StrikePlan(blind=False)


def test_a_teleporter_closes_onto_the_rooftop_the_runner_cannot_reach():
    """The mid-air retry. The point one metre short of an enemy standing on a
    six-metre roof hangs in the air, and teleportation must finish on
    something solid -- so aiming there fails. Retried at the enemy's own
    (supported) square, the teleport arrives and the strike is legal."""
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),       # on the street, west of the roof
        target_pos=Position(15, 10, 6),     # on the roof
        mode="teleportation",
        half_move_m=20.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike == StrikePlan(blind=False)
    assert out.reach.in_reach is True
    # The retry lands the actor ON the enemy's square, which the ordinary
    # path refuses (see `_point_short_of`). Pinned deliberately: the retry
    # runs only when the point one Reach short cannot be landed on, so this
    # is the sole arrival the mode allows, and the caller — not this pure
    # resolver — decides what two combatants in one square do about it.
    assert out.landing == Position(15, 10, 6)
    assert out.distance_after_m == pytest.approx(0.0)


def test_the_scene_less_path_ignores_movement_mode_by_design():
    """Documented approximation, pinned so it stays deliberate: with no scene
    there is no geometry to consult, so the close is a straight line and
    `mode` is not applied. A runner therefore "closes" straight down a
    six-metre drop -- which the identical scene-bound close refuses."""
    args = dict(
        actor_pos=Position(15, 10, 6),
        target_pos=Position(15, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    sceneless = resolve_move_strike(scene=None, **args)
    assert sceneless.strike == StrikePlan(blind=False)
    assert sceneless.landing.z == pytest.approx(1.0)

    scened = resolve_move_strike(scene=_rooftop_arena(), **args)
    assert scened.strike is None


def test_a_sceneless_close_still_applies_the_reach_rule():
    # No scene ⇒ no legality to consult, so the close is a straight line. The
    # reach rule still decides whether the strike happens.
    out = resolve_move_strike(
        scene=None,
        actor_pos=Position(0, 0, 0),
        target_pos=Position(30, 0, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.distance_after_m == pytest.approx(24.0)


def test_perception_is_judged_where_the_close_LANDED():
    """The Fringe of an Invisible enemy is only perceivable close up, so the
    position perception is measured at changes the answer.

    The attacker starts six metres from an Invisible enemy — too far for the
    Fringe — and closes to one metre, where a successful PER roll spots it.
    Judged at the PRE-close position the strike would come back blind, which
    is the wrong geometry: the actor is not standing there any more.
    """
    scene = _rooftop_arena()
    observer, target = _observer(), _unseeable_target()
    scene.combatant_positions.update({
        observer.id: Position(2, 2, 0), target.id: Position(8, 2, 0),
    })
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 2, 0),
        target_pos=Position(8, 2, 0),       # 6m away: beyond Fringe range
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id=observer.id,
        observer=observer,
        target=target,
        target_invisible=True,
        roller=_SharpRoller(),              # the PER roll succeeds
    )
    assert out.distance_after_m == pytest.approx(1.0)
    assert out.strike == StrikePlan(blind=False)


def test_perception_follows_the_OBSERVER_id_not_the_movement_id():
    """The same close, with the movement id left at its default while the
    observer carries its own. `perceive` looks a position up under the
    observer's id, so that is the id the post-close position must be written
    under — keying on the movement id instead silently reinstates the
    stale-position bug for any caller whose two ids differ.
    """
    scene = _rooftop_arena()
    observer, target = _observer(), _unseeable_target()
    scene.combatant_positions.update({
        observer.id: Position(2, 2, 0), target.id: Position(8, 2, 0),
    })
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 2, 0),
        target_pos=Position(8, 2, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        # actor_id deliberately left at its "mover" default: NOT observer.id
        observer=observer,
        target=target,
        target_invisible=True,
        roller=_SharpRoller(),
    )
    assert out.strike == StrikePlan(blind=False)


def test_the_composite_is_on_the_import_surface():
    import kirby_combat

    assert kirby_combat.resolve_move_strike is resolve_move_strike
    assert kirby_combat.MoveStrikeOutcome is MoveStrikeOutcome


def test_a_leaper_closes_onto_the_rooftop_instead_of_falling_short_of_it():
    """The mid-air retry, reached by the FALL door rather than the refusal one.

    A leap at the point one metre short of a rooftop enemy is perfectly legal
    -- it is within both the horizontal and the vertical capacity -- so the
    close is `reachable`, and it arrives in reach. It just happens to arrive
    in EMPTY AIR beside the roof, so the leaper drops. Judging the retry on
    reachability alone never fires here, and the whole phase is spent falling.
    The retry must therefore also fire when the short-of attempt FELL: falling
    is what "that point is unsupported" looks like from the outside.
    """
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),       # on the street, west of the roof
        target_pos=Position(15, 10, 6),     # on the roof
        mode="leaping",
        half_move_m=12.0,                   # 12m across, 6m up: enough for both
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.reason == ""
    assert out.strike == StrikePlan(blind=False)
    assert out.fell is False
    # Same arrival as the teleporter's: the enemy's own supported square is
    # the only landing the mode allows. See the note in that test.
    assert out.landing == Position(15, 10, 6)


def test_a_leap_that_cannot_be_rescued_still_reports_the_fall():
    """The other half of the retry decision, pinned. Here the retry itself
    fails -- the enemy's roof is beyond the leap's vertical capacity -- so
    there is no rescue to be had, and the original attempt's fall must survive
    the attempt to rescue it. A falling character is prone and hurt; the
    composite must not swallow that just because it went looking for a better
    landing and did not find one.
    """
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(15, 10, 6),
        mode="leaping",
        half_move_m=11.0,   # 5.5m of lift: clears the mid-air point, not the roof
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "fell"
    assert out.fell is True
    assert out.reach.in_reach is True    # it arrived; it just arrived falling


def test_a_retry_that_also_falls_leaves_the_original_landing_alone():
    """The retry is a rescue, not a replacement. Against an enemy hovering in
    mid-air there is no supported square to retry onto either, so the retry
    falls as well -- and an attempt that is no better must not displace the
    one already resolved. The leaper stays where its own leap put it and the
    fall is reported once, from that spot.
    """
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(5, 10, 0),
        target_pos=Position(8, 10, 4),      # airborne, west of the roof
        mode="leaping",
        half_move_m=8.0,                    # 8m across, 4m up: both reachable
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "fell"
    assert out.fell is True
    # The short-of point, NOT the enemy's own square: adopting a retry that
    # is itself a fall would move the actor for nothing.
    assert out.landing.x == pytest.approx(7.4)
    assert out.landing.z == pytest.approx(3.2)
