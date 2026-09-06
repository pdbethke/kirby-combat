"""Raise Force Wall — deploy a FORCEWALL power defensively.

A combatant with a FORCEWALL power can raise a physical barrier that
blocks movement and ranged attacks. Tactically this splits the combat
area: enemies must either destroy the wall (costing them phases) or
find a way around it (adding movement cost). Meanwhile the wall-raiser
can fire from behind or through it if the wall is not fully opaque.

Module name is ``raise_force_wall_t`` (``_t`` suffix) to avoid
clashing with the ``force_wall`` action kind string used by the
action enumeration layer. The class name and tactic name are both
``raise_force_wall`` without the suffix.

Preconditions:
  * Actor has a FORCEWALL power in hero.powers (xmlid == "FORCEWALL").

Gate: scans actor.hero.powers directly — same pattern as
``action_enumeration.forcewall_power`` (which this could call if a
clean import path existed). The circular-import check: tactics ← this
module ← action_enumeration would introduce a cycle because
action_enumeration imports nothing from tactics. HOWEVER, importing
action_enumeration from a catalog tactic is a tactics → services
direction — we avoid it to keep catalogs pure (no services imports,
no DB). Therefore we scan actor.hero.powers directly with a comment
referencing the authoritative helper.

Terrain linkage:
  The ``force_wall`` action in the enumerated menu is the concrete
  expression of this advice. This tactic's narrative text signals the
  chooser to choose it defensively (between the actor and the main threat).
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

# NOTE: action_enumeration.forcewall_power is the authoritative FORCEWALL
# detector. We cannot import it here without creating a tactics ← services
# cycle (catalog modules must stay pure/DB-free). Duplicate the scan
# logic with a comment so the two stay in sync if the xmlid ever changes.
_FORCEWALL_XMLID = "FORCEWALL"


def _has_forcewall(situation: Situation) -> bool:
    """True if actor.hero has a FORCEWALL power.

    Mirrors action_enumeration.forcewall_power() without the import.
    """
    hero = getattr(situation.actor, "hero", None)
    for p in (getattr(hero, "powers", None) or []):
        if (getattr(p, "xmlid", "") or "").upper() == _FORCEWALL_XMLID:
            return True
    return False


@register
class RaiseForceWall(Tactic):
    name = "raise_force_wall"
    basis = Basis(judgement="a barrier buys phases, and phases are what a losing side lacks")
    priority = 53
    narrative_summary = (
        "Raise a Force Wall between yourself and the primary threat. "
        "The wall blocks incoming ranged attacks and forces melee enemies "
        "to go around or destroy it — buying you phases of free action. "
        "Place it so it cuts off the most dangerous attacker's line of fire. "
        "Once the wall is up, attack from behind it. "
        "If enemies try to destroy the wall, that's phases they're NOT "
        "spending attacking you or your allies."
    )

    def applicable(self, situation: Situation) -> bool:
        return _has_forcewall(situation)

    def execute(self, situation: Situation) -> Plan:
        target = situation.enemies[0] if situation.enemies else None
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                "Actor has FORCEWALL power. Raising a defensive barrier "
                "between actor and the primary threat forces attackers to "
                "destroy it or go around — both cost them phases."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=_FORCEWALL_XMLID,
                    notes=(
                        "Select the force_wall action from the menu. "
                        "Place the wall between you and the main attacker "
                        "to block their line of fire. "
                        "After raising, move behind the wall and shoot "
                        "through or over it next phase."
                    ),
                    params={
                        "action_kind": "force_wall",
                        "defensive": True,
                        "face_toward_threat": True,
                    },
                ),
            ],
            expected_outcome=(
                "Force Wall up between actor and primary threat. "
                "Attacker must destroy wall or reposition — 1-2 phases delay. "
                "Actor can act freely from behind wall."
            ),
        )
