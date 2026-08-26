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

import copy
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
    # it -- `default_factory` is required. It must return a FRESH,
    # INDEPENDENT copy each time, not the DEFAULT_TEMPLATE singleton itself:
    # CombatTemplate is mutable, so handing every Campaign the same object
    # would let mutating one campaign's template silently rewrite every
    # other campaign's default, and poison the module-level DEFAULT_TEMPLATE
    # / RAW_SUPERHEROIC constant for the rest of the process.
    #
    # `dataclasses.replace(DEFAULT_TEMPLATE)` looks like a fix but is NOT
    # one -- `replace` is a SHALLOW copy: it re-invokes __init__ with
    # DEFAULT_TEMPLATE's existing field VALUES, so the two mutable fields on
    # CombatTemplate (`custom_rules: dict`, `allowed_hit_locations: list`)
    # come along by identity, unchanged. Every Campaign built with `replace`
    # gets its own CombatTemplate wrapper object, but that wrapper's
    # `custom_rules` dict and `allowed_hit_locations` list are still the
    # SAME dict/list DEFAULT_TEMPLATE (and therefore RAW_SUPERHEROIC,
    # RAW_HEROIC, and CombatTemplate.default_6e_superheroic() -- see
    # template.py) points at. Mutating `campaign.template.custom_rules[...]`
    # on one campaign is still visible on every other campaign and on those
    # module-level constants for the rest of the process. `copy.deepcopy`
    # is required to actually sever the shared dict/list, not just the
    # top-level CombatTemplate instance. (Reviewer finding, task 4;
    # corrected on whole-branch review -- the original `replace()` fix only
    # covered scalar fields like `tie_rule`.)
    template: CombatTemplate = field(default_factory=lambda: copy.deepcopy(DEFAULT_TEMPLATE))
    worlds: "list[World]" = field(default_factory=list)


def resolve_template(campaign: Campaign, encounter: "Encounter") -> CombatTemplate:
    """Resolve the CombatTemplate that governs ``encounter``.

    Per ``template.py``'s docstring, a CombatTemplate "is attached to a
    campaign (or individual encounter)" -- the campaign's template is the
    default, and an encounter's own ``template``, when set, overrides it.
    """
    if encounter.template is not None:
        return encounter.template
    return campaign.template
