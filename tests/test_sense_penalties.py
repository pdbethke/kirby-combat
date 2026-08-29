"""The "inability to sense an opponent" CV penalties — 6E2 p.9 / p.127.

These tests pin the rule that governs the whole sense-affecting family
(Flash, Darkness, Invisibility): a character who cannot perceive an
opponent with a Targeting Sense fights at reduced CV, and a Nontargeting
PER Roll mitigates that **against one opponent only**.

The Orion example (6E2 p.9) is the case that forces the design. Its
numbers are asserted end-to-end in ``examples/raw_orion.py``; what is
pinned here is the seam those numbers come out of.
"""

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.flash import Flash
from kirby_combat.cv_modifiers import effective_dcv_for, effective_ocv_for
from kirby_combat.sense_penalties import NontargetingPerception


def _c(id_: str, **kw):
    base = dict(
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=3,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    base.update(kw)
    return synthetic_combatant(id=id_, name=id_, **base)


def _session(roller=None) -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("orion"), _c("durak"), _c("fiacho")],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller or FakeRoller([]),
    ).start()


def _blind(session, target_id="orion"):
    """Flash ``target_id``'s Sight Group — a normal human's only Targeting Sense."""
    s, _ = Flash.apply(
        session, attacker_id="durak", target_id=target_id,
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    return s


# ---------------------------------------------------------------------------
# The unmodified case — nothing changes for a combatant who can see
# ---------------------------------------------------------------------------

def test_perceiving_combatant_cv_is_unchanged():
    s = _session()
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 8
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 8
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 8
    assert effective_dcv_for(s, "orion", against="durak", combat_type="ranged") == 8


def test_omitting_against_keeps_todays_behaviour():
    """The per-opponent sources are skipped when no opponent is named, so an
    existing caller of ``effective_dcv_for(session, id)`` is unaffected."""
    s = _blind(_session())
    assert effective_dcv_for(s, "orion") == 8
    assert effective_ocv_for(s, "orion") == 8


# ---------------------------------------------------------------------------
# 6E2 p.9 — the standard "lack of Targeting Sense" modifiers
# ---------------------------------------------------------------------------

def test_unperceiving_combatant_is_half_ocv_half_dcv_in_hth():
    """6E2 p.9: in HTH Combat the character is at 1/2 OCV and 1/2 DCV."""
    s = _blind(_session())
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 4
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_unperceiving_combatant_is_zero_ocv_half_dcv_at_range():
    """6E2 p.9: in Ranged Combat the character is at 0 OCV and 1/2 DCV.

    This is the first source in the engine to produce a 0.0 CV factor --
    the branch ``_fold_cv_factors`` documents as untested by construction.
    """
    s = _blind(_session())
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 0
    assert effective_dcv_for(s, "orion", against="durak", combat_type="ranged") == 4


def test_zero_ocv_wins_over_a_simultaneous_halving():
    """6E2 p.39: a reduction of OCV to 0 is applied as the very last step.

    Composed with any other active factor the answer is still 0, never a
    halved 0 or a 0 that a later halving turns into something else.
    """
    from kirby_combat.cv_modifiers import _fold_cv_factors
    assert _fold_cv_factors(8, [0.5, 0.0]) == 0
    assert _fold_cv_factors(8, [0.0, 0.5]) == 0


# ---------------------------------------------------------------------------
# Only a TARGETING Sense counts (6E2 p.9)
# ---------------------------------------------------------------------------

def test_flash_to_a_nontargeting_sense_costs_no_cv():
    """6E2 p.9: the penalty applies when a character cannot perceive his
    opponent with **any Targeting Sense**. For a normal human, Hearing is
    Nontargeting -- a Hearing Flash blinds nothing that aims.
    """
    s = _session()
    s, _ = Flash.apply(
        s, attacker_id="durak", target_id="orion",
        sense_group="hearing", body_dealt=8, flash_defense=3,
    )
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 8
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 8


def test_penalty_lifts_when_the_flash_recovers():
    s = _blind(_session())
    s, _ = Flash.recover(s, target_id="orion", sense_group="sight",
                         segments_to_recover=99)
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 8
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 8


# ---------------------------------------------------------------------------
# THE ORION CASE (6E2 p.9) — mitigation is per-opponent, and a FLAT -1 DCV
# ---------------------------------------------------------------------------

def _orion_hears_durak(session):
    """Orion makes his Hearing PER Roll against Durak (3d6 = 6, a hit)."""
    s = session
    s, result = NontargetingPerception.acquire(
        s, observer_id="orion", target_id="durak",
        sense_group="hearing", roller=FakeRoller([[2, 2, 2]]),
    )
    assert result.succeeded
    return s


def test_orion_against_durak_is_minus_one_dcv_half_ocv_in_hth():
    """6E2 p.9: "against that target only he is at -1 DCV, 1/2 OCV when
    attacked or attacking in HTH Combat". -1 is a FLAT modifier, not a
    second halving: 8 DCV becomes 7, not 4 and not 2.
    """
    s = _orion_hears_durak(_blind(_session()))
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 7
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_orion_against_durak_is_full_dcv_half_ocv_at_range():
    """6E2 p.9: "...and full DCV, 1/2 OCV when attacked from or attacking
    at Range". Full DCV -- the halving is gone, not softened."""
    s = _orion_hears_durak(_blind(_session()))
    assert effective_dcv_for(s, "orion", against="durak", combat_type="ranged") == 8
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 4


def test_orion_against_everyone_else_is_still_a_sitting_duck():
    """6E2 p.9: "He's still at 1/2 OCV and DCV in HTH and 1/2 DCV, 0 OCV at
    Range against all other opponents." The same combatant, the same
    Segment, different CVs per opponent -- the constraint that forces the
    seam to be per-opponent at all.
    """
    s = _orion_hears_durak(_blind(_session()))
    assert effective_ocv_for(s, "orion", against="fiacho", combat_type="hth") == 4
    assert effective_dcv_for(s, "orion", against="fiacho", combat_type="hth") == 4
    assert effective_ocv_for(s, "orion", against="fiacho", combat_type="ranged") == 0
    assert effective_dcv_for(s, "orion", against="fiacho", combat_type="ranged") == 4


def test_a_failed_per_roll_mitigates_nothing():
    s = _blind(_session())
    s, result = NontargetingPerception.acquire(
        s, observer_id="orion", target_id="durak",
        sense_group="hearing", roller=FakeRoller([[6, 6, 6]]),
    )
    assert not result.succeeded
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_mitigation_expires_at_the_start_of_the_observers_next_phase():
    """6E2 p.9: "The benefits of making this roll last until the beginning
    of the character's next Phase; if he wants them to continue, he has to
    use another Half Phase Action and succeed with another PER Roll."
    """
    s = _orion_hears_durak(_blind(_session()))
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 7
    s, expired = NontargetingPerception.expire_for_combatant_next_phase(s, "orion")
    assert len(expired) == 1
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_mitigation_does_not_leak_between_observers():
    """Durak hearing Orion must not give Orion anything."""
    s = _blind(_session())
    s = _blind(s, target_id="durak")
    s, _ = NontargetingPerception.acquire(
        s, observer_id="durak", target_id="orion",
        sense_group="hearing", roller=FakeRoller([[2, 2, 2]]),
    )
    assert effective_dcv_for(s, "durak", against="orion", combat_type="hth") == 7
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4


# ---------------------------------------------------------------------------
# Composition with the conditions already at the seam
# ---------------------------------------------------------------------------

def test_stunned_and_unperceiving_compose_sequentially():
    """Two halvings apply one at a time (6E1 p.14, "round at each separate
    step"), never as a pre-multiplied 0.25: 8 -> 4 -> 2.
    """
    from kirby_combat.cv_modifiers import _fold_cv_factors
    assert _fold_cv_factors(8, [0.5, 0.5]) == 2


def test_the_half_phase_action_is_recorded_on_the_log():
    """6E2 p.9 makes the PER Roll a Half Phase Action; the log has to show
    it was spent, or a driver cannot charge for it."""
    s = _orion_hears_durak(_blind(_session()))
    declared = [e for e in s.event_log
                if e.kind == "ActionDeclared"
                and e.action_type == "nontargeting_perception"]
    assert len(declared) == 1
    assert declared[0].combatant_id == "orion"
    assert declared[0].parameters["phase_cost"] == "half"
