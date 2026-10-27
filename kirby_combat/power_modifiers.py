"""The power modifiers that change the SHAPE of an attack, read off the build.

Area Of Effect, Constant, Damage Over Time, Side Effects and Increased
Endurance Cost were all detected by the deleted kirby-api driver
(`_power_has_aoe`, `_power_increased_end_factor`, `_power_has_side_effects`
...) and every one of them was either wrong or inert there: AOE hit every
living enemy on the map wherever they stood, INCREASEDEND was "x2" whatever
the build said, SIDEEFFECTS was a flag in a payload. When the driver was
deleted (kirby-api 70ad60f) the detection went with it, and the engine has
read none of them since.

This module turns the build's modifier objects into small value objects the
combat engine can act on. It reads; it decides no rule. Each object carries
``unbuilt``: the parts of the modifier the engine does not resolve. A power
with anything unbuilt is NOT OFFERED (``unbuilt_reasons``), because an
offer the engine cannot carry out faithfully is a lie the menu tells.

Everything is read through `kirby_cost.model.modifiers.find_modifier`, the
same resolver `hero_view._has_modifier` uses, so a Multipower slot inherits
what its pool was bought with.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AreaShape(str, Enum):
    """6E1 p.322: "Radius; Cone; Line; Any Area; and Surface"."""

    RADIUS = "radius"
    CONE = "cone"
    LINE = "line"
    SURFACE = "surface"
    ANY = "any"


class AreaTargeting(str, Enum):
    """Who in the area is affected, and how.

    STANDARD: everyone in it, one Attack Roll against the target point
    (6E1 p.321). SELECTIVE / NONSELECTIVE: a further Attack Roll against
    each chosen / every target "at that target's normal DCV" (6E1 p.326).
    ACCURATE: one person only, against DCV 3 (6E1 p.322).
    """

    STANDARD = "standard"
    SELECTIVE = "selective"
    NONSELECTIVE = "nonselective"
    ACCURATE = "accurate"


#: 6E1 p.322: a Line is "2m wide and 2m tall" unless widened or heightened.
LINE_DEFAULT_WIDTH_M = 2.0
LINE_DEFAULT_HEIGHT_M = 2.0


@dataclass(frozen=True)
class AreaSpec:
    """An Area Of Effect as bought.

    ``size_m`` is HD's LEVELS on the AOE modifier, which IS the template's
    size in metres (the radius of a Radius, the side of a Cone, the length
    of a Line) --- HD 6E's own LEVELSLABEL is "Size".
    """

    shape: AreaShape
    size_m: float
    targeting: AreaTargeting
    explosion: bool
    personal_immunity: bool
    width_m: float
    height_m: float
    thin_cone: bool
    unbuilt: tuple[str, ...]


@dataclass(frozen=True)
class DamageOverTimeSpec:
    """Damage Over Time as bought (6E1 p.330-333).

    ``increments`` is the upper bound of HD's band (the option "6" reads
    "5-6"): HD records the band and not the number inside it, so the
    engine takes the band's top. RULING, labelled: the band is all the
    build says, and its top is the number the Advantage was priced for.
    """

    increments: int
    interval_segments: int
    lockout: bool
    #: 6E1 p.332: "the victim ... may only apply his defense once against
    #: the overall damage of the attack. He keeps applying his defenses
    #: until such time as the total damage from the attack exceeds the
    #: value of the defense." HD's ONEDEFENSE.
    one_defense: bool
    unbuilt: tuple[str, ...]


class SideEffectSeverity(str, Enum):
    """6E1 p.396's Side Effects Table, in Active Points."""

    MINOR = "minor"
    MAJOR = "major"
    EXTREME = "extreme"

    def active_points(self, power_active_points: int) -> int:
        """"15 Active Points, or one-fourth of the Active Points in the power
        (whichever is greater)"; 30 or half; 60 or all of them."""
        floor, share = _SIDE_EFFECT_SIZES[self]
        return max(floor, int(power_active_points * share))


_SIDE_EFFECT_SIZES = {
    SideEffectSeverity.MINOR: (15, 0.25),
    SideEffectSeverity.MAJOR: (30, 0.5),
    SideEffectSeverity.EXTREME: (60, 1.0),
}


@dataclass(frozen=True)
class SideEffectsSpec:
    """Side Effects as bought (6E1 p.395-397).

    ``always_occurs``: "occurring every time he uses the power, regardless
    of whether he successfully activates it". Otherwise it happens "each
    time the character's attempt to activate or use the power fails".
    """

    severity: SideEffectSeverity
    always_occurs: bool
    text: str
    unbuilt: tuple[str, ...]
    #: 6E1 p.396: "A Side Effect might affect the environment around the
    #: character instead of the character himself ... the character should
    #: rarely, if ever, be allowed to cause damage to others with it or
    #: derive any sort of combat advantage". HD's ONLYNEARCHARACTER. It
    #: happens, is written down, and hurts nobody (`apply_side_effects`).
    environment_only: bool


@dataclass(frozen=True)
class AutofireSpec:
    """Autofire as bought (6E1 p.329): the most shots a Phase may fire.

    HD's options are ``TWO`` / ``THREE`` / ``FIVE``; ``FIVE`` takes a
    ``DOUBLE`` adder whose LEVELS doubles the five that many times (the
    template's ``LVLPOWER="2"``; 6E1 p.329: "You can up to double this 5
    shot maximum for each additional +1/2 Advantage"). ``ODDPOWER`` is the
    +1 surcharge (6E1 p.329), a price and nothing the fight reads.
    """

    shots: int
    unbuilt: tuple[str, ...]


_AUTOFIRE_SHOTS = {"TWO": 2, "THREE": 3, "FIVE": 5}


@dataclass(frozen=True)
class IncreasedEnd:
    """Increased Endurance Cost (6E1 p.376): "x2 END" ... "x10 END"."""

    multiplier: int
    unbuilt: tuple[str, ...]


# ---------------------------------------------------------------------------
# Reading them off the build
# ---------------------------------------------------------------------------

def _find(power: Any, xmlid: str):
    from kirby_cost.model.modifiers import find_modifier

    try:
        return find_modifier(power, xmlid)
    except (AttributeError, TypeError):   # a stub with no modifier tree
        return None


def _option(obj: Any) -> str:
    opt = getattr(obj, "_selected_option", None)
    for candidate in (getattr(opt, "xmlid", None), getattr(obj, "option_id", None)):
        if candidate:
            return str(candidate).strip().upper()
    return ""


def _adders(obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in (getattr(obj, "assigned_adders", None) or []):
        x = (getattr(a, "xmlid", "") or "").upper()
        if x:
            out[x] = a
    return out


def _sub_modifiers(obj: Any) -> set[str]:
    return {(getattr(m, "xmlid", "") or "").upper()
            for m in (getattr(obj, "assigned_modifiers", None) or [])}


def _levels(obj: Any) -> float:
    try:
        return float(getattr(obj, "levels", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def area_spec_of(power: Any) -> AreaSpec | None:
    """The power's Area Of Effect, or None if it has none."""
    mod = _find(power, "AOE")
    if mod is None:
        return None
    unbuilt: list[str] = []
    shape_id = _option(mod)
    try:
        shape = AreaShape(shape_id.lower())
    except ValueError:
        shape = AreaShape.ANY
        unbuilt.append(f"Area Of Effect option {shape_id!r}")
    adders = _adders(mod)
    size = _levels(mod)
    if size <= 0:
        unbuilt.append("Area Of Effect with no size")

    # SURFACE is built (`kirby_combat/standing_areas.py`): on himself it is a
    # Damage Shield (6E1 p.323-324), on another man it is an attack at his
    # own DCV whose covered skin hurts whoever touches it. What a Surface
    # on a mere object would do is asked in `unbuilt_reasons`, which sees
    # the whole view.
    if shape is AreaShape.ANY:
        # 6E1 p.323: the attacker arranges 2m Areas "as desired" each use;
        # nothing in a menu offer says how.
        unbuilt.append("Area Of Effect (Any Area)")
    if "MOBILE" in adders:
        unbuilt.append("Mobile Area Of Effect")
    if _find(power, "HOLEINTHEMIDDLE") is not None:
        unbuilt.append("Hole In The Middle")
    # AUTOFIRE ON AN AREA IS BUILT for one target point (6E1 p.321; 6E2
    # p.45, `actions/autofire_attack.py`); `unbuilt_reasons` refuses only the
    # combinations nothing resolves.

    if "ACCURATE" in adders:
        targeting = AreaTargeting.ACCURATE
    elif "SELECTIVETARGET" in adders:
        targeting = AreaTargeting.SELECTIVE
    elif "NONSELECTIVETARGET" in adders:
        targeting = AreaTargeting.NONSELECTIVE
    else:
        targeting = AreaTargeting.STANDARD

    width = LINE_DEFAULT_WIDTH_M
    height = LINE_DEFAULT_HEIGHT_M
    if "DOUBLEWIDTH" in adders:
        width = max(width, _levels(adders["DOUBLEWIDTH"]))
    if "DOUBLEHEIGHT" in adders:
        height = max(height, _levels(adders["DOUBLEHEIGHT"]))

    return AreaSpec(
        shape=shape, size_m=size, targeting=targeting,
        explosion="EXPLOSION" in adders,
        personal_immunity=_find(power, "PERSONALIMMUNITY") is not None,
        width_m=width, height_m=height,
        thin_cone="THINCONE" in adders,
        unbuilt=tuple(unbuilt),
    )


def is_constant(power: Any) -> bool:
    """HD's CONTINUOUS is 6E's Constant Advantage (+1/2, 6E1 p.336)."""
    return _find(power, "CONTINUOUS") is not None


#: HD's TIMEBETWEEN options, in Segments. 6E2 p.18: a Segment is one
#: second and a Turn is 12; the Time Chart's longer steps are seconds too.
_DOT_INTERVAL_SEGMENTS = {
    "SEGMENT": 1, "2SEGMENTS": 2, "3SEGMENTS": 3, "4SEGMENTS": 4,
    "6SEGMENTS": 6, "TURN": 12, "30SEGMENTS": 30, "MINUTE": 60,
    "5MINUTES": 300, "20MINUTES": 1200, "HOUR": 3600, "6HOURS": 21600,
    "DAY": 86400, "WEEK": 604800,
}


def damage_over_time_of(power: Any) -> DamageOverTimeSpec | None:
    """The power's Damage Over Time, or None."""
    mod = _find(power, "DAMAGEOVERTIME")
    if mod is None:
        return None
    unbuilt: list[str] = []
    adders = _adders(mod)
    increments = 0
    if "INCREMENTS" in adders:
        try:
            increments = int(_option(adders["INCREMENTS"]))
        except ValueError:
            increments = 0
    if increments <= 0:
        unbuilt.append("Damage Over Time with no readable increments")
    interval = 0
    if "TIMEBETWEEN" in adders:
        interval = _DOT_INTERVAL_SEGMENTS.get(_option(adders["TIMEBETWEEN"]), 0)
    if interval <= 0:
        unbuilt.append("Damage Over Time with no readable interval")
    subs = _sub_modifiers(mod)
    return DamageOverTimeSpec(
        increments=max(increments, 0), interval_segments=max(interval, 0),
        lockout="LOCKOUT" in subs, one_defense="ONEDEFENSE" in subs,
        unbuilt=tuple(unbuilt),
    )


def side_effects_of(power: Any) -> SideEffectsSpec | None:
    """The power's Side Effects, or None."""
    mod = _find(power, "SIDEEFFECTS")
    if mod is None:
        return None
    unbuilt: list[str] = []
    option = _option(mod)
    try:
        severity = SideEffectSeverity(option.lower())
    except ValueError:
        severity = SideEffectSeverity.MINOR
        unbuilt.append(f"Side Effects option {option!r}")
    adders = _adders(mod)
    for adder, why in (
        ("ALWAYSAFTERACT", "Side Effect on some specific act"),
        ("PREDEFINEDDAMAGE", "Side Effect of a predefined amount"),
        ("AFTERUSE", "Side Effect after the power stops"),
        ("ONLYAFFECTSRECIPIENT", "Side Effect on the power's recipient"),
    ):
        if adder in adders:
            unbuilt.append(why)
    # 6E1 p.396: an environment-only Side Effect "should rarely, if ever,
    # be allowed to cause damage to others with it or derive any sort of
    # combat advantage". So it is built as exactly that: it occurs when the
    # table says, is recorded, and changes nothing in the fight.
    environment_only = "ONLYNEARCHARACTER" in adders
    text = str(getattr(mod, "input", None) or getattr(mod, "_input", None)
               or getattr(mod, "_alias", None) or "")
    return SideEffectsSpec(
        severity=severity,
        always_occurs="ALWAYSOCCURS" in _sub_modifiers(mod),
        text=text, unbuilt=tuple(unbuilt),
        environment_only=environment_only,
    )


def autofire_of(power: Any) -> AutofireSpec | None:
    """The power's Autofire, or None."""
    mod = _find(power, "AUTOFIRE")
    if mod is None:
        return None
    option = _option(mod)
    shots = _AUTOFIRE_SHOTS.get(option, 0)
    unbuilt: list[str] = []
    if shots <= 0:
        unbuilt.append(f"Autofire option {option!r}")
    doubled = _adders(mod).get("DOUBLE")
    if doubled is not None and shots:
        shots *= 2 ** max(0, int(_levels(doubled)))
    return AutofireSpec(shots=shots, unbuilt=tuple(unbuilt))


def increased_end_of(power: Any) -> IncreasedEnd | None:
    """The power's Increased Endurance Cost, or None."""
    mod = _find(power, "INCREASEDEND")
    if mod is None:
        return None
    unbuilt: list[str] = []
    option = _option(mod)              # "2X" ... "10X"
    try:
        multiplier = int(option.rstrip("X"))
    except ValueError:
        multiplier = 0
        unbuilt.append(f"Increased Endurance Cost option {option!r}")
    if "CIRCUMSTANCE" in _adders(mod):
        # 6E1 p.376: the higher cost "only applies in an Uncommon / Common
        # / Very Common circumstance" the build describes in words.
        unbuilt.append("Increased Endurance Cost only in certain circumstances")
    return IncreasedEnd(multiplier=multiplier, unbuilt=tuple(unbuilt))


# ---------------------------------------------------------------------------
# What the engine can and cannot resolve
# ---------------------------------------------------------------------------

def unbuilt_reasons(power: Any) -> list[str]:
    """Every part of this attack view's modifiers the engine cannot resolve.

    Empty means the engine can carry the power out as bought. Read by the
    loop's offer filter (`attack_shapes.offers_the_engine_can_keep`).
    """
    out: list[str] = []
    area = getattr(power, "area", None)
    dot = getattr(power, "damage_over_time", None)
    constant = bool(getattr(power, "constant", False))
    autofire = getattr(power, "autofire", None)
    for spec in (area, dot, getattr(power, "side_effects", None),
                 getattr(power, "increased_end", None), autofire):
        if spec is not None:
            out.extend(spec.unbuilt)
    if autofire is not None and (constant or dot is not None):
        # 6E2 p.44: an Autofire Constant attack "continues to affect the
        # target with the same number of shots that hit him the first time";
        # a maintained use here is one shot, and a lingering dose has no
        # shot count at all.
        out.append("Autofire on a Constant or Damage Over Time attack (6E2 p.44)")
    if (autofire is not None and area is not None
            and area.shape is AreaShape.SURFACE):
        out.append("Autofire Surface")
    if (constant or dot is not None) and getattr(power, "uncontrolled", False):
        # 6E1 p.354: "the character feeds as much END as he desires into the
        # power to create a pool of END to fuel it", and it runs until "a
        # reasonably common and obvious set of circumstances" turns it off.
        # The pool is a choice no offer carries, and the circumstance is
        # words on the build; maintained as plain Constant it would stop
        # when he is Stunned or loses sight of it, which Uncontrolled
        # exists to prevent.
        out.append("Uncontrolled (6E1 p.354)")
    if constant and dot is not None:
        # No page says what a power bought with both does: Constant's dose
        # "in every Segment in which the attacker has a Phase" (6E1 p.129)
        # and Damage Over Time's own clock (p.331) are two different
        # answers to the same question.
        out.append("Constant and Damage Over Time together")
    if area is not None:
        surface = area.shape is AreaShape.SURFACE
        if surface and dot is not None:
            out.append("Damage Over Time on a Surface")
        if surface and getattr(power, "damage_type", "") == "mental":
            # 6E1 p.324's Mental Damage Shield needs Mental Contact Only and
            # works through mental contact, which no offer makes.
            out.append("Mental Surface (6E1 p.324)")
        if surface and not getattr(power, "is_ranged", False) and not constant:
            # 6E1 p.323: "A Constant Area Of Effect (personal Surface) power
            # that a character applies to himself is known as a Damage
            # Shield." An Instant one on his own skin lasts no time at all.
            out.append("Instant Surface on himself")
        if dot is not None and dot.one_defense:
            # 6E1 p.332's spent defense is the victim's against "the overall
            # damage of the attack"; a zone doses whoever walks in, each on
            # his own clock, and the book does not say whose total it is.
            out.append("Damage Over Time Area with defenses that apply once")
        if area.explosion and getattr(power, "damage_type", "") not in (
                "normal", "killing"):
            # 6E1 p.325 writes Explosion for Normal and Killing damage, Flash
            # and Entangle; an attack door kind with any other damage is
            # none of those.
            out.append("Explosion on an attack that is neither Normal nor "
                       "Killing")
    return out
