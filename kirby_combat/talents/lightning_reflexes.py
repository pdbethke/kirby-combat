"""Lightning Reflexes (6E1 p.116) -- initiative only, never Agility rolls.

    "A character with a base DEX of 16 and +6 Lightning Reflexes (total
    effective DEX 16 + 6 = 22) would act before a character with a base DEX
    of 20. However, his Agility Skill Rolls remain 12-."

Two consequences that shape this module:

  1. The bonus touches *acting order only*. It must never be added to a
     DEX Roll target (session/tie_rule.py's `dex_roll_target` takes plain
     printed DEX for exactly this reason) or to any other DEX-based roll.
  2. 6E1 p.116 continues: taking the bonus is an election that costs the
     rest of the Phase ("he may only execute the specific Action or
     maneuver he purchased Lightning Reflexes for... no movement,
     acrobatics, or other Actions"). `phase_restricted_to`/
     `restriction_for_slot` below enforce that forfeiture; the election
     itself (`ActionIntent.elect_lightning_reflexes`) changes *ordering*
     via `timeline.ordering_value`, and the restriction is what then
     narrows what the combatant may declare that Phase.

The central trap this module exists to avoid (see `lightning_reflexes_bonus`
docstring): every real Lightning Reflexes instance sampled from character
files on this machine carries XMLID ``LIGHTNING_REFLEXES_ALL`` -- including
the ones bought narrowly. Scope comes from OPTIONID, never the XMLID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.timeline import ActingSlot, ActionIntent

# The two XMLIDs kirby-cost's HDC loader can produce for this Talent.
# LIGHTNING_REFLEXES_SINGLE is kirby-cost's ported class for the 5E-named
# variant; it appears in ZERO of the 76 real instances sampled from character
# files on this machine (every one, including narrow-scope ones, was written
# out as LIGHTNING_REFLEXES_ALL with a narrowing OPTIONID). It is scanned for
# here anyway, defensively, in case a hand-built or older document uses it --
# but real data never exercises this branch.
_LIGHTNING_REFLEXES_XMLIDS = frozenset(
    {"LIGHTNING_REFLEXES_ALL", "LIGHTNING_REFLEXES_SINGLE"}
)


def _option_id(talent: Any) -> str:
    """The scope the Talent was bought for, e.g. ``ALL`` / ``SINGLE`` /
    ``LARGEGROUP`` / ``ALLRANGED``.

    kirby-cost's HDC loader maps the document's OPTION attribute (which is
    always written identical to OPTIONID for this Talent -- confirmed
    against every real Lightning Reflexes instance on this machine) onto
    ``source_option``. Read that generically rather than importing
    kirby-cost's Talent class here, so a synthetic/duck-typed stub (as
    tests build) works the same as a real loaded object.
    """
    return (getattr(talent, "source_option", None)
            or getattr(talent, "option_id", None)
            or "") or ""


def _option_alias_text(talent: Any) -> str:
    """The named action/group this Talent's narrow scope applies to.

    Prefers kirby-cost's ``option_alias()`` helper (which also checks a
    resolved ``selected_option`` object) when kirby-cost is importable and
    the talent is one of its real objects; falls back to the raw
    ``OPTION_ALIAS`` document attribute (``source_option_alias``) for
    duck-typed stubs, which is the same string by a shorter route.
    """
    try:
        from kirby_cost.objects.base import option_alias
        text = option_alias(talent)
        if text:
            return text
    except Exception:  # noqa: BLE001 -- talent isn't a kirby-cost object
        pass
    return getattr(talent, "source_option_alias", None) or getattr(
        talent, "option_alias", None) or ""


def _matches_named_action(option_alias_text: str, action_type: str) -> bool:
    """SINGLE / LARGEGROUP scope: the Talent only applies to the one
    named Action or group it was bought for (6E1 p.116). Matched by
    case-insensitive text equality against OPTION_ALIAS, which is the only
    thing the document states the scope in terms of -- there is no
    canonical action-type vocabulary shared between HD's OPTION_ALIAS
    strings ("Spirit Travel", "with Claws") and this engine's
    ``ActionIntent.action_type`` strings, so callers must pass the same
    text the character sheet uses for that action."""
    return bool(option_alias_text) and option_alias_text.strip().lower() == (
        action_type or "").strip().lower()


def _is_ranged_action_type(action_type: str) -> bool:
    """ALLRANGED scope: applies to ranged attacks (6E1 p.116 lets a
    character buy Lightning Reflexes for a category of Action, not only a
    single one; "All Ranged Attacks" is the observed OPTION_ALIAS for it).

    KNOWN GAP: ``ActionIntent`` carries only ``action_type``/``is_mental``/
    ``elect_lightning_reflexes`` -- nothing marks an action as ranged vs.
    HtH at this layer (that lives on ``AttackPower.is_ranged``, which
    ``ActionIntent`` does not reference). Only 2 of 76 real instances are
    ALLRANGED-scoped, and there is no test coverage yet for the ranged
    case, so rather than invent a real classification here (and risk it
    disagreeing with whatever a future driver decides "ranged" means for
    an ActionIntent), this checks for the literal substring "RANGED" in
    the declared action_type -- a conservative heuristic that fails
    closed (no match -> no bonus) until a real ranged/HtH signal reaches
    ActionIntent. A disclosed gap, not a silent one."""
    return "ranged" in (action_type or "").strip().lower()


@dataclass(frozen=True)
class LightningReflexesGrant:
    """The three facts one Lightning Reflexes Talent instance states about
    its own scope, lifted off the loaded object so they can be captured
    once (at provisional-order time, when the build is in hand) and
    evaluated later against a declared action (at resolve time, when the
    intent is in hand) without holding onto the Talent object or the hero
    it came from. See timeline.py's ``ActingSlot.lightning_reflexes_grants``
    for why the two passes are split this way.
    """
    levels: int
    option_id: str
    option_alias: str


def _grant_for_talent(talent: Any) -> "LightningReflexesGrant":
    return LightningReflexesGrant(
        levels=int(getattr(talent, "levels", 0) or 0),
        option_id=_option_id(talent).strip().upper(),
        option_alias=_option_alias_text(talent),
    )


def lightning_reflexes_grants(hero: Any) -> tuple["LightningReflexesGrant", ...]:
    """Every Lightning Reflexes Talent instance on ``hero``, as scope-only
    ``LightningReflexesGrant`` snapshots (build-time data: levels + bought
    scope). Scans BOTH ``hero.talents`` and ``hero.powers``, following the
    ``_has_talent`` pattern verified in perception.py."""
    grants: list[LightningReflexesGrant] = []
    for coll in (getattr(hero, "talents", None), getattr(hero, "powers", None)):
        for t in coll or []:
            xmlid = (getattr(t, "xmlid", None) or "").upper()
            if xmlid in _LIGHTNING_REFLEXES_XMLIDS:
                grants.append(_grant_for_talent(t))
    return tuple(grants)


def _bonus_for_grant(grant: "LightningReflexesGrant", action_type: str) -> int:
    """The DEX bonus one ``LightningReflexesGrant`` contributes for
    ``action_type``, or 0 if its bought scope does not cover it.

    Scope comes from OPTIONID (`_option_id`), never the XMLID -- see the
    module docstring and `lightning_reflexes_bonus`. An OPTIONID this
    function does not recognise returns 0: 6E1 p.116 defines exactly four
    ways to buy this Talent (all Actions / a group / a single Action, plus
    the observed ALLRANGED category), and failing closed on anything else
    keeps an unrecognised scope from silently becoming "applies to
    everything" -- the same trap the XMLID would have set.
    """
    if grant.levels <= 0:
        return 0

    if grant.option_id == "ALL":
        # 6E1 p.116: bought for all Actions.
        return grant.levels

    if grant.option_id in ("SINGLE", "LARGEGROUP"):
        # 6E1 p.116: bought for a single Action, or a named group (often a
        # Multipower's slots) -- OPTIONID doesn't say WHICH powers are in
        # the group, only its OPTION_ALIAS name (e.g. "Sonic Implants
        # Multipower"); group *membership* isn't resolvable from the
        # Talent alone, so this matches the declared action_type against
        # that name the same way it matches a genuinely single Action.
        return grant.levels if _matches_named_action(
            grant.option_alias, action_type) else 0

    if grant.option_id == "ALLRANGED":
        return grant.levels if _is_ranged_action_type(action_type) else 0

    # Fail closed: an unrecognised OPTIONID must never grant the bonus.
    return 0


def bonus_for_grants(
    grants: "tuple[LightningReflexesGrant, ...]", action_type: str,
) -> int:
    """The best Lightning Reflexes bonus ``action_type`` earns across all
    of ``grants``. More than one applicable grant (a character with
    alternate Lightning Reflexes "modes", as seen in the corpus) are
    alternative purchases, not stacking ones -- 6E1 never describes them as
    additive -- so the largest applicable bonus wins, not the sum."""
    return max((_bonus_for_grant(g, action_type) for g in grants), default=0)


def lightning_reflexes_bonus(hero: Any, action_type: str) -> int:
    """The Lightning Reflexes DEX bonus ``hero`` gets for ``action_type``
    (6E1 p.116), or 0 if the Talent is absent or its bought scope doesn't
    cover this action.

    THE CENTRAL TRAP THIS FUNCTION EXISTS TO AVOID: every one of the 76
    real Lightning Reflexes instances sampled from character files on this
    machine -- including all 20 that were bought for a single narrow
    Action -- carries ``XMLID="LIGHTNING_REFLEXES_ALL"``. Branching on the
    XMLID (as kirby-cost's separate ``LightningReflexesSingle`` class name
    might suggest) would read every one of those 20 as "all Actions" and
    grant a universal DEX bonus in the player-favouring direction. The
    document's OPTIONID attribute is the only place the real scope is
    stated -- see `_bonus_for_grant`.

    Scans BOTH ``hero.talents`` and ``hero.powers``, following the
    ``_has_talent`` pattern verified in perception.py (Danger Sense /
    Combat Sense load as ``hero.talents`` entries in the real HDCLoader
    shape; scanning both collections keeps this robust to alternate load
    shapes / synthetic stubs). If more than one matching Talent instance
    applies to the same action (a character with alternate Lightning
    Reflexes "modes", as seen in the corpus), the largest applicable bonus
    wins -- these are alternative purchases, not stacking ones, and 6E1
    never describes them as additive.
    """
    return bonus_for_grants(lightning_reflexes_grants(hero), action_type)


def phase_restricted_to(intent: "ActionIntent | None") -> str | None:
    """6E1 p.116(c): "When a character uses Lightning Reflexes to increase
    his effective DEX, he may only execute the specific Action or maneuver
    he purchased Lightning Reflexes for... no movement, acrobatics, or
    other Actions." The pure, intent-only view of that restriction:
    whichever ``action_type`` the combatant declared alongside the
    election is the only action legal this Phase; ``None`` when the bonus
    was not elected (the Phase is unrestricted) or ``intent`` is absent.

    This function is deliberately ignorant of the elected grant's bought
    SCOPE (ALL vs. SINGLE/LARGEGROUP/ALLRANGED) -- ``ActionIntent`` itself
    doesn't carry that, only the action being declared. Taken alone this
    function would wrongly narrow an ALL-scope elector down to one action
    (see the module docstring's central trap and `restriction_for_slot`
    below, which corrects for that using the elected grant). Callers that
    hold an ``ActingSlot`` (and so have ``lightning_reflexes_grants`` in
    hand) must use `restriction_for_slot`, not this function, to decide
    what to actually enforce.
    """
    if intent is None or not intent.elect_lightning_reflexes:
        return None
    return intent.action_type


def _bonus_applied_by_ordering(slot: "ActingSlot") -> int:
    """The Lightning Reflexes bonus that ``timeline.ordering_value`` actually
    added to ``slot``'s acting order -- mirrors that function's rule rather
    than re-deriving it, so the two can't drift apart.

    This is deliberately NOT the same question as "does a grant on the
    build cover this action" (``bonus_for_grants``): for a mental intent,
    ``ordering_value`` orders on EGO (APG p.50) and never looks at
    Lightning Reflexes at all, so the bonus is 0 here even when a grant
    would otherwise cover the action. ``restriction_for_slot`` gates 6E1
    p.116(c)'s forfeiture on THIS -- whether the bonus actually reached
    ordering -- not on mere scope coverage, because 6E1 p.116(c) forfeits
    the Phase for a character who "uses Lightning Reflexes to increase his
    effective DEX"; a mental actor whose ordering ran on EGO increased
    nothing.
    """
    intent = slot.intent
    if intent is None or not intent.elect_lightning_reflexes:
        return 0
    if intent.is_mental:
        return 0
    return bonus_for_grants(slot.lightning_reflexes_grants, intent.action_type)


def restriction_for_slot(slot: "ActingSlot") -> str | None:
    """The Phase restriction (6E1 p.116(c)) actually enforced for one
    *resolved* ``ActingSlot`` (post-``resolve_acting_order``, so
    ``slot.intent`` is populated) -- `phase_restricted_to`, corrected three
    ways using ``slot.lightning_reflexes_grants`` (captured at
    provisional-order time, see ``ActingSlot``'s docstring):

      1. If the bonus never reached acting order at all -- because the
         intent was mental (ordering ran on EGO, per
         ``timeline.ordering_value``) or no grant on the build covers the
         declared action_type -- nothing was "used" to increase effective
         DEX, so 6E1 p.116(c)'s forfeiture does not apply either. See
         `_bonus_applied_by_ordering`, which mirrors `ordering_value`'s
         rule for exactly this reason: restricting on mere scope coverage
         (``bonus_for_grants`` alone) would wrongly restrict a mental
         actor who elected the bonus but whose ordering never used it.
      2. If the grant that supplies the bonus is ALL-scoped, the
         combatant is not meaningfully restricted: the "specific Action...
         he purchased Lightning Reflexes for" IS every Action, so there is
         nothing to narrow the Phase down to. Only a
         SINGLE/LARGEGROUP/ALLRANGED-scoped grant narrows the Phase to the
         one action/group/category it was bought for.
    """
    intent = slot.intent
    restricted = phase_restricted_to(intent)
    if restricted is None:
        return None
    if _bonus_applied_by_ordering(slot) <= 0:
        return None
    for grant in slot.lightning_reflexes_grants:
        if grant.option_id == "ALL" and _bonus_for_grant(
                grant, intent.action_type) > 0:
            return None
    return restricted
