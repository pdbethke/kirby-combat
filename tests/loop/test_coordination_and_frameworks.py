"""The last three kinds — coordination and framework state.

These needed machinery rather than wiring. `coordinate` had a tactic and an
offer and no window; `reallocate` and `reconfigure_vpp` had framework state
that lived only in the parked wrapper's database.
"""
from __future__ import annotations

import pytest

from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.coordination import (
    CoordinationRoll, is_coordinated, roll_profile, window_for,
)
from kirby_combat.enumeration import LegalAction
from kirby_combat.framework import (
    ReserveExceeded, active_slots, allocation_for, parse_reallocation,
    validate_allocation,
)
from kirby_combat.loop import registered_kinds
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller, RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _Skill:
    def __init__(self, xmlid: str) -> None:
        self.xmlid = xmlid


# ---------------------------------------------------------------------------
# Framework fixtures. `validate_allocation` reads the build, so a combatant
# with no frameworks can reallocate nothing -- which is correct, and is why
# these tests need a real one.
# ---------------------------------------------------------------------------

from kirby_combat.models import FrameworkView, SlotView  # noqa: E402


def _framework(
    framework_id: str = "fw1", *, reserve: int = 60, slots=(),
) -> FrameworkView:
    return FrameworkView(
        framework_id=framework_id, xmlid="MULTIPOWER", name="Multipower",
        kind="multipower", reserve_or_pool=reserve, slots=list(slots),
    )


def _slot(slot_id: str, points: int, *, variable: bool = False) -> SlotView:
    return SlotView(
        slot_id=slot_id, name=slot_id.title(), active_points=points,
        variable=variable, kind="attack", attack=None,
    )


def _with_frameworks(combatant, *frameworks):
    """Attach frameworks to a synthetic combatant.

    `framework_view()` normally derives them from `hero.powers`; a synthetic
    hero has none, so the method is replaced wholesale rather than faking
    power objects the deriver would have to parse.
    """
    object.__setattr__(combatant, "framework_view", lambda: list(frameworks))
    return combatant


def _session(*extra):
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=2),
        combatants=[
            fighter("alice", side=Side.named("heroes"), dex=25),
            fighter("bob", side=Side.named("heroes"), dex=20),
            fighter("mark", side=Side.named("villains"), dex=10),
            *extra,
        ],
    ).start()


def _act(kind: str, action_id: str, target: str | None = "mark") -> LegalAction:
    return LegalAction(
        action_id=action_id, kind=kind, target_id=target,
        power_xmlid=None, power_name=None, summary=kind,
    )


# ---- The whole menu is now executable ----

def test_every_enumerable_kind_is_registered():
    """59 of 59. The number this session started at was 4.

    Checked against `ALL_ACTION_KINDS`, which enumeration DECLARES, rather
    than against an AST walk. The walk was the earlier test and it was
    wrong: three offers build their kind from a variable (`kind = "sweep"
    if is_hth else "multiple_attack"`, the interaction-skill loop, the
    climb loop), so matching `kind="literal"` saw 51 and missed eight.

    That test passed while `sweep`, `multiple_attack`, `climb`,
    `climb_fast`, `charm`, `persuasion`, `conversation` and `trading` had
    no resolver at all. The gap surfaced only when a real fight -- the
    O.K. Corral, eight men -- spent 27 of 31 Phases picking
    `multiple_attack` and having it skipped.
    """
    from kirby_combat.enumeration import ALL_ACTION_KINDS

    assert ALL_ACTION_KINDS - registered_kinds() == set(), (
        f"offered but not executable: "
        f"{sorted(ALL_ACTION_KINDS - registered_kinds())}"
    )
    assert registered_kinds() - ALL_ACTION_KINDS == set(), (
        f"registered but never offered: "
        f"{sorted(registered_kinds() - ALL_ACTION_KINDS)}"
    )
    assert len(ALL_ACTION_KINDS) == 59


def test_the_declared_kinds_cover_every_literal_in_enumeration():
    """Guards the guard. `ALL_ACTION_KINDS` is maintained by hand, so a
    literal kind added to an offer without being declared would slip past
    the check above. The AST walk cannot see dynamic kinds, but it is a
    perfectly good check that no LITERAL one was forgotten."""
    import ast
    import pathlib

    from kirby_combat.enumeration import ALL_ACTION_KINDS

    src = pathlib.Path("kirby_combat/enumeration.py").read_text()
    literals = {
        kw.value.value
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "LegalAction"
        for kw in node.keywords
        if kw.arg == "kind" and isinstance(kw.value, ast.Constant)
    }
    assert literals - ALL_ACTION_KINDS == set(), (
        f"offered as a literal but not declared: "
        f"{sorted(literals - ALL_ACTION_KINDS)}"
    )


# ---- Coordination: the roll ladder ----

def test_teamwork_is_the_skill_the_book_names():
    actor = fighter("a", side=Side.named("x"), dex=20)
    actor.hero.skills = [_Skill("TEAMWORK")]
    skill, target = roll_profile(actor)
    assert skill == "Teamwork"
    assert target == 9 + 20 // 5      # 6E1 p.58: 9 + CHAR/5


def test_tactics_is_the_fallback():
    actor = fighter("a", side=Side.named("x"), dex=20)
    actor.hero.skills = [_Skill("TACTICS")]
    assert roll_profile(actor)[0] == "Tactics"


def test_anyone_may_try_at_dex_8():
    """A character with neither skill can still time a blow, just not
    well."""
    actor = fighter("a", side=Side.named("x"), dex=20)
    actor.hero.skills = []
    assert roll_profile(actor) == ("DEX", 8)


@pytest.mark.parametrize("roll, joined", [(3, True), (8, True), (9, False), (18, False)])
def test_the_join_is_a_standard_skill_roll(roll, joined):
    attempt = CoordinationRoll(
        combatant_id="a", target_id="m", skill="DEX", target_number=8, roll=roll,
    )
    assert attempt.joined is joined


# ---- Coordination: the window ----

def _join(session, who: str, *, roll: list[int]):
    return resolve_chosen(
        session, session.combatants[who], _act("coordinate", "coordinate:mark"),
        template=TEMPLATE, roller=FakeRoller([roll]),
    ).session


def test_one_combatant_cannot_coordinate_alone():
    session = _join(_session(), "alice", roll=[1, 1, 1])
    assert window_for(session, "mark", 12) == ("alice",)
    assert is_coordinated(session, "mark", 12) is False


def test_two_joiners_make_a_coordinated_strike():
    session = _join(_join(_session(), "alice", roll=[1, 1, 1]), "bob", roll=[1, 1, 1])
    assert set(window_for(session, "mark", 12)) == {"alice", "bob"}
    assert is_coordinated(session, "mark", 12) is True


def test_a_failed_roll_does_not_join_the_window():
    session = _join(_session(), "alice", roll=[6, 6, 6])
    assert window_for(session, "mark", 12) == ()


def test_the_window_is_scoped_to_its_segment():
    """6E2 p.46's premise is that the blows land TOGETHER, so a join from
    an earlier Segment is not part of this strike."""
    session = _join(_session(), "alice", roll=[1, 1, 1])
    assert window_for(session, "mark", 12) == ("alice",)
    assert window_for(session, "mark", 3) == ()


def test_the_window_is_scoped_to_its_target():
    session = _join(_session(), "alice", roll=[1, 1, 1])
    assert window_for(session, "someone-else", 12) == ()


# ---- Framework state ----

@pytest.mark.parametrize("action_id, expected", [
    ("reallocate_slots:fw1:a,b,c", ("fw1", ("a", "b", "c"))),
    ("reallocate_slots:fw1:a", ("fw1", ("a",))),
    ("reconfigure_vpp:pool9", ("pool9", ())),
    ("reallocate_slots:fw1:", ("fw1", ())),
    ("reallocate_slots", ("", ())),
    ("", ("", ())),
])
def test_the_framework_is_read_off_the_offer(action_id, expected):
    assert parse_reallocation(action_id) == expected


def test_an_unidentifiable_framework_refuses():
    session = _session()
    for kind in ("reallocate", "reconfigure_vpp"):
        with pytest.raises(UnresolvableAction, match=kind):
            resolve_chosen(
                session, session.combatants["alice"], _act(kind, kind, None),
                template=TEMPLATE, roller=RandomRoller(seed=2),
            )


def test_reallocating_records_the_whole_active_set():
    """The LATEST reallocation wins, and each states the whole set rather
    than a change to it -- the same absolute-value discipline every other
    state-changing event in this engine uses. A delta would be
    unrecoverable the moment one was missed."""
    session = _session()
    alice = _with_frameworks(
        session.combatants["alice"],
        _framework(slots=[_slot("a", 20), _slot("b", 20), _slot("c", 20)]),
    )

    session = resolve_chosen(
        session, alice, _act("reallocate", "reallocate_slots:fw1:a,b", None),
        template=TEMPLATE, roller=RandomRoller(seed=2),
    ).session
    assert active_slots(session, "alice", "fw1") == ("a", "b")

    session = resolve_chosen(
        session, alice, _act("reallocate", "reallocate_slots:fw1:c", None),
        template=TEMPLATE, roller=RandomRoller(seed=2),
    ).session
    assert active_slots(session, "alice", "fw1") == ("c",), "the latest wins"


def test_no_reallocation_means_no_opinion_not_nothing_active():
    """The build's own default set is the caller's to supply."""
    assert active_slots(_session(), "alice", "fw1") == ()


def test_frameworks_and_combatants_do_not_bleed_into_each_other():
    session = _session()
    _with_frameworks(
        session.combatants["alice"], _framework(slots=[_slot("a", 20)]),
    )
    session = resolve_chosen(
        session, session.combatants["alice"],
        _act("reallocate", "reallocate_slots:fw1:a", None),
        template=TEMPLATE, roller=RandomRoller(seed=2),
    ).session
    assert active_slots(session, "alice", "fw2") == ()
    assert active_slots(session, "bob", "fw1") == ()


def test_reconfiguring_a_vpp_records_the_intent_and_builds_nothing():
    """Constructing a costed power is the BUILD engine's work. Combat
    consumes the build engine's shape; it does not become a second one."""
    session = _session()
    resolved = resolve_chosen(
        session, session.combatants["alice"],
        _act("reconfigure_vpp", "reconfigure_vpp:pool9", None),
        template=TEMPLATE, roller=RandomRoller(seed=2),
    )
    payload = resolved.session.event_log[-1].result_payload
    assert payload["framework_id"] == "pool9"
    assert list(resolved.session.combatants["alice"].attacks) == list(
        session.combatants["alice"].attacks
    ), "no power was conjured in the combat engine"


# ---------------------------------------------------------------------------
# THE POOL RESTRICTION. The reserve is the entire reason a Multipower is
# cheaper than buying its powers outright (6E1 p.204): it caps the Active
# Points the slots may draw AT ONCE.
# ---------------------------------------------------------------------------


def test_a_set_that_fits_the_reserve_is_allowed():
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=60, slots=[_slot("a", 30), _slot("b", 30)]),
    )
    assert validate_allocation(actor, "fw1", ("a", "b")) == 60


def test_fixed_slots_over_the_reserve_are_REFUSED():
    """The one thing the framework exists to prevent."""
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=60, slots=[_slot("a", 40), _slot("b", 40)]),
    )
    with pytest.raises(ReserveExceeded) as excinfo:
        validate_allocation(actor, "fw1", ("a", "b"))
    assert excinfo.value.requested == 80
    assert excinfo.value.reserve == 60


def test_the_resolver_refuses_an_over_reserve_reallocation():
    """An OFFER IS NOT A PERMISSION SLIP. `enumerate_actions` gates which
    slots it offers, but a reallocate names its whole set in one id -- a
    chooser returning a hand-built id would otherwise switch on a
    configuration the build cannot pay for."""
    session = _session()
    _with_frameworks(
        session.combatants["alice"],
        _framework(reserve=60, slots=[_slot("a", 40), _slot("b", 40)]),
    )
    with pytest.raises(UnresolvableAction, match="reallocate"):
        resolve_chosen(
            session, session.combatants["alice"],
            _act("reallocate", "reallocate_slots:fw1:a,b", None),
            template=TEMPLATE, roller=RandomRoller(seed=2),
        )


def test_an_unknown_slot_is_refused():
    session = _session()
    _with_frameworks(
        session.combatants["alice"], _framework(slots=[_slot("a", 10)]),
    )
    with pytest.raises(UnresolvableAction, match="reallocate"):
        resolve_chosen(
            session, session.combatants["alice"],
            _act("reallocate", "reallocate_slots:fw1:a,ghost", None),
            template=TEMPLATE, roller=RandomRoller(seed=2),
        )


# ---- Fixed vs variable ----

def test_a_variable_slot_dials_down_to_fit_what_is_left():
    """A variable slot may run at ANY portion of its Active Points -- it
    costs more real points for exactly that flexibility -- so charging it
    full price would refuse configurations the book allows."""
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=60, slots=[
            _slot("fixed", 40), _slot("flex", 40, variable=True),
        ]),
    )
    # 40 fixed + a variable capped at the remaining 20.
    assert validate_allocation(actor, "fw1", ("fixed", "flex")) == 60


def test_the_same_set_of_fixed_slots_would_be_refused():
    """The contrast that makes the distinction load-bearing: identical
    point values, different legality."""
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=60, slots=[_slot("f1", 40), _slot("f2", 40)]),
    )
    with pytest.raises(ReserveExceeded):
        validate_allocation(actor, "fw1", ("f1", "f2"))


def test_variable_slots_alone_never_exceed_the_reserve():
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=50, slots=[
            _slot("v1", 40, variable=True), _slot("v2", 40, variable=True),
        ]),
    )
    assert validate_allocation(actor, "fw1", ("v1", "v2")) == 50


def test_a_variable_slot_with_no_room_left_is_on_at_zero():
    """Legal: the slot is switched on, drawing nothing."""
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=40, slots=[
            _slot("fixed", 40), _slot("flex", 30, variable=True),
        ]),
    )
    assert validate_allocation(actor, "fw1", ("fixed", "flex")) == 40


def test_switching_everything_off_is_legal():
    actor = _with_frameworks(
        fighter("a", side=Side.named("x")),
        _framework(reserve=60, slots=[_slot("a", 30)]),
    )
    assert validate_allocation(actor, "fw1", ()) == 0


# ---- The gate the loop now feeds ----

def test_the_allocation_is_assembled_from_the_build_and_the_log():
    """`slot_allocation` was a parameter the caller had to keep in step with
    reallocations it was not otherwise tracking. The reserve and slot costs
    are build data; the active set is the fight's."""
    session = _session()
    _with_frameworks(
        session.combatants["alice"],
        _framework(reserve=60, slots=[_slot("a", 20), _slot("b", 20)]),
    )
    alloc = allocation_for(session, session.combatants["alice"])
    reserve, used, active, costs = alloc["fw1"]
    assert (reserve, used, active) == (60, 0, set())
    assert costs == {"a": 20, "b": 20}

    session = resolve_chosen(
        session, session.combatants["alice"],
        _act("reallocate", "reallocate_slots:fw1:a", None),
        template=TEMPLATE, roller=RandomRoller(seed=2),
    ).session
    reserve, used, active, _ = allocation_for(
        session, session.combatants["alice"],
    )["fw1"]
    assert (used, active) == (20, {"a"}), "the fight's own reallocation"


def test_no_frameworks_means_no_gate():
    """Which is exactly what a caller passing nothing has always meant."""
    session = _session()
    assert allocation_for(session, session.combatants["alice"]) is None


# ---------------------------------------------------------------------------
# THE POOL. 6E2 p.46 + p.106: a coordinated strike's STUN pools against CON,
# so two blows that each fall short can together Stun. That is the entire
# reason to coordinate, and it is what this section pins.
# ---------------------------------------------------------------------------


def _attack_payload(session, attacker_id: str, target_id: str, stun: int,
                    segment: int = 12):
    """Land an attack of exactly `stun` STUN, with no `status_changes` --
    so any Stun that appears can only have come from the pool."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(attacker_id),
        declaration_event_id="",
        result_payload={
            "kind": "attack", "hit": True, "stun_dealt": stun,
            "body_dealt": 0, "status_changes": [],
            "target_id": target_id, "segment": segment,
        },
    ))


def _coordinated_pair():
    """Alice and Bob both join a strike on Mark (CON 18)."""
    session = _session()
    session = _join(session, "alice", roll=[1, 1, 1])
    return _join(session, "bob", roll=[1, 1, 1])


def test_two_blows_that_each_fall_short_together_stun():
    """Mark's CON is 18. Neither 10 nor 11 exceeds it; 21 does."""
    from kirby_combat.coordination import pooled_stun, pools_into_a_stun

    session = _coordinated_pair()
    assert session.combatants["mark"].combat_stats().con == 18

    session = _attack_payload(session, "alice", "mark", 10)
    assert pools_into_a_stun(session, "mark", 12, 18) is False

    session = _attack_payload(session, "bob", "mark", 11)
    assert pooled_stun(session, "mark", 12) == 21
    assert pools_into_a_stun(session, "mark", 12, 18) is True


def test_the_pooled_stun_shows_up_as_a_real_status():
    """Not just a helper returning True -- `statuses_for` must report it,
    because that is what every consumer reads."""
    from kirby_combat.statuses import STUNNED, statuses_for

    session = _coordinated_pair()
    session = _attack_payload(session, "alice", "mark", 10)
    assert STUNNED not in statuses_for(session, "mark")

    session = _attack_payload(session, "bob", "mark", 11)
    assert STUNNED in statuses_for(session, "mark"), (
        "a Stun that no single attack's status_changes ever named"
    )


def test_an_uncoordinated_ally_does_not_pool():
    """Joining is what makes the blows simultaneous. Swinging in the same
    Segment without joining is just two separate attacks."""
    from kirby_combat.coordination import pooled_stun

    session = _join(_session(), "alice", roll=[1, 1, 1])   # only alice joined
    session = _attack_payload(session, "alice", "mark", 10)
    session = _attack_payload(session, "bob", "mark", 11)
    assert pooled_stun(session, "mark", 12) == 0, "the window was never full"


def test_one_character_cannot_pool_with_themselves():
    from kirby_combat.coordination import pooled_stun

    session = _join(_session(), "alice", roll=[1, 1, 1])
    session = _attack_payload(session, "alice", "mark", 30)
    assert pooled_stun(session, "mark", 12) == 0


def test_the_pool_is_scoped_to_its_segment():
    """Blows in different Segments did not land together, whatever the
    window said."""
    from kirby_combat.coordination import pooled_stun

    session = _coordinated_pair()
    session = _attack_payload(session, "alice", "mark", 10, segment=12)
    session = _attack_payload(session, "bob", "mark", 11, segment=5)
    assert pooled_stun(session, "mark", 12) == 10


def test_the_join_itself_contributes_no_stun():
    """A `coordinate` payload is not an attack."""
    from kirby_combat.coordination import pooled_stun

    assert pooled_stun(_coordinated_pair(), "mark", 12) == 0


def test_exceeds_not_meets_or_exceeds():
    """6E2 p.106 says "exceeds", matching `determine_status_changes`."""
    from kirby_combat.coordination import pools_into_a_stun

    session = _coordinated_pair()
    session = _attack_payload(session, "alice", "mark", 9)
    session = _attack_payload(session, "bob", "mark", 9)      # exactly 18
    assert pools_into_a_stun(session, "mark", 12, 18) is False
