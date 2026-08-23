"""Hold the line — one hero against twenty, without rolling twenty times.

Two subsystems that only exist because HERO has rules most VTTs skip:

  Presence attacks resolve intimidation as a real mechanic — PRE dice against
  the target's PRE, producing an effect on a ladder from "nothing" up to
  "cannot act this phase". A hero can win a fight by walking in.

  Mass combat aggregates a mob into one Unit with a shared BODY pool, so a
  crowd is a single roll rather than twenty. Casualties shrink the unit,
  shrinking BODY drives morale, and morale decides whether it still fights.

Exercises:
  - base_pre_dice / resolve_presence_attack / can_act_after
  - Unit, attack_vs_unit, aoe_vs_unit, cycle_morale, unit_attack_dc_bonus

No dependencies beyond the package.

Run with:
    .venv/bin/python examples/hold_the_line.py
"""
from __future__ import annotations

from kirby_combat.masscombat.resolution import (
    attack_vs_unit, aoe_vs_unit, cycle_morale, declare_offensive,
    unit_attack_dc_bonus,
)
from kirby_combat.masscombat.unit import Unit, UnitMorale
from kirby_combat.models import Combatant
from kirby_combat.pre_attacks.presence import (
    base_pre_dice, can_act_after, resolve_presence_attack,
)


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


HERO = Combatant(
    id="hero", name="The Bulwark",
    ocv=9, dcv=8, omcv=4, dmcv=4,
    spd=5, dex=20, ego=15, str_=50, con=28, pre=40, rec=12,
    pd=20, ed=20, rpd=15, red=15, md=8,
    power_defense=0, flash_defense=0,
    max_stun=60, max_body=18, max_end=50,
    current_stun=60, current_body=18, current_end=50,
    attacks=[], defenses=[],
)

THUG = Combatant(
    id="thug", name="Street Thug",
    ocv=5, dcv=5, omcv=3, dmcv=3,
    spd=3, dex=13, ego=10, str_=13, con=13, pre=10, rec=5,
    pd=4, ed=3, rpd=0, red=0, md=0,
    power_defense=0, flash_defense=0,
    max_stun=22, max_body=10, max_end=25,
    current_stun=22, current_body=10, current_end=25,
    attacks=[], defenses=[],
)


def show(unit: Unit) -> None:
    frac = unit.count / max(1, unit.initial_count)
    filled = max(0, min(20, round(20 * frac)))
    print(f"   {unit.name:16} [{'▓' * filled}{'░' * (20 - filled)}] "
          f"{unit.count:>2}/{unit.initial_count} standing   "
          f"BODY pool {unit.aggregate_body_pool:>3}   morale {unit.morale.name}")


def main() -> None:
    rule("HOLD THE LINE — one against twenty")

    # ── 1. Presence attack — winning without throwing a punch ────────────────
    rule("1. Presence attack — PRE 40 walks into the room")
    base = base_pre_dice(HERO)
    print(f"  {HERO.name} has PRE {HERO.pre} → {base}d6 base Presence dice")
    print(f"  {THUG.name} has PRE {THUG.pre} to resist with\n")

    for label, pip, bonus in (
        ("no flourish",        3, 0),
        ("kicks the door in",  4, 2),   # +dice for a dramatic entrance
        ("tears the door OFF", 5, 4),   # and more for genuine violence
    ):
        # Situational bonus dice are ADDED to the base, so the roll must carry
        # base + bonus values — that is what `effective_dice` reports back.
        dice = [pip] * (base + bonus)
        r = resolve_presence_attack(HERO, THUG, dice,
                                    bonus_dice_from_situation=bonus)
        acts = "can still act" if can_act_after(r.effect) else "CANNOT ACT"
        print(f"  {label:22} {r.effective_dice}d6 → {r.roll_total:>2} "
              f"vs PRE {r.target_pre}   {r.effect:<24} {acts}")

    print("\n  That is a real mechanic, not flavour: the last line ends a thug's")
    print("  phase before initiative is rolled.")

    # ── 2. The mob as one Unit ───────────────────────────────────────────────
    rule("2. The rest of them — twenty thugs as a single Unit")
    mob = Unit(
        id="mob", name="Dockside Mob",
        archetype_combatant_id=THUG.id,
        count=20, initial_count=20,
        aggregate_body_pool=20 * THUG.max_body,
        morale=UnitMorale.FRESH,
        archetype_body_per=THUG.max_body,
        archetype_stun_per=THUG.max_stun,
        archetype_dex=THUG.dex,
    )
    show(mob)
    print(f"   twenty attackers get +{unit_attack_dc_bonus(mob)} DC for numbers")
    print(f"   will they press the attack? {declare_offensive(mob)}")

    # ── 3. Damage removes members; morale follows ────────────────────────────
    rule("3. Cutting the mob down — casualties drive morale")
    for label, apply in (
        ("a single haymaker (18 BODY)", lambda u: attack_vs_unit(u, 18)),
        ("an area attack, 6 BODY each", lambda u: aoe_vs_unit(u, 6)),
        ("another area attack",         lambda u: aoe_vs_unit(u, 6)),
    ):
        res = apply(mob)
        mob = res.new_unit
        print(f"\n  {label}")
        print(f"     BODY dealt {res.body_dealt:>3}   "
              f"morale check triggered: {res.morale_check_triggered}")
        if res.morale_check_triggered:
            mob = cycle_morale(mob, succeeded=False)   # they fail it
            print(f"     morale check FAILED → {mob.morale.name}")
        show(mob)

    print(f"\n   still willing to attack? {declare_offensive(mob)}")
    print("\n  Twenty combatants, three rolls. The unit shrinks, its BODY pool")
    print("  shrinks with it, and morale turns a fight into a rout without the")
    print("  GM tracking twenty initiative slots.")

    rule("END")


if __name__ == "__main__":
    main()
