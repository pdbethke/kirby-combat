"""Campaign — the setting a CombatTemplate is attached to.

``kirby_combat/template.py``'s docstring has always said a CombatTemplate
"is attached to a campaign (or individual encounter)". This module is that
campaign layer, and ``resolve_template`` is the resolution the parenthetical
already specifies: the campaign's template is the default, and an
individual Encounter's template — when set — overrides it.

Deliberately minimal: in this engine, a Campaign owns only what combat
needs to run (its template), plus identity (``id``, ``name``) and the
``World``s that belong to it. The roster, the XP ledger, campaign prose,
players, and session notes are kirby-api concerns, not this engine's --
adding them here would be the layering inversion this package's design is
meant to avoid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kirby_combat.template import DEFAULT_TEMPLATE, CombatTemplate

if TYPE_CHECKING:
    from kirby_combat.encounter import Encounter
    from kirby_combat.world import World


@dataclass
class Campaign:
    """A setting: identity, its CombatTemplate, and the Worlds in it.

    Not persisted and not a container for anything beyond combat's needs
    -- see the module docstring for what deliberately does NOT live here.
    """

    id: str
    name: str
    # CombatTemplate is a plain (non-frozen, non-hashable) @dataclass, so
    # `dataclasses` treats a bare instance as a mutable default and refuses
    # it. `default_factory` returning the same DEFAULT_TEMPLATE singleton
    # sidesteps that without giving every Campaign its own copy.
    template: CombatTemplate = field(default_factory=lambda: DEFAULT_TEMPLATE)
    worlds: "list[World]" = field(default_factory=list)


def resolve_template(campaign: Campaign, encounter: "Encounter") -> CombatTemplate:
    """Resolve the CombatTemplate that governs ``encounter``.

    Per ``template.py``'s docstring, a CombatTemplate "is attached to a
    campaign (or individual encounter)" -- the campaign's template is the
    default, and an encounter's own ``template``, when set, overrides it.
    This mirrors the existing ``.hdt`` -> kirby-cost -> kirby-combat
    override chain: a more specific layer wins when it opts in, and the
    broader layer's value is the fallback otherwise.
    """
    if encounter.template is not None:
        return encounter.template
    return campaign.template
