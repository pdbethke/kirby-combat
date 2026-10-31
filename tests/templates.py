"""A template for tests that are about something other than the template.

`CombatTemplate` has no defaults (no default template anywhere), so a test
that only needs SOME rules states them. `PLAIN` is the switches the
template's old field defaults gave: Superheroic, no hit locations,
knockback at x1, END NOT counted, DEX Roll ties, every optional rule off.
A test that is about one switch says so with `replace(PLAIN, that=...)`.
"""
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.template import CombatTemplate

PLAIN = CombatTemplate(
    name="plain test rules",
    edition="6E",
    mode="superheroic",
    use_hit_locations=False,
    auto_roll_hit_location_npc=False,
    allowed_hit_locations=(),
    use_knockback=True,
    knockback_multiplier=1.0,
    manage_endurance=False,
    manage_endurance_npc=False,
    tie_rule=TieRule.DEX_ROLL,
    minor_dead_at_zero_body=False,
    minor_stunned_is_dead=False,
    minor_hit_counting=False,
    use_multiple_attacker_bonus=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
    use_bleeding_rules=False,
    use_firing_into_melee=False,
)
