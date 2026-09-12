"""Concrete tactics. Importing this module auto-registers all
tactic classes via the @register decorator at class definition."""
from kirby_combat.tactics.catalog import (
    # Existing tactics (original + T2 offensive)
    bait_enraged,
    close_and_strike,
    coordinated_focus_fire,
    exploit_hazards,
    exploit_susceptibility,
    fight_from_cover,
    go_around_the_cover,
    grab_and_throw,
    keep_range,
    presence_attack_demoralize,
    push_when_winning,
    smash_cover,
    sustained_fire,
    throw_something_heavy,
    # T3 defensive tactics
    abort_to_block,
    dodge_under_fire,
    mobility_defense,
    raise_force_wall_t,
    reposition_when_spotted,
    shield_allies,
    stand_and_take_it,
    take_cover_when_hurt,
    # Saving --- doctrine let men bleed to death for want of this one
    stabilize_the_dying,
    # Leaving --- the doctrine the catalogue had no version of
    break_off_when_nothing_works,
    leave_when_the_side_has_broken,
    withdraw_when_outmatched,
)

__all__ = [
    "stabilize_the_dying",
    "throw_something_heavy",
    "leave_when_the_side_has_broken",
    "break_off_when_nothing_works",
    "bait_enraged",
    "close_and_strike",
    "coordinated_focus_fire",
    "exploit_hazards",
    "exploit_susceptibility",
    "fight_from_cover",
    "go_around_the_cover",
    "grab_and_throw",
    "keep_range",
    "presence_attack_demoralize",
    "push_when_winning",
    "smash_cover",
    "sustained_fire",
    # T3 defensive
    "abort_to_block",
    "dodge_under_fire",
    "mobility_defense",
    "raise_force_wall_t",
    "reposition_when_spotted",
    "shield_allies",
    "stand_and_take_it",
    "take_cover_when_hurt",
    "withdraw_when_outmatched",
]
