"""Orion fights blind — 6E2 p.9, reproduced.

This is not an illustration. It is a conformance check that happens to be
readable: the rulebook's own worked example is restated below, the engine is
driven through it, and every number the book states is ASSERTED against what
the engine produced. If the engine ever stops agreeing with the book, this
script exits non-zero and `tests/test_examples.py` fails with it.

THE BOOK'S SCENARIO (6E2 p.9), PARAPHRASED — this project ships no rules
text; open your own copy:

    Orion is blinded by a Flash. Unable to perceive anyone with a Targeting
    Sense, he is halved on both OCV and DCV hand-to-hand, and at Range his
    OCV drops to zero while his DCV is halved. The book calls him a sitting
    duck.

    He then spends a Half Phase Action on a Hearing PER Roll against ONE of
    his attackers, Durak, and makes it. Against Durak ONLY he is now at -1
    DCV and half OCV hand-to-hand, and at FULL DCV and half OCV at Range.
    Against every other opponent the unmitigated numbers still stand.

WHY THIS EXAMPLE IS WORTH A SCRIPT. Three things in it break any design that
treats "blind" as a single global CV factor, and each is asserted below:

  1. The same combatant has DIFFERENT CVs against DIFFERENT opponents in the
     same Segment. Orion is 4 DCV against Fiacho and 7 DCV against Durak.
  2. The mitigated hand-to-hand DCV is a FLAT -1, not a second halving. A
     design that halves again gets 2 where the book says 7.
  3. Mitigation is asymmetric. Hearing Durak restores Orion's FULL DCV at
     Range but only lifts his hand-to-hand DCV to -1 — and it lifts his
     Ranged OCV off zero while leaving his hand-to-hand OCV halved.

Orion's own CVs are not stated on the page, so this script gives him 8 OCV /
8 DCV. The book states RATIOS and a flat modifier; 8 is chosen because it is
even (so "half" needs no rounding argument to be checked by eye) and because
the halved and mitigated values are then plainly different numbers — 4 versus
7 — rather than two roundings of the same one.

Run with:
    .venv/bin/python examples/raw_orion.py
"""
from __future__ import annotations

from kirby_combat.actions.flash import Flash
from kirby_combat.cv_modifiers import effective_dcv_for, effective_ocv_for
from kirby_dice import FakeRoller
from kirby_combat.models import StatBlockCombatant
from kirby_combat.sense_penalties import NontargetingPerception
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def _combatant(id_: str, name: str) -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=name,
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5,
        power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[], defenses=[],
    )


ORION = _combatant("orion", "Orion")
DURAK = _combatant("durak", "Durak")          # the one he hears
FIACHO = _combatant("fiacho", "Fiacho")       # everyone else


def _report(session: CombatSession, opponent: str) -> tuple[int, int, int, int]:
    hth_ocv = effective_ocv_for(session, "orion", against=opponent, combat_type="hth")
    hth_dcv = effective_dcv_for(session, "orion", against=opponent, combat_type="hth")
    rng_ocv = effective_ocv_for(session, "orion", against=opponent, combat_type="ranged")
    rng_dcv = effective_dcv_for(session, "orion", against=opponent, combat_type="ranged")
    print(f"    vs {opponent:<7}  HTH: OCV {hth_ocv}  DCV {hth_dcv}"
          f"   │   Range: OCV {rng_ocv}  DCV {rng_dcv}")
    return hth_ocv, hth_dcv, rng_ocv, rng_dcv


def main() -> None:
    rule("ORION FIGHTS BLIND — 6E2 p.9")

    session = CombatSession.create(
        id="s1",
        combatants=[ORION, DURAK, FIACHO],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()

    print("\n  Orion, unblinded — 8 OCV / 8 DCV against anyone:")
    assert _report(session, "durak") == (8, 8, 8, 8)
    assert _report(session, "fiacho") == (8, 8, 8, 8)

    # ── The Flash ───────────────────────────────────────────────────────
    rule("Eurostar Flashes Orion's Sight Group")

    session, _ = Flash.apply(
        session, attacker_id="fiacho", target_id="orion",
        sense_group="sight", body_dealt=8, flash_defense=0,
    )
    flashed, groups = Flash.is_flashed(session, "orion")
    print(f"\n  Flashed: {flashed}  groups: {groups}")
    print("  Sight is a normal human's only Targeting Sense, so Orion can now")
    print("  perceive NOBODY with one.\n")

    # The book: half OCV and half DCV in HTH; 0 OCV and half DCV at Range.
    print("  A sitting duck — the unmitigated penalties:")
    assert _report(session, "durak") == (4, 4, 0, 4)
    assert _report(session, "fiacho") == (4, 4, 0, 4)

    # ── The Hearing PER Roll ────────────────────────────────────────────
    rule("Orion spends a Half Phase on a Hearing PER Roll against Durak")

    session, per = NontargetingPerception.acquire(
        session, observer_id="orion", target_id="durak",
        sense_group="hearing",
        roller=FakeRoller([[2, 2, 2]]),        # 3d6 = 6, a comfortable make
    )
    print(f"\n  PER Roll: {per.roll} vs {per.target_number}- → "
          f"{'MADE' if per.succeeded else 'MISSED'}")
    assert per.succeeded

    declared = [e for e in session.event_log
                if e.kind == "ActionDeclared"
                and e.action_type == "nontargeting_perception"]
    assert len(declared) == 1
    assert declared[0].parameters["phase_cost"] == "half"
    print(f"  Recorded on the log as a {declared[0].parameters['phase_cost']} "
          f"Phase Action, so a driver can charge for it.\n")

    print("  THE CONTRAST — the same combatant, the same Segment:")
    # Against Durak: -1 DCV (a FLAT modifier: 8 -> 7, NOT 8 -> 4 -> 2) and
    # half OCV in HTH; FULL DCV and half OCV at Range.
    assert _report(session, "durak") == (4, 7, 4, 8)
    # Against everyone else: nothing has changed.
    assert _report(session, "fiacho") == (4, 4, 0, 4)

    print("\n  Read the two rows together — that contrast IS the rule:")
    print("    · DCV 7 vs Durak, DCV 4 vs Fiacho, in the same Segment.")
    print("    · 7, not 2: the mitigation is a flat -1, not a second halving.")
    print("    · FULL DCV 8 at Range vs Durak, but only -1 in HTH — the")
    print("      mitigation is asymmetric, and a single factor cannot say so.")
    print("    · Ranged OCV 4 vs Durak against 0 vs Fiacho.")

    # ── Expiry ──────────────────────────────────────────────────────────
    rule("The benefit lapses at the start of Orion's next Phase")

    session, lapsed = NontargetingPerception.expire_for_combatant_next_phase(
        session, "orion")
    print(f"\n  Lapsed against: {lapsed}")
    assert lapsed == ["durak"]
    print("  Orion is a sitting duck against everyone again until he spends")
    print("  another Half Phase Action and makes another roll:\n")
    assert _report(session, "durak") == (4, 4, 0, 4)
    assert _report(session, "fiacho") == (4, 4, 0, 4)

    rule("END — every number 6E2 p.9 states for Orion confirmed, "
         "against Durak and against everyone else.")


if __name__ == "__main__":
    main()
