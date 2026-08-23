"""Bring the house down — destroying terrain, and what it drops on whom.

Most virtual tabletops treat scenery as decoration. Here a support column is a
combatant with BODY and defences, and destroying a load-bearing one collapses
what it held up, recursively, and hands you the list of people who were
standing on it.

Exercises:
  - ObjectCombatant   (scenery with BODY, defences and a material)
  - StructuralGraph   (what holds up what, which parts bear load, and how
                       many supporters each element needs to stand)
  - cascade_destruction (redundant support, recursive collapse, and who
                       starts falling)

No dependencies beyond the package.

Run with:
    .venv/bin/python examples/bring_the_house_down.py
"""
from __future__ import annotations

from kirby_combat.breakables.object_combatant import ObjectCombatant
from kirby_combat.breakables.structure import (
    StructuralGraph, StructuralLink, cascade_destruction,
)


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def scenery(id_: str, name: str, *, body: int, pd: int, ed: int,
            material: str) -> ObjectCombatant:
    """A piece of terrain that can be attacked like anything else."""
    return ObjectCombatant(
        id=id_, name=name,
        ocv=0, dcv=0, omcv=0, dmcv=0,
        spd=0, dex=0, ego=0, str_=0, con=0, pre=0, rec=0,
        pd=pd, ed=ed, rpd=pd, red=ed, md=0,
        power_defense=0, flash_defense=0,
        max_stun=0, max_body=body, max_end=0,
        current_stun=0, current_body=body, current_end=0,
        attacks=[], defenses=[], material=material,
    )


# ─────────────────────────────────────────────────────────────────────────────
# A warehouse: two columns hold the mezzanine, the mezzanine holds the roof
# ─────────────────────────────────────────────────────────────────────────────

PARTS = {
    o.id: o for o in (
        scenery("column_a", "West Support Column", body=8, pd=6, ed=4, material="concrete"),
        scenery("column_b", "East Support Column", body=8, pd=6, ed=4, material="concrete"),
        scenery("mezzanine", "Steel Mezzanine", body=12, pd=8, ed=6, material="steel"),
        scenery("roof", "Warehouse Roof", body=10, pd=5, ed=3, material="steel"),
        scenery("crate", "Stack of Crates", body=3, pd=2, ed=1, material="wood"),
    )
}

STRUCTURE = StructuralGraph(
    links=[
        StructuralLink(supporter_id="column_a", supported_id="mezzanine"),
        StructuralLink(supporter_id="column_b", supported_id="mezzanine"),
        StructuralLink(supporter_id="mezzanine", supported_id="roof"),
    ],
    load_bearing_ids={"column_a", "column_b", "mezzanine"},
)

#: Who is standing on what when it goes.
STANDING_ON = {
    "mezzanine": ["sniper"],
    "roof": ["lookout", "gargoyle"],
}


def show_structure() -> None:
    print("  The warehouse, as the engine sees it:\n")
    print("        roof            ← lookout, gargoyle")
    print("          ↑ held by")
    print("      mezzanine         ← sniper")
    print("        ↑     ↑ held by")
    print("   column_a  column_b")
    print("\n  load-bearing:", ", ".join(sorted(STRUCTURE.load_bearing_ids)))
    print("  scenery is attackable — each part has real BODY and defences:")
    for p in PARTS.values():
        flag = "load-bearing" if p.id in STRUCTURE.load_bearing_ids else "decorative"
        print(f"     {p.name:22} BODY {p.current_body:>2}  "
              f"rPD {p.rpd} rED {p.red}  {p.material:<9} {flag}")


def main() -> None:
    rule("BRING THE HOUSE DOWN")
    show_structure()

    # ── 1. Shoot something decorative ────────────────────────────────────────
    rule("1. Destroy the crates — nothing was holding them up")
    flat = cascade_destruction(STRUCTURE, "crate", STANDING_ON)
    print(f"  destroyed: {flat.initial_destroyed_id}")
    for e in flat.cascade_events:
        print(f"     collapsed: {PARTS[e.element_id].name}  ({e.reason})")
    print(f"  combatants dropped:  {flat.triggered_falling_for or 'none'}")
    print("  → the crates were holding nothing up, so the cascade stops at")
    print("    the crates themselves. The building shrugs.")

    # ── 2. Take out one column — the load is shared ──────────────────────────
    rule("2. Destroy ONE column — the mezzanine still has the other")
    one = cascade_destruction(STRUCTURE, "column_a", STANDING_ON)
    print(f"  destroyed: {one.initial_destroyed_id}")
    for e in one.cascade_events:
        print(f"     collapsed: {PARTS[e.element_id].name}  ({e.reason})")
    print(f"  combatants dropped:  {one.triggered_falling_for or 'none'}")
    for line in one.audit:
        print(f"     · {line}")
    print("  → support is redundant: the mezzanine needs one intact column")
    print("    and still has east. Nobody falls.")

    # ── 2b. Now take the second one ──────────────────────────────────────────
    rule("2b. Destroy the OTHER column — now it comes down")
    both = cascade_destruction(
        STRUCTURE, "column_b", STANDING_ON,
        already_destroyed={"column_a"},      # the first one is already gone
    )
    print(f"  destroyed: {both.initial_destroyed_id}  (column_a already gone)")
    for e in both.cascade_events:
        print(f"     collapsed: {PARTS[e.element_id].name}  ({e.reason})")
    print(f"  combatants dropped:  {sorted(both.triggered_falling_for)}")
    print("  → pass `already_destroyed` so a structure worn down across")
    print("    several phases converges instead of healing between attacks.")

    # ── 3. Take out the mezzanine itself ─────────────────────────────────────
    rule("3. Destroy the mezzanine — everything above it comes with it")
    big = cascade_destruction(STRUCTURE, "mezzanine", STANDING_ON)
    print(f"  destroyed: {big.initial_destroyed_id}")
    for e in big.cascade_events:
        print(f"     collapsed: {PARTS[e.element_id].name}  ({e.reason})")
    print(f"  affected:  {sorted(big.affected_combatants) or 'none'}")
    print(f"  now falling: {sorted(big.triggered_falling_for) or 'none'}")
    print("\n  The collapse is recursive: the roof was never attacked, but the")
    print("  thing holding it up stopped existing. Everyone standing on either")
    print("  surface is handed to the falling rules — which is where the")
    print("  scene's elevation and the falling-damage resolver take over.")

    # ── 4. A GM who wants all three pillars to matter ────────────────────────
    rule("4. When one spare is not enough — required_supporters")
    dome = StructuralGraph(
        links=[StructuralLink(f"pillar_{i}", "dome") for i in (1, 2, 3)],
        load_bearing_ids={"pillar_1", "pillar_2", "pillar_3"},
        required_supporters={"dome": 3},     # this dome needs all three
    )
    r = cascade_destruction(dome, "pillar_1", {"dome": ["cultist"]})
    print("  A dome on three pillars, declared to need all three:")
    for e in r.cascade_events:
        print(f"     collapsed: {e.element_id}  ({e.reason})")
    print(f"  combatants dropped: {r.triggered_falling_for}")
    print("  → one pillar down and the dome goes. The default is 1, so this")
    print("    is opt-in for the structures a GM wants to be fragile.")

    rule("END")


if __name__ == "__main__":
    main()
