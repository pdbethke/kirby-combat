"""What a bought martial maneuver DOES, decoded from Hero Designer's EFFECT.

HD stores every maneuver as an OCV, a DCV, a DC count, a damage-type code and
an EFFECT string built from ELEMENTS --- ``"[NORMALDC] Strike, Target Falls"``,
``"Grab One Limb; [NNDDC]"``, ``"Disarm; [STRDC] to Disarm"``. Each element of
the 6E2 Martial Maneuvers Table (6E2 p.93) maps onto a rule this engine already
has: a Strike's damage, a Grab, a Disarm, a fall. This module turns the string
into that object once, so the menu offers only what the resolver can carry and
the resolver never re-reads a string.

WHAT IS DECODED, and where each rule comes from:

* ``[NORMALDC]`` --- STR + the maneuver's DCs as Normal Damage: "STR means the
  Maneuver does STR/5 in d6 of Normal Damage" (6E2 p.93), "+1 DC for each +1
  DC from the Maneuver" (6E2 p.101).
* ``[KILLINGDC]`` --- Killing Strike: "Rules regarding adding STR (as if to an
  HKA) ... apply" (6E2 p.93); 3 DC per 1d6 of Killing Damage (6E2 p.99;
  6E1 p.244 "+1 Damage Class for every 5 points of STR").
* ``[NNDDC]`` --- Nerve Strike / Choke Hold NND: each DC of an NND attack is
  1/2d6 (6E2 p.99), STR adds nothing ("Martial Maneuvers that don't add dice of
  damage - such as Killing Damage strikes, NND Strikes ... can't be used to add
  damage", 6E2 p.101).
* ``[STRDC]`` --- a STR bonus for one purpose only: holding on (Martial Grab,
  6E2 p.94) or the Disarm contest (Martial Disarm, 6E2 p.94). HD writes the
  maneuver's DCs as +5 STR each.
* ``Grab One/Two/Three Limbs`` --- a Grab (6E2 p.67; Martial Grab p.94; Choke
  Hold p.86 / p.93).
* ``Disarm`` --- a Disarm (6E2 p.65; Martial Disarm p.94).
* ``Target Falls`` / ``You Fall`` --- the target / the attacker ends prone
  (Legsweep, Martial Throw, Sacrifice Throw, 6E2 p.94).
* ``+v/10`` / ``+v/5`` --- velocity damage. A ``maneuver`` offer composes no
  movement, so the velocity is 0 and adds nothing: "A character has to have a
  full 6m/10m of movement ... to get +1 DC - anything less than that has no
  effect" (6E2 p.101).
* ``Strike`` --- the word that decorates a damage token; it states no damage of
  its own. HD's own output for a custom "Strike" with damage type NONE is the
  bare word, so none is guessed at.
* Extra Damage Classes (``EXTRADC``): "Each Extra DC adds one Damage Class to
  any Maneuver ... or +5 STR to any Maneuver that grants extra STR for limited
  purposes" (6E2 p.94). The caller folds them into the DC count it passes.

WHAT IS REFUSED --- ``UnbuildableManeuver`` --- is every element this engine
has no faithful rule for. Each comes from HD's maneuver builder (the HERO
System Martial Arts book's elements), not from 6E2's table, so there is no 6E2
page to implement them against: ``FMove`` (a Full Move made as part of the
maneuver, which a ``maneuver`` offer does not compose), ``Must Follow Block`` /
``Must Follow Grab``, ``Crush``, ``Bind``, ``Shove``, ``Grab Weapon``,
``Disable``, ``Block`` / ``Dodge`` / ``Abort`` (defensive, not offensive),
``vs. Grabs`` / ``to Escape``, ``[FLASHDC]`` (a Sense Group the view does not
carry), a Grab that also does Normal or Killing damage, and free-text STR
figures ("+10 STR") that duplicate the DC count HD already records. Refusing
keeps the menu honest: enumeration does not offer what the resolver would have
to approximate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ManeuverDamage(str, Enum):
    """The damage family a maneuver deals, by HD's damage-type code or token.

    A ``str`` Enum so the view's ``damage_type`` still compares equal to the
    plain "normal" / "killing" it carried before, and so a snapshot written
    with those strings rehydrates onto it.
    """

    NONE = "none"
    STR = "str"
    NORMAL = "normal"
    KILLING = "killing"
    NND = "nnd"
    FLASH = "flash"
    #: The EFFECT names two different damage tokens. HD can store it; there
    #: is no single rule to resolve it by.
    MIXED = "mixed"


#: HD's damage tokens, in the EFFECT string.
_TOKENS: dict[str, ManeuverDamage] = {
    "[normaldc]": ManeuverDamage.NORMAL,
    "[killingdc]": ManeuverDamage.KILLING,
    "[nnddc]": ManeuverDamage.NND,
    "[strdc]": ManeuverDamage.STR,
    "[flashdc]": ManeuverDamage.FLASH,
}


def damage_family(effect: str, damage_code: int) -> ManeuverDamage:
    """The maneuver's damage family.

    A standard maneuver names its damage with a token in the EFFECT and
    carries damage-type code 0. A custom one writes ``[DAMAGE]`` (or nothing)
    and states the type in the code. kirby-cost's ``Maneuver`` resolves them
    the same way (``_substitute_dc`` for the tokens, ``damage_string`` for the
    code), and its constants name the codes.
    """
    from kirby_cost.objects.martial_arts.maneuver import Maneuver

    lowered = (effect or "").lower()
    found = {fam for tok, fam in _TOKENS.items() if tok in lowered}
    if len(found) > 1:
        return ManeuverDamage.MIXED
    if found:
        return next(iter(found))
    by_code = {
        Maneuver.NONE: ManeuverDamage.NONE,
        Maneuver.STR: ManeuverDamage.STR,
        Maneuver.NORMAL: ManeuverDamage.NORMAL,
        Maneuver.KILLING: ManeuverDamage.KILLING,
        Maneuver.NND: ManeuverDamage.NND,
        Maneuver.FLASH: ManeuverDamage.FLASH,
    }
    code = int(damage_code)
    if code not in by_code:
        raise ValueError(f"unknown HD maneuver damage-type code {code!r}")
    return by_code[code]


class UnbuildableManeuver(Exception):
    """A maneuver whose effect this engine cannot resolve faithfully."""

    def __init__(self, name: str, effect: str, reason: str) -> None:
        self.name, self.effect, self.reason = name, effect, reason
        super().__init__(f"maneuver {name!r} ({effect!r}) is not built: {reason}")


@dataclass(frozen=True)
class MartialEffect:
    """What resolving one maneuver does, decided before any die is rolled."""

    #: NONE for a Grab or Disarm without damage; else NORMAL / KILLING / NND.
    damage: ManeuverDamage
    #: The maneuver's own DCs plus every Extra DC (6E2 p.94).
    damage_classes: int
    #: Whether the wielder's STR adds (HD's ADDSTR).
    adds_str: bool
    grab: bool
    disarm: bool
    #: +STR for holding on (Grab) or for the Disarm contest; 0 otherwise.
    str_bonus: int
    target_falls: bool
    actor_falls: bool


#: Elements removed from the EFFECT as they are recognised. Order matters:
#: a qualifier goes before the bare word it qualifies.
_ELEMENTS: tuple[tuple[str, str], ...] = (
    ("grab", r"\bgrab (one|two|three|[123]) limbs?\b"),
    ("holding", r"\bfor holding on\b"),
    ("disarm_q", r"\bto disarm( roll)?\b"),
    ("disarm", r"\bdisarm\b"),
    ("target_falls", r"\btarget falls\b"),
    ("actor_falls", r"\byou fall\b"),
    ("token", r"\[(normaldc|killingdc|nnddc|strdc|damage)\]"),
    ("strike", r"\bstrike\b"),
    ("velocity", r"\+?v/(5|10)\b"),
)


def decode_effect(
    *, name: str, effect: str, damage: ManeuverDamage, damage_classes: int,
    adds_str: bool,
) -> MartialEffect:
    """Decode one maneuver, or raise ``UnbuildableManeuver`` saying why.

    STRICT BY DESIGN: every element of the EFFECT must be one this module
    knows. A residue is refused rather than ignored, because an ignored
    element is a rule the menu promises and the resolver silently drops ---
    the exact shape of the defect this module was written to end.
    """
    lowered = (effect or "").lower()
    seen: set[str] = set()
    residue = lowered
    for label, pattern in _ELEMENTS:
        residue, n = re.subn(pattern, " ", residue)
        if n:
            seen.add(label)
    leftover = re.sub(r"[\s;,]+", " ", residue).strip()
    if leftover:
        raise UnbuildableManeuver(name, effect, f"unmodelled element {leftover!r}")

    grab = "grab" in seen
    disarm = "disarm" in seen
    if "holding" in seen and not grab:
        raise UnbuildableManeuver(name, effect, "'for holding on' without a Grab")
    if damage in (ManeuverDamage.FLASH, ManeuverDamage.MIXED):
        raise UnbuildableManeuver(name, effect, f"{damage.value} damage")

    str_bonus = 0
    if damage is ManeuverDamage.STR:
        if not (grab or disarm):
            raise UnbuildableManeuver(name, effect, "a STR bonus with no Grab or Disarm to spend it on")
        if not adds_str:
            raise UnbuildableManeuver(name, effect, "[STRDC] that replaces STR rather than adding to it")
        # HD's `str_dc` writes the total as (DC + STR/5) * 5, so the bonus
        # over the wielder's own STR is the DCs at 5 STR each (6E2 p.94).
        str_bonus = 5 * int(damage_classes)
        damage = ManeuverDamage.NONE

    if grab and disarm:
        raise UnbuildableManeuver(name, effect, "a Grab and a Disarm at once")
    if grab and damage not in (ManeuverDamage.NONE, ManeuverDamage.NND):
        # Choke Hold (6E2 p.86) is the one Grab that does damage as part of
        # taking hold, and it is NND.
        raise UnbuildableManeuver(name, effect, f"a Grab that also does {damage.value} damage")
    if disarm and (damage is not ManeuverDamage.NONE or "target_falls" in seen):
        raise UnbuildableManeuver(name, effect, "a Disarm with another effect")
    if not (grab or disarm) and damage is ManeuverDamage.NONE:
        raise UnbuildableManeuver(name, effect, "no damage, Grab or Disarm to resolve")

    return MartialEffect(
        damage=damage, damage_classes=int(damage_classes), adds_str=bool(adds_str),
        grab=grab, disarm=disarm, str_bonus=str_bonus,
        target_falls="target_falls" in seen, actor_falls="actor_falls" in seen,
    )


def decode_maneuver(mv) -> MartialEffect:
    """``decode_effect`` over a ``MartialManeuverView``."""
    return decode_effect(
        name=mv.name, effect=mv.effect, damage=ManeuverDamage(mv.damage_type),
        damage_classes=mv.dc_bonus, adds_str=mv.add_str,
    )


def killing_dice(damage_classes: int) -> tuple[int, bool, bool]:
    """Killing Damage for a DC count, as (full d6, half d6, +1).

    6E2 p.99's Damage Class Table, Killing Damage column: 15 Active Points per
    1d6, so 3 DC per die --- 1 DC is +1, 2 DC is 1/2d6, 4 DC is 1d6+1, 5 DC is
    1 1/2d6. kirby-cost's ``Maneuver.killing_dc`` writes the same ladder.
    """
    dc = max(0, int(damage_classes))
    full, rem = divmod(dc, 3)
    return full, rem == 2, rem == 1


def nnd_dice(damage_classes: int) -> tuple[int, bool]:
    """NND dice for a DC count, as (full d6, half d6): 1/2d6 per DC (6E2 p.99)."""
    dc = max(0, int(damage_classes))
    return dc // 2, bool(dc % 2)


#: The NND maneuvers' defense, for `resolution/defense.py`'s named-defense
#: match. 6E2 p.94, Nerve Strike: "The target takes full damage from the
#: Nerve Strike unless he has rigid armor protecting his vulnerable spots or
#: PD Resistant Protection." Choke Hold's further defense (Life Support:
#: Self-Contained Breathing, 6E2 p.86) is NOT matched by this text --- see
#: the PR / CHANGELOG note; it is surfaced, not invented.
NND_DEFENSE = "Resistant Protection (PD) or rigid armor"


def maneuver_power(mv, effect: MartialEffect, *, strength: int):
    """The ``AttackPower`` a maneuver's Attack Roll and damage go through.

    Built the way ``HeroCombatant.str_strike_view`` builds the bare Strike
    --- the deleted api driver's own composition ("a STR strike modified by
    the maneuver's OCV/DCV/DC") --- with the damage made the maneuver's:

    * NORMAL: STR dice (kirby-cost's ``strike_dice``, half die included,
      6E2 p.98) + 1d6 per DC (6E2 p.101). STR only if the maneuver adds it.
    * KILLING: DCs + STR/5 (6E2 p.93 "as if to an HKA"; 6E1 p.244), at 3 DC
      per die (6E2 p.99) --- the driver bumped Normal dice and switched the
      type, so a Killing Strike rolled 1d6 of Killing per DC.
    * NND: 1/2d6 per DC, no STR (6E2 p.99, p.101), STUN only (6E1 p.328).
    * NONE (a Grab or Disarm): no damage dice; the roll is the whole of it.

    END: "They do not cost END to use, though the character has to pay END
    for any STR used with them" (6E2 p.93). So the power's Active Points are
    the STR it uses, and a maneuver that uses none costs nothing.
    """
    from kirby_cost.engine.damage import str_damage_classes, strike_dice

    from kirby_combat.models import AttackPower

    uses_str = effect.adds_str and effect.damage in (
        ManeuverDamage.NORMAL, ManeuverDamage.KILLING)
    dc = effect.damage_classes
    full, half, plus_one, damage_type = 0, False, False, "normal"
    if effect.damage is ManeuverDamage.NORMAL:
        str_full, str_half = strike_dice(strength) if uses_str else (0, False)
        full, half = str_full + dc, str_half
    elif effect.damage is ManeuverDamage.KILLING:
        damage_type = "killing"
        full, half, plus_one = killing_dice(
            dc + (str_damage_classes(strength) if uses_str else 0))
    elif effect.damage is ManeuverDamage.NND:
        full, half = nnd_dice(dc)
    nnd = effect.damage is ManeuverDamage.NND
    return AttackPower(
        source_id=mv.maneuver_id,
        xmlid="MANEUVER", name=mv.name,
        damage_dice=full, half_die=half, plus_one=plus_one,
        damage_type=damage_type, defense_type="pd",
        range_m=0.0, uses_str=uses_str, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=False, reach_m=mv.reach_m,
        avad=nnd, avad_defense=NND_DEFENSE if nnd else "",
        active_points=int(strength) if uses_str else 0,
        reduced_end=not uses_str,
    )


def describe_effect(effect: MartialEffect, *, strength: int) -> str:
    """The menu's one-line statement of what the maneuver will do."""
    from kirby_cost.engine.damage import str_damage_classes, strike_dice

    parts: list[str] = []
    if effect.damage is ManeuverDamage.NORMAL:
        full, half = (strike_dice(strength) if effect.adds_str else (0, False))
        parts.append(f"{full + effect.damage_classes}{'½' if half else ''}d6")
    elif effect.damage is ManeuverDamage.KILLING:
        f, h, p = killing_dice(effect.damage_classes + (
            str_damage_classes(strength) if effect.adds_str else 0))
        parts.append(f"HKA {f}{'½' if h else ''}d6{'+1' if p else ''}")
    elif effect.damage is ManeuverDamage.NND:
        f, h = nnd_dice(effect.damage_classes)
        parts.append(f"{f}{'½' if h else ''}d6 NND")
    if effect.grab:
        parts.append("Grab" + (f" (+{effect.str_bonus} STR to hold)" if effect.str_bonus else ""))
    if effect.disarm:
        parts.append("Disarm" + (f" (+{effect.str_bonus} STR)" if effect.str_bonus else ""))
    if effect.target_falls:
        parts.append("target falls")
    if effect.actor_falls:
        parts.append("you fall")
    return ", ".join(parts)

