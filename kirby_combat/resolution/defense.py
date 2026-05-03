"""Defense aggregation for HERO System 6E combat resolution.

compute_defense(target, power) → DefenseProfile

Aggregation order:
  1. Base (non-resistant) defense from target characteristics by defense_type.
  2. Resistant defense from target characteristics.
  3. Defense items: add applicable pd/ed/md/power_defense/flash_defense and
     their resistant counterparts.
  4. Armor Piercing: halve total_defense and resistant_defense (integer division).
  5. Aggregate damage_reduction_pct, damage_negation, knockback_resistance.
"""
from __future__ import annotations

from kirby_combat.models import AttackPower, Combatant, DefenseProfile


# Maps defense_type string → (base_attr, resistant_attr, item_base_attr, item_resistant_attr)
# For "pd" and "ed" we track separate resistant fields on Combatant; for others resistant
# is the same field (all items and characteristic values are already resistant).
_DEFENSE_MAP: dict[str, tuple[str, str, str, str]] = {
    "pd":    ("pd",             "rpd",          "pd",             "rpd"),
    "ed":    ("ed",             "red",          "ed",             "red"),
    "md":    ("md",             "md",           "md",             "md"),
    "power": ("power_defense",  "power_defense", "power_defense", "power_defense"),
    "flash": ("flash_defense",  "flash_defense", "flash_defense", "flash_defense"),
}


def compute_defense(target: Combatant, power: AttackPower) -> DefenseProfile:
    """Return a DefenseProfile for *target* against *power*.

    Parameters
    ----------
    target:
        The combatant receiving the attack.
    power:
        The attacking power, which determines which defense type applies and
        whether Armor Piercing is active.

    Returns
    -------
    DefenseProfile
        Fully aggregated defense totals with audit trail.
    """
    audit: list[str] = []
    defense_tags: list[str] = []

    dtype = power.defense_type
    mapping = _DEFENSE_MAP.get(dtype)

    if mapping is None:
        # Unknown defense type — no defense applies.
        audit.append(f"Unknown defense_type '{dtype}'; no defense applied.")
        return DefenseProfile(
            total_defense=0,
            resistant_defense=0,
            non_resistant_defense=0,
            damage_reduction_pct=0,
            damage_negation=0,
            knockback_resistance=target.knockback_resistance,
            defense_tags=["no_applicable_defense"],
            audit=audit,
        )

    char_base_attr, char_res_attr, item_base_attr, item_res_attr = mapping

    # ------------------------------------------------------------------
    # 1 & 2. Characteristic-based defense
    # ------------------------------------------------------------------
    char_base: int = getattr(target, char_base_attr, 0)
    char_res: int = getattr(target, char_res_attr, 0)

    # For pd/ed, characteristic resistant is a subset of the base pool.
    # For md/power/flash, the characteristic value is both base and resistant.
    if dtype in ("pd", "ed"):
        # total from characteristics = the base value (includes resistant portion).
        total_from_chars = char_base
        res_from_chars = char_res
    else:
        total_from_chars = char_base
        res_from_chars = char_res  # same field, effectively all resistant

    audit.append(
        f"Characteristic {dtype.upper()}: base={total_from_chars}, resistant={res_from_chars}"
    )
    if total_from_chars > 0:
        defense_tags.append(f"char_{dtype}")

    # ------------------------------------------------------------------
    # 3. Defense items
    # ------------------------------------------------------------------
    total_from_items = 0
    res_from_items = 0
    # Damage Reduction: per HERO 6E1 p185 multiple DR powers don't
    # stack — apply max(matching). Track candidate %s per class.
    matching_dr_pcts: list[int] = []
    # Damage Negation: per HERO 6E1 p185 stacks additively (each
    # 5 CP = -1 DC). Sum DCs for matching class.
    total_damage_negation = 0
    total_kb_from_items = 0

    # Map attack's defense_type to the DR/DN damage_class label.
    # Attacks with no engine-side class (defense_type == "") apply
    # universally; DR/DN with no class (legacy) match anything.
    attack_class = {
        "pd": "physical",
        "ed": "energy",
        "mental": "mental",
    }.get((power.defense_type or "").lower(), "")

    is_killing = (power.damage_type == "killing")

    for item in target.defenses:
        item_base: int = getattr(item, item_base_attr, 0)
        item_res: int = getattr(item, item_res_attr, 0)

        if dtype in ("pd", "ed"):
            added_base = item_base
            added_res = item_res
        else:
            added_base = item_base
            added_res = item_res

        total_from_items += added_base
        res_from_items += added_res
        total_kb_from_items += item.knockback_resistance

        # Class-match DR / DN per attack class. Empty class on item
        # OR attack means "applies".
        item_class = (item.damage_class or "").lower()
        class_matches = (
            not item_class
            or not attack_class
            or item_class == attack_class
        )

        if item.damage_reduction_pct > 0 and class_matches:
            # Resistant DR works on Normal + Killing.
            # Non-resistant DR works on Normal only (NOT killing).
            if (item.dr_resistant) or (not is_killing):
                matching_dr_pcts.append(item.damage_reduction_pct)
                audit.append(
                    f"DR matches '{item.name}' "
                    f"({item.damage_reduction_pct}% "
                    f"{'resistant' if item.dr_resistant else 'normal'} "
                    f"{item_class or 'any'})"
                )

        if item.damage_negation > 0 and class_matches:
            if (item.dr_resistant) or (not is_killing):
                total_damage_negation += item.damage_negation
                audit.append(
                    f"DN adds {item.damage_negation} DC from '{item.name}' "
                    f"({item_class or 'any'})"
                )

        if added_base > 0 or added_res > 0:
            audit.append(
                f"Item '{item.name}': {dtype}={added_base}, r{dtype}={added_res}"
            )
            defense_tags.append(f"item:{item.name}")

    # Pick highest matching DR (no stacking per 6E1 p185)
    total_damage_reduction_pct = max(matching_dr_pcts) if matching_dr_pcts else 0
    if matching_dr_pcts:
        audit.append(
            f"Damage Reduction selected: {total_damage_reduction_pct}% "
            f"(from {len(matching_dr_pcts)} candidate(s); 6E1 p185 — pick max, no stack)"
        )

    # ------------------------------------------------------------------
    # Combine totals before Armor Piercing
    # ------------------------------------------------------------------
    gross_total = total_from_chars + total_from_items
    gross_resistant = res_from_chars + res_from_items

    audit.append(
        f"Pre-AP totals: total={gross_total}, resistant={gross_resistant}"
    )

    # ------------------------------------------------------------------
    # 4. Armor Piercing — halves both totals (integer division)
    # ------------------------------------------------------------------
    if power.armor_piercing > 0:
        gross_total = gross_total // 2
        gross_resistant = gross_resistant // 2
        audit.append(
            f"Armor Piercing x{power.armor_piercing}: "
            f"total halved to {gross_total}, resistant halved to {gross_resistant}"
        )
        defense_tags.append("armor_piercing")

    # ------------------------------------------------------------------
    # 5. Knockback resistance
    # ------------------------------------------------------------------
    total_kb = target.knockback_resistance + total_kb_from_items
    if total_kb > 0:
        audit.append(
            f"Knockback resistance: char={target.knockback_resistance}, "
            f"items={total_kb_from_items}, total={total_kb}"
        )
        defense_tags.append("knockback_resistance")

    # Guard: resistant can never exceed total (sanity clamp).
    gross_resistant = min(gross_resistant, gross_total)

    non_res = gross_total - gross_resistant

    if not defense_tags:
        defense_tags.append("no_defense")

    return DefenseProfile(
        total_defense=gross_total,
        resistant_defense=gross_resistant,
        non_resistant_defense=non_res,
        damage_reduction_pct=total_damage_reduction_pct,
        damage_negation=total_damage_negation,
        knockback_resistance=total_kb,
        defense_tags=defense_tags,
        audit=audit,
    )
