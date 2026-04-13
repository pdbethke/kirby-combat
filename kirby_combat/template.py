"""HERO System 6E CombatTemplate — campaign/game-mode configuration."""
from __future__ import annotations

from dataclasses import dataclass, field


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
    randomize_dex_ties: bool = False    # True → re-roll DEX ties on a d6

    # One-Hit Wonder optional rule
    one_hit_wonder_enabled: bool = False
    one_hit_wonder_pct: float = 0.5     # fraction of max STUN to trigger

    # Killing attack STUN multiplier
    killing_stun_mult_base: int = 1     # base before the d3 roll
    killing_stun_mult_fixed: int | None = None  # None → roll d3; int → fixed value

    # Extension hooks
    custom_rules: dict = field(default_factory=dict)


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
    randomize_dex_ties=False,
    one_hit_wonder_enabled=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
)

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
    randomize_dex_ties=False,
    one_hit_wonder_enabled=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
)
