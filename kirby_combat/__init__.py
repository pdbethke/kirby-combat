"""kirby-combat: HERO System 6E combat engine."""
from importlib.metadata import PackageNotFoundError, version as _version

try:
    #: Read from the installed distribution rather than restated here.
    #: A hardcoded literal drifts: this said "0.3.0" while pyproject said
    #: 0.3.28 and the built wheel carried 0.3.28, so anything introspecting
    #: the version got a wrong answer -- and 0.3.28 shipped to PyPI that way.
    __version__ = _version("kirby-combat")
except PackageNotFoundError:  # not installed (e.g. a source checkout on sys.path)
    __version__ = "0.0.0+unknown"

# kirby-cost is NOT optional, and this import is what makes that true at load
# time rather than in principle.
#
# Every `from kirby_cost...` in this package is function-local -- a leftover
# from when the dependency WAS optional and was imported behind try/except.
# That left a real hole: `dependencies = ["kirby-cost>=0.4.0"]` could be wrong,
# or satisfied by a version missing the modules this package calls, and nothing
# would notice until a specific combat function ran. Measured 2026-08-25: a
# wheel pinned to kirby-cost==0.3.0, which contains no `kirby_cost.engine`
# at all, installed and imported without complaint.
#
# So resolve the load-bearing modules here, eagerly. A floor that is too low
# now fails at `import kirby_combat` with a clear ImportError, which is a
# problem someone can act on, instead of surfacing mid-fight.
from kirby_cost.engine import damage as _damage  # noqa: F401,E402
from kirby_cost.engine import rolls as _rolls  # noqa: F401,E402

from kirby_combat.campaign import Campaign  # noqa: E402
from kirby_combat.encounter import Encounter  # noqa: E402
from kirby_combat.world import World  # noqa: E402

__all__ = ["Campaign", "Encounter", "World"]
