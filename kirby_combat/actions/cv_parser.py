"""Parse HERO Designer maneuver CV grammar into combat modifiers.

Maneuver OCV/DCV arrive as raw HD strings on the loaded Maneuver object
(`.ocv` / `.dcv`): flat ("+2", "-1", "0"), not-applicable ("--", ""), or
velocity-based ("+v/5" — the modifier is velocity/divisor, used by
move-by / move-through style maneuvers). This is the §3 boundary parser
(spec 2026-06-07-martial-arts-pipeline-design.md §3).

The parser must NEVER crash combat: any unrecognized grammar resolves to a
not-applicable modifier (kind="none").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_VELOCITY_RE = re.compile(r"^([+-]?)v/(\d+)$")


@dataclass(frozen=True)
class CVMod:
    """A parsed CV modifier. `kind` is 'flat' | 'velocity' | 'none'.

    For velocity-based mods the flat `value` is 0 (the actual bonus depends on
    attacker velocity); the sign of the velocity bonus lives in `sign` so that
    "+v/5" and "-v/5" are distinguishable and value=0 stays unambiguous.
    """
    kind: str
    value: int             # the flat modifier (0 for velocity/none)
    velocity_divisor: int  # divisor for velocity-based (0 otherwise)
    sign: int = 1          # +1 / -1; only meaningful for velocity mods

    def flat(self) -> int:
        """The integer to apply when velocity is unknown (view-build time).
        Velocity-based resolves to 0 here (documented v1 simplification)."""
        return self.value

    def resolve(self, velocity_m: int = 0) -> int:
        """The integer to apply given an attacker velocity (m). Flat ignores
        velocity; velocity-based = sign * (velocity // divisor)."""
        if self.kind == "velocity" and self.velocity_divisor:
            mag = velocity_m // self.velocity_divisor
            return self.sign * mag
        return self.value


def parse_cv(s: str | None) -> CVMod:
    if s is None:
        return CVMod(kind="none", value=0, velocity_divisor=0)
    t = s.strip()
    if t == "" or t == "--":
        return CVMod(kind="none", value=0, velocity_divisor=0)
    m = _VELOCITY_RE.match(t)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        return CVMod(
            kind="velocity",
            value=0,
            velocity_divisor=int(m.group(2)),
            sign=sign,
        )
    # flat
    try:
        return CVMod(kind="flat", value=int(t), velocity_divisor=0)
    except ValueError:
        # unknown grammar → treat as not-applicable, never crash combat
        return CVMod(kind="none", value=0, velocity_divisor=0)
