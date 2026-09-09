"""Tombstone, Arizona Territory, 1881 --- as scenery.

WHAT THIS IS FOR. The showcase fight happens in a five-metre lot, and the
replay showed that lot standing alone on a patch of dirt. PeterB, with the
1881 town plat in hand: "can you render the whole town?"

SCENERY, NOT TERRAIN, and the distinction is load-bearing. Every
`Construct` in a Scene becomes an `attack_construct` target ---
`constructs_in` projects the lot, so before this the barrels and the
boarding house were things you could shoot. Putting ninety buildings in
the Scene would flood every menu in the fight and let a man take aim at a
saloon four blocks away. So the town never enters the engine's Scene at
all: the recorder merges it into the SNAPSHOT the renderer reads, and the
fight is resolved exactly as it was before.

Nothing here blocks line of sight, gives cover or can be hit, and none of
that matters for a thirty-second gunfight in a lot: the nearest thing this
module draws is across the street.

THE GRID IS THE PLAT'S, THE SCALE IS NOT. Tombstone's blocks run about
300 feet with 80-foot streets, which is a hundred times the fight --- at a
zoom that shows the lot the town is off-screen, and at a zoom that shows
the town the fight is one pixel. Blocks here are 44 metres and streets 9,
which is a deliberate compression that keeps a few blocks in frame around
the men. The ARRANGEMENT is the map's: Safford, Fremont, Allen and
Toughnut running east-west, Second through Seventh running north-south,
and the lot on the south side of Fremont between Third and Fourth.
"""
from __future__ import annotations

import random

#: The lot sits at x 0.6-5.6, y -3-4 and Fremont runs along its north
#: side. Everything here is laid out around that, so the fight's own
#: coordinates never move.
FREMONT_S, FREMONT_N = 4.0, 13.0

BLOCK = 44.0
STREET = 9.0

#: East-west streets, north to south, as (name, south edge, north edge).
EW_STREETS = [
    ("Safford Street", FREMONT_N + BLOCK, FREMONT_N + BLOCK + STREET),
    ("Fremont Street", FREMONT_S, FREMONT_N),
    ("Allen Street", FREMONT_S - BLOCK - STREET, FREMONT_S - BLOCK),
    ("Toughnut Street", FREMONT_S - 2 * (BLOCK + STREET),
     FREMONT_S - 2 * BLOCK - STREET),
]

#: North-south streets, west to east, as (name, west edge, east edge). The
#: lot is between Third and Fourth, so those two bracket it.
#: The lot's block runs from Third to Fourth, so those two bracket it and
#: everything else steps out from there by one block and one street. Laid
#: out this way rather than by absolute coordinates so the blocks are
#: actually BLOCK wide -- the first cut left an eighty-metre block between
#: Third and Fourth because both were placed by hand.
_THIRD_E = -36.0
_FOURTH_W = _THIRD_E + BLOCK


def _ns(name: str, step: int) -> tuple[str, float, float]:
    """A north-south street `step` blocks east of Third."""
    west = _THIRD_E - STREET + step * (BLOCK + STREET)
    return (name, west, west + STREET)


NS_STREETS = [
    _ns("Second Street", -1),
    _ns("Third Street", 0),
    _ns("Fourth Street", 1),
    _ns("Fifth Street", 2),
    _ns("Sixth Street", 3),
]


def ground() -> dict:
    """The desert the town sits on.

    One tile under everything, drawn FIRST so the streets and the lot paint
    over it. Without it the block interiors are holes: buildings line the
    frontages and the yards behind them were void, so the town read as a
    grid of rectangles floating in black.
    """
    west = NS_STREETS[0][1] - BLOCK * 1.5
    east = NS_STREETS[-1][2] + BLOCK * 1.5
    south = EW_STREETS[-1][1] - BLOCK * 1.5
    north = EW_STREETS[0][2] + BLOCK * 1.5
    return {"id": "desert", "name": "Tombstone", "surface_type": "ground",
            "polygon": [(west, south), (east, south), (east, north), (west, north)]}


def streets() -> list[dict]:
    """The roadway itself, as flat surfaces the renderer paints.

    Drawn as one wide band per street rather than a road network with
    junctions: at this scale the crossings look right anyway, and a
    polygon per intersection would be a lot of geometry for nothing.
    """
    out = []
    west = NS_STREETS[0][1] - BLOCK
    east = NS_STREETS[-1][2] + BLOCK
    south = EW_STREETS[-1][1] - BLOCK
    north = EW_STREETS[0][2] + BLOCK
    for name, y0, y1 in EW_STREETS:
        out.append({"id": f"st-{name}", "name": name, "surface_type": "street",
                    "polygon": [(west, y0), (east, y0), (east, y1), (west, y1)]})
    for name, x0, x1 in NS_STREETS:
        out.append({"id": f"st-{name}", "name": name, "surface_type": "street",
                    "polygon": [(x0, south), (x1, south), (x1, north), (x0, north)]})
    return out


def _storefronts(x0: float, x1: float, y0: float, y1: float, rng, *,
                 skip=()) -> list[dict]:
    """One block, cut into buildings along the street frontages.

    The plat's blocks are solid rows of narrow storefronts facing the
    street with yards behind, which is what makes the map read as a town
    rather than a set of rectangles. This walks each frontage laying down
    buildings of varying width and depth, and leaves the middle empty.
    """
    out = []
    for edge, (a0, a1) in (("s", (x0, x1)), ("n", (x0, x1))):
        cursor = a0 + rng.uniform(0.0, 3.0)
        while cursor < a1 - 4.0:
            width = rng.uniform(4.0, 11.0)
            depth = rng.uniform(7.0, 15.0)
            if cursor + width > a1:
                width = a1 - cursor
            near_y = y0 if edge == "s" else y1 - depth
            rect = (cursor, near_y, cursor + width, near_y + depth)
            if not any(_overlaps(rect, s) for s in skip):
                out.append({
                    "id": f"b{len(out)}-{edge}-{int(cursor)}-{int(y0)}",
                    "height": rng.choice([3.5, 4.0, 5.0, 6.0]),
                    "polygon": [(rect[0], rect[1]), (rect[2], rect[1]),
                                (rect[2], rect[3]), (rect[0], rect[3])],
                })
            cursor += width + rng.uniform(0.0, 1.5)
    return out


def _overlaps(rect, other) -> bool:
    ax0, ay0, ax1, ay1 = rect
    bx0, by0, bx1, by1 = other
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def buildings(seed: int = 7) -> list[dict]:
    """Every building in town, as {id, height, polygon}.

    Seeded, so the town is the same town every time it is rendered --- a
    backdrop that reshuffled between takes would be worse than none.
    """
    rng = random.Random(seed)
    #: Where the fight is. No generated building may land on the lot, the
    #: two houses that front it, or the stretch of Fremont the Earps
    #: walked in along.
    keep_clear = [(-14.0, -12.0, 20.0, 14.0)]

    out: list[dict] = []
    ns_edges = [(NS_STREETS[i][2], NS_STREETS[i + 1][1])
                for i in range(len(NS_STREETS) - 1)]
    ew_edges = [(EW_STREETS[i + 1][2], EW_STREETS[i][1])
                for i in range(len(EW_STREETS) - 1)]
    for x0, x1 in ns_edges:
        for y0, y1 in ew_edges:
            out.extend(_storefronts(x0, x1, y0, y1, rng, skip=keep_clear))
    # Unique ids across blocks.
    for i, b in enumerate(out):
        b["id"] = f"town-{i}"
    return out
