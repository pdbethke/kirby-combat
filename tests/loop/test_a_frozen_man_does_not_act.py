"""A Presence Attack that stops you stops you, and then wears off.

6E2 p.139 stops the target outright from `awed` upward, and
`presence_effects.can_act` says so:

    def can_act(session, combatant_id) -> bool:
        \"\"\"False while a Presence Attack is holding this combatant
        frozen.\"\"\"

NOTHING EVER ASKED IT. Measured by sweeping every public function in the
engine for references: `can_act` is called nowhere outside its own module
--- so a man the rules have frozen in place took his Phase and shot
somebody, and the strongest result on the Presence ladder did nothing
whatever to what he did. Only `presence_cv_modifiers` was wired in, so
the HALF DCV landed and the "takes no Action" half did not.

`PresenceEffects.tick_all` --- documented as "what a driver advancing a
Segment calls" --- had no caller either. So the effect never counted down.
Nothing noticed, because the half that was live is a defensive penalty
nobody was tracking across Segments.

ONE PHASE, NOT FIVE MINUTES, and reading the citation is the whole of it.
6E2 p.139 at PRE+20: "will not act for 1 Full Phase and is at half DCV;
about 5 Minutes." Two clocks. The DCV penalty runs the tier's duration --
`awed` is 5 minutes, `overwhelmed` an hour -- and the LOST ACTION is a
single Phase. Gating every Phase while the tier is active would delete a
combatant from the entire fight on one good shout, which is not the rule
and would be a far worse bug than the one being fixed.

So the forfeit is its own clock, recorded by its own event, folded the
same way everything else here is.

WHERE THEY GO, and why it is not a new rule. `next_actor_id` already
skips combatants who cannot use a Phase --- the unconscious (6E1 p.421)
and those who have left the field --- consuming the slot silently,
because "they had a Phase, and they are in no condition to use it". A man
held rigid by terror is the same sentence. And the Segment advance is
where every other per-Segment clock is wound.
"""
from __future__ import annotations

from conftest import fighter, session_of            # tests/loop/conftest.py
from kirby_combat.loop.run import run_phase
from kirby_combat.pre_attacks.presence_effects import PresenceEffects, can_act
from kirby_combat.session.effects import presence_state
from kirby_combat.side import Side


def _frozen(session, combatant_id, tier="awed"):
    """Put a real PresenceApplied on the log, not a stub."""
    session, _ = PresenceEffects.apply(
        session, target_id=combatant_id, attacker_id="virgil", tier=tier,
    )
    return session


def _started(*, spd=4):
    """A session with an acting order written, which is what the loop runs
    on -- `run_phase` alone finds no slots and reports `actor_id is None`."""
    from kirby_combat.session.timeline import build_acting_order_for_segment

    session = session_of(
        fighter("tom", side=Side.named("cow"), spd=spd),
        fighter("virgil", side=Side.named("law"), spd=spd),
    )
    session.timeline.acting_order[:] = build_acting_order_for_segment(
        list(session.combatants.values()), session.timeline.segment,
    )
    return session


def test_the_rules_say_he_cannot_act():
    """The predicate itself, so the wiring test below cannot pass by the
    predicate being wrong in the same direction."""
    session = _frozen(_started(), "tom")
    assert can_act(session, "tom") is False
    assert can_act(session, "virgil") is True


def test_the_loop_does_not_hand_him_a_phase():
    """The defect. He was asked to decide and he shot somebody.

    `run_segment` writes the acting order and then runs every slot in it,
    which is the real path -- `run_phase` alone finds no slots.
    """
    from kirby_combat.loop.chooser import FirstLegalChooser
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    session = _frozen(_started(), "tom")
    notes = []
    for _ in range(4):
        result = run_phase(
            session, FirstLegalChooser(), on_unresolvable="skip",
            template=CombatTemplate.default_6e_superheroic(),
            roller=RandomRoller(seed=3),
        )
        session = result.session
        notes += result.notes
        if result.actor_id is None:
            break

    assert any("Presence Attack" in n for n in notes), notes
    tom_acted = [
        e for e in session.event_log
        if getattr(e, "kind", "") == "ActionDeclared"
        and getattr(e, "combatant_id", None) == "tom"
    ]
    assert not tom_acted, "a man frozen by terror declared an action"
    assert any(
        getattr(e, "kind", "") == "ActionDeclared"
        and getattr(e, "combatant_id", None) == "virgil"
        for e in session.event_log
    ), "and everyone else still acts"
    assert can_act(session, "tom") is True, "the forfeit was spent"


def test_and_the_phase_after_is_his_again():
    """The forfeit is recorded, so it is spent exactly once."""
    session = _frozen(_started(), "tom")
    assert can_act(session, "tom") is False
    session = PresenceEffects.forfeit_phase(session, "tom")
    assert can_act(session, "tom") is True


def test_he_loses_ONE_phase_and_then_fights_on():
    """6E2 p.139: "will not act for 1 Full Phase and is at half DCV; about
    5 Minutes". Two clocks. Freezing him for the whole five minutes would
    delete him from the fight on one good shout."""
    session = _frozen(_started(), "tom")
    assert can_act(session, "tom") is False

    session = PresenceEffects.forfeit_phase(session, "tom")
    assert can_act(session, "tom") is True, "the lost action was one Phase"
    assert presence_state(session, "tom").is_active, (
        "and the half-DCV half of the result is still running"
    )


def test_the_duration_still_counts_down():
    """`tick_all` is documented as what a driver advancing a Segment
    calls, and nothing called it -- so the DCV penalty was permanent."""
    session = _frozen(_started(), "tom")
    before = presence_state(session, "tom").segments_remaining
    assert before > 0
    session = PresenceEffects.tick_all(session)
    assert presence_state(session, "tom").segments_remaining == before - 1


def test_a_lesser_result_still_lets_him_act():
    """Only `awed` and up stop the target outright (6E2 p.139). A merely
    impressed man fights on at a penalty, and gating him would be a
    harsher rule than the book's."""
    session = _frozen(_started(), "tom", tier="impressed")
    assert can_act(session, "tom") is True


# ---- The other clock: the tier's duration ----

def test_the_encounter_winds_the_presence_clock():
    """`PresenceEffects.tick_all` is documented as "what a driver advancing
    a Segment calls", and NOTHING CALLED IT -- so the half-DCV half of a
    Presence result, which is the half that was actually wired in through
    the CV seam, never expired. A man shouted at once in Segment 3 was at
    half DCV for the rest of the fight and for every fight after it in the
    same session.

    `advance_segment` is where it belongs: it is already the home of the
    Post-Segment 12 Recovery and of `SegmentAdvanced`, and a Presence
    duration is the same kind of per-Segment clock.
    """
    from kirby_combat.encounter import Encounter

    session = _frozen(_started(), "tom")
    before = presence_state(session, "tom").segments_remaining
    assert before > 0

    encounter = Encounter(id="e", turn=1, segment=3, sessions=[session])
    encounter = encounter.advance_segment()
    after = presence_state(encounter.sessions[0], "tom").segments_remaining
    assert after == before - 1, "one Segment of terror should have passed"


def test_it_winds_across_the_turn_boundary_too():
    """Segment 12 wraps to Segment 1 of the next Turn on a different
    branch, and a clock wound on only one branch stops for a Turn every
    Turn."""
    from kirby_combat.encounter import Encounter

    session = _frozen(_started(), "tom")
    before = presence_state(session, "tom").segments_remaining
    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session])
    encounter = encounter.advance_segment()
    after = presence_state(encounter.sessions[0], "tom").segments_remaining
    assert after == before - 1
