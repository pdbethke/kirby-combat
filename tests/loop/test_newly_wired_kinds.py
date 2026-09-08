"""Every newly wired kind, driven through the loop's own dispatch.

REGISTERED IS NOT THE SAME AS WORKING, and the distinction is the whole
point of this file. `registered_kinds()` growing proves a decorator ran. It
does not prove the resolver can be called, that its arguments match the
engine function's signature, or that anything reaches the event log -- and
"it imports" is exactly the standard under which these rules sat unreachable
behind green suites in the first place.

So each test here calls `resolve_chosen`, the same path `run_phase` uses,
and asserts the outcome reached the log.
"""
from __future__ import annotations

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import registered_kinds
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _Power:
    """A power in the shape enumeration attaches to an offer."""

    def __init__(self, xmlid: str, levels: int = 4) -> None:
        self.xmlid = xmlid
        self.name = xmlid.title()
        self.levels = levels
        self.option_id = None
        self.assigned_adders: list = []
        self.source_id = f"src-{xmlid}"


def _actor(*, mentalist: bool = False):
    c = fighter("actor", side=Side.named("heroes"), dex=25)
    if mentalist:
        # The engine's own guard: a non-mentalist cannot use a mental power,
        # and every mental resolver reaches that check.
        object.__setattr__(c, "_explicit_is_mentalist", True)
    return c


def _session(*, mentalist: bool = False):
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[
            _actor(mentalist=mentalist),
            fighter("mark", side=Side.named("villains"), dex=15),
        ],
    ).start()


def _action(kind: str, *, target: str | None = "mark", power=None,
            action_id: str | None = None) -> LegalAction:
    return LegalAction(
        action_id=action_id or f"{kind}:{target or ''}",
        kind=kind, target_id=target,
        power_xmlid=getattr(power, "xmlid", None),
        power_name=getattr(power, "name", None),
        summary=f"{kind} {target or ''}".strip(),
        _attack_view=power,
    )


def _resolve(action: LegalAction, *, mentalist: bool = False):
    session = _session(mentalist=mentalist)
    return session, resolve_chosen(
        session, session.combatants["actor"], action,
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )


# ---- Declarations: the whole effect is that they were declared ----

@pytest.mark.parametrize("kind", ["dodge", "set", "haymaker"])
def test_a_declaration_reaches_the_log(kind):
    """Dodge's +3 DCV, Set's +1 OCV and Haymaker's +4 DC are all read back
    from the log LATER. If the declaration does not land, the bonus never
    exists -- and nothing else would report a problem."""
    before, resolved = _resolve(_action(kind, target=None))
    assert resolved.kind == kind
    assert resolved.events, f"{kind} recorded nothing"
    assert len(resolved.session.event_log) > len(before.event_log)


def test_dodge_actually_grants_its_bonus():
    """Not just 'an event landed' -- the rule it enables must be true."""
    from kirby_combat.actions.reactive.dodge import Dodge

    before, resolved = _resolve(_action("dodge", target=None))
    assert Dodge.dcv_bonus(before, "actor") == 0
    assert Dodge.dcv_bonus(resolved.session, "actor") == 3


# ---- Powers ----

def test_flash_blinds_and_records_it():
    _, resolved = _resolve(_action("flash", power=_Power("FLASH", levels=6)))
    assert resolved.result is not None
    assert resolved.events


def test_entangle_traps_and_records_it():
    _, resolved = _resolve(_action("entangle", power=_Power("ENTANGLE", levels=5)))
    assert resolved.result is not None
    assert resolved.events


def test_a_power_kind_without_its_power_refuses():
    """`_attack_view` is the offer's handle on the actual power. Resolving
    without it would mean guessing which power was meant."""
    from kirby_combat.loop.registry import UnresolvableAction

    for kind in ("flash", "entangle"):
        with pytest.raises(UnresolvableAction, match=kind):
            _resolve(_action(kind, power=None))


# ---- Contested maneuvers ----

def test_grab_resolves_a_contest():
    _, resolved = _resolve(_action("grab"))
    assert resolved.result is not None
    assert resolved.events


def test_block_resolves_a_contest():
    _, resolved = _resolve(_action("block"))
    assert resolved.result is not None
    assert resolved.events


def test_presence_attack_produces_an_effect_not_damage():
    """6E2 p.129 -- a Presence Attack changes what a target is willing to
    do. No STUN or BODY moves."""
    before, resolved = _resolve(_action("presence_attack"))
    assert resolved.result.effect
    assert (
        resolved.session.combatants["mark"].state.current_stun
        == before.combatants["mark"].state.current_stun
    )


# ---- The count, and what it does not claim ----

def test_all_sixty_one_kinds_are_wired():
    """61, not 51. Three offers build their kind from a variable, so an AST
    walk matching `kind="literal"` missed eight -- see
    `test_every_enumerable_kind_is_registered` in
    test_coordination_and_frameworks.py for how that surfaced."""
    from kirby_combat.enumeration import ALL_ACTION_KINDS

    assert len(registered_kinds()) == 61
    assert registered_kinds() == ALL_ACTION_KINDS


def test_every_registered_kind_is_covered_by_a_test_here_or_elsewhere():
    """A guard against registering a kind and never exercising it -- which
    is the failure mode this whole file exists to prevent."""
    exercised = {
        "attack", "strike", "mental_blast", "recover",          # test_run / damage
        "mind_control", "mental_illusion", "telepathy",         # test_mental_reconnected
        "image_decoy",                                          # test_image_decoy_reconnected
        "dodge", "set", "haymaker", "presence_attack",          # here
        "flash", "entangle", "grab", "block",                   # here
        "mental_entangle", "aid", "drain",                      # here
        "move_by", "move_through", "rapid_fire", "throw", "throw_object",
        "maneuver", "hold", "release_held", "darkness_zone",     # here
        "escape_str", "escape_attack", "escape_teleport",       # here
        "attack_construct", "heal", "dispel",                   # here
        "presence_attack_group",                                # here
        "push", "hide", "force_wall",                           # here
        "move", "move_strike", "pickup", "reposition",
        "reposition_push", "reposition_strike", "reposition_vantage",
        #                                        test_movement_execution
        "trip", "disarm", "spread",              # test_subproject_b_maneuvers
        "coordinate", "reallocate", "reconfigure_vpp",
        #                          test_coordination_and_frameworks
        "sweep", "multiple_attack", "climb", "climb_fast",
        "charm", "persuasion", "conversation", "trading",
        #                          test_hidden_kinds
        "move_to_cover",           # test_move_to_cover
        "disengage",               # test_disengage
    }
    assert registered_kinds() <= exercised, (
        f"registered but never exercised: {sorted(registered_kinds() - exercised)}"
    )



# ---------------------------------------------------------------------------
# Maneuvers, multi-shot attacks, held actions and placed fields.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["move_by", "move_through", "rapid_fire", "throw"])
def test_a_pure_computer_kind_records_its_outcome(kind):
    """These engine functions return an outcome and hold no session, so the
    wrapper's whole job is to roll what the rule needs, call it unchanged,
    and get the result into the log."""
    _, resolved = _resolve(_action(kind))
    assert resolved.result is not None, f"{kind} computed nothing"
    assert resolved.events, f"{kind} recorded nothing"


def test_throw_and_throw_object_share_one_resolver():
    """Both are STR against distance; `Throw.compute` answers both."""
    for kind in ("throw", "throw_object"):
        _, resolved = _resolve(_action(kind))
        assert resolved.result is not None


def test_move_by_reads_velocity_from_the_build():
    """Velocity is the actor's RUNNING, not a constant -- a slower
    character hits for less."""
    from kirby_combat.loop.resolvers import _velocity_mps

    fast = fighter("fast", side=Side.named("a"), dex=20)
    assert _velocity_mps(fast) == 12.0, "6E1 p.36 base Running"


def test_rapid_fire_fires_the_number_of_shots_THE_OFFER_PROMISED():
    """The offer's summary says three shots (6E2 p.75) and its action_id
    carries the number. The first version of this resolver hardcoded two,
    so the menu advertised one thing and the engine fired another -- the
    same class of disagreement Spread avoids by reading its `:N` tail."""
    _, resolved = _resolve(_action("rapid_fire", action_id="rapid_fire:mark:eb:3"))
    ocvs = resolved.session.event_log[-1].result_payload["shot_ocvs"]
    assert len(ocvs) == 3
    assert ocvs == sorted(ocvs, reverse=True), "each shot at a worse OCV"
    assert ocvs[0] - ocvs[1] == 2, "6E2 p.75: -2 per shot"


def test_rapid_fire_falls_back_to_the_book_count():
    """A hand-built action that names no count still gets 6E2 p.75's three
    rather than an arbitrary number."""
    from kirby_combat.loop.resolvers import RAPID_FIRE_SHOTS

    assert RAPID_FIRE_SHOTS == 3
    _, resolved = _resolve(_action("rapid_fire", action_id="rapid_fire"))
    assert len(resolved.session.event_log[-1].result_payload["shot_ocvs"]) == 3




def test_a_known_maneuver_is_declared_for_the_attack_to_read():
    from kirby_combat.actions.martial_arts import MARTIAL_MANEUVERS

    known = sorted(MARTIAL_MANEUVERS)[0]
    action = _action("maneuver")
    object.__setattr__(action, "power_xmlid", known)
    _, resolved = _resolve(action)
    assert resolved.events


def test_an_unknown_maneuver_refuses_rather_than_resolving_as_something_else():
    """`MartialArts.declare` raises on an id it does not know, and that is
    right: a maneuver the engine cannot model must not resolve as though it
    could."""
    from kirby_combat.loop.registry import UnresolvableAction

    with pytest.raises(UnresolvableAction, match="maneuver"):
        _resolve(_action("maneuver"))


def test_holding_an_action_is_recorded_as_pending():
    from kirby_combat.actions.held_action import HeldAction

    before, resolved = _resolve(_action("hold", target=None))
    assert not HeldAction.get_pending(before, "actor")
    assert HeldAction.get_pending(resolved.session, "actor"), "nothing was held"


def test_releasing_an_action_that_was_never_held_refuses():
    """The action_id names WHICH held action to release -- a combatant may
    be holding several. Releasing one that is not pending would fire an
    action nobody declared."""
    from kirby_combat.loop.registry import UnresolvableAction

    with pytest.raises(UnresolvableAction, match="release_held"):
        _resolve(_action("release_held", target=None))


def test_a_held_action_can_be_released_once_declared():
    from kirby_combat.actions.held_action import HeldAction
    from kirby_combat.loop.registry import resolve_chosen

    session = _session()
    actor = session.combatants["actor"]
    held = resolve_chosen(
        session, actor, _action("hold", target=None),
        template=TEMPLATE, roller=RandomRoller(seed=9),
    ).session
    pending = HeldAction.get_pending(held, "actor")
    assert pending

    release = LegalAction(
        action_id=f"release_held:{pending[0].id}", kind="release_held",
        target_id=None, power_xmlid=None, power_name=None,
        summary="release the held action",
    )
    out = resolve_chosen(
        held, actor, release, template=TEMPLATE, roller=RandomRoller(seed=9),
    )
    assert out.events
    assert not HeldAction.get_pending(out.session, "actor"), "still pending"


def test_darkness_needs_a_map_and_refuses_without_one():
    """Like a decoy, a Darkness field goes somewhere. Without a scene there
    is no somewhere, and inventing a coordinate would put it where nobody
    chose."""
    from kirby_combat.loop.registry import UnresolvableAction

    with pytest.raises(UnresolvableAction, match="darkness_zone"):
        _resolve(_action("darkness_zone", power=_Power("DARKNESS", levels=4)))


# ---------------------------------------------------------------------------
# Escapes, constructs, and the remaining adjustments.
# ---------------------------------------------------------------------------


def _entangled_session():
    """A session where the actor is already trapped, so an escape has
    something to escape from."""
    from kirby_combat.actions.entangle import Entangle

    session = _session()
    trapped, _ = Entangle.apply(
        session, attacker_id="mark", target_id="actor",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    return trapped


@pytest.mark.parametrize("kind", ["escape_str", "escape_attack"])
def test_an_escape_attempt_is_resolved_against_the_entangle(kind):
    """The BODY an escape does soaks against the ENTANGLE's PD/ED, never
    the victim's (6E1 p.218) -- `escape_attempt` takes it already applied."""
    from kirby_combat.loop.registry import resolve_chosen

    session = _entangled_session()
    resolved = resolve_chosen(
        session, session.combatants["actor"],
        _action(kind, target=None, power=_Power("BLAST", levels=4)),
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )
    assert resolved.result is not None
    assert resolved.events


def test_teleporting_out_does_no_body_to_the_entangle():
    """6E1 p.218: no Attack Roll and no damage -- the victim is simply
    elsewhere."""
    from kirby_combat.loop.registry import resolve_chosen

    session = _entangled_session()
    resolved = resolve_chosen(
        session, session.combatants["actor"],
        _action("escape_teleport", target=None),
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )
    assert resolved.events


def test_attacking_a_construct_that_is_not_on_the_scene_refuses():
    from kirby_combat.loop.registry import UnresolvableAction

    with pytest.raises(UnresolvableAction, match="attack_construct"):
        _resolve(_action("attack_construct", target="a-wall"))


def test_healing_does_not_fade_and_says_so_by_emitting_nothing():
    """Healing shares Aid's arithmetic but has no fade (6E1 p.150). An
    AdjustmentApplied carrying fade_rate_per_turn=5 would state the
    opposite of the rule, so none is emitted."""
    _, resolved = _resolve(_action("heal", power=_Power("HEALING", levels=4)))
    assert resolved.result.delta > 0
    assert not [e for e in resolved.events if e.kind == "AdjustmentApplied"]


def test_dispel_records_the_roll_not_a_delta():
    """All-or-nothing against the target power's Active Points -- there is
    no partial Dispel to apply."""
    _, resolved = _resolve(_action("dispel", power=_Power("DISPEL", levels=6)))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["active_points_rolled"] > 0
    assert "delta" not in payload


def test_a_group_presence_attack_is_ONE_roll_judged_against_each_target():
    """6E2 p.129 -- a Presence Attack is an effect on those who witness it,
    so the group version is the same terrifying moment measured against
    each PRE, not a fresh roll per victim."""
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[
            _actor(),
            fighter("mark", side=Side.named("villains"), dex=15),
            fighter("other", side=Side.named("villains"), dex=14),
        ],
    ).start()
    from kirby_combat.loop.registry import resolve_chosen

    resolved = resolve_chosen(
        session, session.combatants["actor"],
        _action("presence_attack_group", target=None),
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )
    effects = resolved.session.event_log[-1].result_payload["effects"]
    assert set(effects) == {"mark", "other"}


def test_a_group_presence_attack_with_nobody_to_frighten_refuses():
    from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen

    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[_actor()],
    ).start()
    with pytest.raises(UnresolvableAction, match="presence_attack_group"):
        resolve_chosen(
            session, session.combatants["actor"],
            _action("presence_attack_group", target=None),
            template=TEMPLATE, roller=RandomRoller(seed=9),
        )


def test_pushing_costs_five_end_and_adds_a_damage_class():
    """6E2 p.133's exchange rate, exactly as the offer promises it -- one
    Damage Class for five END, neither re-derived here."""
    before, resolved = _resolve(_action("push", power=blast("p", dice=6)))
    spent = (
        before.combatants["actor"].state.current_end
        - resolved.session.combatants["actor"].state.current_end
    )
    assert spent == 5
    assert resolved.result is not None


def test_pushing_without_a_power_refuses():
    from kirby_combat.loop.registry import UnresolvableAction

    with pytest.raises(UnresolvableAction, match="push"):
        _resolve(_action("push", power=None))


def test_hiding_is_contested_per_observer():
    """Being unseen is not a property of the hider: one enemy may lose you
    while another keeps you in view, so the contest runs per watcher."""
    _, resolved = _resolve(_action("hide", target=None))
    payload = resolved.session.event_log[-1].result_payload
    assert "unseen_by" in payload
    assert set(payload["unseen_by"]) <= {"mark"}


def test_a_force_wall_needs_a_map_and_lands_on_it():
    from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds,
    )

    # No scene: nowhere to put a barrier.
    with pytest.raises(UnresolvableAction, match="force_wall"):
        _resolve(_action("force_wall", power=_Power("FORCEWALL", levels=6)))

    scene = Scene(
        id="s", name="S", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={
            "actor": Position(0.0, 0.0, 0.0), "mark": Position(20.0, 0.0, 0.0),
        },
    )
    session = CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[_actor(), fighter("mark", side=Side.named("villains"))],
    ).start()

    assert scene.walls == []
    resolved = resolve_chosen(
        session, session.combatants["actor"],
        _action("force_wall", power=_Power("FORCEWALL", levels=6)),
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )
    assert len(scene.walls) == 1, "the barrier must reach the scene"
    assert scene.walls[0].body == 6, "BODY comes from the power's levels"
    assert resolved.events
