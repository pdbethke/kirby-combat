"""What can this combatant legally do right now — with no database at all.

This is the worked example the import-surface ratchet owed for
`enumerate_actions`, and it is also the point of moving enumeration into the
engine at all.

Before the move, "which actions are legal this phase" was answered inside
kirby-api. Legality is a rule, so a consumer owning it meant the engine could
not answer its own question, and no fight could be driven without a web
application and a Postgres behind it. A grep for `enumerate_actions` across
`kirby_combat` returned nothing.

So the thing to notice below is what is ABSENT: no session, no engine, no
`SessionLocal`, no HTTP. Two combatants built from stubs, one call, a menu.
That is the whole demonstration -- a fight can be reasoned about in memory.

The menu is also the interface a chooser sees. `enumerate_actions` says what
is LEGAL; something else picks one. A scripted chooser and a model-backed one
are indistinguishable from here, which is what keeps the engine free of any
opinion about what does the choosing.

This is a demo script, not a test. Run with:
    .venv/bin/python examples/what_can_i_do.py
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from kirby_combat import LegalAction, enumerate_actions
from kirby_combat.hero_view import HeroCombatant, HeroCombatState


#: Synthetic objects still need identities. kirby indexes on ids, and the bare
#: STR strike takes its identity from the STR characteristic's id -- falling
#: back to xmlid+name is what once made 630 corpus objects share a token,
#: silently. So even a stub carries real ids.
_IDS = itertools.count(9_000_001)


@dataclass
class _StubChar:
    """A characteristic object, which is where the unarmed strike gets its id."""
    xmlid: str
    id: int = field(default_factory=lambda: next(_IDS))


class _StubHero:
    """Stands in for a loaded build so this script needs no character file.

    Enumeration reads very little off a hero: the characteristics the offers
    are gated on, and the powers that become attack offers. A real caller
    passes a `LoadedHero` from kirby-cost.
    """

    def __init__(self, name: str, *, str_: int = 20) -> None:
        self.name = name
        self.powers: list = []
        self.skills: list = []
        self.perks: list = []
        self.talents: list = []
        self.complications: list = []
        self.equipment: list = []
        self.characteristics = [_StubChar("STR"), _StubChar("DEX"),
                                _StubChar("CON")]
        self._chars = {
            "STR": str_, "DEX": 15, "CON": 15, "INT": 15, "EGO": 12,
            "PRE": 15, "OCV": 8, "DCV": 8, "OMCV": 3, "DMCV": 3, "SPD": 4,
            "PD": 10, "ED": 10, "REC": 5, "END": 40, "BODY": 12, "STUN": 40,
            "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
        }

    def characteristic_value(self, xmlid: str) -> int:
        return self._chars.get(xmlid.upper(), 0)

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        """The value BEFORE any in-fight adjustment. `combat_stats()` folds
        Aid/Drain onto this base and reads it instead of
        `characteristic_value`; no stub here has been adjusted, so they agree.
        """
        return self.characteristic_value(xmlid)


def _combatant(cid: str, *, str_: int = 20) -> HeroCombatant:
    return HeroCombatant(
        id=cid, hero=_StubHero(cid, str_=str_),   # type: ignore[arg-type]
        state=HeroCombatState(current_stun=40, current_body=12, current_end=40),
        knockback_resistance=0,
    )


def _show(title: str, actions: list[LegalAction]) -> None:
    print(f"\n{title} — {len(actions)} legal action(s)")
    for a in actions:
        print(f"  [{a.action_id}] {a.summary}")


def main() -> None:
    brick = _combatant("brick", str_=40)
    thug = _combatant("thug", str_=10)

    # No scene: the actor and one enemy, nothing else. This is the smallest
    # question the engine can be asked.
    _show("Toe to toe, no terrain", enumerate_actions(brick, [thug]))

    # Two enemies. Every attack offer is per (power x perceivable enemy), so
    # the menu grows with the target list rather than with the rules.
    goon = _combatant("goon", str_=10)
    _show("Two enemies", enumerate_actions(brick, [thug, goon]))

    # No enemies at all: the defensive and preparatory offers remain, which
    # is what makes "nothing to attack" a legal position rather than a stall.
    _show("Alone", enumerate_actions(brick, []))


if __name__ == "__main__":
    main()
