"""Was that a GOOD choice? — the question every benchmark here dodged.

`docs/gaps.md` ends on the admission that closes a week of measurement:
"It does not settle that the choices are GOOD ... nothing here grades a
decision as right or wrong." Coverage counts VARIETY -- how many of 62
action kinds get chosen, which rule paths fire -- so a fighter who spends
the fight demolishing scenery scores as pleasing breadth, and did.

THESE ONLY EVER INDICT. A Phase with no finding is not endorsed; it is
merely not provably wrong. Whether an attack was the BEST available
choice is judgement and `critique` has none. Whether it could not
possibly have worked is arithmetic.

AND THEY GRADE DOCTRINE. Pointed at `TacticChooser` on the street
benchmark, this found three Phases spent shooting a building while a man
was on the menu. That is an engine finding, not a chooser finding, and
nothing before this could count it.

Exercises:
  - critique / Finding
  - the futile attack: a best-possible roll that gets nothing through
  - the scenery finding, and why "a wall is all there is" is not one
  - the wasted Phase: Recover at full STUN and END

Run: python examples/grading_a_decision.py
"""
from __future__ import annotations

from kirby_combat import critique
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.models import AttackPower, StatBlockCombatant


def a_man(name: str, *, pd: int, rpd: int, stun: int = 20, end: int = 20):
    return StatBlockCombatant(
        id=name.lower(), name=name, ocv=8, dcv=8, omcv=5, dmcv=5, spd=4,
        dex=10, ego=10, str_=15, con=15, pre=15, rec=5,
        pd=pd, ed=pd, rpd=rpd, red=rpd, md=0, power_defense=0,
        flash_defense=0, max_stun=20, max_body=20, max_end=20,
        current_stun=stun, current_body=20, current_end=end,
    )


def a_gun(name: str, dice: int, *, killing: bool) -> AttackPower:
    return AttackPower(
        xmlid="RKA" if killing else "EB", name=name, damage_dice=dice,
        half_die=False, plus_one=False,
        damage_type="killing" if killing else "normal",
        defense_type="pd", range_m=100.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=True,
    )


def shot_at(target_id: str, power: AttackPower, *, scenery: bool = False):
    return LegalAction(
        action_id=f"attack:{target_id}:src1", kind="attack",
        target_id=target_id, power_xmlid=power.xmlid, power_name=power.name,
        summary=f"{power.name} at {target_id}", _attack_view=power,
        targets_construct=scenery,
    )


RECOVER = LegalAction(action_id="recover", kind="recover", target_id=None,
                      power_xmlid=None, power_name=None, summary="Recover")


def verdict(situation: PhaseSituation, action_id: str) -> str:
    found = critique(situation, action_id)
    if not found:
        return "  (nothing provably wrong — which is NOT praise)"
    return "\n".join(f"  {f.render()}" for f in found)


def main() -> None:
    ironclad = a_man("Ironclad", pd=30, rpd=30)   # a man in plate
    mark = a_man("Mark", pd=10, rpd=2)            # a man in a shirt

    print("1. A 1d6 blast at a man in plate")
    peashooter = shot_at("ironclad", a_gun("Blast", 1, killing=False))
    print(verdict(PhaseSituation(actor=mark, menu=[peashooter],
                                 enemies=[ironclad], segment=12), peashooter.action_id))

    print("\n2. The SAME blast at a man in a shirt — still futile.")
    print("   1d6 maxes at 6 STUN and 2 BODY; 10 PD eats both. A gun")
    print("   can be useless against an ordinary man, not just a tank.")
    shirt = shot_at("mark", a_gun("Blast", 1, killing=False))
    print(verdict(PhaseSituation(actor=ironclad, menu=[shirt], enemies=[mark],
                                 segment=12), shirt.action_id))

    print("\n2b. 2d6 at the same man: maxes at 12 STUN against 10 PD, so")
    print("    2 points get through on a perfect roll and nothing on most.")
    print("    A bad bet is NOT a finding — this indicts only what")
    print("    cannot work at all.")
    thin = shot_at("mark", a_gun("Blast", 2, killing=False))
    print(verdict(PhaseSituation(actor=ironclad, menu=[thin], enemies=[mark],
                                 segment=12), thin.action_id))

    print("\n3. A Colt at the same shirt: killing BODY answers to")
    print("   RESISTANT defense alone, so 2 rPD is not 10 PD")
    colt = shot_at("mark", a_gun("Colt", 2, killing=True))
    print(verdict(PhaseSituation(actor=ironclad, menu=[colt], enemies=[mark],
                                 segment=12), colt.action_id))

    print("\n4. Shooting a building while a man is on the menu")
    wall = shot_at("harwood-interior", a_gun("Colt", 2, killing=True), scenery=True)
    man = shot_at("mark", a_gun("Colt", 2, killing=True))
    print(verdict(PhaseSituation(actor=ironclad, menu=[wall, man],
                                 enemies=[mark], segment=12), wall.action_id))

    print("\n5. The same shot when the building is all there is")
    print("   (the engine's own words: 'when a wall is all there is,")
    print("    a wall is what he hits')")
    print(verdict(PhaseSituation(actor=ironclad, menu=[wall], enemies=[],
                                 segment=12), wall.action_id))

    print("\n5b. Emptying a revolver into a stone bank wall")
    print("    A construct's BODY answers to its DEF (6E2 p.173).")
    print("    2d6 killing maxes at 12 BODY; DEF 12 eats all of it,")
    print("    so the wall can be shot all day and never mark.")
    from kirby_combat.scene.construct import Construct

    class _Scene:
        constructs = [Construct(obj_id="stone-bank", kind="wall",
                                def_value=12, body=30)]
        walls = ()
        furnishings = ()

    class _Session:
        scene = _Scene()

    bank = shot_at("stone-bank", a_gun("Colt", 2, killing=True), scenery=True)
    print(verdict(PhaseSituation(actor=ironclad, menu=[bank], enemies=[],
                                 session=_Session(), segment=12), bank.action_id))
    print("    (A plank fence at DEF 3 would NOT be a finding --- and the")
    print("     Harwood house at DEF 8 is not either: a Colt gets 4 BODY")
    print("     through at best, which is slow, not impossible.)")

    print("\n6. Recovering at full STUN and END")
    whole = a_man("Whole", pd=10, rpd=2)
    print(verdict(PhaseSituation(actor=whole, menu=[RECOVER], segment=12),
                  "recover"))

    print("\n7. Recovering at 4 STUN and 2 END")
    hurt = a_man("Hurt", pd=10, rpd=2, stun=4, end=2)
    print(verdict(PhaseSituation(actor=hurt, menu=[RECOVER], segment=12),
                  "recover"))


if __name__ == "__main__":
    main()
