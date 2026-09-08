"""When a side breaks.

Spec: `kirby/docs/superpowers/specs/2026-09-08-side-morale-design.md`.

A SIDE, NOT A MAN. HERO gives an individual no morale stat, deliberately:
PRE is the stat, and 6E2 p.140 says so in a worked example --- Howler's
"demoralized henchmen are about to run" and she fixes it with a Presence
Attack, not a morale roll. A per-character morale number would be a
second system competing with PRE.

A side is different. A side is the thing that routs, and the book has no
opinion about it because a side is not a character. So everything here is
JUDGEMENT, and the tiers are the ones `masscombat.UnitMorale` already
names --- FRESH, STEADY, SHAKEN, ROUTING, BROKEN --- rather than a sixth
vocabulary invented beside it. That enum has existed, correct and wired
to nothing, since mass combat was written.

WHY THIS EXISTS. Power Lad killed seven armed men in twenty-eight Phases
and nobody left the lot. `threat` says who to shoot, not when to stop.
Violence-as-Presence scales with the terrifier's PRE and his is 10.
`break_off_when_nothing_works` needs LANDED blows, and at OCV 5 against
DCV 6 those arrive far slower than he kills. They die faster than they
can learn. Casualties are the fast signal and nothing read them.

DERIVED, NEVER STORED, for the same reason `Roster.standing` reads a
position rather than a flag: a second copy of the truth goes stale, and
this project has already proved that folding backwards cannot be made
correct.
"""
from __future__ import annotations

from typing import Any

from kirby_combat.masscombat import UnitMorale

#: Fraction of a side down or gone, and the tier it earns. JUDGEMENTS,
#: stated as numbers so they can be argued with. Men die in fights, so one
#: loss in four is not a rout; half the side gone in two Turns is.
_CASUALTY_TIERS: tuple[tuple[float, UnitMorale], ...] = (
    (2 / 3, UnitMorale.BROKEN),
    (1 / 2, UnitMorale.ROUTING),
    (1 / 3, UnitMorale.SHAKEN),
    (0.001, UnitMorale.STEADY),
)

#: Weakest first --- the order a side falls through.
_LADDER = (UnitMorale.FRESH, UnitMorale.STEADY, UnitMorale.SHAKEN,
           UnitMorale.ROUTING, UnitMorale.BROKEN)

#: Landed blows that did nothing, pooled across the side, before the fact
#: costs a tier. Matches `break_off_when_nothing_works`: one is luck, two
#: is coincidence, three is a pattern.
FUTILITY_THRESHOLD = 3

#: Psychological complications that keep a man in a fight his side has
#: lost. OUR JUDGEMENT, and the reverse of the book's: 6E2 p.138 prices a
#: psych comp as a BONUS to an attack that plays to it. Nothing in HERO
#: says Overconfidence resists a rout --- it follows from what the
#: complication means, and it is recorded here as ours rather than
#: dressed up as RAW.
HOLDS_FAST = ("overconfidence", "overconfident")


def _is_down(combatant: Any) -> bool:
    if getattr(combatant, "is_ko", False):
        return True
    state = getattr(combatant, "state", None)
    return bool(state is not None and getattr(state, "current_body", 1) <= 0)


def _one_tier_worse(morale: UnitMorale) -> UnitMorale:
    index = _LADDER.index(morale)
    return _LADDER[min(len(_LADDER) - 1, index + 1)]


def side_morale(session: Any, members: list) -> UnitMorale:
    """How this side is holding, from what has happened to it.

    `members` is the side as it STARTED --- the down and the gone
    included --- because a side of four that has lost two is not a side
    of two that has lost nobody, and reading only the survivors would say
    exactly that.
    """
    if not members:
        return UnitMorale.FRESH

    lost = sum(1 for m in members if _is_down(m))
    fraction = lost / len(members)
    morale = UnitMorale.FRESH
    for threshold, tier in _CASUALTY_TIERS:
        if fraction >= threshold:
            morale = tier
            break

    # Losing a man is bad; losing him to something your bullets bounce off
    # is worse, and the side watched both happen. Costs a tier.
    #
    # It costs one from FRESH too, which was a deliberate second thought.
    # The first pass exempted an unhurt side on the grounds that one
    # armoured enemy is "a problem, not a crisis" -- but FRESH is not
    # neutral, it is +1 to checks, i.e. actively confident. A side that
    # has put three bullets into a man and watched him not notice is not
    # confident. STEADY, the tier with no modifier at all, is exactly "a
    # problem, not a crisis", so that is where they belong.
    if _futility_proved(session, members):
        morale = _one_tier_worse(morale)
    return morale


def _futility_proved(session: Any, members: list) -> bool:
    from kirby_combat.futility import futile_hits

    ids = tuple(getattr(m, "id", "") for m in members)
    if not ids:
        return False
    pooled = futile_hits(session, ids[0], also=ids[1:])
    return any(count >= FUTILITY_THRESHOLD for count in pooled.values())


def holds_fast(combatant: Any) -> bool:
    """Does this man stay when his side has broken?

    The side breaks; WHICH men break with it depends on who they are. A
    fighter who cannot conceive of losing is still standing there when
    everyone around him has gone --- which is the interesting half of
    morale, and the reason this is not a bar on a screen.
    """
    from kirby_combat.complications import complications_of

    for complication in complications_of(combatant):
        if complication.xmlid != "PSYCHOLOGICALLIMITATION":
            continue
        if any(word in complication.trigger_keywords for word in HOLDS_FAST):
            return True
    return False
