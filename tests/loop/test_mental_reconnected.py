"""The mental resolvers, reconnected.

WHAT WAS WRONG. ``mental/mind_control.py``, ``mental_illusion.py`` and
``telepathy.py`` held correct, tested resolvers that nothing in production
ever called. The parked kirby-api driver wrote its own copy of each inside a
1,070-line dispatcher, so the engine's versions were reachable only from
their own unit tests.

The measurement: the engine states the mental Attack Roll once, in
``mental_combat.py`` --- "Target number = 11 + attacker.omcv -
target.dmcv". The parked driver writes that expression out at four separate
lines (8619, 9592, 9706, 11172).

**Every one of those suites was green.** The rules were correct and tested;
what was missing was a caller, and no test asserted "something reaches
this". These tests are that assertion --- they drive each kind through the
loop's own dispatch rather than calling the resolver directly, because
calling it directly is exactly what never proved anything.
"""
from __future__ import annotations

import pytest

from conftest import encounter_of, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import PhaseSituation, registered_kinds, run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()
MENTAL_KINDS = ("mind_control", "mental_illusion", "telepathy")


def _power(xmlid: str, levels: int = 10) -> AttackPower:
    p = AttackPower(
        xmlid=xmlid, name=xmlid.title(), damage_dice=levels,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="md", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=f"src-{xmlid}",
    )
    object.__setattr__(p, "levels", levels) if hasattr(p, "__dataclass_fields__") else None
    return p


def _mentalist(id: str, side: str):
    c = fighter(id, side=Side.named(side), dex=20)
    object.__setattr__(c, "_explicit_is_mentalist", True)
    return c


def _action(kind: str, target_id: str, levels: int = 10) -> LegalAction:
    power = _power(kind.upper().replace("_", ""), levels)
    try:
        power.levels = levels
    except Exception:  # frozen — carried via the attribute set above
        pass
    return LegalAction(
        action_id=f"{kind}:{target_id}:src", kind=kind, target_id=target_id,
        power_xmlid=power.xmlid, power_name=power.name,
        summary=f"{kind} on {target_id}", _attack_view=power,
    )


# ---- Registered, and therefore countable ----

@pytest.mark.parametrize("kind", MENTAL_KINDS)
def test_the_kind_is_registered(kind):
    assert kind in registered_kinds()


# The full registered set is pinned once, in test_run.py -- not duplicated
# here, so that adding a kind fails in one place rather than two.


# ---- Reachable through the dispatch, not just importable ----

@pytest.mark.parametrize("kind", MENTAL_KINDS)
def test_the_engine_resolves_the_kind_and_records_it(kind):
    enc = encounter_of(_mentalist("psi", "a"), fighter("mark", side=Side.named("b")))
    session = enc.sessions[0]
    actor = session.combatants["psi"]

    resolved = resolve_chosen(
        session, actor, _action(kind, "mark"),
        template=TEMPLATE, roller=RandomRoller(seed=4),
    )

    assert resolved.kind == kind
    assert resolved.events, "the outcome must reach the log for a consumer"
    payload = resolved.session.event_log[-1].result_payload
    assert payload["kind"] == kind
    assert payload["target_id"] == "mark"


@pytest.mark.parametrize("kind", MENTAL_KINDS)
def test_the_outcome_is_a_degree_against_ego_not_damage(kind):
    """Mind Control, Mental Illusion and Telepathy classify an effect roll
    on the degree ladder. None of them deals STUN or BODY, so none may
    move the target's vitals."""
    enc = encounter_of(_mentalist("psi", "a"), fighter("mark", side=Side.named("b")))
    session = enc.sessions[0]
    before = session.combatants["mark"].state.current_stun

    resolved = resolve_chosen(
        session, session.combatants["psi"], _action(kind, "mark"),
        template=TEMPLATE, roller=RandomRoller(seed=4),
    )

    assert resolved.result.degree is not None
    assert resolved.result.target_ego > 0
    assert resolved.session.combatants["mark"].state.current_stun == before


@pytest.mark.parametrize("kind", MENTAL_KINDS)
def test_a_non_mentalist_is_refused_by_the_engines_own_rule(kind):
    """The pure resolver's guard, reached through the dispatch — proof the
    wrapper runs the engine's rule rather than a copy of it."""
    enc = encounter_of(fighter("mundane", side=Side.named("a")),
                       fighter("mark", side=Side.named("b")))
    session = enc.sessions[0]
    with pytest.raises(ValueError, match="not marked as mentalist"):
        resolve_chosen(
            session, session.combatants["mundane"], _action(kind, "mark"),
            template=TEMPLATE, roller=RandomRoller(seed=4),
        )


def test_each_declaration_is_paired_with_its_resolution():
    enc = encounter_of(_mentalist("psi", "a"), fighter("mark", side=Side.named("b")))
    session = enc.sessions[0]
    resolved = resolve_chosen(
        session, session.combatants["psi"], _action("mind_control", "mark"),
        template=TEMPLATE, roller=RandomRoller(seed=4),
    )
    declared, resolution = resolved.events[-2], resolved.events[-1]
    assert declared.kind == "ActionDeclared"
    assert resolution.declaration_event_id == declared.id
