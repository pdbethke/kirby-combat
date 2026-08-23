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
