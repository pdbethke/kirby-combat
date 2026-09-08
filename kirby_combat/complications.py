"""Reading a character's complications for the fight.

`Situation` has carried `actor_complications` and `enemy_complications`
since tactics existed, and two tactics read them --- `bait_enraged` and
`exploit_susceptibility`. NOTHING IN THE LOOP EVER FILLED THEM, so in
every loop-driven fight this engine has run both tactics saw an empty
list and could never fire. This module is the missing half.

WHERE THE DATA ACTUALLY IS, recorded because three separate probes
guessed wrong before the object was listed:

    the TEXT     `input`         "Code vs Killing", "Overconfidence"
    NOT          `input_value`   absent
    NOT          `name`          empty on every psych comp in the corpus
    the SEVERITY the adders, or `adder_string` --- HD writes
                 "Intensity Is Total, Situation Is (Common)"

The severity matters beyond flavour: 6E2 p.138's Presence Attack
Modifiers Table prices a psychological complication at Moderate +1d6,
Strong +2d6, Total +3d6 when an attack plays to it.
"""
from __future__ import annotations

import re
from typing import Any

from kirby_combat.tactics.base import Complication

#: HD writes severity into a free-text adder string. The three words are
#: the book's own rungs (6E2 p.138), so matching them is reading HD's
#: rendering rather than inventing a scale.
_INTENSITY = re.compile(r"Intensity\s+Is\s+(Moderate|Strong|Total)", re.I)

#: Tokens too common to discriminate anything. `trigger_keywords` exists
#: for matching "rage" or "fire", and a keyword list full of "is" and
#: "the" matches everything and means nothing.
_NOISE = frozenset({"is", "a", "an", "the", "of", "vs", "and", "or", "to",
                    "in", "on", "at", "by", "for", "with"})


def _keywords(text: str) -> tuple[str, ...]:
    words = [w for w in re.split(r"[^A-Za-z]+", (text or "").lower()) if w]
    return tuple(w for w in words if w not in _NOISE)


def _adders_of(raw: Any) -> dict[str, str]:
    """Severity and circumstance, however this build recorded them.

    Structured adders first; the rendered string is the fallback, because
    a build that came through the doc keeps the string when the adder
    objects did not survive.
    """
    out: dict[str, str] = {}
    for adder in (getattr(raw, "adders", None) or []):
        xmlid = (getattr(adder, "xmlid", "") or "").upper()
        option = (getattr(getattr(adder, "selected_option", None), "xmlid", None)
                  or getattr(adder, "option_id", None) or "")
        if xmlid and option:
            out[xmlid] = str(option).upper()
    if "INTENSITY" not in out:
        found = _INTENSITY.search(getattr(raw, "adder_string", "") or "")
        if found:
            out["INTENSITY"] = found.group(1).upper()
    return out


def complications_of(combatant: Any) -> list[Complication]:
    """Every complication on this combatant, as tactics want them.

    Empty for anything with no build --- synthetic stat blocks, vehicles,
    breakables --- because most of this engine's own suite is made of
    those and none of them has a character sheet.
    """
    hero = getattr(combatant, "hero", None)
    raws = getattr(hero, "complications", None) or []
    out: list[Complication] = []
    for raw in raws:
        text = (getattr(raw, "input", "") or "").strip()
        alias = (getattr(raw, "alias", "") or "").strip()
        out.append(Complication(
            xmlid=(getattr(raw, "xmlid", "") or "").upper(),
            # The text if there is one, else the generic alias -- "Hunted"
            # says something on its own; "Psychological Complication" does
            # not, which is why `input` is preferred.
            name=text or alias,
            alias=alias,
            notes=(getattr(raw, "notes", "") or ""),
            levels=int(getattr(raw, "levels", 0) or 0),
            trigger_keywords=_keywords(f"{text} {alias}"),
            adders=_adders_of(raw),
        ))
    return out
