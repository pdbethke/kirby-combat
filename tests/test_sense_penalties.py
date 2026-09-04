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
from kirby_dice import FakeRoller
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
    """6E2 p.9 halves both OCV and DCV in hand-to-hand combat."""
    s = _blind(_session())
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 4
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_unperceiving_combatant_is_zero_ocv_half_dcv_at_range():
    """6E2 p.9 drops OCV to zero and halves DCV at Range.

    This is the first source in the engine to produce a 0.0 CV factor --
    the branch ``_fold_cv_factors`` documents as untested by construction.
    """
    s = _blind(_session())
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 0
    assert effective_dcv_for(s, "orion", against="durak", combat_type="ranged") == 4


def test_zero_ocv_wins_over_a_simultaneous_halving():
    """6E2 p.39 applies a reduction of OCV to 0 as the very last step.

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
    """6E2 p.9 attaches the penalty to having NO Targeting Sense that
    reaches the opponent. It names Hearing as Nontargeting for a normal
    human, so a Hearing Flash blinds nothing that aims.
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
    """Against the one opponent he heard, 6E2 p.9 puts him at -1 DCV and
    half OCV hand-to-hand. -1 is a FLAT modifier, not a second halving:
    8 DCV becomes 7, not 4 and not 2.
    """
    s = _orion_hears_durak(_blind(_session()))
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 7
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 4


def test_orion_against_durak_is_full_dcv_half_ocv_at_range():
    """At Range against that same opponent, 6E2 p.9 gives him FULL DCV and
    half OCV. Full -- the halving is gone, not softened."""
    s = _orion_hears_durak(_blind(_session()))
    assert effective_dcv_for(s, "orion", against="durak", combat_type="ranged") == 8
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 4


def test_orion_against_everyone_else_is_still_a_sitting_duck():
    """6E2 p.9 leaves the unmitigated penalties in force against everyone
    he did not hear. The same combatant, the same Segment, different CVs
    per opponent -- the constraint that forces the seam to be
    per-opponent at all.
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
    """6E2 p.9 ends the benefit at the start of the character's next
    Phase; keeping it costs another Half Phase Action and another
    successful roll.
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
    """Two halvings apply one at a time -- 6E1 p.14 rounds at each separate
    step of a calculation -- never as a pre-multiplied 0.25: 8 -> 4 -> 2.
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


# ---------------------------------------------------------------------------
# The stat-block path — found by examples/raw_orion.py, not by review
# ---------------------------------------------------------------------------

def _statblock_session():
    """A session of ``StatBlockCombatant``s, which expose no ``senses()``."""
    from kirby_combat.models import StatBlockCombatant

    def sb(id_):
        return StatBlockCombatant(
            id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
            spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
            pd=5, ed=5, rpd=0, red=0, md=5,
            power_defense=0, flash_defense=0,
            max_stun=30, max_body=15, max_end=30,
            current_stun=30, current_body=15, current_end=30,
            attacks=[], defenses=[],
        )

    return CombatSession.create(
        id="s1", combatants=[sb("orion"), sb("durak")], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def test_a_stat_block_combatant_is_blinded_too():
    """Only a build-backed combatant has ``senses()``. Treating the absence
    as "nothing blocks him" made the whole rule a no-op for stat blocks --
    every example script, much of this suite, and any driver working from a
    flat stat block. The fallback is 6E2 p.9's normal human: Sight is the
    only Targeting Sense.
    """
    s = _statblock_session()
    s, _ = Flash.apply(s, attacker_id="durak", target_id="orion",
                       sense_group="sight", body_dealt=8, flash_defense=0)
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 4
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 4
    assert effective_ocv_for(s, "orion", against="durak", combat_type="ranged") == 0


def test_a_stat_block_flashed_in_a_nontargeting_group_still_aims():
    """The fallback has to be the whole rule, not just its punishing half."""
    s = _statblock_session()
    s, _ = Flash.apply(s, attacker_id="durak", target_id="orion",
                       sense_group="hearing", body_dealt=8, flash_defense=0)
    assert effective_ocv_for(s, "orion", against="durak", combat_type="hth") == 8
    assert effective_dcv_for(s, "orion", against="durak", combat_type="hth") == 8


def test_per_roll_target_works_for_a_stat_block():
    """``per_roll_target`` read ``observer.hero``, which a stat block has
    not got, so asking one for a PER roll raised AttributeError. INT 10
    against the 6E defaults is an 11-."""
    from kirby_combat.perception import per_roll_target

    s = _statblock_session()
    assert per_roll_target(s.combatants["orion"]) == 11
