"""Keep range — maintain distance from melee-only enemies.

A ranged combatant facing enemies who can only reach them in melee
should stay back.  The enemy must spend their move to close; every
meter of separation is a free phase advantage for the shooter.

Preconditions (combatant-shaped — Situation carries no distance data):
  * Actor has at least one ranged attack (range_m > 0).
  * At least one enemy lacks any ranged attack (range_m == 0 on all
    their attacks, or they have no attacks at all).

Note: if ALL enemies also have ranged attacks the range advantage is
neutral — this tactic does not apply.  The terrain linkage lives in
the narrative_summary: the situation summary will also carry terrain lines
describing cover and spacing which reinforce this advice when relevant.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _MENTAL_XMLIDS, _best_ranged_attack
from kirby_combat.tactics.library import register


def _has_any_ranged(combatant) -> bool:
    for a in getattr(combatant, "attacks", []):
        if (
            (a.damage_dice or 0) > 0
            and a.range_m is not None
            and a.range_m > 0
            and (a.xmlid or "").upper() not in _MENTAL_XMLIDS
        ):
            return True
    return False


def _is_melee_threat(combatant) -> bool:
    """Close-quarters, and able to do something about it.

    Carrying an attack is the discriminator rather than raw STR: a man
    with bare hands and STR 10 in a gunfight is not who a lawman holds a
    firing line against.
    """
    return bool(getattr(combatant, "attacks", None)) and not _has_any_ranged(combatant)


@register
class KeepRange(Tactic):
    name = "keep_range"
    basis = Basis(judgement="a ranged attacker that lets a brick close has thrown away its advantage")
    priority = 45
    narrative_summary = (
        "Your ranged attacks outclass enemies who can only fight in melee. "
        "Stay back — every meter they must close is a phase they waste. "
        "If they start to close, use a half-move AWAY before attacking. "
        "Use cover to deny their approach. "
        "Never let a melee brawler get adjacent when you can stay at range."
    )

    def applicable(self, situation: Situation) -> bool:
        if not _has_any_ranged(situation.actor):
            return False
        # A MELEE ENEMY WORTH DENYING, not merely one who lacks a gun.
        # This fired against anybody without a ranged attack, and an
        # unarmed man lacks one too -- so at the O.K. Corral the Earps
        # spent the historical fight shooting Billy Claiborne and Ike
        # Clanton, the two Cowboys who were unarmed and RUNNING, while
        # three armed men shot back. Ike died at BODY -8 in that run.
        # Both of them ran and lived.
        #
        # Being harmless is exactly what makes someone easy to keep range
        # from. A fighter carrying nothing is not a melee threat in a
        # gunfight; he is a man leaving.
        return any(_is_melee_threat(e) for e in situation.enemies)

    def execute(self, situation: Situation) -> Plan:
        best = _best_ranged_attack(situation)
        # The melee enemy worth DENYING, not merely the first one listed.
        # This took `melee_enemies[0]` -- roster order -- and at the O.K.
        # Corral both Ike Clanton (unarmed, running) and Power Lad (claws)
        # were melee-only, so the Earps kept their distance from the man
        # who could not hurt them. Being harmless is exactly what makes
        # someone easy to outrange, which is why this doctrine of all of
        # them needed a notion of danger.
        melee_enemies = [e for e in situation.enemies if _is_melee_threat(e)]
        pool = melee_enemies or list(situation.enemies)
        threat = situation.threat
        target = max(pool, key=lambda e: threat.get(e.id, 0.0)) if pool else None
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                "Actor has ranged attacks and at least one enemy is melee-only. "
                "Maintaining range denies the enemy their attack while actor "
                f"shoots freely at {best.damage_dice}d6."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid if best else None,
                    notes=(
                        "Fire at the melee-threat enemy from range. "
                        "If they have closed, half-move away first, "
                        "then shoot. Keep terrain between you."
                    ),
                    params={"maintain_range": True},
                ),
            ],
            expected_outcome=(
                "Melee enemy forced to waste a phase closing while actor "
                "lands ranged damage each segment."
            ),
        )
