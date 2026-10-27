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
* ``[FLASHDC]`` --- Martial Flash: 1d6 of Flash per DC (kirby-cost
  ``Maneuver.flash_dc``, HD's own reading) against the Sense Group the
  maneuver's INPUT names, resolved as the Flash power is (6E1 p.228).
* ``[STRDC]`` --- a STR bonus for one purpose only: holding on (Martial Grab,
  6E2 p.94), the Disarm contest (Martial Disarm, 6E2 p.94), wrenching a
  weapon away (Takeaway) or the distance of a Shove. HD writes the maneuver's
  DCs as +5 STR each. A free-text "+10 STR" is the same figure written by
  hand, and is read only when it agrees with the DCs HD costed.
* ``Grab One/Two/Three Limbs`` --- a Grab (6E2 p.67; Martial Grab p.94; Choke
  Hold p.86 / p.93). A Grab that also does damage is a Grab with its free
  Squeeze: "If the Grabber chooses to Squeeze ... in the same Segment in which
  he ... successfully Grabbed him, the Squeeze ... does not require an Attack
  Roll" (6E2 p.64), so the damage lands when the Grab does.
* ``Disarm`` --- a Disarm (6E2 p.62; Martial Disarm p.94).
* ``Grab Weapon`` + ``to take weapon away`` --- 6E2 p.69: "A character can
  choose to Grab a target's weapon, Accessible Focus, or other held or
  carried object instead of the target himself ... use normal Grab rules to
  see if the attacker succeeds" (Takeaway, Disarming Throw).
* ``Shove`` (``to Shove``) --- 6E2 p.81's Shove.
* ``Target Falls`` / ``You Fall`` --- the target / the attacker ends prone
  (Legsweep, Martial Throw, Sacrifice Throw, 6E2 p.94).
* ``+v/10`` / ``+v/5`` --- velocity damage: +1 DC per full 10m (5m) of
  velocity, "anything less than that has no effect" (6E2 p.101). A plain
  ``maneuver`` composes no movement, so its velocity is 0.
* ``FMove`` --- the maneuver is made as part of a Full Move, which is what a
  Move By or Move Through is (6E2 p.72): see `actions/martial_fmove.py`.
* ``Must Follow Block`` --- Counterstrike: usable only in the Phase after a
  successful Block of that attacker (the Block, and its "acts first" reward,
  are 6E2 p.59-60).
* ``Must Follow Grab`` --- Crush, Grappling Throw: usable only on a man the
  attacker is holding, i.e. a Squeeze or Throw "in a later Phase" (6E2 p.64).
* ``Crush`` --- the Squeeze of 6E2 p.64 ("regular STR damage ... the character
  retains his hold"), with the maneuver's DCs on top.
* ``Strike`` --- the word that decorates a damage token; it states no damage of
  its own.
* Extra Damage Classes (``EXTRADC``): "Each Extra DC adds one Damage Class to
  any Maneuver ... or +5 STR to any Maneuver that grants extra STR for limited
  purposes" (6E2 p.94). The caller folds them into the DC count it passes.

FMove, Must Follow, Crush, Grab Weapon, Shove and Martial Flash are HERO System
Martial Arts elements, not rows of 6E2's table. Each is built because the 6E
core books define the mechanic it names (above). The ones that are not:

WHAT IS REFUSED --- ``UnbuildableManeuver`` --- is every element this engine
has no faithful rule for:

* ``Bind`` --- a HERO System Martial Arts element with no 6E core mechanic.
* ``Disable`` (Joint Break) --- the Impairing/Disabling wound rules it names
  are an optional rule over Hit Locations (6E2 p.111-113) this engine does
  not model.
* ``Block`` / ``Dodge`` / ``Abort`` (defensive, read by
  `actions/reactive/martial.py`, not offensive), ``vs. Grabs`` / ``to
  Escape`` (escapes, read by `martial_escape`), ``to resist Shove``.
* a Strike with damage type NONE: HD's own reading is that it does no damage
  (kirby-cost ``Maneuver.does_damage``), so there is nothing to resolve.
* a free-text STR or dice figure that disagrees with the DCs HD costed
  ("60 STR for holding on", "4d6"), and anything else left over.

Refusing keeps the menu honest: enumeration does not offer what the resolver
would have to approximate.
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


class MustFollow(str, Enum):
    """What a maneuver must follow (a HERO System Martial Arts element)."""

    BLOCK = "block"
    GRAB = "grab"


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


#: HD's DEFENSE attribute on Choke Hold (Main6E.hdt): its NND is stopped by
#: something other than Nerve Strike's defence (6E2 p.86).
HD_SPECIAL_DEFENSE = "SPECIAL"

#: A Martial Flash's INPUT, as HD writes it, -> the engine's Sense Group.
_FLASH_SENSES: dict[str, str] = {
    "sight": "sight", "sight group": "sight",
    "hearing": "hearing", "hearing group": "hearing",
    "smell": "smell", "smell/taste": "smell", "smell/taste group": "smell",
    "radio": "radio", "radio group": "radio",
    "mental": "mental", "mental group": "mental",
}


@dataclass(frozen=True)
class MartialEffect:
    """What resolving one maneuver does, decided before any die is rolled."""

    #: NONE for a Grab, Disarm, Takeaway or Shove without damage; else
    #: NORMAL / KILLING / NND / FLASH.
    damage: ManeuverDamage
    #: The maneuver's own DCs plus every Extra DC (6E2 p.94).
    damage_classes: int
    #: Whether the wielder's STR adds (HD's ADDSTR).
    adds_str: bool
    grab: bool
    disarm: bool
    #: +STR for holding on (Grab), the Disarm contest, wrenching a weapon
    #: away (Takeaway) or a Shove's distance; 0 otherwise.
    str_bonus: int
    target_falls: bool
    actor_falls: bool
    #: Grab Weapon: the target's weapon, not the target (6E2 p.69).
    grab_weapon: bool
    #: Shove (6E2 p.81).
    shove: bool
    #: Crush: a Squeeze of a man already held (6E2 p.64).
    crush: bool
    #: Made as part of a Full Move (6E2 p.72's Move By / Move Through).
    fmove: bool
    #: +1 DC per this many metres of velocity, or None (6E2 p.101).
    velocity_divisor: int | None
    must_follow: MustFollow | None
    #: A Grab whose NND is Choke Hold's (6E2 p.86): Life Support (Self-
    #: Contained Breathing) is a defence against it too.
    choke: bool
    #: Martial Flash's Sense Group, or None.
    flash_sense: str | None


#: Elements removed from the EFFECT as they are recognised. Order matters:
#: a qualifier goes before the bare word it qualifies.
_ELEMENTS: tuple[tuple[str, str], ...] = (
    ("must_follow_block", r"\bmust follow block\b"),
    ("must_follow_grab", r"\bmust follow grab\b"),
    ("grab_weapon", r"\bgrab weapon\b"),
    ("take_away", r"\bto take weapon away\b"),
    ("grab", r"\bgrab (one|two|three|[123]) limbs?\b"),
    ("holding", r"\bfor holding on\b"),
    ("disarm_q", r"\bto disarm( roll)?\b"),
    ("disarm", r"\bdisarm\b"),
    ("shove", r"\bto shove\b"),
    ("target_falls", r"\btarget falls\b"),
    ("actor_falls", r"\byou fall\b"),
    ("token", r"\[(normaldc|killingdc|nnddc|strdc|flashdc|damage)\]"),
    ("strike", r"\bstrike\b"),
    ("crush", r"\bcrush\b"),
    ("fmove", r"\bfmove\b"),
)

_VELOCITY = re.compile(r"\+?v/(5|10)\b")
_FREE_STR = re.compile(r"\+(\d+) str\b")


def decode_effect(
    *, name: str, effect: str, damage: ManeuverDamage, damage_classes: int,
    adds_str: bool, hd_defense: str, sense_input: str,
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

    divisors = {int(m) for m in _VELOCITY.findall(residue)}
    if len(divisors) > 1:
        raise UnbuildableManeuver(name, effect, "two velocity divisors")
    residue = _VELOCITY.sub(" ", residue)
    free_str = [int(m) for m in _FREE_STR.findall(residue)]
    residue = _FREE_STR.sub(" ", residue)

    for label, pattern in _ELEMENTS:
        residue, n = re.subn(pattern, " ", residue)
        if n:
            seen.add(label)
    leftover = re.sub(r"[\s;,]+", " ", residue).strip()
    if leftover:
        raise UnbuildableManeuver(name, effect, f"unmodelled element {leftover!r}")

    grab = "grab" in seen
    disarm = "disarm" in seen
    grab_weapon = "grab_weapon" in seen
    shove = "shove" in seen
    crush = "crush" in seen
    fmove = "fmove" in seen
    must_follow = (MustFollow.BLOCK if "must_follow_block" in seen
                   else MustFollow.GRAB if "must_follow_grab" in seen else None)
    if "must_follow_block" in seen and "must_follow_grab" in seen:
        raise UnbuildableManeuver(name, effect, "must follow both a Block and a Grab")
    if "holding" in seen and not grab:
        raise UnbuildableManeuver(name, effect, "'for holding on' without a Grab")
    if "take_away" in seen and not grab_weapon:
        raise UnbuildableManeuver(name, effect, "'to take weapon away' without Grab Weapon")
    if damage is ManeuverDamage.MIXED:
        raise UnbuildableManeuver(name, effect, "two damage families")

    str_purpose = grab or disarm or grab_weapon or shove
    str_bonus = 0
    if free_str:
        # A HAND-WRITTEN "+10 STR". HD costs the maneuver on its DC count,
        # and writes that count as +5 STR a DC (6E2 p.94); a figure that
        # agrees with it is the same bonus spelled out, one that does not is
        # a number HD never priced, and is not guessed between.
        if len(free_str) > 1 or not str_purpose or damage is not ManeuverDamage.NONE:
            raise UnbuildableManeuver(name, effect, "a free-text STR figure")
        if free_str[0] != 5 * int(damage_classes):
            raise UnbuildableManeuver(
                name, effect,
                f"free-text +{free_str[0]} STR disagrees with its {damage_classes} DC")
        str_bonus = free_str[0]
    if damage is ManeuverDamage.STR:
        if not str_purpose:
            raise UnbuildableManeuver(name, effect, "a STR bonus with nothing to spend it on")
        if not adds_str:
            raise UnbuildableManeuver(name, effect, "[STRDC] that replaces STR rather than adding to it")
        # HD's `str_dc` writes the total as (DC + STR/5) * 5, so the bonus
        # over the wielder's own STR is the DCs at 5 STR each (6E2 p.94).
        str_bonus = 5 * int(damage_classes)
        damage = ManeuverDamage.NONE

    if damage is ManeuverDamage.NONE and not (
            grab or disarm or grab_weapon or shove):
        raise UnbuildableManeuver(
            name, effect,
            "no damage, Grab, Disarm, Takeaway or Shove to resolve (HD's damage "
            "type NONE does no damage: kirby-cost Maneuver.does_damage)")
    flash_sense = None
    if damage is ManeuverDamage.FLASH:
        flash_sense = _FLASH_SENSES.get((sense_input or "").strip().lower())
        if flash_sense is None:
            raise UnbuildableManeuver(
                name, effect, f"a Flash against no Sense Group the engine knows ({sense_input!r})")
        if seen - {"token", "strike"} or divisors:
            raise UnbuildableManeuver(name, effect, "a Flash with another effect")

    takes = sum(map(bool, (grab, disarm, grab_weapon, shove, crush)))
    if takes > 1:
        raise UnbuildableManeuver(name, effect, "two of Grab / Disarm / Takeaway / Shove / Crush")
    if (disarm or shove) and (damage is not ManeuverDamage.NONE or "target_falls" in seen):
        raise UnbuildableManeuver(name, effect, "a Disarm or Shove with another effect")
    if grab_weapon and damage is not ManeuverDamage.NONE:
        raise UnbuildableManeuver(name, effect, "a Takeaway that also does damage")
    if crush and (must_follow is not MustFollow.GRAB or damage is not ManeuverDamage.NORMAL):
        raise UnbuildableManeuver(name, effect, "a Crush that is not a Squeeze of a held man")
    if must_follow is MustFollow.GRAB and (grab or grab_weapon or disarm or shove or fmove):
        raise UnbuildableManeuver(name, effect, "a held man's maneuver that takes hold again")
    if must_follow is MustFollow.BLOCK and (takes or fmove):
        raise UnbuildableManeuver(name, effect, "a Block's follow-up that is not a blow")
    if fmove and (must_follow or crush or grab_weapon or shove
                  or damage is ManeuverDamage.FLASH):
        raise UnbuildableManeuver(name, effect, "an FMove with an effect a charge cannot carry")
    if divisors and damage is not ManeuverDamage.NORMAL:
        raise UnbuildableManeuver(name, effect, "velocity damage on a non-Normal attack")

    return MartialEffect(
        damage=damage, damage_classes=int(damage_classes), adds_str=bool(adds_str),
        grab=grab, disarm=disarm, str_bonus=str_bonus,
        target_falls="target_falls" in seen, actor_falls="actor_falls" in seen,
        grab_weapon=grab_weapon, shove=shove, crush=crush, fmove=fmove,
        velocity_divisor=next(iter(divisors)) if divisors else None,
        must_follow=must_follow,
        choke=(grab and damage is ManeuverDamage.NND
               and (hd_defense or "").upper() == HD_SPECIAL_DEFENSE),
        flash_sense=flash_sense,
    )


def decode_maneuver(mv) -> MartialEffect:
    """``decode_effect`` over a ``MartialManeuverView``."""
    return decode_effect(
        name=mv.name, effect=mv.effect, damage=ManeuverDamage(mv.damage_type),
        damage_classes=mv.dc_bonus, adds_str=mv.add_str,
        hd_defense=mv.hd_defense, sense_input=mv.sense_input,
    )


def velocity_dcs(effect: MartialEffect, velocity_mps: float) -> int:
    """+1 DC per FULL 10m (or 5m) of velocity; "anything less than that has
    no effect" (6E2 p.101)."""
    if effect.velocity_divisor is None:
        return 0
    return int(max(0.0, float(velocity_mps)) // effect.velocity_divisor)


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
#: PD Resistant Protection."
NND_DEFENSE = "Resistant Protection (PD) or rigid armor"
#: 6E2 p.86, Choke: "The defense against this NND is having rigid armor on
#: the neck, Resistant Protection PD on the neck, or Life Support:
#: Self-Contained Breathing." The last is matched by
#: `defense._target_has_named_defense` on the combatant's own Life Support.
CHOKE_DEFENSE = (
    "Resistant Protection (PD) or rigid armor, or Life Support "
    "(Self-Contained Breathing)")


def maneuver_power(mv, effect: MartialEffect, *, strength: int, velocity_mps: float):
    """The ``AttackPower`` a maneuver's Attack Roll and damage go through.

    Built the way ``HeroCombatant.str_strike_view`` builds the bare Strike
    --- the deleted api driver's own composition ("a STR strike modified by
    the maneuver's OCV/DCV/DC") --- with the damage made the maneuver's:

    * NORMAL: STR dice (kirby-cost's ``strike_dice``, half die included,
      6E2 p.98) + 1d6 per DC (6E2 p.101) + 1d6 per full 10m (5m) of
      velocity (6E2 p.101). STR only if the maneuver adds it.
    * KILLING: DCs + STR/5 (6E2 p.93 "as if to an HKA"; 6E1 p.244), at 3 DC
      per die (6E2 p.99) --- the driver bumped Normal dice and switched the
      type, so a Killing Strike rolled 1d6 of Killing per DC.
    * NND: 1/2d6 per DC, no STR (6E2 p.99, p.101), STUN only (6E1 p.328).
    * NONE (a Grab, Disarm, Takeaway or Shove) and FLASH: no damage dice; the
      roll is the whole of it (a Flash rolls its own dice, 6E1 p.228).

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
        full, half = str_full + dc + velocity_dcs(effect, velocity_mps), str_half
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
        avad=nnd,
        avad_defense=(CHOKE_DEFENSE if effect.choke
                      else NND_DEFENSE if nnd else ""),
        active_points=int(strength) if uses_str else 0,
        reduced_end=not uses_str,
    )


def describe_effect(effect: MartialEffect, *, strength: int) -> str:
    """The menu's one-line statement of what the maneuver will do."""
    from kirby_cost.engine.damage import str_damage_classes, strike_dice

    parts: list[str] = []
    if effect.must_follow is MustFollow.BLOCK:
        parts.append("after your Block")
    if effect.must_follow is MustFollow.GRAB:
        parts.append("on the man you hold")
    if effect.fmove:
        parts.append("at the end of a Full Move")
    if effect.damage is ManeuverDamage.NORMAL:
        full, half = (strike_dice(strength) if effect.adds_str else (0, False))
        vel = (f" +1d6 per {effect.velocity_divisor}m of velocity"
               if effect.velocity_divisor else "")
        parts.append(f"{full + effect.damage_classes}{'½' if half else ''}d6"
                     f"{vel}{' Squeeze' if effect.crush else ''}")
    elif effect.damage is ManeuverDamage.KILLING:
        f, h, p = killing_dice(effect.damage_classes + (
            str_damage_classes(strength) if effect.adds_str else 0))
        parts.append(f"HKA {f}{'½' if h else ''}d6{'+1' if p else ''}")
    elif effect.damage is ManeuverDamage.NND:
        f, h = nnd_dice(effect.damage_classes)
        parts.append(f"{f}{'½' if h else ''}d6 NND")
    elif effect.damage is ManeuverDamage.FLASH:
        parts.append(f"{effect.damage_classes}d6 Flash ({effect.flash_sense})")
    bonus = f" (+{effect.str_bonus} STR)" if effect.str_bonus else ""
    if effect.grab:
        parts.append("Grab" + (f" (+{effect.str_bonus} STR to hold)" if effect.str_bonus else ""))
    if effect.disarm:
        parts.append("Disarm" + bonus)
    if effect.grab_weapon:
        parts.append("take his weapon" + bonus)
    if effect.shove:
        parts.append(f"Shove {(strength + effect.str_bonus) // 5}m")
    if effect.target_falls:
        parts.append("target falls")
    if effect.actor_falls:
        parts.append("you fall")
    return ", ".join(parts)
