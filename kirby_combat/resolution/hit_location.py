"""Where you hit somebody, and what it costs them (6E2 p.110-111).

THE TABLE WAS ALWAYS HERE AND ONLY ONE COLUMN OF IT WAS READ.
`tables.HIT_LOCATIONS` carries `stunX`, `nStunX`, `bodyX` and `ocvMod` for
every location, and `HIT_LOCATION_ROLL` maps 3d6 to a body part.
`resolution/to_hit.py` reads `ocvMod`. Nothing read the other three, and
nothing ever rolled on the table.

So a fighter could aim at the head, pay -8 OCV for it, hit --- and do
exactly the damage he would have done swinging at nothing in particular.
`compute_damage` took a `hit_location`, passed it through to the result
untouched, and hardcoded `body_multiplier=1.0`. AIMING WAS STRICTLY WORSE
THAN NOT AIMING, in every fight this engine has run.

THE RULES, quoted, because the ordering is not what you would guess.

KILLING (6E2 p.110): "Multiply the BODY rolled by the STUNx for the
location hit INSTEAD of rolling a STUN Multiplier. The result is the
amount of STUN done to the target before his defenses are applied.
Subtract the target's appropriate defenses to determine how much STUN he
takes." And: "Subtract the target's appropriate Resistant Defense from the
BODY of the attack to determine the BODY done. Then multiply that BODY
total by the BODYx."

NORMAL (6E2 p.111): "Roll the dice to determine how much STUN damage the
attack does. Then apply the target's defenses. Multiply the amount of
damage the target takes AFTER applying his defenses by the modifier for
that part of the body in the N STUN column." BODY the same way: "Subtract
the target's appropriate defenses from the BODY of the attack ... Then
multiply that BODY total by the BODYx."

THE ASYMMETRY IS REAL AND IS THE POINT OF THIS MODULE. Killing STUN
multiplies BEFORE defenses; Normal STUN multiplies AFTER. BODY always
multiplies after. Getting that backwards changes a head shot from lethal
to survivable and is exactly the sort of thing a resolver written from
memory gets wrong.

A PLACED SHOT USES THE SAME NUMBERS (6E2 p.111): "If a character succeeds
with an Attack Roll after applying the OCV modifier, his attack hits the
location listed, doing the BODYx and STUNx listed." Aiming and rolling
differ only in how the location is chosen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kirby_combat.tables import HIT_LOCATIONS, HIT_LOCATION_ROLL


@dataclass(frozen=True)
class LocationEffect:
    """What one location does to an attack's numbers."""

    name: str
    stun_x: float          # killing: multiplies BODY *before* defenses
    normal_stun_x: float   # normal: multiplies STUN *after* defenses
    body_x: float          # both: multiplies BODY *after* defenses
    ocv_mod: int


def effect_for(location: str | None, *, template: Any = None) -> LocationEffect | None:
    """The table row for a location name, or None when there is none.

    None is the ordinary case --- most attacks are not aimed and most
    campaigns do not roll locations --- and it means "resolve damage the
    way this engine always has".

    `CombatTemplate.allowed_hit_locations` narrows it. The field is a GM
    setting whose own comment reads "empty = all", and it was written by
    nothing and read by nothing, so a table that listed the locations it
    uses was ignored. A location outside the list comes back None: the
    campaign has taken it out of play, so the multipliers do not apply.

    NOT THE SAME THING as 6E2 p.45's cover case --- "Only Andarra's head,
    arms, shoulders, and chest are exposed, so any Hit Location roll of 12
    or more hits the rock, doing no damage to her" --- which is per-TARGET
    and per-cover, needs a map from cover to exposed locations that the
    book leaves to the GM, and is not built here.
    """
    row = HIT_LOCATIONS.get(location or "")
    if row is None:
        return None
    allowed = list(getattr(template, "allowed_hit_locations", None) or [])
    if allowed and location not in allowed:
        return None
    return LocationEffect(
        name=str(row.get("label", location)),
        stun_x=float(row.get("stunX", 1)),
        normal_stun_x=float(row.get("nStunX", 1)),
        body_x=float(row.get("bodyX", 1)),
        ocv_mod=int(row.get("ocvMod", 0)),
    )


def location_for_roll(total: int) -> str | None:
    """The body part a 3d6 Hit Location roll lands on (6E2 p.110 step 1).

    `HIT_LOCATION_ROLL` has been in `tables.py` the whole time and nothing
    ever consulted it: no fight this engine has run ever rolled a location.
    """
    return HIT_LOCATION_ROLL.get(int(total))


def killing_damage(body_rolled: int, *, total_defense: int,
                   resistant_defense: int, effect: LocationEffect) -> tuple[int, int]:
    """STUN and BODY for a Killing attack at a location (6E2 p.110).

    STUN is BODY x STUNx and THEN defenses; BODY is defenses and THEN
    BODYx. The book's worked example: an RKA rolling 13 BODY into the Arms
    (BODYx 1/2) against 3 PD leaves 10, halved to "5 BODY".
    """
    stun = max(0, int(body_rolled * effect.stun_x) - total_defense)
    body = int(max(0, body_rolled - resistant_defense) * effect.body_x)
    return stun, max(0, body)


def normal_damage(stun_rolled: int, body_rolled: int, *, total_defense: int,
                  effect: LocationEffect) -> tuple[int, int]:
    """STUN and BODY for a Normal attack at a location (6E2 p.111).

    Both multiply AFTER defenses --- the opposite of Killing STUN.
    """
    stun = int(max(0, stun_rolled - total_defense) * effect.normal_stun_x)
    body = int(max(0, body_rolled - total_defense) * effect.body_x)
    return max(0, stun), max(0, body)


def uses_hit_locations(template: Any, target: Any) -> bool:
    """Whether this campaign resolves damage by location at all.

    `RAW_SUPERHEROIC` ships `use_hit_locations=False`; `RAW_HEROIC` ships
    it True with `auto_roll_hit_location_npc` beside it --- "auto-roll for
    NPCs even if flag is off", the field's own comment, and the second
    half of the same pair as `manage_endurance` / `manage_endurance_npc`.
    """
    if template is None:
        return False
    if getattr(template, "use_hit_locations", False):
        return True
    return bool(getattr(target, "is_npc", False)
                and getattr(template, "auto_roll_hit_location_npc", False))


#: How much of a man each level of cover hides, as a threshold on the 3d6
#: Hit Location roll. A JUDGEMENT, stated because the book does not give a
#: general rule --- it gives one worked example and leaves the rest to the
#: GM, exactly as `collapse.COLLAPSE_RADIUS_M` is a judgement about a
#: footprint the book has no opinion on.
#:
#: THE EXAMPLE IS THE ANCHOR (6E2 p.45): "Only Andarra's head, arms,
#: shoulders, and chest are exposed, so any Hit Location roll of 12 or
#: more hits the rock, doing no damage to her." Her rock is cover 2 on
#: this engine's 0-4 scale, and 18 - 3*2 = 12 --- the FIRST BLOCKED roll,
#: not the last exposed one, which is what "12 or more" says. The other
#: levels follow the same three-rolls-per-level slope: cover 1 blocks 15
#: and up, cover 3 blocks 9 and up, cover 4 blocks 6 and up --- leaving
#: only 3-5, the head, which is the cover table's own "full cover except
#: head/torso" for the top band.
#:
#: The ordering does the work: `HIT_LOCATION_ROLL` runs head-first (3-5
#: Head, 9 Shoulder, 10-11 Chest, 15 Thigh, 18 Foot), so a man crouched
#: behind something is exposed on the LOW rolls and covered on the high
#: ones, which is what "12 or more hits the rock" describes.
ROLLS_HIDDEN_PER_COVER_LEVEL = 3
MAX_LOCATION_ROLL = 18


def exposed_through_cover(roll: int, *, cover_level: int) -> bool:
    """Whether a Hit Location roll finds the man or the thing he is behind.

    A roll above the threshold hits the cover and, per p.45, does no
    damage to him. Damaging the COVER on such a shot is not modelled here;
    the book's example does not do it either.
    """
    level = max(0, min(4, int(cover_level or 0)))
    if level <= 0:
        return True
    # STRICTLY LESS THAN: p.45's "12 or more hits the rock" makes 12 the
    # first blocked roll at cover 2, and 18 - 3*2 is 12.
    return int(roll) < MAX_LOCATION_ROLL - ROLLS_HIDDEN_PER_COVER_LEVEL * level
