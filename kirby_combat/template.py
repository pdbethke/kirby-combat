"""HERO System 6E CombatTemplate — campaign/game-mode configuration."""
from __future__ import annotations

from dataclasses import dataclass, replace

from kirby_combat.session.tie_rule import TieRule

#: The values `CombatTemplate.page_knowledge` takes.
PAGE_KNOWLEDGE = frozenset({"judged", "sheet"})


@dataclass(frozen=True)
class CombatTemplate:
    """All campaign-level switches that govern combat resolution.

    A CombatTemplate is attached to a campaign (or individual encounter)
    and controls which optional rules are active.  Two pre-built instances
    are provided: RAW_SUPERHEROIC and RAW_HEROIC.

    NO DEFAULTS. Every switch is stated by whoever builds a template. A
    default here is the engine choosing a campaign's optional rules for it
    without saying so; `DEFAULT_TEMPLATE` was that choice made for every
    Encounter that lacked one, and a heroic fight ran on Superheroic rules
    until somebody noticed it charged no END (2026-10-29).

    FROZEN. One template is shared by every campaign and fight that names
    it, so a change made in place was a change to all of them (and to
    `RAW_SUPERHEROIC` itself). A campaign's own rules are a
    `dataclasses.replace` of the one it starts from.
    """

    name: str
    edition: str
    mode: str                           # "superheroic" | "heroic"

    # Hit location options
    use_hit_locations: bool
    auto_roll_hit_location_npc: bool    # auto-roll for NPCs even if flag is off
    #: Empty is every location. A tuple: a template is shared by every
    #: campaign that names it, and a list here was one mutable object
    #: behind all of them.
    allowed_hit_locations: tuple[str, ...]

    # Knockback
    use_knockback: bool
    knockback_multiplier: float         # scale factor on KB distance

    # Endurance
    manage_endurance: bool
    manage_endurance_npc: bool

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
    # set, overrides the Campaign's); with no Campaign it is the
    # Encounter's own `template`, and an Encounter with neither raises. A GM changing `tie_rule` on a template
    # now reaches the sort through that path.
    #
    # ALSO WIRED: `Encounter.run_segment()` (kirby_combat/encounter.py)
    # resolves a CombatTemplate the same way and passes its `tie_rule`
    # into `resolve_acting_order`, then writes each session's slice of
    # the resolved order onto that session's `Timeline.acting_order` --
    # `Encounter.acting_order()` is NOT the only caller that does this.
    # `run_segment` is also the driver that writes a resolved acting
    # order back onto a session's Timeline during a live combat, and it
    # lives in THIS package, not kirby-api -- see `session/apply.py`'s
    # `_enforce_lightning_reflexes_phase_restriction` docstring, "STILL
    # INERT, precisely" paragraph, for what remains genuinely unwired
    # around that driver (including a second inert case beyond a
    # never-run session).
    tie_rule: TieRule

    # One-Hit Wonder optional rule
    # MINOR NPCs, 6E2 p.121-122's optional rules, which "should only apply
    # to minor or trivial NPCs" (a combatant's `minor_hits`; see
    # `kirby_combat/mooks.py`). Each is the campaign's choice. They replace
    # `one_hit_wonder_enabled` / `one_hit_wonder_pct`, which nothing read
    # and which described a STUN threshold the book does not have.
    #: "Once a minor enemy hits 0 BODY, he falls over dead."
    minor_dead_at_zero_body: bool
    #: "any time a minor NPC becomes Stunned by a Normal Damage or Killing
    #: Damage attack, he's not Stunned - he's dead."
    minor_stunned_is_dead: bool
    #: Counting hits: a minor NPC dies to `minor_hits` successful Attack
    #: Rolls, a roll made by N or more counting as N.
    minor_hit_counting: bool
    #: 6E2 p.51's optional Multiple Attacker Bonus: against attackers who
    #: Coordinate, the defender is -1 DCV per attacker after the first, down
    #: to 1/2 DCV (`coordination.multiple_attacker_dcv_delta`). The page
    #: calls it "particularly inappropriate" where heroes cut through
    #: crowds, so the cinematic templates leave it off and the gang ones
    #: turn it on (Peter, 2026-10-31).
    use_multiple_attacker_bonus: bool

    # Killing attack STUN multiplier
    killing_stun_mult_base: int         # base before the d3 roll
    killing_stun_mult_fixed: int | None  # None → roll d3; int → fixed value

    # 6E2 p.115's optional Bleeding rules. OFF by default, because the
    # page itself frames them as a choice -- "In situations where a
    # character can get immediate medical care, there's no need to use
    # the Bleeding rules" -- and because every fight this engine has run
    # so far ran without them. A gunfight is the case they were written
    # for; see `resolution/bleeding.py`.
    #
    # 6E2 p.109's bleeding to DEATH is NOT gated by this and never should
    # be: it is a core rule, it applies only at or below 0 BODY, and it
    # takes BODY rather than STUN.
    use_bleeding_rules: bool
    #: 6E2 p.45's optional "firing into melee" rule. OFF by default,
    #: because the page offers it rather than imposing it --- "Gamemasters
    #: may, if they wish, use the normal Behind Cover rules when a
    #: character tries to make a Ranged Attack against a character in the
    #: middle of a HTH Combat" -- and because it can hurt a combatant
    #: nobody aimed at, which no campaign should acquire by default.
    use_firing_into_melee: bool
    #: What a fighter's page shows of her ENEMIES: "judged" is what she can
    #: reasonably judge of them; "sheet" is their full sheet.
    #:
    #: RULING: every named template is "judged" (Peter, 2026-11-01): facts
    #: are "what she can reasonably judge", which replaces the Brief's
    #: earlier "perception is the only line drawn". "sheet" remains for
    #: benchmarks and tests that want the full sheet (the O.K. Corral
    #: harness may opt in explicitly). No default: which knowledge a page
    #: carries is the campaign's decision, not the engine's.
    page_knowledge: str

    def __post_init__(self) -> None:
        if self.page_knowledge not in PAGE_KNOWLEDGE:
            raise ValueError(
                f"page_knowledge must be one of {sorted(PAGE_KNOWLEDGE)}, "
                f"got {self.page_knowledge!r}"
            )

    # `custom_rules: dict` was here, an untyped bag that nothing read. A
    # house rule is a named, typed field the engine reads, or it is not a
    # rule.

    @classmethod
    def default_6e_superheroic(cls) -> "CombatTemplate":
        """Factory returning the standard RAW Superheroic 6E template.

        This is an alias for the module-level RAW_SUPERHEROIC constant. Kept as
        a classmethod for API ergonomics (CombatSession.create callers use this).
        """
        return RAW_SUPERHEROIC

    @classmethod
    def by_name(cls, name: str) -> "CombatTemplate":
        """The named template, or a KeyError listing the names there are.

        A fight is run under ONE set of campaign switches, and a consumer
        that stores a fight has to store which. A name is the smallest
        thing it can store, and this is where a name becomes a template.

        NO DEFAULT ARGUMENT, deliberately. A default would mean a
        consumer that lost the name, or stored one this engine has never
        heard of, silently ran the fight under Superheroic switches ---
        hit locations off, END untracked, knockback on --- and reported
        the result as though those had been the campaign's rules all
        along. An unknown name is a question the engine cannot answer, so
        it raises and names the ones it can.
        """
        try:
            return TEMPLATES_BY_NAME[name]
        except KeyError:
            raise KeyError(
                f"unknown combat template {name!r}; known templates: "
                f"{', '.join(sorted(TEMPLATES_BY_NAME))}"
            ) from None


# ---------------------------------------------------------------------------
# Pre-built templates
# ---------------------------------------------------------------------------

#: Standard RAW Superheroic play (Four-colour comics feel).
#: Hit locations optional, END COUNTED, knockback on.
#:
#: END WAS OFF HERE, labelled "optional", and every fight the product ran
#: used this template --- so nobody ever paid END for anything. The book
#: says the opposite of optional: 6E2 p.133, "In Superheroic campaigns,
#: many characters pay END just to maintain their Powers, so END is very
#: important." Peter's ruling, 2026-10-29: superheroic counts END, for
#: player characters and NPCs alike. A table that hand-waves it can still
#: say so with its own template.
RAW_SUPERHEROIC = CombatTemplate(
    name="RAW Superheroic",
    edition="6E",
    mode="superheroic",
    use_hit_locations=False,
    auto_roll_hit_location_npc=False,
    allowed_hit_locations=(),
    use_knockback=True,
    knockback_multiplier=1.0,
    manage_endurance=True,
    manage_endurance_npc=True,
    tie_rule=TieRule.DEX_ROLL,
    minor_dead_at_zero_body=False,
    minor_stunned_is_dead=False,
    minor_hit_counting=False,
    use_multiple_attacker_bonus=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
    use_bleeding_rules=False,
    use_firing_into_melee=False,
    page_knowledge="judged",
)

#: Standard RAW Heroic play (grittier; hit locations and END tracked).
RAW_HEROIC = CombatTemplate(
    name="RAW Heroic",
    edition="6E",
    mode="heroic",
    use_hit_locations=True,
    auto_roll_hit_location_npc=True,
    allowed_hit_locations=(),
    use_knockback=True,
    knockback_multiplier=1.0,
    manage_endurance=True,
    manage_endurance_npc=True,
    tie_rule=TieRule.DEX_ROLL,
    minor_dead_at_zero_body=False,
    minor_stunned_is_dead=False,
    minor_hit_counting=False,
    use_multiple_attacker_bonus=False,
    killing_stun_mult_base=1,
    killing_stun_mult_fixed=None,
    use_bleeding_rules=False,
    use_firing_into_melee=False,
    page_knowledge="judged",
)


# ---------------------------------------------------------------------------
# The named registry
# ---------------------------------------------------------------------------

#: Name -> template, for `CombatTemplate.by_name`. The keys are what a
#: consumer persists against a fight, so they are stable identifiers
#: ("6e-superheroic"), not the display `name` field ("RAW Superheroic")
#: which is prose and may be reworded.
#: The RAW templates with 6E2 p.121-122's minor-NPC rules on (`mooks.py`):
#: "to make a game a little more like novels and movies". Peter's choice
#: (2026-10-31) of how a table turns them on, until GM-editable templates.
CINEMATIC_SUPERHEROIC = replace(
    RAW_SUPERHEROIC, name="Cinematic Superheroic",
    minor_dead_at_zero_body=True, minor_stunned_is_dead=True, minor_hit_counting=True,
)
CINEMATIC_HEROIC = replace(
    RAW_HEROIC, name="Cinematic Heroic",
    minor_dead_at_zero_body=True, minor_stunned_is_dead=True, minor_hit_counting=True,
)

#: The cinematic templates with 6E2 p.51's Multiple Attacker Bonus on: a
#: horde that Coordinates is dangerous. Peter's choice (2026-10-31), kept
#: apart from the cinematic ones because the page itself advises against
#: the bonus in exactly the games those are for.
CINEMATIC_SUPERHEROIC_GANG = replace(
    CINEMATIC_SUPERHEROIC, name="Cinematic Superheroic, Gangs",
    use_multiple_attacker_bonus=True,
)
CINEMATIC_HEROIC_GANG = replace(
    CINEMATIC_HEROIC, name="Cinematic Heroic, Gangs",
    use_multiple_attacker_bonus=True,
)

TEMPLATES_BY_NAME: dict[str, CombatTemplate] = {
    "6e-superheroic": RAW_SUPERHEROIC,
    "6e-heroic": RAW_HEROIC,
    "6e-superheroic-cinematic": CINEMATIC_SUPERHEROIC,
    "6e-heroic-cinematic": CINEMATIC_HEROIC,
    "6e-superheroic-cinematic-gang": CINEMATIC_SUPERHEROIC_GANG,
    "6e-heroic-cinematic-gang": CINEMATIC_HEROIC_GANG,
}
