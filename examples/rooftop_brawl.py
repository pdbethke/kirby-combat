"""Rooftop brawl — a narrated mini-combat demonstrating kirby-combat through Task 18.

Runs end-to-end on the Phase 2 engine. Exercises:
  - CombatSession lifecycle + Timeline (SPD chart phases)
  - Phase 1 attack pipeline (resolve_to_hit + compute_damage + compute_defense)
  - Reactive Dodge (+3 DCV)
  - Knockback that pushes a target off a rooftop edge
  - Scene-aware falling damage
  - Recovery (Post-Segment 12)
  - Per-action rewind

This is a demo script, not a test. Run with:
    .venv/bin/python examples/rooftop_brawl.py
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.actions.movement.knockback_movement import resolve_knockback_movement
from kirby_combat.actions.reactive.dodge import Dodge
from kirby_dice import FakeRoller
from kirby_combat.models import (
    AttackInput, AttackPower, DefenseItem, DiceValues, StatBlockCombatant,
)
from kirby_combat.resolution.damage import compute_damage
from kirby_combat.resolution.defense import compute_defense
from kirby_combat.resolution.recovery import compute_recovery
from kirby_combat.resolution.to_hit import resolve_to_hit
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session import CombatSession, build_acting_order_for_segment
from kirby_combat.template import RAW_SUPERHEROIC


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cast
# ─────────────────────────────────────────────────────────────────────────────

ENERGY_BLAST = AttackPower(
    xmlid="ENERGYBLAST", name="Energy Blast",
    damage_dice=10, half_die=False, plus_one=False,
    damage_type="normal", defense_type="ed",
    range_m=200, uses_str=False, str_min=0,
    armor_piercing=0, penetrating=0, increased_stun_mult=0,
)

NIGHTHAWK = StatBlockCombatant(
    id="nighthawk", name="Nighthawk",
    ocv=9, dcv=8, omcv=4, dmcv=4,
    spd=5, dex=23, ego=15, int_=13, str_=20, con=20, pre=20, rec=8,
    pd=10, ed=10, rpd=4, red=4, md=5,
    power_defense=0, flash_defense=0,
    max_stun=40, max_body=14, max_end=40,
    current_stun=40, current_body=14, current_end=40,
    attacks=[ENERGY_BLAST],
    defenses=[DefenseItem(name="Armored Cape", pd=4, ed=4, rpd=4, red=4, is_resistant=True)],
)

VOLT = StatBlockCombatant(
    id="volt", name="Volt",
    ocv=8, dcv=7, omcv=3, dmcv=3,
    spd=5, dex=20, ego=12, int_=18, str_=15, con=23, pre=18, rec=7,
    pd=8, ed=15, rpd=2, red=8, md=4,
    power_defense=0, flash_defense=0,
    max_stun=45, max_body=12, max_end=50,
    current_stun=45, current_body=12, current_end=50,
    attacks=[ENERGY_BLAST],
    defenses=[DefenseItem(name="Force Field", ed=12, red=8)],
    knockback_resistance=2,  # 2m KB resistance
)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scene — rooftop with ground below and a parapet wall
# ─────────────────────────────────────────────────────────────────────────────

SCENE = Scene(
    id="warehouse-roof", name="Industrial District Warehouse — Roof",
    bounds=SceneBounds(0, 0, 0, 30, 30, 60),
    surfaces=[
        Surface(id="ground", name="Street",
                polygon_xy=[(0, 0), (30, 0), (30, 30), (0, 30)],
                elevation_m=0.0, surface_type="ground",
                cover_level=0, is_supporting=True),
        Surface(id="roof", name="Warehouse Roof",
                polygon_xy=[(5, 5), (25, 5), (25, 25), (5, 25)],
                elevation_m=12.0, surface_type="rooftop",
                cover_level=0, is_supporting=True),
    ],
    walls=[
        Wall(id="parapet", name="Roof Parapet",
             segment=(Position(5, 5, 12), Position(25, 5, 12)),
             height_m=1.2, blocks_los=True, blocks_movement=True,
             cover_level=2, body=4),
    ],
    hazards=[],
    ambient=AmbientConditions(light_level=2, weather="rain"),
).place_combatant("nighthawk", Position(8, 12, 12)).place_combatant("volt", Position(20, 12, 12))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Helpers — apply Phase 1 attack result to session combatants
# ─────────────────────────────────────────────────────────────────────────────

def resolve_attack(attacker: StatBlockCombatant, target: StatBlockCombatant, dice: DiceValues,
                   *, ocv_mod: int = 0, dcv_mod: int = 0):
    """Run the Phase 1 pipeline. Returns (stun_dealt, body_dealt, hit, audit)."""
    inp = AttackInput(
        attacker=attacker, target=target, power=ENERGY_BLAST,
        distance_m=8.0, aim=None, dice=dice,
        ocv_modifier=ocv_mod, dcv_modifier=dcv_mod, dc_modifier=0,
    )
    th = resolve_to_hit(inp, RAW_SUPERHEROIC)
    if not th.hit:
        return 0, 0, False, [f"  → MISS: rolled {th.roll} vs {th.target_number}"]

    dmg = compute_damage(ENERGY_BLAST, dice, RAW_SUPERHEROIC, hit_location=None)
    defn = compute_defense(target, ENERGY_BLAST)
    stun = max(0, dmg.stun - defn.total_defense)
    body = max(0, dmg.body - defn.total_defense)
    audit = [
        f"  → HIT: rolled {th.roll} vs {th.target_number} (margin {th.margin})",
        f"     raw  STUN={dmg.stun} BODY={dmg.body}",
        f"     def  total={defn.total_defense} resistant={defn.resistant_defense}",
        f"     dealt STUN={stun} BODY={body}",
    ]
    return stun, body, True, audit


def apply_damage(session: CombatSession, target_id: str, stun: int, body: int) -> CombatSession:
    target = session.combatants[target_id]
    new_target = replace(
        target,
        current_stun=target.current_stun - stun,
        current_body=target.current_body - body,
    )
    new_combatants = dict(session.combatants)
    new_combatants[target_id] = new_target
    return replace(session, combatants=new_combatants)


def banner(text: str) -> None:
    print(f"\n{'═' * 70}\n  {text}\n{'═' * 70}")


def status(session: CombatSession) -> None:
    for c in session.combatants.values():
        bar = "▓" * (c.current_stun * 20 // c.max_stun) + "░" * (20 - c.current_stun * 20 // c.max_stun)
        pos = SCENE.combatant_positions.get(c.id)
        loc = f"({pos.x:.0f},{pos.y:.0f},{pos.z:.0f})" if pos else "—"
        print(f"   {c.name:9} STUN [{bar}] {c.current_stun:>3}/{c.max_stun}  "
              f"BODY {c.current_body:>2}/{c.max_body}  END {c.current_end:>2}/{c.max_end}  @ {loc}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Run the fight
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    banner("ROOFTOP BRAWL — Nighthawk vs Volt")
    print("  Setting:  Industrial District warehouse roof, light rain, dusk")
    print(f"  Scene:    elevation 12m, parapet 1.2m around perimeter")
    print(f"  Template: {RAW_SUPERHEROIC.name}")

    session = CombatSession.create(
        id="rooftop-brawl-1",
        combatants=[NIGHTHAWK, VOLT],
        scene=SCENE,
        template=RAW_SUPERHEROIC,
        dice_roller=FakeRoller([]),
    ).start()

    status(session)

    # ── Segment 3: both have phases (SPD 5 acts on 3, 5, 8, 10, 12) ──
    banner("Turn 1, Segment 3 — phase resolution")
    slots = build_acting_order_for_segment(list(session.combatants.values()), segment=3)
    for slot in slots:
        print(f"  • {session.combatants[slot.combatant_id].name} "
              f"(DEX {slot.dex_at_phase}, EGO {slot.int_tiebreak}) acts")

    # ── Nighthawk's action: Energy Blast at Volt ──
    banner("Nighthawk fires Energy Blast at Volt!")
    print("  Volt sees the shot coming and aborts to Dodge (+3 DCV)…")
    session, dodge_evt = Dodge.declare(session, "volt")
    print(f"     [event seq {dodge_evt.sequence}] {dodge_evt.kind} → to_action={dodge_evt.to_action}")
    print(f"     Volt's effective DCV: {VOLT.dcv} + {Dodge.dcv_bonus(session, 'volt')} = "
          f"{VOLT.dcv + Dodge.dcv_bonus(session, 'volt')}")

    # Ten dice for Energy Blast 10d6
    dice_n1 = DiceValues(
        to_hit=[4, 5, 4],   # 13 — needs 11 + OCV9 - DCV(7+3) = 10 to hit. 13 > 10 → MISS.
        damage=[3, 5, 4, 6, 1, 4, 2, 5, 3, 4],
        knockback=[3],
    )
    stun, body, hit, audit = resolve_attack(
        session.combatants["nighthawk"], session.combatants["volt"], dice_n1,
        dcv_mod=Dodge.dcv_bonus(session, "volt"),
    )
    for line in audit:
        print(line)

    # ── Volt's action: counter-attack ──
    banner("Volt fires back!")
    print("  No abort — Nighthawk takes the shot at full DCV.")
    # Volt rolls hot — most dice land 5+, punching through Nighthawk's energy defense.
    dice_v1 = DiceValues(
        to_hit=[2, 3, 4],   # 9, well under target → solid hit
        damage=[5, 5, 6, 6, 6, 6, 5, 6, 5, 6],   # 16 BODY raw; 14 ED stops 14, 2 BODY through
        knockback=[5, 4, 3],
    )
    stun, body, hit, audit = resolve_attack(
        session.combatants["volt"], session.combatants["nighthawk"], dice_v1,
    )
    for line in audit:
        print(line)

    if hit:
        session = apply_damage(session, "nighthawk", stun, body)

        # ── Task 20: scene-aware knockback in ONE call ──
        kb_out = resolve_knockback_movement(
            combatant_id="nighthawk",
            attacker_pos=SCENE.combatant_positions["volt"],
            target_pos=SCENE.combatant_positions["nighthawk"],
            body_dealt=body,
            kb_resistance=session.combatants["nighthawk"].knockback_resistance,
            dice=dice_v1,
            scene=SCENE,
            template=RAW_SUPERHEROIC,
        )
        print(f"  → Knockback: {kb_out.intended_distance_m:.1f}m intended, "
              f"{kb_out.actual_distance_traveled_m:.1f}m actual, "
              f"direction ({kb_out.direction_xy[0]:+.1f}, {kb_out.direction_xy[1]:+.1f})")
        print(f"     start: ({kb_out.start_position.x:.1f}, {kb_out.start_position.y:.1f}, "
              f"{kb_out.start_position.z:.1f})  →  "
              f"end: ({kb_out.final_position.x:.1f}, {kb_out.final_position.y:.1f}, "
              f"{kb_out.final_position.z:.1f})")

        if kb_out.wall_collision:
            print(f"     ★ slammed into wall '{kb_out.wall_collision.wall_id}' "
                  f"with {kb_out.collision_damage_dice}d6 collision damage")
        if kb_out.hazard_triggers:
            for h in kb_out.hazard_triggers:
                print(f"     ★ hazard '{h.hazard_id}' triggered ({h.trigger_reason}) — "
                      f"{h.effect.damage_dice}d6 {h.effect.damage_type}")
        if kb_out.fall:
            f = kb_out.fall
            print(f"\n  ⚠ Nighthawk knocked OFF THE ROOFTOP — falling…")
            print(f"     • Falls from z={f.from_pos.z:.1f}m to z={f.landed_at.z:.1f}m "
                  f"({f.fall_distance_m:.1f}m total)")
            print(f"     • Falling damage: {f.damage_dice}d6 normal damage vs PD")
            # Apply falling damage with stub-average rolls.
            stub_stun = sum([4] * f.damage_dice)
            stub_body = f.damage_dice                  # 1 BODY per die at value 4
            target = session.combatants["nighthawk"]
            fall_stun_dealt = max(0, stub_stun - target.pd)
            fall_body_dealt = max(0, stub_body - target.pd)
            print(f"     • Stub rolls: STUN={stub_stun}, BODY={stub_body}; "
                  f"PD={target.pd} → dealt STUN={fall_stun_dealt}, BODY={fall_body_dealt}")
            session = apply_damage(session, "nighthawk", fall_stun_dealt, fall_body_dealt)

        # Update scene position to where Nighthawk actually ended up
        SCENE.combatant_positions["nighthawk"] = kb_out.final_position

    print()
    status(session)

    # ── Post-Segment 12 Recovery for everyone ──
    banner("End of Turn 1 — Post-Segment 12 Recovery")
    for cid, c in list(session.combatants.items()):
        stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
        print(f"  {c.name:9}: +{stun_d} STUN, +{end_d} END  (REC {c.rec})")
        new_c = replace(c, current_stun=c.current_stun + stun_d, current_end=c.current_end + end_d)
        new_combatants = dict(session.combatants)
        new_combatants[cid] = new_c
        session = replace(session, combatants=new_combatants)

    print()
    status(session)

    # ── Demonstrate rewind ──
    # ── What-If: same hit, but with an HVAC unit between them ──
    banner("WHAT-IF: same scenario, but an HVAC unit blocks the path")
    print("  Re-resolving the knockback with an interior wall added at x=6 on the rooftop.")
    print("  Same dice, same characters, same blast — only the geometry changes.")

    hvac_wall = Wall(
        id="hvac", name="HVAC unit",
        segment=(Position(6, 8, 12), Position(6, 16, 12)),
        height_m=1.8, blocks_los=True, blocks_movement=True,
        cover_level=2, body=8,
    )
    scene_with_wall = Scene(
        id="warehouse-roof-v2", name="…with HVAC unit",
        bounds=SCENE.bounds,
        surfaces=list(SCENE.surfaces),
        walls=[*SCENE.walls, hvac_wall],
        hazards=list(SCENE.hazards),
        ambient=SCENE.ambient,
        combatant_positions={
            "nighthawk": Position(8, 12, 12),
            "volt":      Position(20, 12, 12),
        },
    )

    kb_alt = resolve_knockback_movement(
        combatant_id="nighthawk",
        attacker_pos=scene_with_wall.combatant_positions["volt"],
        target_pos=scene_with_wall.combatant_positions["nighthawk"],
        body_dealt=2,                     # same body_dealt as Volt's hit above
        kb_resistance=NIGHTHAWK.knockback_resistance,
        dice=dice_v1,
        scene=scene_with_wall,
        template=RAW_SUPERHEROIC,
    )
    print(f"\n  → Knockback: {kb_alt.intended_distance_m:.1f}m intended, "
          f"{kb_alt.actual_distance_traveled_m:.1f}m actual, "
          f"direction ({kb_alt.direction_xy[0]:+.1f}, {kb_alt.direction_xy[1]:+.1f})")
    print(f"     start: ({kb_alt.start_position.x:.1f}, {kb_alt.start_position.y:.1f}, "
          f"{kb_alt.start_position.z:.1f})  →  "
          f"end: ({kb_alt.final_position.x:.1f}, {kb_alt.final_position.y:.1f}, "
          f"{kb_alt.final_position.z:.1f})")

    if kb_alt.wall_collision:
        wc = kb_alt.wall_collision
        print(f"     ★ slammed into wall '{wc.wall_id}' "
              f"({kb_alt.collision_damage_dice}d6 collision damage applies)")
        print(f"     ★ {wc.distance_into_wall_m:.1f}m of intended KB absorbed by impact")
    if kb_alt.fall:
        print(f"     ★ also fell {kb_alt.fall.fall_distance_m:.1f}m")
    else:
        print(f"     ★ stayed on the rooftop — wall caught him before the edge")

    print()
    print("  Comparison:")
    print(f"     no wall:   ended at {kb_out.final_position.x:.1f}, {kb_out.final_position.y:.1f}, "
          f"{kb_out.final_position.z:.1f}  (fell)")
    print(f"     with wall: ended at {kb_alt.final_position.x:.1f}, {kb_alt.final_position.y:.1f}, "
          f"{kb_alt.final_position.z:.1f}  (collided, no fall)")

    banner("REWIND DEMO — let's roll back to before Volt's counter-attack")
    print(f"  Current event log: {len(session.event_log)} events")
    print(f"  Current Nighthawk STUN: {session.combatants['nighthawk'].current_stun}")
    print()
    from kirby_combat.session.rewind import rewind_to_sequence
    # Find the sequence right after the Dodge declaration (the Volt counter-attack mutated state directly,
    # not via a CombatEvent in this demo, so rewind here just unwinds the lifecycle/reactive events).
    target_seq = next(
        (e.sequence for e in session.event_log if e.kind == "AbortDeclared"),
        1,
    )
    rewound = rewind_to_sequence(session, target_sequence=target_seq)
    print(f"  Rewound to sequence {target_seq}: log now has {len(rewound.event_log)} events")
    print(f"  Note: snapshot mutations applied OUTSIDE the event-log (this demo) don't rewind.")
    print(f"  Plan 1 Tasks 21+ wire damage/effects through apply_event so rewind covers everything.")

    banner("END")


if __name__ == "__main__":
    main()
