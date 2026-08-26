"""Encounter -- precise time for one Scene.

6E2 p.8, "COMBAT AND NONCOMBAT TIME": "Unless it looks like there's going
to be a fight (or some other sequence you need to detail precisely, like
a car chase), you don't have to be exact about things like time or
distance." An Encounter is that precisely-timed sequence -- it exists
only while a scene needs Segment-level accounting, and it need not
contain a fight at all: a rocket countdown with zero CombatSessions is a
legitimate Encounter.

Combat begins on Segment 12 (6E2 p.20, "BEGINNING COMBAT"), which is why
``segment`` defaults to 12. A Turn is 12 Segments (6E2 p.18, "SEGMENT"),
so advancing past Segment 12 wraps to Segment 1 of the next Turn.

Post-Segment 12 Recovery (6E2 p.131: "After Segment 12 each Turn, all
characters (even Stunned ones) get a free Post-Segment 12 Recovery") is
implemented here, in `advance_segment`, on the wrap step -- the acting
order (`run_segment`, below) now puts the participants in play, so the
Recovery this docstring used to defer "until the acting-order work"
lands with it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Iterable

from kirby_combat.resolution.recovery import compute_recovery
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import RecoveryTaken, make_author_engine
from kirby_combat.session.timeline import (
    ActionIntent,
    build_acting_order_for_segment,
    build_provisional_order_for_segment,
    consume_block_priority,
    resolve_acting_order,
)
from kirby_combat.template import DEFAULT_TEMPLATE

if TYPE_CHECKING:
    from typing import Mapping

    from kirby_combat.campaign import Campaign
    from kirby_combat.models import StatBlockCombatant
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.timeline import ActingSlot
    from kirby_combat.template import CombatTemplate

#: 6E2 p.18, "SEGMENT": a Turn consists of 12 Segments.
SEGMENTS_PER_TURN = 12


def _apply_stun_end_recovery(combatant, stun_delta: int, end_delta: int):
    """Return a NEW combatant with ``stun_delta``/``end_delta`` added to its
    current STUN/END.

    Mirrors ``actions/movement/base.py``'s ``_decrement_end`` dispatch (the
    established pattern for this exact StatBlockCombatant/HeroCombatant
    split): ``StatBlockCombatant.state`` returns ``self`` -- its flat
    ``current_*`` fields ARE its state -- so ``combatant.state is
    combatant`` distinguishes it from ``HeroCombatant``, whose vitals live
    on a separate ``HeroCombatState`` dataclass. See
    ``StatBlockCombatant.state``'s docstring (models.py) for why that
    identity check, not an equality check, is load-bearing.
    """
    if combatant.state is not combatant:
        # HeroCombatant: STUN/END live on a separate `state` dataclass.
        new_state = replace(
            combatant.state,
            current_stun=combatant.state.current_stun + stun_delta,
            current_end=combatant.state.current_end + end_delta,
        )
        return replace(combatant, state=new_state)
    # StatBlockCombatant: current_stun/current_end are fields on self.
    return replace(
        combatant,
        current_stun=combatant.current_stun + stun_delta,
        current_end=combatant.current_end + end_delta,
    )


def _apply_post_12_recovery(
    session: "CombatSession", template: "CombatTemplate",
) -> "CombatSession":
    """Apply the free Post-Segment 12 Recovery (6E2 p.131) to every
    combatant in ``session``, emitting one ``RecoveryTaken`` event per
    combatant onto that same session's own event log.

    6E2 p.131, "POST-SEGMENT 12 RECOVERY": "After Segment 12 each Turn,
    all characters (even Stunned ones) get a free Post-Segment 12
    Recovery." This applies to EVERY combatant unconditionally -- no
    consciousness/status filter belongs here. `compute_recovery`'s
    "post_12" branch (kirby_combat/resolution/recovery.py) already
    applies REC unconditionally: unlike its "phase_12" branch, which
    returns ``(0, 0)`` for a KO'd (``combatant.is_ko``) combatant,
    "post_12" has no such check and falls straight through to `stun_delta
    = min(rec, max_stun - current_stun)`. So the "even Stunned ones"
    carve-out is already honored one layer down; duplicating a filter
    here would contradict the rule, not implement it. (This engine DOES
    compute a Stunned condition distinct from KO -- `resolution/
    status.py`'s `determine_status_changes`: `stun_dealt > con`,
    independent of the `stun_after <= 0` Knocked Out check; also
    `mental/mental_blast.py`'s `target_stunned` -- but neither call site
    ever persists it: nothing constructs a `StatusChanged` event or
    writes "stunned" into `HeroCombatState.statuses`. So there is no
    state-level hook to build a "Stunned-but-conscious" combatant here,
    and "even Stunned ones" is exercised here via a KO'd/0-STUN
    combatant instead.)

    Applied by mutating combatant state directly, THEN logging via
    `apply_event` -- not by routing the stat change through `apply_event`
    itself. `session/apply.py`'s dispatcher treats "RecoveryTaken" (along
    with ActionResolved/MovementResolved/StatusChanged/...) as log-only by
    design: see its comment "Recovery / status / movement: resolved at
    action time, not on apply" -- calling `apply_event` alone would append
    the event without changing anyone's STUN/END.
    `actions/movement/base.py`'s `MovementAction.resolve` establishes the
    identical two-step precedent for an END spend (mutate the combatant
    first, `apply_event` second, with the comment "apply_event won't do it
    for us").
    """
    new_combatants = dict(session.combatants)
    for combatant_id, combatant in session.combatants.items():
        stun_delta, end_delta = compute_recovery(combatant, template, "post_12")
        new_combatants[combatant_id] = _apply_stun_end_recovery(
            combatant, stun_delta, end_delta,
        )
        evt = RecoveryTaken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            combatant_id=combatant_id,
            stun_recovered=stun_delta,
            end_recovered=end_delta,
        )
        # apply_event only appends to event_log/updated_at (see the
        # log-only note above) -- it never touches `.combatants`, so
        # accumulating `new_combatants` separately and writing them onto
        # the final session below is safe and does not get overwritten.
        session = apply_event(session, evt)

    return replace(session, combatants=new_combatants)


@dataclass
class Encounter:
    """Precise time for one Scene, existing only while a sequence needs it.

    Immutable-by-convention like ``Scene``: ``advance_segment`` returns a
    NEW ``Encounter`` via ``dataclasses.replace`` rather than mutating in
    place (``Scene.place_combatant`` sets this precedent).
    """

    id: str
    turn: int = 1
    segment: int = 12  # 6E2 p.20: combat begins on Segment 12.
    #: HAZARD -- TWO INDEPENDENT CLOCKS (PARTIALLY CLOSED). `Encounter(turn,
    #: segment, current_slot_index)` duplicates `Timeline(turn, segment,
    #: current_slot_index)` (kirby_combat/session/timeline.py) field for
    #: field, and the two do not automatically advance together.
    #:
    #: WIRED (was unwired): `current_slot_index` was the first field this
    #: comment described as fixed, by `run_segment` (below) resetting both
    #: sides to `0` whenever it builds a fresh order. `turn`/`segment` are
    #: now ALSO synced by that same write: `run_segment` was found to write
    #: `acting_order`/`current_slot_index` onto a session's `Timeline`
    #: without ever touching that Timeline's own `turn`/`segment` --
    #: meaning `session/apply.py`'s Lightning Reflexes Phase-restriction
    #: guard, which matches a resolved `ActingSlot` against
    #: `session.timeline.segment`, only ever matched when the Encounter
    #: happened to be sitting on whatever segment `CombatSession.create()`
    #: hardcodes (12, 6E2 p.20's combat-start default) -- a live Critical
    #: bug this docstring's own "NEITHER is authoritative" line had
    #: (wrongly) treated as already understood and merely unfixed. Fixed:
    #: `run_segment` now also sets `segment=self.segment, turn=self.turn`
    #: on every session's `Timeline` it writes, so a session's Timeline is
    #: guaranteed to agree with the Encounter for turn/segment/
    #: current_slot_index immediately after any `run_segment` call.
    #: (Regression coverage: `tests/session/test_apply.py::
    #: test_lightning_reflexes_restriction_fires_at_a_non_segment_12_phase`.)
    #:
    #: STILL OPEN, precisely: `advance_segment` below moves ONLY the
    #: Encounter's own `turn`/`segment` (plus, on the Segment-12 wrap,
    #: applies Post-Segment 12 Recovery to combatants) -- it does not touch
    #: any session's `Timeline.turn`/`segment` at all. So between an
    #: `advance_segment` call and the NEXT `run_segment` call, a session's
    #: Timeline lags the Encounter it belongs to by however many
    #: `advance_segment` calls have happened since that last `run_segment`
    #: -- not by a fixed "one step" (measured: `run_segment@3` then three
    #: `advance_segment` calls leaves `enc.segment=6` against
    #: `tl.segment=3`, still carrying segment 3's resolved order); the
    #: two are only back in agreement once `run_segment` runs again. And
    #: `session/apply.py`'s own `SegmentAdvanced` handler remains a wholly
    #: separate path: a caller can advance a `CombatSession`'s Timeline
    #: directly (`to_turn`/`to_segment` taken verbatim off the event, no
    #: Segment-12 wrap applied) without going through any `Encounter` at
    #: all, and `run_segment`'s fix does nothing to reconcile that path
    #: with `Encounter.advance_segment`'s. Collapsing these into one clock
    #: remains later work (see this plan's sequencing note), not something
    #: this fix attempted.
    #:
    #: This is precisely why kirby-api's live clock path (`apply_event`'s
    #: `SegmentAdvanced` branch, above, is its ONLY clock path) re-inerts
    #: the Lightning Reflexes Phase-restriction guard one segment after
    #: every `run_segment` call -- see `session/apply.py`'s
    #: `_enforce_lightning_reflexes_phase_restriction` docstring, "STILL
    #: INERT, precisely" paragraph, case 2, for the measured sequence.
    current_slot_index: int = 0
    #: HAZARD -- CAN GO STALE. `Scene.encounter -> Encounter.sessions ->
    #: CombatSession.scene` is a reference cycle. `Scene` and `Encounter`
    #: are immutable-by-convention (mutation is via `dataclasses.replace`,
    #: never in place), so a `replace(scene, encounter=...)` produces a new
    #: `Scene` without touching any `CombatSession` already reachable
    #: through the OLD `encounter.sessions` -- that session's `.scene`
    #: keeps pointing at the Scene that was replaced. Nothing in this
    #: package enforces that the two ever agree; a caller that walks
    #: `encounter.sessions[i].scene` after replacing the owning Scene can
    #: read stale data. Kept (per spec: `Encounter -> CombatSession` is the
    #: named containment link) rather than deleted -- the follow-up that
    #: wires acting order through here is `run_segment`, below, in this
    #: same file; it does not touch this hazard.
    sessions: list["CombatSession"] = field(default_factory=list)
    template: "CombatTemplate | None" = None
    #: The scene-wide acting order for `self.segment`, as last built by
    #: `run_segment`. 6E2 p.18 counts DEX among the characters who have a
    #: Phase in a Segment -- it does not partition by fight -- so this is
    #: the ONE order `run_segment` resolves for the whole Encounter. Each
    #: session's `Timeline.acting_order` only ever gets the slice of this
    #: list that belongs to that session's own combatants (a session's
    #: timeline describes that fight); this field is where the scene-wide
    #: order itself is kept so it is not lost once it has been sliced up.
    #: `run_segment` copies each `ActingSlot` (`replace(slot)`) when it
    #: builds a session's slice, so this list and every session's
    #: `Timeline.acting_order` hold independent `ActingSlot` objects --
    #: mutating `has_acted` (or anything else) on one slot is NOT visible
    #: through the other, deliberately, since `ActingSlot` is an unfrozen
    #: dataclass and a cursor walking `Timeline.acting_order` marking
    #: slots acted is the expected future caller. Empty until
    #: `run_segment` is called.
    scene_acting_order: list["ActingSlot"] = field(default_factory=list)
    #: Carried Block "acts first" priority (6E2 p.60, "ACTING FIRST"):
    #: blocker_id -> attacker_id, as produced by
    #: `Block.acts_first_priority`. This is state, not a per-call
    #: argument, because the rule is explicit the benefit holds "even if
    #: [the attacker] does not attack again" -- it must survive from the
    #: successful Block until the blocker and that attacker next share a
    #: Segment, which can be more than one `run_segment` call away.
    #: `run_segment` reads this (when no explicit `acts_first=` is passed;
    #: see that method's docstring for how the two interact), forwards it
    #: into `resolve_acting_order`, and returns a NEW `Encounter` whose
    #: `acts_first` has been run through `consume_block_priority` so a
    #: priority spent this Segment is gone from the result. Defaults to an
    #: empty mapping -- this is a public shape kirby-api constructs
    #: directly, and a required field here would break every existing
    #: caller.
    acts_first: "Mapping[str, str]" = field(default_factory=dict)

    def _resolve_template(self, campaign: "Campaign | None") -> "CombatTemplate":
        """Resolve the CombatTemplate this Encounter should use right now.

        Shared by `advance_segment`, `acting_order`, and `run_segment`:
        when `campaign` is given, the template is resolved via
        `campaign.resolve_template` (encounter-level override, else the
        campaign's default); otherwise `self.template` is used if set,
        else the module-level `DEFAULT_TEMPLATE`. Pure refactor -- see
        each caller's own docstring for why this resolution order is the
        right one for that caller.
        """
        if campaign is not None:
            from kirby_combat.campaign import resolve_template

            return resolve_template(campaign, self)
        return self.template or DEFAULT_TEMPLATE

    def advance_segment(self, *, campaign: "Campaign | None" = None) -> "Encounter":
        """Return a new Encounter one Segment later.

        6E2 p.18: a Turn is 12 Segments, so advancing past Segment 12
        wraps to Segment 1 of the next Turn.

        6E2 p.131, "POST-SEGMENT 12 RECOVERY": leaving Segment 12 (i.e.
        this wrap) additionally gives every combatant in every session a
        free Recovery -- see `_apply_post_12_recovery`. It fires ONLY on
        this branch; a plain within-Turn advance (the `else` below) does
        not touch anyone's STUN/END.

        Template resolution for that Recovery mirrors `acting_order`/
        `run_segment` above: `campaign`, when given, resolves the
        Encounter's template via `resolve_template(campaign, self)`
        (campaign -> encounter override); otherwise `self.template or
        DEFAULT_TEMPLATE`. The CAMPAIGN/ENCOUNTER-resolved template is
        used deliberately, NOT any per-`CombatSession`'s own `template`
        field -- the campaign->encounter hierarchy exists so the campaign
        owns the rules, and a scene-wide Post-Segment 12 Recovery is an
        Encounter-level event, not a per-fight one. (`compute_recovery`
        currently ignores its `template` argument entirely -- see its
        docstring -- so this choice is not yet observable in any output;
        it is here so a future house-rule hook has an unambiguous,
        deliberately-chosen source to read from, rather than an accident
        of whichever template happened to be passed.)
        """
        if self.segment >= SEGMENTS_PER_TURN:
            template = self._resolve_template(campaign)

            new_sessions = [
                _apply_post_12_recovery(session, template)
                for session in self.sessions
            ]
            return replace(
                self, turn=self.turn + 1, segment=1, sessions=new_sessions,
            )
        return replace(self, segment=self.segment + 1)

    def acting_order(
        self,
        combatants: Iterable["StatBlockCombatant"],
        *,
        campaign: "Campaign | None" = None,
        roller: Callable[[], int | list[int] | tuple[int, ...]] | None = None,
    ) -> list["ActingSlot"]:
        """Build the acting order for ``self.segment``, honoring the
        resolved CombatTemplate's ``tie_rule`` (6E2 p.21).

        This is the wiring `CombatTemplate.tie_rule` never had: it plumbs
        the resolved template's tie-breaking rule into
        `build_acting_order_for_segment`, which otherwise falls back to
        its own `TieRule.INT_THEN_PRE` default.

        Template resolution: when ``campaign`` is given, the template is
        resolved via `campaign.resolve_template` (encounter-level
        override, else the campaign's default -- see that function's
        docstring). When no ``campaign`` is given, ``self.template`` is
        used if set, else the module-level `DEFAULT_TEMPLATE`
        (`TieRule.DEX_ROLL`, 6E2 p.21's default rule). This fallback lets
        an Encounter resolve acting order standalone -- a fight can exist
        before the Campaign/World hierarchy above it is populated, and
        requiring a Campaign here would make Encounter unusable on its
        own.

        `TieRule.DEX_ROLL` (6E2 p.21's default: a contested DEX Roll)
        requires a ``roller`` -- `build_acting_order_for_segment` raises
        `ValueError` if the resolved tie_rule needs one and none is
        supplied. Callers whose template resolves to `DEX_ROLL` (which
        includes the engine-wide default template) must pass a roller;
        this method does not silently substitute a rule that needs none.
        """
        template = self._resolve_template(campaign)

        return build_acting_order_for_segment(
            combatants, self.segment, tie_rule=template.tie_rule, roller=roller,
        )

    def run_segment(
        self,
        *,
        campaign: "Campaign | None" = None,
        intents: dict[str, "ActionIntent"] | None = None,
        roller: Callable[[], int | list[int] | tuple[int, ...]] | None = None,
        acts_first: "Mapping[str, str] | None" = None,
    ) -> "Encounter":
        """Resolve the acting order for ``self.segment``, scene-wide, and
        write it onto every session's timeline.

        This is the "whoever" `session/apply.py`'s Lightning Reflexes Phase
        restriction and `actions/reactive/block.py` have both been waiting
        on: nothing else in this codebase writes a resolved order onto
        `Timeline.acting_order`, which is why both of those guards have
        stood as documented no-ops.

        6E2 p.18, "SEGMENT": "Characters who can perform an Action in a
        Segment (i.e., who have a Phase in that Segment) do so in order of
        their DEX values" -- counting DEX among the characters PRESENT, not
        characters-in-your-fight. So the order below is built ONCE across
        every combatant in every one of `self.sessions`, exactly like
        `acting_order` builds one order for whatever combatants it is
        handed -- an Encounter holding two sessions produces one
        interleaved order, not two independent ones.

        The resulting scene-wide order is kept whole on
        `self.scene_acting_order` (so the ordering itself is never lost),
        while each session's own `Timeline.acting_order` receives only the
        slots for that session's own combatants -- a session's timeline
        describes that fight, not the whole scene.

        Does NOT advance the clock: this resolves the order for the
        CURRENT `self.segment`. Advancing to the next Segment/Turn is
        `advance_segment`'s job (6E2 p.18's Segment-12 wrap); composing the
        two is later work.

        `current_slot_index` finally becomes meaningful once an order
        exists to index into -- both the returned Encounter's and every
        returned session's `Timeline.current_slot_index` are reset to 0,
        since a freshly-built order has nothing yet marked as acted.

        Template resolution and the `roller`/`DEX_ROLL` requirement are
        identical to `acting_order` (see that method's docstring) -- this
        method resolves the template once, the same way, before building
        the provisional order.

        Block "acts first" priority (6E2 p.60, "ACTING FIRST"): when the
        caller passes `acts_first=`, that mapping is used for this call
        and `self.acts_first` is IGNORED -- an explicit argument OVERRIDES
        the carried field rather than merging with it. This mirrors how
        `campaign=`/`self.template` already work above (an explicit
        argument wins outright, no merge with instance state), and it
        keeps the semantics simple: a caller who passes `acts_first=`
        explicitly is asserting "this is the priority state for this
        call", not "add these on top of whatever the Encounter already
        carries" -- the two mappings could otherwise disagree about the
        same blocker_id with no defined precedence. A caller who wants to
        both use and update the carried state should read `self.acts_first`
        (merging in a new `Block.acts_first_priority` entry themselves if
        one was just recorded) and pass the merged result in; leaving
        `acts_first=None` (the default) uses `self.acts_first` as-is. Either
        way, whichever mapping was actually used is run through
        `consume_block_priority` below and becomes the returned
        Encounter's `acts_first` -- a priority spent this Segment (both
        the blocker and the named attacker had a Phase in `self.segment`)
        does not survive into the result; one that could not yet be spent
        (one or both had no Phase this Segment) is carried forward
        untouched.
        """
        template = self._resolve_template(campaign)

        intents = intents or {}

        # Scene-wide: every combatant from every session, not partitioned
        # by fight (6E2 p.18 -- see docstring above). `owner_of` remembers
        # which session each combatant_id came from so the resolved order
        # can be sliced back apart below.
        all_combatants: list["StatBlockCombatant"] = []
        owner_of: dict[str, int] = {}
        for session_index, session in enumerate(self.sessions):
            for combatant in session.combatants.values():
                all_combatants.append(combatant)
                owner_of[combatant.id] = session_index

        acts_first_used = acts_first if acts_first is not None else self.acts_first

        provisional = build_provisional_order_for_segment(all_combatants, self.segment)
        resolved = resolve_acting_order(
            provisional, intents, tie_rule=template.tie_rule, roller=roller,
            acts_first=acts_first_used,
        )
        remaining_acts_first = consume_block_priority(
            acts_first_used, all_combatants, self.segment,
        )

        new_sessions = []
        for session_index, session in enumerate(self.sessions):
            # `replace(slot)` copies each slot rather than reusing the
            # same `ActingSlot` instance kept whole on `scene_acting_order`
            # below: `ActingSlot` is an unfrozen dataclass with a mutable
            # `has_acted` field, so without this copy, a future caller
            # doing `session.timeline.acting_order[0].has_acted = True`
            # (the natural cursor operation) would silently mutate
            # `self.scene_acting_order` too, since both lists would be
            # holding the very same object. Nothing mutates slots today,
            # so this was latent, not live -- but it is the same shape as
            # shared-mutable Criticals shipped on preceding branches, so
            # it is closed here rather than left to bite a later caller.
            own_slots = [
                replace(slot) for slot in resolved
                if owner_of[slot.combatant_id] == session_index
            ]
            # Bring the session's own Timeline.segment/turn into step
            # with the Encounter's -- session/apply.py's Lightning
            # Reflexes guard matches a resolved ActingSlot against
            # `session.timeline.segment`, and `CombatSession.create()`
            # hardcodes `Timeline(turn=1, segment=12, ...)` (6E2 p.20's
            # combat-start default). Writing `acting_order` alone left
            # that guard comparing every slot's REAL segment against a
            # frozen 12: it only ever matched when `self.segment` also
            # happened to be 12 (which is why the guard's own driver test
            # passed at Encounter's default segment and nowhere else --
            # see `tests/session/test_apply.py::
            # test_lightning_reflexes_restriction_fires_at_a_non_segment_
            # 12_phase`, the regression test for exactly this). The
            # Encounter is the authoritative clock for the order it just
            # built, so a session's timeline must not be able to disagree
            # with it.
            new_timeline = replace(
                session.timeline, acting_order=own_slots, current_slot_index=0,
                segment=self.segment, turn=self.turn,
            )
            new_sessions.append(replace(session, timeline=new_timeline))

        return replace(
            self,
            sessions=new_sessions,
            scene_acting_order=resolved,
            current_slot_index=0,
            acts_first=remaining_acts_first,
        )
