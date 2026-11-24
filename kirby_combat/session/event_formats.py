"""Per-kind event formats, and the steps that walk an old row up to today.

Two-databases spec §6, R2. Each event class declares ``FORMAT`` (a
``ClassVar[int]`` on `BaseEvent`, 1 unless the class says otherwise), and
`to_dict` stamps it on every row as ``__format__``. A version per KIND, not
one global number (Peter, 2026-11-24: "sep events"): only the kinds whose
shape changes move, and each carries its own upgrade steps.

WHEN A KIND'S SHAPE CHANGES: raise its ``FORMAT`` by one and add
``UPGRADES[(kind, old_format)]``, a function from a row in ``old_format``
to the same row in ``old_format + 1``. Never edit an existing step: rows in
storage were written against it. `tests/serialization/test_event_formats.py`
refuses a kind whose chain has a gap.

THE ONE INFERRED STAMP. Rows written by kirby-combat 0.39.x and earlier
carry no ``__format__``. They are their kind's first format, by history
rather than by default: stamping did not exist, and every kind was at its
first format then. `UNSTAMPED_ROWS_ARE_FORMAT` names that fact; nothing
else is ever inferred.
"""
from __future__ import annotations

from collections.abc import Callable

#: Rows written before stamping existed (kirby-combat <= 0.39.x).
UNSTAMPED_ROWS_ARE_FORMAT = 1

#: (kind, format) -> the step from that format to the next.
UPGRADES: dict[tuple[str, int], Callable[[dict], dict]] = {}


class UnknownEventFormat(Exception):
    """A row in a format this engine cannot read: newer than the kind's
    ``FORMAT``, or older with no upgrade step to walk it up."""


def upgrade(kind: str, row: dict, current: int) -> dict:
    """``row`` (a serialized event of ``kind``) walked up to ``current``."""
    version = row.get("__format__", UNSTAMPED_ROWS_ARE_FORMAT)
    if not isinstance(version, int) or version < 1:
        raise UnknownEventFormat(f"{kind} row has format {version!r}")
    if version > current:
        raise UnknownEventFormat(
            f"{kind} row is format {version}, newer than this engine's "
            f"{current}: read it with the engine that wrote it, or newer")
    while version < current:
        step = UPGRADES.get((kind, version))
        if step is None:
            raise UnknownEventFormat(
                f"{kind} row is format {version} and there is no upgrade "
                f"step from it (event_formats.UPGRADES)")
        row = step(row)
        version += 1
    return {**row, "__format__": current}


__all__ = ["UNSTAMPED_ROWS_ARE_FORMAT", "UPGRADES", "UnknownEventFormat", "upgrade"]
