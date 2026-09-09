"""Re-export of `kirby_combat.synthetic`.

The helper moved into the package on 2026-09-09 so a shippable example
could build a cast without Hero Designer's licensed template --- see that
module. This shim keeps the 65 test files that import
`fixtures.synthetic_hero` working unchanged.
"""
from __future__ import annotations

from kirby_combat.synthetic import *          # noqa: F401,F403
from kirby_combat.synthetic import (          # noqa: F401
    synthetic_combatant,
)
