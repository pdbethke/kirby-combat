"""Pushing — exceeding a characteristic's normal limit for one Phase (6E2 p135).

A character can spend extra END to exceed a STR or Power's normal points for
a single Phase, at the cost of extra fatigue. The rulebook caps how much a
character may Push in a given campaign (Heroic: up to 5 points, gated by an
EGO Roll; Superheroic: up to 10 points, no roll needed, with the GM free to
allow more for extraordinary circumstances) and caps how far any one Power's
Active Points can be stretched (never more than doubled). Both caps are a
GM/session-level judgment call, not a number this module can enforce in
isolation, so they are left to the caller.

This module supplies only what is unconditionally true of Pushing itself:
the END price. Every Character Point Pushed costs one additional END, on top
of whatever the ability already costs to use.

The Push itself is expressed the same way every other characteristic
adjustment is: a `Contribution` — an unconditional, this-Phase-only delta
declared against a characteristic. Nothing about "lasts one Phase" needed a
new field on `Contribution`; it is simply a contribution the caller adds when
the Push is declared and drops at the end of the Phase, the same lifecycle
any transient contribution would have. That the interface needed nothing
more than this is the point of building Pushing first.
"""
from __future__ import annotations

from kirby_cost.model.activation import Contribution

#: END spent per Character Point Pushed (6E2 p135).
PUSH_END_PER_POINT = 1


def push_contribution(xmlid: str, points: int) -> Contribution:
    """A Contribution describing a Push of ``points`` onto ``xmlid``.

    Unconditional (``requires_hero_id=False``): Pushing is something the
    character does in the moment, not a purchase that can be limited to one
    of their identities.
    """
    return Contribution(
        xmlid=xmlid,
        delta=float(points),
        source_label="Pushed",
    )
