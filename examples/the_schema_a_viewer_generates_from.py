#!/usr/bin/env python3
"""The schema a viewer generates from, and the state it checks itself against.

A front end that draws these fights holds a fold of the event log: it turns
the record into positions, bars and conditions on a board. That fold is a
VIEW, not a rule — and a view nobody checks drifts. This example shows the
two engine surfaces that make the check possible.

Run it:

    python examples/the_schema_a_viewer_generates_from.py
"""
from __future__ import annotations

import json

from kirby_combat import state_view
from kirby_combat.models import StatBlockCombatant
from kirby_combat.schema import SCHEMA_PATH
from kirby_combat.serialization import json_schema
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import RAW_SUPERHEROIC
from kirby_dice import RandomRoller


def a_fighter(id_: str) -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=id_.title(), ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def main() -> None:
    # 1. THE CONTRACT. One schema per event kind, derived from the union
    #    itself, so a generator on the other side cannot be given a kind
    #    this engine does not emit or miss one it does.
    schema = json_schema()
    # The VERSION comes off the shipped document, not off the derivation.
    # `json_schema()` stamps `importlib.metadata`, which reports whatever
    # distribution this interpreter happens to resolve — in a source
    # checkout that can lag the repository. The file in the package is
    # the artefact a consumer generates from, so it is the one to quote.
    shipped = json.loads(SCHEMA_PATH.read_text())
    print(f"engine {shipped['x-kirby-combat-version']}, "
          f"{len(schema['oneOf'])} event kinds")
    print("  e.g.", json.dumps(
        sorted(schema["$defs"]["VitalsChanged"]["properties"])))

    # 2. THE CHECK. A viewer folds the log for display; this is the fold
    #    the engine itself performs, in a shape a viewer can compare
    #    against field by field. Rewind the session to any sequence and
    #    project it here to get the fight as it stood at that point.
    session = CombatSession.create(
        id="demo", combatants=[a_fighter("alice"), a_fighter("bob")],
        scene=None, template=RAW_SUPERHEROIC, dice_roller=None,
    )
    # THE ROLLER IS REQUIRED, and this is why: the perception fold rolls
    # for an Invisible target inside the 2 m Fringe and for a Hidden
    # target's Stealth contest. A view that seeded itself would answer
    # differently every time it was asked about the same sequence, so a
    # replay would not replay. A caller reading sequence N passes a
    # roller derived from N and gets the same board back every time.
    view = state_view(session, roller=RandomRoller(seed=1))
    print(f"turn {view.turn} segment {view.segment} status {view.status}, "
          f"next {view.next_actor_id}")
    for c in view.combatants:
        where = "off the map" if c.position is None else (
            f"({c.position.x:.1f}, {c.position.z:.1f}) facing "
            f"{c.position.facing:.2f}")
        print(f"  {c.name}: {c.current_stun} STUN, {c.current_body} BODY, "
              f"{c.health}, down={c.down}, {where}")
        # WHO HE CAN SEE, through the engine's one perception predicate.
        # A viewer draws its fog from THIS rather than deciding for
        # itself who is visible to whom — the rule stays in one place and
        # the board just shows what the rule said.
        print(f"    perceives: {c.perceives or 'nobody'}")


if __name__ == "__main__":
    main()
