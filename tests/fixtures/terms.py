"""The terms a hand-built test fight is fought under.

The engine has no default (`kirby_combat.ending`): a fight with no
`FightTermsStated` refuses to step. Tests written before 2026-11-24 all
fought under last side standing, ended by the engine, so that is what they
state here, by name.
"""
from __future__ import annotations

from kirby_combat.ending import EndMode, FightTerms, StopKind, state_terms

LAST_SIDE_STANDING_AUTO = FightTerms(stop=StopKind.LAST_SIDE_STANDING,
                                     end_mode=EndMode.AUTO_STOP)


def terms_stated(session, terms: FightTerms = LAST_SIDE_STANDING_AUTO):
    """``session`` with its terms on the log (a started, unmoved fight)."""
    return state_terms(session, terms)
