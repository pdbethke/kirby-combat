"""A whiskey barrel is a thing you can pick up and throw.

`pickup` and `throw_object` are two complete action kinds that have
**never fired in any benchmark** --- offered zero times across every
western run. `Construct.portable` carries the scar of the first attempt:

    "PORTABLE IS A PROPERTY OF THE OBJECT, not a kind of object.
     `pickup` used to filter on `kind == "debris"` --- a kind that is not
     in `ConstructKind` and that nothing in this engine has ever created,
     so `pickup` and `throw_object` were two complete action kinds that
     could never fire."

That fix removed the wrong filter and the kinds still never fired,
because the chain has a second break one layer down: **nothing a scene
can author is ever portable.** `Furnishing` had no such field, `Wall` has
none, and `constructs_in` projects a furnishing to a `Construct` without
one --- so every barrel, crate and wagon took the dataclass default of
False. The only portable construct possible was one hand-authored as a
bare `Construct`, which no scene does.

A water barrel at BODY 4 is ~200 kg by the engine's own
`_DEBRIS_KG_PER_BODY`, which a STR 15 man lifts exactly (25 x 2^(STR/5)).
So the weight gate is the interesting part of this offer and it only
becomes reachable once portability can be declared at all.
"""
from __future__ import annotations

from kirby_combat.scene.construct import constructs_in
from kirby_combat.scene.scene import Furnishing


def _scene(*, portable: bool):
    from kirby_combat.scene.scene import (
        AmbientConditions, Scene, SceneBounds, Surface,
    )

    return Scene(
        id="lot", name="The lot",
        bounds=SceneBounds(0, 0, 0, 30, 30, 10),
        surfaces=[Surface(id="ground", name="Ground",
                          polygon_xy=[(0, 0), (30, 0), (30, 30), (0, 30)],
                          elevation_m=0.0, surface_type="ground",
                          cover_level=0, is_supporting=True)],
        walls=[], hazards=[], ambient=AmbientConditions(),
        furnishings=[Furnishing(
            id="barrels", name="Water barrels",
            polygon_xy=[(10, 10), (11, 10), (11, 11), (10, 11)],
            height_m=1.2, material="wooden wall", body=4, cover_level=2,
            portable=portable,
        )],
    )


def test_a_furnishing_can_declare_itself_portable():
    """The field has to exist on the thing a scene actually authors."""
    assert Furnishing(
        id="b", name="Barrel", polygon_xy=[(0, 0), (1, 0), (1, 1)],
        height_m=1.0, material="wooden wall", body=4, portable=True,
    ).portable is True


def test_furniture_is_not_portable_unless_it_says_so():
    """A building must not become liftable by default."""
    assert Furnishing(
        id="w", name="Wall", polygon_xy=[(0, 0), (1, 0), (1, 1)],
        height_m=3.0, material="wooden wall", body=12,
    ).portable is False


def test_the_projection_carries_portability():
    """`constructs_in` is where a furnishing becomes a thing you can act
    on. A flag that stops here is the same defect one layer down."""
    liftable = {c.obj_id: c.portable for c in constructs_in(_scene(portable=True))}
    assert liftable.get("barrels") is True

    fixed = {c.obj_id: c.portable for c in constructs_in(_scene(portable=False))}
    assert fixed.get("barrels") is False
