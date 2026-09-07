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
from kirby_combat.framework import active_slots, parse_reallocation
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
    """51 of 51. The number this session started at was 4."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("kirby_combat/enumeration.py").read_text())
    offered = {
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "LegalAction"
        for kw in node.keywords
        if kw.arg == "kind" and isinstance(kw.value, ast.Constant)
    }
    assert offered - registered_kinds() == set(), (
        f"offered but not executable: {sorted(offered - registered_kinds())}"
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
    alice = session.combatants["alice"]

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
