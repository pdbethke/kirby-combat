"""What a landed Presence Attack COSTS the target — 6E2 p.138-139.

`pre_attacks/presence.py` has always resolved the roll and named the tier.
Its `can_act_after` said the rest out loud: *"RAW is stricter — at 'awed'
(PRE+20) the target 'will not act for 1 Full Phase' — but consuming the
table's mechanical consequences is separate work."* This is that work.

**It follows the house pattern for persistent effects, and invents nothing.**
Adjustment, Entangle and Flash all do the same thing and their machinery is
`session/effects.py`:

  * `PresenceApplied` carries the tier and its initial duration.
  * `PresenceFaded` carries the **resulting remaining segments, absolute** —
    never a delta to subtract. That is what makes a forward fold correct and
    is exactly what backwards reconstruction cannot do (see the Krackle
    replay: END clamps at 0, so the amount really taken is destroyed).
  * `presence_state()` folds them forward in `effects.py`.
  * The decrement is caller-driven, like `Flash.recover()`.

Durations are DERIVED, not invented. 6E2 p.18: a Turn is 12 seconds and 12
Segments, each 1 second, so the book's wall-clock figures convert exactly.
"""

from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import FakeRoller
from kirby_combat.pre_attacks.presence_effects import (
    PRESENCE_TIERS, PresenceEffects, effect_for_tier,
)
from kirby_combat.session import CombatSession
from kirby_combat.session.effects import presence_state
from kirby_combat.template import CombatTemplate


def _c(id_):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_c("alice"), _c("bob"), _c("carl")], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _land(session, tier, target="bob", attacker="alice"):
    return PresenceEffects.apply(
        session, target_id=target, attacker_id=attacker, tier=tier)


# ---------------------------------------------------------------------------
# The table — verified against 6E2 p.139, not transcribed from elsewhere
# ---------------------------------------------------------------------------

def test_every_tier_the_resolver_can_produce_has_a_rule():
    assert set(PRESENCE_TIERS) == {
        "impressed", "very_impressed", "awed", "cowed", "overwhelmed",
    }


def test_impressed_lets_the_attacker_act_first_and_nothing_else():
    """6E2 p.139: at PRE the target hesitates enough that the attacker may
    act before him that Phase. No DCV penalty, no lost action."""
    r = PRESENCE_TIERS["impressed"]
    assert r.yields is True
    assert r.half_phase is False and r.no_action is False
    assert r.dcv_factor == 1.0


def test_very_impressed_costs_half_a_phase():
    """6E2 p.139: at PRE+10 he hesitates as above AND performs only a Half
    Phase Action during his next Phase."""
    r = PRESENCE_TIERS["very_impressed"]
    assert r.yields is True and r.half_phase is True
    assert r.no_action is False and r.dcv_factor == 1.0


def test_awed_costs_a_full_phase_and_half_dcv():
    """6E2 p.139: at PRE+20 he will not act for 1 Full Phase, at 1/2 DCV."""
    r = PRESENCE_TIERS["awed"]
    assert r.no_action is True and r.dcv_factor == 0.5


def test_cowed_is_zero_dcv():
    """6E2 p.139: at PRE+30 he may surrender, run away or faint; 0 DCV."""
    assert PRESENCE_TIERS["cowed"].dcv_factor == 0.0


def test_overwhelmed_has_the_same_COMBAT_effects_as_cowed():
    """6E2 p.139 is explicit that PRE+40 produces the SAME combat effects as
    PRE+30 — the difference is mental severity, which this engine does not
    model. Matching fields exactly, rather than inventing a distinction the
    book does not draw."""
    cowed, over = PRESENCE_TIERS["cowed"], PRESENCE_TIERS["overwhelmed"]
    assert (over.yields, over.half_phase, over.no_action, over.dcv_factor) == \
           (cowed.yields, cowed.half_phase, cowed.no_action, cowed.dcv_factor)


def test_only_grounded_dcv_factors_are_used():
    """`apply_cv_factor` accepts 1.0/0.5/0.0 and refuses the rest, because
    6E2 p.39 grounds only those. A tier inventing 0.75 would raise in
    combat."""
    assert {r.dcv_factor for r in PRESENCE_TIERS.values()} <= {1.0, 0.5, 0.0}


def test_durations_convert_the_books_wall_clock_exactly():
    """6E2 p.18: a Turn is 12 seconds and 12 Segments, each 1 second, so:
    1 Turn = 12, 1 Minute = 60, 5 Minutes = 300, 20 Minutes = 1200,
    1 Hour = 3600. Any other scale is a house rule wearing a citation."""
    assert PRESENCE_TIERS["impressed"].duration_segments == 12
    assert PRESENCE_TIERS["very_impressed"].duration_segments == 60
    assert PRESENCE_TIERS["awed"].duration_segments == 300
    assert PRESENCE_TIERS["cowed"].duration_segments == 1200
    assert PRESENCE_TIERS["overwhelmed"].duration_segments == 3600


def test_ranks_order_the_tiers_by_severity():
    ranks = ["impressed", "very_impressed", "awed", "cowed", "overwhelmed"]
    assert [PRESENCE_TIERS[t].rank for t in ranks] == [1, 2, 3, 4, 5]


def test_effect_for_tier_is_none_for_no_effect():
    assert effect_for_tier("no_effect") is None


# ---------------------------------------------------------------------------
# Applied / Faded on the log, folded forward — the house pattern
# ---------------------------------------------------------------------------

def test_a_landed_tier_is_recorded_and_folds_back():
    s, _ = _land(_session(), "awed")
    st = presence_state(s, "bob")
    assert st.tier == "awed"
    assert st.segments_remaining == 300
    assert st.is_active is True


def test_impressed_records_who_the_target_yields_to():
    """6E2 p.139's "the attacker may act before him" is per-attacker: the
    target yields to THAT character, not to everyone."""
    s, _ = _land(_session(), "impressed")
    assert presence_state(s, "bob").yields_to_id == "alice"


def test_awed_yields_to_nobody_it_freezes():
    s, _ = _land(_session(), "awed")
    assert presence_state(s, "bob").yields_to_id is None


def test_no_effect_records_nothing():
    s, result = _land(_session(), "no_effect")
    assert result is None
    assert presence_state(s, "bob").is_active is False
    assert not [e for e in s.event_log if e.kind == "PresenceApplied"]


def test_an_untouched_combatant_has_no_effect():
    s, _ = _land(_session(), "cowed")
    assert presence_state(s, "carl").is_active is False


def test_the_fade_event_carries_the_ABSOLUTE_remaining_not_a_delta():
    """The load-bearing property of this whole pattern. A delta would have to
    be inverted to read state backwards, and this project has already proved
    that inversion cannot be made correct."""
    s, _ = _land(_session(), "impressed")
    s = PresenceEffects.tick(s, "bob", segments=5)
    faded = [e for e in s.event_log if e.kind == "PresenceFaded"]
    assert len(faded) == 1
    assert faded[0].segments_remaining == 7          # 12 - 5, stated outright


# ---------------------------------------------------------------------------
# A weaker shout must not un-cow someone
# ---------------------------------------------------------------------------

def test_a_weaker_tier_never_downgrades_a_stronger_one():
    s, _ = _land(_session(), "cowed")
    s, applied = _land(s, "impressed", attacker="carl")
    assert applied is None
    assert presence_state(s, "bob").tier == "cowed"


def test_a_stronger_tier_replaces_a_weaker_one_and_resets_the_clock():
    s, _ = _land(_session(), "impressed")
    s, _ = _land(s, "awed", attacker="carl")
    st = presence_state(s, "bob")
    assert st.tier == "awed" and st.segments_remaining == 300


def test_an_equal_tier_refreshes_the_duration():
    """Shouting again at the same intensity renews it — the target is freshly
    cowed, not ignored."""
    s, _ = _land(_session(), "awed")
    s = PresenceEffects.tick(s, "bob", segments=295)
    assert presence_state(s, "bob").segments_remaining == 5
    s, _ = _land(s, "awed")
    assert presence_state(s, "bob").segments_remaining == 300


# ---------------------------------------------------------------------------
# Ticking down
# ---------------------------------------------------------------------------

def test_ticking_reduces_the_remaining_segments():
    s, _ = _land(_session(), "impressed")
    s = PresenceEffects.tick(s, "bob")
    assert presence_state(s, "bob").segments_remaining == 11


def test_an_effect_expires_when_its_last_segment_elapses():
    s, _ = _land(_session(), "impressed")
    s = PresenceEffects.tick(s, "bob", segments=12)
    st = presence_state(s, "bob")
    assert st.is_active is False
    assert st.tier is None


def test_ticking_past_zero_does_not_go_negative():
    s, _ = _land(_session(), "impressed")
    s = PresenceEffects.tick(s, "bob", segments=99)
    assert presence_state(s, "bob").segments_remaining == 0


def test_ticking_an_unaffected_combatant_is_a_no_op():
    s = _session()
    before = len(s.event_log)
    s = PresenceEffects.tick(s, "bob")
    assert len(s.event_log) == before


def test_tick_all_moves_everyone_at_once():
    """What a driver advancing a Segment actually calls."""
    s, _ = _land(_session(), "awed", target="bob")
    s, _ = _land(s, "impressed", target="carl")
    s = PresenceEffects.tick_all(s)
    assert presence_state(s, "bob").segments_remaining == 299
    assert presence_state(s, "carl").segments_remaining == 11


# ---------------------------------------------------------------------------
# The CV consequence reaches the existing seam
# ---------------------------------------------------------------------------

def test_awed_halves_dcv_through_the_existing_seam():
    from kirby_combat.cv_modifiers import effective_dcv_for

    s, _ = _land(_session(), "awed")
    assert effective_dcv_for(s, "bob") == 4


def test_cowed_drops_dcv_to_zero():
    """6E2 p.39's "a reduction to 0 is applied as the very last step" gets its
    second real producer — 6E2 p.9's Ranged OCV was the first."""
    from kirby_combat.cv_modifiers import effective_dcv_for

    s, _ = _land(_session(), "cowed")
    assert effective_dcv_for(s, "bob") == 0


def test_impressed_costs_no_dcv():
    from kirby_combat.cv_modifiers import effective_dcv_for

    s, _ = _land(_session(), "impressed")
    assert effective_dcv_for(s, "bob") == 8


def test_an_expired_effect_restores_dcv():
    from kirby_combat.cv_modifiers import effective_dcv_for

    s, _ = _land(_session(), "awed")
    assert effective_dcv_for(s, "bob") == 4
    s = PresenceEffects.tick(s, "bob", segments=300)
    assert effective_dcv_for(s, "bob") == 8


def test_presence_and_stunned_compose_sequentially():
    """Two halvings apply one at a time (6E1 p.14 rounds at each step),
    never as a pre-multiplied 0.25: 8 -> 4 -> 2."""
    from kirby_combat.cv_modifiers import _fold_cv_factors
    assert _fold_cv_factors(8, [0.5, 0.5]) == 2


# ---------------------------------------------------------------------------
# Acting restrictions
# ---------------------------------------------------------------------------

def test_awed_and_worse_cannot_act():
    for tier in ("awed", "cowed", "overwhelmed"):
        assert effect_for_tier(tier).no_action is True


def test_impressed_and_very_impressed_can_still_act():
    for tier in ("impressed", "very_impressed"):
        assert effect_for_tier(tier).no_action is False


def test_can_act_now_reads_live_state():
    from kirby_combat.pre_attacks.presence_effects import can_act

    s, _ = _land(_session(), "cowed")
    assert can_act(s, "bob") is False
    assert can_act(s, "carl") is True
    s = PresenceEffects.tick(s, "bob", segments=1200)
    assert can_act(s, "bob") is True
