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
    on ``STUNNED in statuses_for(...)`` would drop the penalty too early.
    The exact width of that extension -- one Segment (the recovery
    Segment itself), NOT one full Phase -- is derived and grounded in
    ``statuses.py::stunned_or_recovering_for``'s own docstring (see its
    CORRECTED WINDOW section, including the residual approximation it
    documents); this function does not re-derive it.

    As of Task 3 (``conditions-must-bite``), this is a thin wrapper over
    ``statuses.py::stunned_or_recovering_for`` -- the SAME wider window is
    also the one 6E2 p.106's "can take no Actions... cannot move... [is]
    unaffected by Presence Attacks" sentence names, so Task 3's action
    denials (``actions/reactive/abort.py``, ``scene/movement_legality.py``,
    ``pre_attacks/presence.py``) need the identical fold. Kept as its own
    named function here (rather than calling ``statuses_for`` directly at
    each CV-modifier call site) so this module's own contract -- "how
    Stunned contributes to the CV seam" -- stays readable as one
    self-contained unit; the fold itself now lives in exactly one place.
    """
    from kirby_combat.statuses import stunned_or_recovering_for

    return stunned_or_recovering_for(session, combatant_id)


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


def _sense_penalty_cv_modifiers(
    session: "CombatSession", combatant_id: str, opponent_id: str,
    combat_type: str,
) -> dict[str, float]:
    """The inability-to-sense contribution to the seam (6E2 p.9).

    Thin delegation to ``kirby_combat.sense_penalties``, which owns the
    rule, the Targeting/Nontargeting distinction, and the Nontargeting
    PER Roll that mitigates it. Kept as a named function here so this
    module's seam still reads as a list of conditions.
    """
    from kirby_combat.sense_penalties import sense_penalty_modifiers

    return sense_penalty_modifiers(session, combatant_id, opponent_id, combat_type)


#: Ordered sources folded into ``cv_modifiers_for``. THIS tuple is the
#: seam: add one more ``(session, combatant_id) -> dict`` entry here for a
#: new CV-affecting condition (see the module docstring's sense-affecting-
#: powers example). Nothing else in this module needs to change.
_CV_MODIFIER_SOURCES: tuple[
    Callable[["CombatSession", str], dict[str, float]], ...
] = (
    _stunned_cv_modifiers,
)


# ---------------------------------------------------------------------------
# The per-opponent seam (6E2 p.9)
# ---------------------------------------------------------------------------
#
# **Why a SECOND tuple rather than widening the first.** The module
# docstring above predicted that sense-affecting powers would "plug in by
# adding ONE more entry to ``_CV_MODIFIER_SOURCES``... Nothing in
# ``cv_modifiers_for``, ``CVModifiers``, or ``apply_cv_factor`` needs to
# change for that to work." **That prediction was wrong, and the reason it
# was wrong is the whole shape of this section**, so it is corrected here
# rather than quietly worked around: 6E2 p.9's Orion example has one
# combatant at DIFFERENT CVs against DIFFERENT opponents in the same
# Segment (-1 DCV against Durak, 1/2 DCV against everyone else), and it
# expresses the mitigated case as a FLAT -1, which ``apply_cv_factor``
# refuses by design. A ``(session, combatant_id) -> factors`` source can
# express neither. So the existing seam is kept exactly as it is -- every
# opponent-independent condition (Stunned, and whatever follows it) still
# goes there and nothing about it changed -- and per-opponent conditions
# get their own tuple with the two extra pieces of context they need.
#
# Sources here return the same ``*_factor`` keys plus, optionally,
# ``*_delta`` keys for a flat modifier the book states as an integer.
_PER_OPPONENT_CV_MODIFIER_SOURCES: tuple[
    Callable[["CombatSession", str, str, str], dict[str, float]], ...
] = (
    _sense_penalty_cv_modifiers,
)


@dataclass(frozen=True)
class CVModifiers:
    """A SUMMARY of composed CV factors from every active condition --
    see ``cv_modifiers_for``'s docstring for what this is (and is not)
    safe to use for.

    1.0 = no effect on that CV. Reported here as the plain product of
    every active source's factor -- e.g. Stunned x a hypothetical
    0.5-DCV condition would report ``dcv_factor=0.25`` -- never by
    ``min()`` or an override, so no condition's contribution needs to
    know any other condition exists. This product is a fine thing to
    compare against 1.0/0.5 ("is anything affecting this CV, and is it
    exactly one halving") but is NOT the value ``effective_dcv_for`` and
    friends actually compute a multi-condition result from -- 6E2 p.39
    only grounds a single halving's arithmetic (see
    ``apply_cv_factor``), so those functions apply each source's own
    factor to the running value in turn (``_fold_cv_factors``) rather
    than using this pre-multiplied summary.
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
    """The seam's public entry point: a SUMMARY of every active
    condition's CV contribution, as one composed ``CVModifiers``.

    Returns the all-1.0 default for a combatant with no active
    CV-affecting condition, so a caller that always applies this (even to
    a combatant it hasn't checked for conditions) gets today's behaviour
    back unchanged.

    **This composed value is informational, not a computation recipe.**
    Its fields are the plain product of every active source's factor for
    that CV (e.g. two independent 0.5-DCV conditions active at once would
    report ``dcv_factor=0.25``) -- useful for a caller asking "is
    anything at all affecting this combatant's DCV right now", which is
    all today's tests need (only one source, Stunned, is wired into
    ``_CV_MODIFIER_SOURCES``, so no field here is ever anything but 1.0
    or 0.5 in practice yet). It must NOT be fed into ``apply_cv_factor``
    when more than one source could be simultaneously active: 6E2 p.39
    only grounds a SINGLE halving's arithmetic (and its negative-CV
    variant), not a composed fraction like 0.25 -- see
    ``apply_cv_factor``'s docstring for why, and ``_fold_cv_factors``
    below (used by ``effective_dcv_for``/``effective_dmcv_for``/
    ``effective_ocv_for``) for how this module actually computes a
    multi-condition result: by applying each source's own grounded factor
    to the running value in turn, never by pre-multiplying them.
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
    """Apply ONE condition's CV factor to a base int CV/penalty value.

    **Grounded by 6E2 p.39's halving clause, quoted in full because the
    sign-dependent arithmetic is easy to get backwards (and this module
    shipped that exact bug once -- see git history on this docstring):**

    > "If a character already has a negative OCV and suffers a further
    > penalty that would halve his OCV, halve the negative OCV and apply
    > that half amount to reduce the OCV further; normal rounding rules
    > apply. For example, if a character has OCV -4, halving reduces it
    > to -6 (-4 plus half of -4, or -2). If he has OCV -3, halving
    > reduces it to -4."

    So halving a POSITIVE (or zero) CV shrinks it toward zero as expected
    (``ceil(base * 0.5)``: 8 -> 4, 5 -> ceil(2.5) -> 3), but halving a
    NEGATIVE CV makes it WORSE -- computed as ``cv + cv/2`` (i.e.
    ``cv * 1.5``), per the page's own worked examples: -4 -> ceil(-6.0) =
    -6 (exact); -3 -> ceil(-4.5) = -4. Both are pinned as tests in
    ``tests/test_stunned_enforcement.py``
    (``test_apply_cv_factor_matches_6e2_p39_negative_worked_examples``).
    "Normal rounding rules apply" is 6E2 p.39 invoking 6E1 p.14's general
    HERO rounding rule BY NAME ("always round off to the next whole
    number in favor of the... character... .5 rounds up or down
    [whichever is more beneficial]"). **This IS an extrapolation, not a
    direct citation, and an earlier version of this docstring was right
    to call it one -- a later revision overstated it and that overstatement
    is corrected here.** 6E1 p.14's actual text is scoped to Character
    Point arithmetic ("When you calculate the cost of something using
    division or multiplication, always round off... in favor of the
    Player Character") -- it is not a general-purpose combat-math rule,
    and it names the PLAYER CHARACTER specifically, not "the character"
    generically (see ``apply_hit_location_factor`` below for where that
    distinction actually bites). 6E2 p.39 borrows the ROUNDING
    DIRECTION ("round toward whoever benefits") for a combat-CV context
    p.14 was never written for; applying it here is defensible -- 6E2
    p.39 itself invokes "normal rounding rules" by name, so SOME external
    rounding rule has to fill that gap, and p.14 is the only one HERO 6E
    defines -- but it is extrapolation, and this docstring says so rather
    than dressing it up as a direct hit.

    **This function is for a combatant's own CV (OCV/DCV/OMCV/DMCV)
    only.** The hit-location/Placed-Shot factor is deliberately NOT
    routed through here -- see ``apply_hit_location_factor`` below for
    why p.39's sign-aware stacking rule does not apply to it.

    **Grounded only for factor 1.0 (no-op), 0.5 (halving, both branches
    above), and 0.0 (a condition that overrides a CV to 0 outright, e.g.
    6E2 p.9's Ranged unperceived-opponent OCV -- not produced by any
    source wired into this engine today, but planned for the
    sense-affecting-powers spec).** Nothing in this engine calls this
    function with any other factor -- ``_stunned_cv_modifiers`` only ever
    emits 0.5, and multi-condition composition goes through
    ``_fold_cv_factors`` below, which applies EACH source's own 0.5/0.0
    through this function rather than pre-multiplying them into an
    ungrounded fraction. Any other factor has no page to ground its
    negative-CV arithmetic in yet, so rather than silently inventing one
    (this task's explicit brief), this function refuses it outright.
    """
    if factor == 1.0:
        return base
    if factor == 0.0:
        return 0
    if factor != 0.5:
        raise ValueError(
            f"apply_cv_factor: factor {factor!r} is not grounded in 6E2 "
            "p.39 (only 1.0, 0.5, and 0.0 are -- see this function's "
            "docstring); refusing to invent an arithmetic rule the book "
            "doesn't give."
        )
    if base < 0:
        # 6E2 p.39: halving a negative CV makes it WORSE (cv + cv/2).
        return math.ceil(base * 1.5)
    return math.ceil(base * 0.5)


def apply_hit_location_factor(base_penalty: int, factor: float) -> int:
    """Apply a hit-location/Placed-Shot factor to a base OCV penalty.

    **Deliberately separate from ``apply_cv_factor``, not a shared code
    path.** 6E2 p.39's sign-aware halving clause ("a further penalty that
    would halve his OCV... halve the negative OCV and apply that half
    amount to reduce the OCV further") describes STACKING a new penalty
    ON TOP OF a combatant's own already-penalized OCV -- a "penalty on a
    penalty" scenario where the compounding effect is meant to make
    things worse. The hit-location factor is a different thing: 6E2 p.106
    states its own, unambiguous direction in the same sentence that sets
    up DCV/DMCV halving -- "the modifiers for making Placed Shots against
    him" (a Stunned target) "drop to half" -- i.e. the table constant
    itself (``tables.py::HIT_LOCATIONS[...]["ocvMod"]``, e.g. Head's -8)
    is HALVED IN MAGNITUDE, unconditionally making it a smaller penalty,
    because a Stunned target is explicitly easier to aim at. There is no
    "already negative and now suffers a further penalty" framing here --
    the base value already IS the full penalty, and the whole point of
    the rule is to shrink it. Running it through ``apply_cv_factor``'s
    sign-aware formula would do the opposite of what p.106 says (e.g.
    -8 -> -12, a WORSE penalty against a Stunned target than an unstunned
    one) -- confirmed as a real bug caught during review of this module
    and fixed by giving this its own function rather than reusing
    ``apply_cv_factor``.

    Formula: ``math.ceil(base_penalty * factor)`` unconditionally (no
    sign branch). For a negative base, ``math.ceil`` rounds toward zero
    (less negative), which always shrinks the penalty's magnitude --
    consistent with 6E2 p.106's own stated direction ("drop to half",
    a smaller penalty), not derived from 6E1 p.14. **p.14 does NOT
    ground this rounding choice the way an earlier version of this
    docstring claimed:** p.14 is a Character-Point cost rule that rounds
    in favor of the PLAYER CHARACTER specifically ("always round off...
    in favor of the Player Character"), and this function's caller is
    whichever combatant is making the Placed Shot -- against a Stunned
    target, that is routinely an NPC attacking a PC, the OPPOSITE of
    p.14's stated beneficiary. Rounding toward zero here is grounded
    directly in 6E2 p.106's own "drop to half" language (a smaller
    penalty is what "half" of a penalty means, regardless of who is
    rolling), not smuggled in as an extension of p.14's PC-favoring
    rule to whichever side happens to attack: -8 * 0.5 = -4.0 -> -4
    (exact); an odd penalty like -5 * 0.5 = -2.5 -> ceil -> -2 (smaller
    penalty, not -3).

    Same grounded-factor restriction as ``apply_cv_factor`` (1.0, 0.5, or
    0.0 only) -- refuses anything else rather than inventing arithmetic
    for it.
    """
    if factor == 1.0:
        return base_penalty
    if factor == 0.0:
        return 0
    if factor != 0.5:
        raise ValueError(
            f"apply_hit_location_factor: factor {factor!r} is not "
            "grounded in 6E2 p.106 (only 1.0, 0.5, and 0.0 are -- see "
            "this function's docstring)."
        )
    return math.ceil(base_penalty * factor)


def _fold_cv_factors(base: int, factors: list[float]) -> int:
    """Apply a combatant's list of per-condition CV factors to a base CV,
    for when more than one condition may be simultaneously active.

    Two rules from 6E2 p.39, both handled explicitly rather than left to
    fall out of ``cv_modifiers_for``'s pre-multiplied summary:

    1. **Multiple halvings compose SEQUENTIALLY, not by multiplying their
       factors together first.** 0.5 * 0.5 = 0.25 is not one of p.39's
       grounded cases (see ``apply_cv_factor``). **An earlier version of
       this docstring justified that with a false mathematical claim --
       that pre-multiplying diverges from sequential application "once
       the running value crosses zero partway through" -- and that
       justification is wrong, not just imprecise:**
       ``apply_cv_factor`` can never change its input's sign in the
       first place (positives use ``ceil(b * 0.5)``, which stays >= 0;
       negatives use ``ceil(b * 1.5)``, which stays negative), so there
       is no zero-crossing case for sequential application to diverge
       at, ever (checked exhaustively for every integer base in
       [-40, 40]). The REAL reason sequential and pre-multiplied answers
       differ: on positive/zero bases the two ARE identical
       (``ceil(ceil(x / 2) / 2) == ceil(x / 4)`` for every non-negative
       integer x -- halving twice and quartering once round to the same
       place), but on negative bases they are NOT (1.5 * 1.5 = 2.25, not
       0.5 * 0.5's reciprocal-consistent 1.25 -- the sign-dependent
       formula does not compose multiplicatively the way the positive
       branch's does). That is a real, grounded reason on its own and
       does not need an invented zero-crossing story. The rule that
       settles which composition is correct is 6E1 p.14: "If a
       calculation involves two or more separate parts or stages, round
       at each separate step of the calculation" -- each halving is its
       own stage, so each is rounded (via ``apply_cv_factor``) before
       the next is applied, exactly what this function does. This
       function instead applies each 0.5 (or 1.0 no-op) one at a time,
       via ``apply_cv_factor``, to the RUNNING value: "halve it, then
       halve the result again" -- which is literally p.39's own phrasing
       for a second halving ("a further penalty that would halve
       his OCV").
    2. **A 0.0 factor wins and is applied LAST**, regardless of where it
       appears in ``factors``: 6E2 p.39, "A reduction of OCV or DCV to 0
       should generally be considered as 'reducing CV by a percentage,'
       and thus be applied as the very last step in the OCV or DCV
       calculation." Mathematically, 0 times anything is 0 regardless of
       order, so this only matters for how a 0.0 condition interacts with
       modifiers OUTSIDE this module (situational/maneuver/CSL bonuses,
       which this engine's resolvers -- ``resolution/to_hit.py`` -- add
       AFTER the value this function returns, e.g. ``effective_dcv =
       base_dcv + attack.dcv_modifier``). Because this function's output
       feeds INTO that later additive step rather than the other way
       round, "0 applied last" is already the resulting order for a
       caller using this seam correctly -- this branch exists so a 0.0
       source's contribution is never accidentally averaged into a
       sequence of halvings instead of overriding them.

    No source wired into ``_CV_MODIFIER_SOURCES`` produces 0.0 today
    (Stunned only ever emits 0.5), so branch 2 is not exercised by any
    test yet -- it exists so 6E2 p.9's 0.0 OCV (Ranged, unperceived
    opponent) composes correctly the day the sense-affecting-powers spec
    wires it in, with no change to this function.
    """
    if any(f == 0.0 for f in factors):
        return 0
    value = base
    for f in factors:
        value = apply_cv_factor(value, f)
    return value


def apply_cv_delta(base: int, delta: int) -> int:
    """Apply a FLAT CV modifier — plain integer addition, no rounding.

    Separate from ``apply_cv_factor`` because it is a different kind of
    thing, and the difference is exactly what 6E2 p.9's Orion example
    turns on. Orion, blinded but hearing Durak, is "-1 DCV... in HTH
    Combat" against him: an 8 DCV becomes 7. Routing that through
    ``apply_cv_factor`` would mean inventing a factor (0.875 for THIS
    combatant, something else for the next), which that function refuses
    outright and rightly so -- the book states a modifier, not a
    proportion, and a proportion would give a different answer for every
    starting DCV.

    No rounding rule is invoked because none is needed: both operands are
    integers. No sign branch either -- 6E2 p.39's sign-aware clause is
    scoped to a penalty "that would HALVE his OCV", which this is not.
    """
    return base + int(delta)


def _factors_for(session: "CombatSession", combatant_id: str, key: str) -> list[float]:
    """The raw, per-source list of factors for one CV -- e.g.
    ``key="dcv_factor"`` returns one entry per source in
    ``_CV_MODIFIER_SOURCES`` that touches DCV. Feeds ``_fold_cv_factors``;
    kept separate from ``cv_modifiers_for`` because that function
    deliberately returns a pre-multiplied SUMMARY (see its docstring),
    which is the wrong shape for ``_fold_cv_factors``'s sequential
    application.
    """
    return [
        source(session, combatant_id).get(key, 1.0)
        for source in _CV_MODIFIER_SOURCES
    ]


def _per_opponent_modifiers(
    session: "CombatSession", combatant_id: str, against: str | None,
    combat_type: str,
) -> list[dict[str, float]]:
    """Every per-opponent source's dict, or ``[]`` when no opponent is named.

    Naming no opponent is the honest answer for a caller asking "what is
    this combatant's DCV" in the abstract: 6E2 p.9's penalties do not
    HAVE an opponent-independent value (Orion is simultaneously 4 DCV and
    7 DCV), so returning nothing is better than picking one arbitrarily.
    It is also what keeps every pre-existing call site unchanged.
    """
    if against is None:
        return []
    return [
        source(session, combatant_id, against, combat_type)
        for source in _PER_OPPONENT_CV_MODIFIER_SOURCES
    ]


def _effective_cv(
    session: "CombatSession", combatant_id: str, key: str, base: int,
    against: str | None, combat_type: str,
) -> int:
    """Fold both seams onto one base CV.

    Order: every factor (sequentially, via ``_fold_cv_factors``), then
    every flat delta. Factors first because 6E2 p.9's own mitigated row
    reads that way -- the -1 is stated as the character's resulting DCV
    against that opponent, not as something applied before a halving --
    and because the only source producing a delta today never produces a
    halving on the same CV in the same breath (the table in
    ``sense_penalties`` emits ``dcv_factor`` or ``dcv_delta``, never
    both), so the two orders cannot currently disagree. Stated explicitly
    anyway: the day a second delta source lands, the ordering is already
    decided and written down rather than being whatever fell out.

    A 0.0 factor still wins outright (6E2 p.39, "applied as the very last
    step"), so a delta cannot pull a zeroed OCV back above zero.
    """
    factor_key = f"{key}_factor"
    delta_key = f"{key}_delta"
    per_opponent = _per_opponent_modifiers(session, combatant_id, against, combat_type)

    factors = _factors_for(session, combatant_id, factor_key)
    factors += [m.get(factor_key, 1.0) for m in per_opponent]
    if any(f == 0.0 for f in factors):
        return 0

    value = _fold_cv_factors(base, factors)
    for m in per_opponent:
        if delta_key in m:
            value = apply_cv_delta(value, int(m[delta_key]))
    return value


def effective_dcv_for(
    session: "CombatSession", combatant_id: str, *,
    against: str | None = None, combat_type: str = "hth",
) -> int:
    """This combatant's DCV as modified by every active condition.

    ``against`` names the opponent this DCV is being read against, and
    ``combat_type`` (``"hth"`` / ``"ranged"``) the kind of combat between
    them. Both are optional and default to today's behaviour: without
    ``against``, only the opponent-independent conditions (Stunned, &c.)
    are folded, so every pre-existing call site returns exactly what it
    did before. With it, 6E2 p.9's inability-to-sense penalties apply --
    and they genuinely differ per opponent, which is why they cannot be
    folded without one.
    """
    combatant = session.combatants[combatant_id]
    return _effective_cv(session, combatant_id, "dcv",
                         combatant.combat_stats().dcv, against, combat_type)


def effective_dmcv_for(
    session: "CombatSession", combatant_id: str, *,
    against: str | None = None, combat_type: str = "hth",
) -> int:
    """This combatant's DMCV as modified by every active condition.

    No per-opponent source touches DMCV today: 6E2 p.9's penalties are
    stated for OCV and DCV, and this module does not extend them to the
    mental CVs on its own authority (Stunned's DMCV halving is written
    down on p.106 in as many words; nothing comparable is written for the
    inability to sense).
    """
    combatant = session.combatants[combatant_id]
    return _effective_cv(session, combatant_id, "dmcv",
                         combatant.combat_stats().dmcv, against, combat_type)


def effective_ocv_for(
    session: "CombatSession", combatant_id: str, *,
    against: str | None = None, combat_type: str = "hth",
) -> int:
    """This combatant's OCV as modified by every active condition.

    No source in ``_CV_MODIFIER_SOURCES`` sets ``ocv_factor`` (Stunned
    does not touch OCV per 6E2 p.106/p.39 -- only DCV/DMCV/hit
    locations), so without ``against`` this still returns the base OCV.
    The per-opponent seam does set it: 6E2 p.9's 1/2 OCV in HTH and **0
    OCV at Range** against an opponent the combatant cannot perceive with
    a Targeting Sense -- the engine's first producer of the 0.0 factor
    that ``_fold_cv_factors``'s "applied last" branch was written for.
    """
    combatant = session.combatants[combatant_id]
    return _effective_cv(session, combatant_id, "ocv",
                         combatant.combat_stats().ocv, against, combat_type)
