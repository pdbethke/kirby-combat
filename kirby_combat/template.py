"""HERO System 6E CombatTemplate — campaign/game-mode configuration."""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.session.tie_rule import TieRule


@dataclass
class CombatTemplate:
    """All campaign-level switches that govern combat resolution.

    A CombatTemplate is attached to a campaign (or individual encounter)
    and controls which optional rules are active.  Two pre-built instances
    are provided: RAW_SUPERHEROIC and RAW_HEROIC.
    """

    name: str
    edition: str = "6E"
    mode: str = "superheroic"           # "superheroic" | "heroic"

    # Hit location options
    use_hit_locations: bool = False
    auto_roll_hit_location_npc: bool = False   # auto-roll for NPCs even if flag is off
    allowed_hit_locations: list[str] = field(default_factory=list)  # empty = all

    # Knockback
    use_knockback: bool = True
    knockback_multiplier: float = 1.0   # scale factor on KB distance

    # Endurance
    manage_endurance: bool = False
    manage_endurance_npc: bool = False

    # Initiative / DEX ties
    # Was `randomize_dex_ties: bool = False`, declared, defaulted in both
    # templates below, and read by nothing (never wired to acting order).
    # 6E2 p.21's default for a DEX tie is a contested DEX Roll; grep for
    # `randomize_dex_ties` if you're looking for the old flag -- this is
    # where it went, widened to name the GM's stated alternative too.
    #
    # WIRED (was DORMANT): `Encounter.acting_order()` (kirby_combat/
    # encounter.py) resolves this field and passes it into
    # `session.timeline.build_acting_order_for_segment` as its `tie_rule`
    # argument, in place of that function's own `TieRule.INT_THEN_PRE`
    # default. When a `Campaign` is supplied, resolution goes through
    # `campaign.resolve_template` (an Encounter's own `template`, when
    # set, overrides the Campaign's); with no Campaign, `Encounter.
    # acting_order` falls back to `self.template or DEFAULT_TEMPLATE`
    # so a standalone Encounter (no Campaign/World hierarchy built yet)
    # still resolves a tie rule. A GM changing `tie_rule` on a template
    # now reaches the sort through that path.
    #
    # STILL UNWIRED: `Encounter.acting_order()` is, as of this change, the
    # ONLY caller anywhere in this codebase that resolves a CombatTemplate
    # and passes its `tie_rule` in. `CombatSession` itself does not call
    # `build_acting_order_for_segment`/`resolve_acting_order` at all --
    # nothing in this codebase currently writes a resolved acting order
    # onto `session.timeline.acting_order` during a live combat (see
    # `session/apply.py`'s `_enforce_lightning_reflexes_phase_restriction`
    # docstring for the honest account of that gap). The driver that would
    # call `resolve_acting_order` and store its output on a session's
    # timeline is external to this package (kirby-api); wiring that driver
    # to also resolve and pass a CombatTemplate's `tie_rule` is a follow-up,
    # not this change.
    tie_rule: TieRule = TieRule.DEX_ROLL

    # One-Hit Wonder optional rule
    one_hit_wonder_enabled: bool = False
    one_hit_wonder_pct: float = 0.5     # fraction of max STUN to trigger

    # Killing attack STUN multiplier
    killing_stun_mult_base: int = 1     # base before the d3 roll
    killing_stun_mult_fixed: int | None = None  # None → roll d3; int → fixed value

    # Extension hooks
    custom_rules: dict = field(default_factory=dict)

    @classmethod
    def default_6e_superheroic(cls) -> "CombatTemplate":
        """Factory returning the standard RAW Superheroic 6E template.

        This is an alias for the module-level RAW_SUPERHEROIC constant. Kept as
        a classmethod for API ergonomics (CombatSession.create callers use this).
        """
        return RAW_SUPERHEROIC


# ---------------------------------------------------------------------------
# Pre-built templates
# ---------------------------------------------------------------------------

#: Standard RAW Superheroic play (Four-colour comics feel).
#: Hit locations optional, END optional, knockback on.
RAW_SUPERHEROIC = CombatTemplate(
    name="RAW Superheroic",
    edition="6E",
    mode="superheroic",
    use_hit_locations=False,
    auto_roll_hit_location_npc=False,
    use_knockback=True,
    knockback_multiplier=1.0,
    manage_endurance=False,
    manage_endurance_npc=False,
    tie_rule=TieRule.DEX_ROLL,
    one_hit_wonder_enabled=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
)

#: The engine's default template when no campaign has chosen one yet.
DEFAULT_TEMPLATE = RAW_SUPERHEROIC

#: Standard RAW Heroic play (grittier; hit locations and END tracked).
RAW_HEROIC = CombatTemplate(
    name="RAW Heroic",
    edition="6E",
    mode="heroic",
    use_hit_locations=True,
    auto_roll_hit_location_npc=True,
    use_knockback=True,
    knockback_multiplier=1.0,
    manage_endurance=True,
    manage_endurance_npc=True,
    tie_rule=TieRule.DEX_ROLL,
    one_hit_wonder_enabled=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
)
