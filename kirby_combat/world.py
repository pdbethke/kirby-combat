"""PERMANENT re-export: `World` lives in `kirby_world.world` (0.20.0).

The module object itself is aliased, so `kirby_combat.world` and
`kirby_world.world` are one module and `World` is one class.
"""
import sys

import kirby_world.world as _world

sys.modules[__name__] = _world
