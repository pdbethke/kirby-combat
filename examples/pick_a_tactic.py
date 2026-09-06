"""What kind of fighter is this, and what does the book advise — no database.

The worked example the import-surface ratchet owes for `classify_role` and
`tactics_for`, and the second half of what enumeration started.
`examples/what_can_i_do.py` shows the engine listing what is LEGAL; this
shows it saying what KIND of combatant is choosing, and which tactics apply.

Why the classification is not cosmetic: abort-readiness gates a brawler OFF
at or above 50% STUN. A martial artist misread as a brawler therefore stands
and eats hits instead of aborting to its Martial Dodge -- so `classify_role`
returning the wrong string changes what happens in the fight, not just what
it is called.

Each tactic carries a `Basis` saying where it comes from. Twenty tactics,
eight with a citation for the MECHANISM the book defines, and two with a
citation for DOCTRINE -- 6E2 p39, "Evening The Odds", which names five ways
to affect a foe you cannot hurt. The rest are judgement, and say so, because
an engine that ships heuristics beside rules owes the reader the difference.

This is a demo script, not a test. Run with:
    .venv/bin/python examples/pick_a_tactic.py
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from kirby_combat import Basis, classify_role, tactics_for
from kirby_combat.tactics.base import Situation

_IDS = itertools.count(8_000_001)


@dataclass
class _Power:
    """The little of an attack that classification actually reads."""
    xmlid: str
    range_m: float = 0.0
    damage_dice: int = 8
    name: str = ""
    id: int = field(default_factory=lambda: next(_IDS))


@dataclass
class _Stats:
    """What tactics read off a combatant's sheet. A real caller passes
    `HeroCombatant.combat_stats()`; nothing here needs a character file."""
    str_: int = 20
    ocv: int = 8
    dcv: int = 8
    spd: int = 4
    pre: int = 15
    pd: int = 10
    ed: int = 10
    rpd: int = 4
    red: int = 4
    max_stun: int = 40
    max_end: int = 40
    max_body: int = 12
    ego: int = 12
    omcv: int = 3
    dmcv: int = 3
    int_: int = 15
    con: int = 15
    body: int = 12
    rec: int = 5


@dataclass
class _Maneuver:
    """A bought martial maneuver. Any of attack/dodge/block makes an artist."""
    is_attack: bool = False
    is_dodge: bool = False
    is_block: bool = False


class _Fighter:
    """A stub combatant. Classification needs no character file and no rows."""

    def __init__(self, name, attacks=(), maneuvers=(), stun=40, max_stun=40):
        self.id = name
        self.name = name
        self.attacks = list(attacks)
        self._maneuvers = list(maneuvers)
        # Tactics read live state straight off the combatant (rather than
        # off combat_stats) because it changes mid-fight.
        self.current_stun = stun
        self.max_stun = max_stun
        self.current_end = 40
        self.max_end = 40
        self.current_body = 12
        self.max_body = 12
        self.statuses: set[str] = set()
        self.position = None

    def maneuver_view(self):
        return self._maneuvers

    def combat_stats(self):
        return _Stats()


def _describe(basis: Basis) -> str:
    if basis.is_raw:
        return f"RAW  doctrine {basis.doctrine}, mechanism {basis.mechanism or '-'}"
    if basis.mechanism:
        return f"mechanism {basis.mechanism}; when to use it is judgement"
    return "judgement"


def main() -> None:
    cast = [
        _Fighter("Li Chun", [_Power("HANDTOHANDATTACK")],
                 [_Maneuver(is_dodge=True), _Maneuver(is_attack=True)]),
        _Fighter("Sniper", [_Power("BLAST", range_m=200)]),
        _Fighter("Mentalist", [_Power("MINDCONTROL", range_m=200)]),
        _Fighter("Medic", [_Power("HEALING")]),
        _Fighter("Thug", [_Power("STRIKE")]),
    ]

    print("Roles — read off the build, with no database in the process:\n")
    for f in cast:
        print(f"  {f.name:<12} {classify_role(f)}")

    # A mental attack at 200m is a controller, not a blaster: the decision
    # tree is ordered, and the order is itself the rule.
    print("\n  (Mentalist has a 200m attack and is still a controller —")
    print("   first match wins, so the ordering IS the rule.)")

    actor, enemy = cast[0], cast[4]
    situation = Situation(actor=actor, allies=[], enemies=[enemy])
    applicable = tactics_for(situation)

    print(f"\nTactics applying to {actor.name} ({classify_role(actor)}) "
          f"— {len(applicable)} of 20:\n")
    for t in applicable[:8]:
        print(f"  [{t.priority:>3}] {t.name:<26} {_describe(t.basis)}")


if __name__ == "__main__":
    main()
