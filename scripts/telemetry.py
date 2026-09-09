#!/usr/bin/env python3
"""Run the benchmark N times and write one CSV row per decision.

A TOOL BESIDE THE ENGINE, NOT PART OF IT. kirby-combat is a Tier 1 pure
engine --- no DB, no web framework, tested in memory --- so anything that
persists results lives out here in `scripts/`. The engine's contribution
is `TacticChooser.picks`, which is just a list.

WHY CSV. Twelve fights produce about 300 decision rows; a thousand
produce thirty thousand. That is a `Counter`, not a warehouse. CSV is
queryable in place the moment one `group by` stops being enough:

    duckdb -c "select tactic, count(*) c from 'runs/*.csv'
               where not fell_back group by 1 order by c desc"

Reach for real storage when the question becomes longitudinal --- a
fallback-rate trend across commits, or which tactics went silent after a
change --- and not before.

    python scripts/telemetry.py --runs 25 --out runs/
    python scripts/telemetry.py --runs 25 --power-lad

Needs the same licensed build docs the benchmark does, and says so and
exits cleanly without them.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "examples"))

#: What one decision looks like on disk. Flat on purpose: a row per
#: choice, the fight's outcome repeated on every row of that fight, so a
#: single `group by` can ask "which tactics show up in fights we won".
FIELDS = (
    "seed", "phase", "turn", "segment", "actor", "side",
    "tactic", "fell_back", "basis", "action_kind", "action_id",
    "winner", "decided", "phases",
)


def _fight(seed: int, with_power_lad: bool, make_chooser=None):
    """One fight. `make_chooser` builds the seat that decides each Phase.

    INJECTED, so the same benchmark can be driven by doctrine or by a
    model without a second copy of the setup. It defaults to
    `TacticChooser`; kirby-ai's runner passes a `DeliberatingChooser`, and
    the two produce the same CSV because both keep the same shape of pick
    record. A benchmark you can only run one way cannot answer whether the
    other way is better.
    """
    from dataclasses import replace

    from the_ok_corral import (
        COWBOYS, LAWMEN, arm, arsenal, the_interloper, the_lot, the_sides,
    )
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import TacticChooser, run_encounter
    from kirby_combat.scene.scene import Position
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    guns = arsenal()
    # The sides carry their objectives -- see `the_ok_corral.the_sides`.
    law, cow = the_sides()
    fighters = ([arm(n, a, w, law, guns) for n, a, w in LAWMEN]
                + [arm(n, a, w, cow, guns) for n, a, w in COWBOYS])
    scene = the_lot()
    if with_power_lad:
        lad = the_interloper()
        if lad is not None:
            fighters.append(lad)
            scene = replace(scene, combatant_positions={
                **scene.combatant_positions,
                "power_lad": Position(2.5, 0.5, 0.0),
            })

    roller = RandomRoller(seed=seed)
    chooser = make_chooser() if make_chooser is not None else TacticChooser()
    session = CombatSession.create(
        id=f"run-{seed}", combatants=fighters, scene=scene,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller).start()
    result = run_encounter(
        Encounter(id=f"t-{seed}", turn=1, segment=12, sessions=[session]),
        chooser, roller=roller, on_unresolvable="skip", max_turns=40)
    return chooser, result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=12)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--power-lad", action="store_true")
    args = ap.parse_args()

    from the_ok_corral import BUILDS

    if not BUILDS:
        print("Needs KIRBY_CORRAL_BUILDS (and KIRBY_COST_HDT), the same "
              "licensed build docs the benchmark wants. Nothing to do.")
        return

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / ("power-lad.csv" if args.power_lad else "historical.csv")

    from collections import Counter

    from kirby_combat.side import Side

    fired, fallbacks, total = Counter(), 0, 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for seed in range(args.runs):
            chooser, result = _fight(seed, args.power_lad)
            sides = {c.id: Side.of(c).name
                     for c in result.encounter.sessions[0].combatants.values()}
            for i, pick in enumerate(chooser.picks, 1):
                total += 1
                if pick.fell_back:
                    fallbacks += 1
                else:
                    fired[pick.tactic] += 1
                writer.writerow({
                    "seed": seed, "phase": i,
                    "turn": pick.turn, "segment": pick.segment,
                    "actor": pick.actor_id,
                    "side": sides.get(pick.actor_id, ""),
                    "tactic": pick.tactic or "", "fell_back": pick.fell_back,
                    "basis": pick.basis, "action_kind": pick.action_id.split(":")[0],
                    "action_id": pick.action_id,
                    "winner": result.winner.name if result.winner else "",
                    "decided": result.complete, "phases": result.phases,
                })

    print(f"wrote {path}  ({total} decisions over {args.runs} fights)")
    share = (100 * fallbacks // total) if total else 0
    print(f"  by doctrine {total - fallbacks}   by FALLBACK {fallbacks} ({share}%)")
    for name, count in fired.most_common(8):
        print(f"    {count:>5}  {name}")


if __name__ == "__main__":
    main()
