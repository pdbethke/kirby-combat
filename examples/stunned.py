"""Stunned — a condition that bites.

Most VTTs let a "Stunned" tag sit on a token as decoration: it's true, and
nothing downstream reads it. HERO 6E does not allow that. 6E2 p.106,
"Stunning": a single attack that deals more STUN than the target's CON
Stuns him, and the moment that happens the rules take three things away
at once — his DCV and DMCV, his Abort, and his next Phase — while
pointedly leaving two others alone: his grip on what he's holding, and
the one free Recovery everyone gets regardless of consciousness.

This example runs one hit through that whole chain and prints the
combatant's derived state side by side at each step, the way a person
reading a status panel would: base CV next to effective CV, one status
set next to the next. That side-by-side view is deliberate — on this
branch, two prior conditions have each been individually correct and
only turned out to be jointly nonsensical when printed together.

Exercises:
  - resolve_attack_in_session (a hit that Stuns)
  - cv_modifiers_for / effective_dcv_for / effective_dmcv_for / effective_ocv_for
  - Dodge.declare -> mark_aborting (Abort refused, then allowed)
  - Encounter.advance_segment (the free Post-Segment 12 Recovery; the
    consumed recovery Phase; full recovery)
  - statuses.statuses_for, at every step

No dependencies beyond the package.

Run with:
    .venv/bin/python examples/stunned.py
"""
from __future__ import annotations

from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.cv_modifiers import (
    effective_dcv_for, effective_dmcv_for, effective_ocv_for,
)
from kirby_combat.dice import FakeRoller
from kirby_combat.encounter import Encounter
from kirby_combat.models import AttackInput, AttackPower, DiceValues, StatBlockCombatant
from kirby_combat.session import CombatSession
from kirby_combat.statuses import statuses_for
from kirby_combat.template import CombatTemplate


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def show_statuses(session: CombatSession, combatant_id: str, label: str) -> None:
    ids = sorted(statuses_for(session, combatant_id))
    print(f"   statuses_for({label!r}) = {{{', '.join(ids) if ids else '— none —'}}}")


IRONCLAD = StatBlockCombatant(
    id="ironclad", name="Ironclad",
    ocv=8, dcv=8, omcv=5, dmcv=5,
    spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
    pd=5, ed=5, rpd=0, red=0, md=5,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=15, max_end=30,
    current_stun=30, current_body=15, current_end=30,
    attacks=[
        AttackPower(
            xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
            half_die=False, plus_one=False,
            damage_type="normal", defense_type="ed", range_m=200,
            uses_str=False, str_min=0,
            armor_piercing=0, penetrating=0, increased_stun_mult=0,
        ),
    ],
    defenses=[],
)

# CON 15, no defenses, DCV 9 / DMCV 7 — the same values 20 STUN could
# shrug off but 36 cannot (6E2 p.106: "exceeds his CON", not "meets").
BOB = StatBlockCombatant(
    id="bob", name="Bob",
    ocv=8, dcv=9, omcv=5, dmcv=7,
    spd=4, dex=18, ego=15, str_=15, con=15, pre=15, rec=5,
    pd=0, ed=0, rpd=0, red=0, md=5,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=15, max_end=30,
    current_stun=30, current_body=15, current_end=30,
    attacks=[],
    defenses=[],
)


def main() -> None:
    rule("STUNNED — A CONDITION THAT BITES")

    session = CombatSession.create(
        id="s1",
        combatants=[IRONCLAD, BOB],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()

    # ── 1. A hit that Stuns ───────────────────────────────────────────────
    rule("1. A hit that Stuns — 6E2 p.106")
    print(f"  {BOB.name}: CON {BOB.con}, no PD/ED — anything over 15 STUN Stuns him.")

    # Fixed dice (no `random`): to-hit [3,3,3] -> roll 9, 8+11-9=10 >= DCV 9,
    # hits. Damage dice sum to 20 STUN, no defenses to subtract -- over
    # CON 15 (Stunned) but under current STUN 30 (NOT Knocked Out, so the
    # rest of this example demonstrates Stunned-while-conscious rather
    # than conflating it with unconsciousness).
    attack = AttackInput(
        attacker=IRONCLAD, target=BOB, power=IRONCLAD.attacks[0],
        distance_m=0, aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[3, 2, 3, 2, 3, 2, 1, 2, 1, 1],
        ),
    )
    session, result = resolve_attack_in_session(session, attack, session.template)
    print(f"  {IRONCLAD.name}'s Energy Blast hits for {result.stun_dealt} STUN "
          f"(CON {BOB.con}) -> status_changes={result.status_changes}")
    assert "Stunned" in result.status_changes  # this hit is meant to qualify

    show_statuses(session, "bob", "bob")

    # ── 2. CV before and after, side by side ────────────────────────────────
    rule("2. DCV / DMCV — before and after, side by side")
    print(f"  {'':14}{'OCV':>6}{'DCV':>6}{'DMCV':>6}")
    print(f"  {'base':14}{BOB.ocv:>6}{BOB.dcv:>6}{BOB.dmcv:>6}")
    print(f"  {'effective now':14}"
          f"{effective_ocv_for(session, 'bob'):>6}"
          f"{effective_dcv_for(session, 'bob'):>6}"
          f"{effective_dmcv_for(session, 'bob'):>6}")
    print("\n  OCV is untouched (6E2 p.106 names only DCV and DMCV); both")
    print("  defensive CVs are halved and rounded up (6E2 p.39).")

    # ── 3. An Abort refused ──────────────────────────────────────────────
    rule("3. Abort to Dodge — REFUSED")
    print('  6E2 p.106: "...he cannot even Abort to a defensive Action."')
    try:
        Dodge.declare(session, "bob")
        print("  Dodge.declare succeeded -- THIS WOULD BE THE BUG.")
    except ValueError as exc:
        print(f"  Dodge.declare raised ValueError: {exc}")

    # ── 4. The free Post-Segment 12 Recovery still arrives ─────────────────
    rule("4. Segment 12 wraps — the free Post-Segment 12 Recovery")
    print('  6E2 p.131: "...all characters (even Stunned ones) get a free')
    print('  Post-Segment 12 Recovery."')

    # `resolve_attack_in_session` never mutates vitals itself (log-only --
    # see its own docstring: the event log carries `stun_dealt`, but no
    # combatant's `current_stun` changes because of it). So bob's live
    # STUN is still 30/30 here even though the hit above dealt 20 -- to
    # give the free Recovery below visible room to raise it, set his
    # current STUN directly, the same way `test_stunned_enforcement.py`'s
    # own Recovery test does.
    from dataclasses import replace as _replace
    session = _replace(
        session,
        combatants={
            **session.combatants,
            "bob": _replace(session.combatants["bob"], current_stun=10),
        },
    )
    stun_before = session.combatants["bob"].current_stun
    print(f"  bob's current STUN before the wrap: {stun_before}")

    enc = Encounter(id="e1", segment=12, sessions=[session])
    enc = enc.advance_segment()   # 12 -> 1: this IS the wrap that fires it
    session = enc.sessions[0]

    stun_after = session.combatants["bob"].current_stun
    print(f"  bob's current STUN after the wrap:  {stun_after}   "
          f"(segment now {enc.segment}, turn {enc.turn})")
    assert stun_after > stun_before
    show_statuses(session, "bob", "bob")
    print("\n  Still Stunned by statuses_for (Segment 1 isn't one of bob's own")
    print("  Phases -- SPD 4 -> Segments 3/6/9/12), yet the free Recovery")
    print("  reached him anyway. That is not a contradiction: p.131's free")
    print("  Recovery is explicitly carved out from the p.106 denial, not an")
    print("  exception to it.")

    # ── 5. The recovery Phase itself is consumed ────────────────────────────
    rule("5. Segment 3 — bob's own Phase, spent recovering (6E2 p.107)")
    print('  6E2 p.107: "...recovering from being Stunned is all he can do')
    print('  that Phase." 6E2 p.39: the SAME DCV/hit-location 1/2 penalty')
    print('  is given its own row for "Recovering from being Stunned" --')
    print("  it does not lift the instant the narrower `stunned` id clears.")

    enc = enc.advance_segment()  # -> segment 2
    enc = enc.advance_segment()  # -> segment 3 (bob's Phase)
    session = enc.sessions[0]

    show_statuses(session, "bob", "bob")
    print(f"  effective DCV at segment {enc.segment}: "
          f"{effective_dcv_for(session, 'bob')} (still halved)")
    try:
        Dodge.declare(session, "bob")
        print("  Dodge.declare succeeded -- THIS WOULD BE THE BUG.")
    except ValueError as exc:
        print(f"  Dodge.declare STILL raises: {exc}")
    print("\n  Read side by side: 'stunned' is gone from the status set above,")
    print("  but 'recoveringFromStunned' has taken its place -- 6E2 p.39's")
    print("  own named row for this window (same 1/2 DCV/hit-location")
    print("  penalty as Stunned outright). The Abort is still refused and")
    print("  the DCV penalty is still live, and now the status set actually")
    print("  SAYS why: a status panel reading the id set alone would show")
    print("  bob as still conditioned, not as an unconditioned fighter who")
    print("  inexplicably can't act.")

    # ── 6. Fully recovered — right after the recovery Segment, not bob's
    #      NEXT Phase ──────────────────────────────────────────────────────
    rule("6. Segment 4 — fully recovered (6E2 p.107's Andarra example)")
    print('  6E2 p.107\'s own worked example (Andarra, DEX 20 SPD 3, Stunned')
    print('  Segment 6) restores full DCV and allows the Abort in Segments 9,')
    print('  10, and 11 -- all THREE Segments between her recovery Phase')
    print('  (Segment 8) and her next full Phase (Segment 12), not merely at')
    print('  that next Phase. So "recovering from being Stunned" spans only')
    print("  the ONE Segment containing the recovery Phase (bob's Segment 3,")
    print("  step 5 above) -- it is gone from the very next Segment onward,")
    print("  here Segment 4, well before bob's own next Phase at Segment 6.")

    enc = enc.advance_segment()  # -> segment 4: the Segment right after the
                                  # recovery Segment -- gone from here, not
                                  # from bob's next own Phase (segment 6).
    session = enc.sessions[0]

    show_statuses(session, "bob", "bob")
    print(f"  effective DCV / DMCV at segment {enc.segment}: "
          f"{effective_dcv_for(session, 'bob')} / "
          f"{effective_dmcv_for(session, 'bob')}   (base {BOB.dcv} / {BOB.dmcv})")

    session, evt = Dodge.declare(session, "bob")
    print(f"  Dodge.declare succeeded: to_action={evt.to_action!r}")
    print("\n  bob is clear here, in Segment 4 -- two Segments before his own")
    print("  next Phase (Segment 6) -- exactly the way Andarra is clear in")
    print("  Segments 9-11, well before HER next Phase (Segment 12). See")
    print("  examples/raw_andarra.py for the book's own example, driven and")
    print("  asserted Segment by Segment.")

    rule("END")


if __name__ == "__main__":
    main()
