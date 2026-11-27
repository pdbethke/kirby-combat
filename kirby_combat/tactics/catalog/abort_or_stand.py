"""Abort, or stand and keep your shot: the out-of-turn question, answered.

THE RULE (6E2 p.23-24): a man an attack is coming at may Abort to a
defensive action --- Dodge is +3 DCV --- and the Abort "costs his next
Phase". Nothing in the book says when to.

THE DEFECT THIS ANSWERS. The abort page carried no doctrine: the catalogue's
two abort tactics (`dodge_under_fire`, `abort_to_block`) name ``kind="wait"``,
which is no action kind, so neither reached a page, and the doctrine seat's
"Don't Abort" was its fallback taking the first offer. A model seat at the
O.K. Corral (2026-11-27) aborted to Dodge every time it was shot at: Frank
McLaury and Billy Clanton never fired a shot, and the record has both of
them fighting to the end.

JUDGEMENT (Peter's direction 2026-11-27, "the actions of each fighter should
also be dictated by their personalities"; the thresholds are mine, for his
review): a man's Psychological Complications say first, then his wounds and
his gun.

  * A COWARD DUCKS. "Not Brave", "Coward", "Cowardly": Abort to Dodge.
  * A FEARLESS MAN STANDS. "Vengeful", "No fear of death", "Fearless",
    "Reckless", "Death wish", "Overconfident": keep the Phase.
  * OTHERWISE: whole and holding an attack, he keeps his shot; hurt
    (`health.classify_health` not "healthy") or with nothing to shoot back
    with, he ducks.
"""
from __future__ import annotations

from kirby_combat.health import classify_health
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

#: Complication words that make a man duck, and that make him stand. Read
#: from the text a player wrote (`complications_of(...).name`).
COWARDLY = ("not brave", "coward", "cowardly", "craven", "fearful")
FEARLESS = ("vengeful", "no fear", "fearless", "reckless", "death wish",
            "overconfiden")

DODGE, KEEP = "dodge", "no_abort"


def _says(situation: Situation, words) -> str | None:
    for comp in situation.actor_complications or []:
        text = (getattr(comp, "name", "") or "").lower()
        if any(w in text for w in words):
            return getattr(comp, "name", "")
    return None


def _armed(actor) -> bool:
    return bool(getattr(actor, "attacks", None))


def decide(situation: Situation) -> tuple[str, str]:
    """(kind, why) for the Abort question."""
    coward = _says(situation, COWARDLY)
    if coward:
        return DODGE, f"{coward}: he ducks"
    fearless = _says(situation, FEARLESS)
    if fearless:
        return KEEP, f"{fearless}: he does not duck, and keeps his shot"
    health = classify_health(situation.actor)
    if health != "healthy":
        return DODGE, f"he is {health}: an Abort to Dodge is worth his next Phase"
    if not _armed(situation.actor):
        return DODGE, "he has nothing to shoot back with: ducking costs him nothing"
    return KEEP, "whole and armed: an Abort gives up his next shot (6E2 p.23-24)"


@register
class AbortOrStand(Tactic):
    name = "abort_or_stand"
    basis = Basis(
        mechanism="6E2 p24",
        judgement=("complications first (a coward ducks, a fearless man stands), "
                   "then: whole and armed keeps his shot, hurt or unarmed ducks "
                   "(Peter's direction 2026-11-27; thresholds for his review)"),
    )
    #: Only ever applicable out of turn, where nothing else is, so its rank
    #: among the Phase tactics does not matter; high so it is read first.
    priority = 90
    narrative_summary = (
        "An attack is coming at you. Aborting to Dodge (+3 DCV) costs your "
        "NEXT Phase (6E2 p.23-24) --- a man who ducks every shot never shoots "
        "back. Duck if you are hurt, unarmed or not brave; otherwise take it "
        "and keep your shot."
    )

    def applicable(self, situation: Situation) -> bool:
        from kirby_combat.loop.chooser import OutOfTurnReason

        why = getattr(situation, "out_of_turn", None)
        return why is not None and why.reason is OutOfTurnReason.ABORT

    def execute(self, situation: Situation) -> Plan:
        kind, why = decide(situation)
        return Plan(tactic_name=self.name, rationale=why,
                    steps=[PlanStep(kind=kind, notes=why)])
