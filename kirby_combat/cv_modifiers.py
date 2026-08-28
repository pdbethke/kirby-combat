"""The condition -> CV-modifier seam.

**Why this file exists, and why it is not a change to ``hero_view.py``:**
Task 2 of ``conditions-must-bite`` was scoped to land in
``kirby_combat/hero_view.py`` ("or wherever CV reaches the resolvers --
say which and why"). ``HeroCombatStats``/``HeroCombatant`` (``hero_view.py``)
compute a combatant's CVs from ``hero`` + ``state`` only -- neither holds a
``CombatSession`` reference, and every condition this engine derives
(Stunned included) lives on the session's event log, read via
``statuses.py``/``statuses_for``. Threading a session into
``combat_stats()``/the ``ocv``/``dcv``/``omcv``/``dmcv`` properties would
mean giving a REQUIRED new parameter to methods called from many sites
across ``actions/`` and every resolver that reads ``attacker.dcv`` --
exactly the kind of ripple the plan's signature-discipline constraint
warns about, for a change that is additive by nature (nothing needs a
combatant's session-modified CV until an attack is being built). Instead,
this module is a new, free-standing, additive entry point: it reads a
``CombatSession`` + a combatant's *base* CV values and returns adjusted
ones. A caller building an ``AttackInput`` (kirby-api's driver today; this
engine's own examples/tests) calls this AFTER reading a combatant's base
CVs and BEFORE constructing the attack -- nothing existing changes shape,
and a combatant with no active condition round-trips unchanged (see
``test_unstunned_combatant_cv_is_unchanged`` in
``tests/test_stunned_enforcement.py``).

**The seam itself:** ``_CV_MODIFIER_SOURCES`` below is an ordered tuple of
``(session, combatant_id) -> dict[str, float]`` functions, one per
CV-affecting condition. Each source returns ``{}`` when its condition is
inactive, or a dict of ``*_factor`` keys (matching the convention already
established by ``Entangle.modifiers``/``Flash.modifiers``,
``kirby_combat/actions/entangle.py`` / ``actions/flash.py`` -- this module
extends that same shape to DMCV and the hit-location/Placed-Shot factor,
which those two don't touch) when active. ``cv_modifiers_for`` folds every
source's factors together by MULTIPLICATION, never by ``min()`` or a
hardcoded if/elif chain -- so a combatant under two conditions at once
(e.g. Stunned AND Entangled) gets both penalties compounded automatically,
and no source needs to know any other source exists.

The next spec (sense-affecting powers: Flash, Darkness, Images -- 6E2 p.9,
"a character who cannot perceive his opponent with a Targeting Sense... is
at 1/2 OCV and 1/2 DCV in the HTH Combat, or 0 OCV and 1/2 DCV at Range")
plugs in by adding ONE more entry to ``_CV_MODIFIER_SOURCES`` -- a function
with the same ``(session, combatant_id) -> dict`` shape, returning
``{"ocv_factor": ..., "dcv_factor": ...}`` (``actions/flash.py``'s
``Flash.modifiers`` already computes exactly that value today; it is
simply not yet wired into this composition, which is deliberately out of
scope for THIS task -- see that function's own docstring). Nothing in
``cv_modifiers_for``, ``CVModifiers``, or ``apply_cv_factor`` needs to
change for that to work.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from kirby_combat.tables import segments_for_spd

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


# ---------------------------------------------------------------------------
# Stunned's own CV-window derivation
# ---------------------------------------------------------------------------

def _stunned_or_recovering(session: "CombatSession", combatant_id: str) -> bool:
    """True while Stunned OR recovering from being Stunned.

    6E2 p.39 (condition modifier table) gives these as two SEPARATE rows
    with the IDENTICAL penalty: "Stunned -> DCV 1/2, hit locations 1/2"
    and "Recovering from being Stunned -> DCV 1/2, hit locations 1/2".

    ``statuses.py``'s ``_is_stunned`` already derives the narrower
    ``stunned`` status id, and — by that function's own documented
    design — clears it at the START of the combatant's recovery Phase,
    matching 6E2 p.106-107's narrative text ("he recovers from being
    Stunned when his DEX occurs in the Segment... he regains his full
    DCV"). That clear edge is right for the ``stunned`` status id. But
    p.39's penalty is a SEPARATE row that does not lift at that same
    instant -- recovering-from-being-Stunned is its own condition with
    its own matching penalty -- so a CV-modifier source that gated only
    on ``STUNNED in statuses_for(...)`` would drop the penalty one Phase
    too early. This function tracks one stage further than
    ``_is_stunned``'s fold: the same SET edge (a qualifying "Stunned" in
    an ``ActionResolved.status_changes``), but the fold does not fully
    clear until the SECOND matching ``SegmentAdvanced`` after that (the
    first enters "recovering", mirroring ``_is_stunned``'s clear; the
    second -- the combatant's NEXT full Phase after that -- is when 6E2
    p.107 says "recovering from being Stunned is all he can do that
    Phase" has run its course).

    Deliberately duplicates, rather than reuses, ``_is_stunned``'s fold:
    that function's contract and its heavily-reasoned early-clear
    tradeoff (see its own docstring) is a promise about the ``stunned``
    status id specifically, not about this wider CV-penalty window.
    Keeping the two folds separate means a future change to one cannot
    silently move the other's boundary.
    """
    combatant = session.combatants[combatant_id]
    phase_segments = segments_for_spd(combatant.combat_stats().spd)

    stage = "none"  # "none" -> "stunned" -> "recovering" -> "none"
    for evt in session.event_log:
        kind = evt.kind
        if kind == "ActionResolved":
            payload = getattr(evt, "result_payload", None) or {}
            if (
                payload.get("target_id") == combatant_id
                and "Stunned" in payload.get("status_changes", ())
            ):
                stage = "stunned"
        elif kind == "SegmentAdvanced":
            # Same "no valid Phase to wait for -> treat every SegmentAdvanced
            # as qualifying" guard `_is_stunned` uses for SPD 0 (tables.py's
            # SPEED_TO_SEGMENTS[0] == []) -- see that function's docstring.
            at_phase = not phase_segments or evt.to_segment in phase_segments
            if at_phase:
                if stage == "stunned":
                    stage = "recovering"
                elif stage == "recovering":
                    stage = "none"
    return stage in ("stunned", "recovering")


def _stunned_cv_modifiers(session: "CombatSession", combatant_id: str) -> dict[str, float]:
    """Stunned's contribution to the seam.

    6E2 p.106, "Stunning": "A Stunned character's DCV and DMCV instantly
    drop to 1/2 (as do the modifiers for making Placed Shots against
    him)." 6E2 p.39's condition table confirms both DCV and hit-location
    factors for Stunned AND for recovering from being Stunned (see
    ``_stunned_or_recovering`` above for why both are covered by one
    check). DMCV is named explicitly in the p.106 quote but is not a row
    of its own on p.39's table (that table predates this engine's DMCV
    field); this module treats it identically to DCV since the p.106
    text gives it the identical "drop to 1/2".
    """
    if not _stunned_or_recovering(session, combatant_id):
        return {}
    return {"dcv_factor": 0.5, "dmcv_factor": 0.5, "hit_location_factor": 0.5}


#: Ordered sources folded into ``cv_modifiers_for``. THIS tuple is the
#: seam: add one more ``(session, combatant_id) -> dict`` entry here for a
#: new CV-affecting condition (see the module docstring's sense-affecting-
#: powers example). Nothing else in this module needs to change.
_CV_MODIFIER_SOURCES: tuple[
    Callable[["CombatSession", str], dict[str, float]], ...
] = (
    _stunned_cv_modifiers,
)


@dataclass(frozen=True)
class CVModifiers:
    """Composed multiplicative CV factors from every active condition.

    1.0 = no effect on that CV. Multiple simultaneously-active conditions
    COMPOSE by multiplication (e.g. Stunned x a hypothetical 0.5-DCV
    condition would be 0.5 * 0.5 = 0.25 DCV), never by ``min()`` or an
    override -- so no condition's contribution needs to know any other
    condition exists.
    """

    ocv_factor: float = 1.0
    dcv_factor: float = 1.0
    omcv_factor: float = 1.0
    dmcv_factor: float = 1.0
    #: Applies to the OCV penalty an ATTACKER suffers for a Placed Shot
    #: against this combatant (6E2 p.106: "as do the modifiers for making
    #: Placed Shots against him") -- not one of this combatant's own CVs.
    hit_location_factor: float = 1.0


def cv_modifiers_for(session: "CombatSession", combatant_id: str) -> CVModifiers:
    """The seam's public entry point: fold every active condition's CV
    contribution into one composed ``CVModifiers``.

    Returns the all-1.0 default for a combatant with no active
    CV-affecting condition, so a caller that always applies this (even to
    a combatant it hasn't checked for conditions) gets today's behaviour
    back unchanged.
    """
    factors = {
        "ocv_factor": 1.0, "dcv_factor": 1.0, "omcv_factor": 1.0,
        "dmcv_factor": 1.0, "hit_location_factor": 1.0,
    }
    for source in _CV_MODIFIER_SOURCES:
        for key, value in source(session, combatant_id).items():
            factors[key] *= value
    return CVModifiers(**factors)


def apply_cv_factor(base: int, factor: float) -> int:
    """Apply one ``CVModifiers`` factor to a base int CV/penalty value.

    **Rounding is a rules call, not a preference (see this task's brief).**
    Neither 6E2 p.106 ("Stunning") nor p.39 (the condition modifier table)
    states a rounding direction for a halved CV, and nothing elsewhere in
    this codebase applies one either -- ``Entangle.modifiers`` /
    ``Flash.modifiers`` / ``dive_for_cover.py``'s ``diver_dcv_factor`` all
    stop at returning the raw multiplicative factor; none of them multiply
    it into an int CV anywhere in this engine today (checked via grep --
    no call site consumes them). This function is therefore the first
    place that decision has to be made, and it is made explicitly here
    rather than left to fall out of whatever Python's ``round()`` happens
    to do (which is banker's rounding -- round-half-to-even -- and would
    silently vary by parity):

    **Choice: round the result UP (``math.ceil``), citing 6E1 p.14's
    general HERO fractional-rounding rule** -- "always round off to the
    next whole number in favor of the Player Character... .5 rounds up or
    down [whichever is more beneficial]." That rule is written for
    Character Point/cost calculations, not combat CVs, so this is an
    extrapolation of its PRINCIPLE (round ambiguous fractions toward
    whichever side benefits a character), not a direct citation of a CV
    rounding rule -- stated explicitly rather than silently assumed, per
    this task's brief. For DCV/DMCV/OCV, a higher value benefits the
    combatant possessing it, so halves round up. For the hit-location
    factor (an OCV PENALTY against the target, always <= 0), the same
    ``math.ceil`` reduces the penalty's magnitude (e.g. -5 * 0.5 = -2.5 ->
    ceil -> -2, not -3) -- a smaller penalty benefits whoever is making
    the Placed Shot. One formula, applied uniformly regardless of which
    side of the roll benefits, rather than picking a beneficiary per call
    site.
    """
    if factor == 1.0:
        return base
    return math.ceil(base * factor)


def effective_dcv_for(session: "CombatSession", combatant_id: str) -> int:
    """This combatant's DCV as modified by every active condition."""
    combatant = session.combatants[combatant_id]
    mods = cv_modifiers_for(session, combatant_id)
    return apply_cv_factor(combatant.combat_stats().dcv, mods.dcv_factor)


def effective_dmcv_for(session: "CombatSession", combatant_id: str) -> int:
    """This combatant's DMCV as modified by every active condition."""
    combatant = session.combatants[combatant_id]
    mods = cv_modifiers_for(session, combatant_id)
    return apply_cv_factor(combatant.combat_stats().dmcv, mods.dmcv_factor)


def effective_ocv_for(session: "CombatSession", combatant_id: str) -> int:
    """This combatant's OCV as modified by every active condition.

    No source in ``_CV_MODIFIER_SOURCES`` currently sets ``ocv_factor``
    (Stunned does not touch OCV per 6E2 p.106/p.39 -- only DCV/DMCV/hit
    locations), so this returns the base OCV unchanged today. Provided
    for symmetry and because the sense-affecting-powers spec's condition
    (6E2 p.9) DOES set ``ocv_factor``, at which point this starts
    reflecting it with no change to this function itself.
    """
    combatant = session.combatants[combatant_id]
    mods = cv_modifiers_for(session, combatant_id)
    return apply_cv_factor(combatant.combat_stats().ocv, mods.ocv_factor)
