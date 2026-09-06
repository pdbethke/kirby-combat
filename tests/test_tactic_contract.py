"""The tactic contract, and the RAW/JUDGEMENT distinction it carries."""
import pytest

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic


def test_a_tactic_must_implement_both_halves():
    """An ABC that could be instantiated half-built would fail at resolve
    time, in a fight, instead of at import."""
    with pytest.raises(TypeError):
        Tactic()  # type: ignore[abstract]


def test_basis_distinguishes_advised_from_merely_permitted():
    # Block is DEFINED by the book and not ADVISED by it: aborting to Block
    # against a big incoming hit is judgement.
    block = Basis(mechanism="6E2 p57", judgement="a stopped hit beats a phase")
    assert block.is_raw is False
    # Pushing is both defined and advised -- 6E2 p39 names it first of five.
    push = Basis(mechanism="6E2 p133", doctrine="6E2 p39")
    assert push.is_raw is True


def test_a_bare_basis_claims_nothing():
    assert Basis().is_raw is False
    assert Basis().mechanism is None
    assert Basis().judgement == ""


def test_a_basis_cannot_be_edited_after_the_fact():
    """Frozen: a tactic's provenance is not something a caller adjusts."""
    b = Basis(mechanism="6E2 p57")
    with pytest.raises(Exception):
        b.mechanism = "6E2 p99"  # type: ignore[misc]


def test_a_plan_step_names_its_kind():
    step = PlanStep(kind="attack", target_id="thug")
    plan = Plan(tactic_name="t", rationale="because", steps=[step])
    assert plan.steps[0].kind == "attack"


def test_situation_defaults_are_empty_not_none():
    """A tactic reads these without checking; None would crash mid-fight."""
    s = Situation(actor=object(), allies=[], enemies=[])
    assert s.scene_features == []
    assert s.actor_complications == []
    assert s.actor_skills == {}
