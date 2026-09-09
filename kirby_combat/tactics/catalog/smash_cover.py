"""Smash destructible cover screening enemies.

When an actor has a damaging attack, the right play against entrenched
enemies is to destroy the cover they hide behind.  A DEF-6 stone wall
or a DEF-3 wooden barrier becomes rubble in 1-2 phases — then the
enemy stands exposed.

Preconditions:
  * Actor has at least one attack with damage_dice > 0.

Terrain linkage:
  The ``attack:construct`` and rapid-fire-vs-construct offers generated
  by the action enumeration layer are the concrete expression of this
  advice. This tactic's narrative text signals the chooser to prefer those
  menu entries when they appear.
"""
from __future__ import annotations

from kirby_combat.perception import perceive
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


#: Average BODY a die contributes. A killing attack's BODY is the dice
#: total (3.5 a die); a normal attack's is 1 on a 1, 2 on a 6 and 1
#: otherwise, which averages to exactly 1.
_KILLING_BODY_PER_DIE = 3.5
_NORMAL_BODY_PER_DIE = 1.0


def _expected_body(attack: Any) -> float:
    """What this attack puts into an object on an average roll."""
    dice = float(getattr(attack, "damage_dice", 0) or 0)
    killing = getattr(attack, "damage_type", "") == "killing"
    per_die = _KILLING_BODY_PER_DIE if killing else _NORMAL_BODY_PER_DIE
    body = dice * per_die
    if getattr(attack, "half_die", False):
        body += per_die / 2.0
    if getattr(attack, "plus_one", False):
        body += 1.0
    if getattr(attack, "minus_one", False):
        body -= 1.0
    return max(0.0, body)


def _can_hurt(attack: Any, wall: Any) -> bool:
    """Whether this attack gets any BODY at all through that wall.

    ARITHMETIC RATHER THAN JUDGEMENT. 6E2 p.172: an object takes BODY
    damage reduced by its DEF, so an attack whose average BODY does not
    beat DEF never marks the wall however long it fires. A tactic whose
    basis is "cover the enemy is using is worth more destroyed than
    ignored" is simply wrong in that case, and this can tell which case it
    is in.

    IT DOES NOT SETTLE THE O.K. CORRAL, and the numbers say so plainly.
    Everyone there carries roughly 2d6 killing --- the Colt Peacemaker is
    `LEVELS=1 + MINUSONEPIP`, one die ADDED to the base, so 2d6-1 and 6
    BODY average --- which puts 2 through the Harwood House's resistant
    DEF 4 and takes its 8-BODY wall in four shots. The 127 of 781
    decisions this benchmark spent shooting buildings were not futile.
    They were absurd for a different reason: an 8-BODY wall segment stands
    in for an entire boarding house, and destroying it calls
    `bring_it_down` on the whole structure. Four pistol shots level the
    Harwood House. That is a SCALE defect in the scene, not something a
    tactic gate can fix.

    6E2 p.173: a defense the Objects Table prints in parentheses is Normal
    Defense and does not apply against Killing damage --- glass is
    (1)/(1)/1 --- so the Colt that cannot scratch the boarding house goes
    straight through a window. `apply_attack_to_construct` already reads
    `resistant` this way; this asks the same question before spending a
    Phase on the answer.
    """
    defense = 0 if (getattr(attack, "damage_type", "") == "killing"
                    and not getattr(wall, "resistant", True)) else \
        int(getattr(wall, "def_value", 0) or 0)
    return _expected_body(attack) - defense > 0


def _screening_wall(situation: Situation) -> str | None:
    """The id of the wall between the actor and an enemy, if there is one.

    IT NAMED A PERSON. `attack_construct` offers are keyed by the WALL id
    (`attack:construct:flys-studio:...`), and this handed the chooser
    `target_id=virgil_earp`, so the plan matched no offer in any fight
    this engine ever ran --- 50 of the O.K. Corral benchmark's 142
    fall-throughs were this tactic alone, every Phase, never executable.
    The mirror of the defect the file already documents below, where it
    named the right man with the wrong kind.

    `perceive` has always returned `occluder_id`, "the REAL id of the
    nearest blocking wall". Nothing outside the perception tests read it.
    """
    session = getattr(situation, "session", None)
    scene = getattr(session, "scene", None)
    if scene is None:
        return None
    best = _best_damaging_attack(situation)
    walls = {getattr(w, "id", None): w
             for w in (getattr(scene, "walls", None) or [])}
    for enemy in situation.enemies:
        occluder = perceive(situation.actor, enemy, scene).occluder_id
        if not occluder:
            continue
        wall = walls.get(occluder)
        # A wall nothing on the map describes is not one we can price;
        # naming it is still better than naming the man.
        if wall is None or (best is not None and _can_hurt(best, wall)):
            return occluder
    return None


def _best_damaging_attack(situation: Situation):
    """Return the attack with the highest damage_dice, or None."""
    attacks = getattr(situation.actor, "attacks", [])
    damaging = [a for a in attacks if (a.damage_dice or 0) > 0]
    if not damaging:
        return None
    return max(damaging, key=lambda a: a.damage_dice)


@register
class SmashCover(Tactic):
    name = "smash_cover"
    basis = Basis(judgement="cover the enemy is using is worth more destroyed than ignored")
    priority = 35
    narrative_summary = (
        "Target the destructible cover or barrier screening your enemy. "
        "Fire your strongest attack into the wall or obstacle — a DEF-6 "
        "stone slab crumbles in 1-2 phases, leaving them fully exposed. "
        "Use rapid-fire or the attack:construct menu option to chip it "
        "down fast. Once cover is gone the enemy has nowhere to hide."
    )

    def applicable(self, situation: Situation) -> bool:
        """A damaging attack, somebody behind something, and a real chance
        of getting through it.

        This asked only the first half, which is true of everybody with a
        gun --- so the tactic whose basis is "cover the enemy is using is
        worth more destroyed than ignored" fired when no enemy was using
        any cover, at priority 35, ahead of tactics that would have shot
        somebody.
        """
        return (_best_damaging_attack(situation) is not None
                and _screening_wall(situation) is not None)

    # `_screening_wall` applies the futility test, so a wall this gun
    # cannot dent takes the tactic out of the running rather than
    # producing a plan nobody should follow.

    def execute(self, situation: Situation) -> Plan:
        best = _best_damaging_attack(situation)
        target_id = _screening_wall(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                "Enemies are shielded by destructible cover. "
                f"Best attack ({best.name}, {best.damage_dice}d6) should "
                "focus on the cover first — removing it denies their defense "
                "and opens a clear shot next phase."
            ),
            steps=[
                PlanStep(
                    # `attack_construct` is the kind that shoots the WALL.
                    # This said kind="attack" and put "choose
                    # attack:construct" in the notes, so it shot the man
                    # instead -- an ordinary attack wearing a tactic's name.
                    kind="attack_construct",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Aim at the cover or barrier screening the target, "
                        "not the target."
                    ),
                    params={"prefer_construct_target": True},
                ),
            ],
            expected_outcome=(
                "Cover DEF reduced or destroyed this phase, "
                "exposing the enemy for follow-up attacks."
            ),
        )
