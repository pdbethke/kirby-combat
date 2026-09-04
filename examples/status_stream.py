"""The status stream — a combat published as a sequence a client replays.

The motivation for this whole feature line: *"so we can publish live
code-based combat sequences."* A Foundry (or any VTT) client does not want
to understand HERO System rules to keep its tokens honest. It wants a feed
it can apply blindly: "this token gained id X", "this token lost id Y".

Two event families exist side by side in this engine, and this example is
built to show the SEAM between them:

  - The *rules* events (`EntangleApplied`, `FlashApplied`, the `ActionResolved`
    payloads for a Grab or a Grab Escape) are the ground truth. They carry
    HERO mechanics: entangle BODY/PD/ED (HERO 6E1 Entangle; 6E2 Entangled
    characters are 0 DCV / half OCV), Flash segments-blinded (HERO 6E1
    Flash: segments = BODY dealt − Flash Defense), a Grab's Attack Roll
    (6E2 p67 SS USING GRAB). A client that wants to know *why* a token
    changed replays these -- but to render a token's ring icons it would
    first have to re-derive "is this combatant currently entangled" itself,
    by scanning for an Applied event with no matching Escape/Recovered event
    -- exactly the derivation `kirby_combat.statuses.statuses_for` already
    does once, engine-side (see that module's docstring).

  - The *status* event (`StatusEffectsChanged`, from
    `kirby_combat.status_emission.status_deltas`) is the derived, Foundry-
    shaped output of that derivation: a combatant id plus the set of
    `kirby_combat.statuses.ALL_STATUS_IDS` gained and lost. A client
    toggles those ids on a token directly -- `token.toggleStatusEffect(id)`
    -- and never needs to know an Entangle from a Grab.

This example runs a short, fully scripted fight and prints BOTH streams
side by side at each step, so the contrast is visible: the raw rules event
that just happened, and the one-line status delta a client actually
consumes.

Conditions demonstrated (the full set this engine can currently produce,
per `kirby_combat/statuses.py`):
    entangled, grab, sightSenseDisabled, hearingSenseDisabled, aborted, holding,
    knockedOut -- gained, and (where the underlying rule allows it) later
    lost again, so the stream shows both directions of the toggle.

Two honest gaps, not papered over (see step 7 and the closing note):

  - `stunned` is computed by `resolution/status.py`'s
    `determine_status_changes` (HERO 6E: a single attack's STUN dealt
    exceeding the target's CON) but nothing in the engine logs that
    computation today -- `actions/base.py` sets it on the returned
    `AttackResult` and emits no `ActionResolved` for it. Step 7 calls that
    same pure function directly to show it firing, then shows the status
    stream for the same STUN drop -- `knockedOut` arrives, `stunned` does
    not. That gap is architectural (attack resolution needs to log before
    this can close), not something this example works around.

  - `prone` never appears at all: it is a parameter into cover resolution
    and a maneuver flag, not a per-combatant stored condition anywhere in
    this engine (see the NOTE in `kirby_combat/statuses.py`), so there is
    nothing to emit.

No dependencies beyond the package. No randomness -- every roll and STUN
value below is a fixed literal so the output is identical on every run.

Run with:
    .venv/bin/python examples/status_stream.py
"""
from __future__ import annotations

import dataclasses

from kirby_combat.actions.entangle import Entangle
from kirby_combat.actions.flash import Flash
from kirby_combat.actions.grab import Grab
from kirby_combat.actions.held_action import HeldAction
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_dice import FakeRoller
from kirby_combat.models import StatBlockCombatant
from kirby_combat.resolution.status import determine_status_changes
from kirby_combat.session import CombatSession
from kirby_combat.status_emission import status_deltas
from kirby_combat.template import CombatTemplate


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


WEAVER = StatBlockCombatant(
    id="weaver", name="The Weaver",
    ocv=8, dcv=6, omcv=4, dmcv=4,
    spd=4, dex=18, ego=13, int_=13, str_=20, con=18, pre=15, rec=8,
    pd=8, ed=8, rpd=0, red=0, md=3,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=14, max_end=40,
    current_stun=30, current_body=14, current_end=40,
    attacks=[], defenses=[],
)

VANGUARD = StatBlockCombatant(
    id="vanguard", name="Vanguard",
    ocv=8, dcv=5, omcv=5, dmcv=5,
    spd=4, dex=20, ego=15, int_=13, str_=15, con=15, pre=20, rec=8,
    pd=6, ed=6, rpd=0, red=0, md=5,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=15, max_end=40,
    current_stun=30, current_body=15, current_end=40,
    attacks=[], defenses=[],
)


def event_kinds_since(session: CombatSession, prior_len: int) -> list[str]:
    """The raw rules-event kinds appended by the action just taken."""
    return [evt.kind for evt in session.event_log[prior_len:]]


def show_step(label: str, before: CombatSession, after: CombatSession) -> CombatSession:
    """Print one step's raw rules events beside its derived status stream,
    then return `after` unchanged (the caller threads session state)."""
    kinds = event_kinds_since(after, len(before.event_log))
    print(f"\n  {label}")
    print(f"     rules events logged:  {', '.join(kinds)}")

    deltas = status_deltas(
        before, after, session_id=after.id,
        start_sequence=len(after.event_log) + 1,
    )
    if not deltas:
        print("     status stream:        (no change)")
    for evt in deltas:
        gained = ", ".join(sorted(evt.added)) or "-"
        lost = ", ".join(sorted(evt.removed)) or "-"
        print(f"     status stream:        {evt.combatant_id:10} "
              f"+[{gained}]  -[{lost}]")
    return after


def main() -> None:
    rule("THE STATUS STREAM — a combat published as tokens a client toggles")

    session = CombatSession.create(
        id="showcase",
        combatants=[WEAVER, VANGUARD],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()

    # ── 1. Entangle lands ─────────────────────────────────────────────────
    rule("1. The Weaver entangles Vanguard (HERO 6E1 Entangle)")
    before = session
    session, _ = Entangle.apply(
        session, attacker_id="weaver", target_id="vanguard",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    show_step("Entangle: 8 BODY / 4 PD / 4 ED", before, session)

    # ── 2. Flash — two sense groups at once ─────────────────────────────────
    rule("2. The Weaver flashes Vanguard's sight, then hearing")
    before = session
    session, _ = Flash.apply(
        session, attacker_id="weaver", target_id="vanguard",
        sense_group="sight", body_dealt=10, flash_defense=0,
    )
    show_step("Flash vs Sight Group (10 BODY, 0 Flash Defense)", before, session)

    before = session
    session, _ = Flash.apply(
        session, attacker_id="weaver", target_id="vanguard",
        sense_group="hearing", body_dealt=10, flash_defense=0,
    )
    show_step("Flash vs Hearing Group (10 BODY, 0 Flash Defense)", before, session)
    print("\n     Two Applied events, two independent ids -- statuses_for")
    print("     never collapses simultaneous conditions into one.")

    # ── 3. Vanguard aborts to Dodge, then holds an action ───────────────────
    rule("3. Vanguard aborts to Dodge, then holds a phase")
    before = session
    session, _ = mark_aborting(session, "vanguard", to_action="dodge")
    show_step('Abort to Dodge (6E2 p63, DODGE -- "Characters can Abort to Dodge")', before, session)

    before = session
    session, _ = HeldAction.declare(
        session, "vanguard", trigger_condition="Weaver breaks cover",
    )
    show_step("Hold an Action (6E2 p61 SS HOLD AN ACTION)", before, session)

    # ── 4. Weaver grabs Vanguard on top of the entangle ─────────────────────
    rule("4. The Weaver grabs Vanguard (6E2 p67 SS USING GRAB)")
    before = session
    session, grab = Grab.declare_and_resolve(
        session, attacker_id="weaver", target_id="vanguard",
        attacker_str=20, target_str=15,
        attacker_ocv=8, target_dcv=5, attack_roll=10,
    )
    show_step(f"Grab attack roll 10 vs effective DCV -> hit={grab.hit}",
               before, session)

    # ── 5. Vanguard breaks the entangle with full STR ──────────────────────
    rule("5. Vanguard breaks free of the entangle (full STR)")
    before = session
    session, _ = Entangle.escape_attempt(
        session, target_id="vanguard", damage_body=99, escape_type="full",
    )
    show_step("Full-STR escape (6E2, damage = STR/5 - entangle PD)",
               before, session)

    # ── 6. Vanguard escapes the grab too ────────────────────────────────────
    rule("6. Vanguard escapes the grab (STR vs STR)")
    before = session
    session, _ = Grab.escape(
        session, escaper_id="vanguard", escaper_str=25, grabber_str=15,
    )
    show_step("Escape: 25 STR vs 15 STR -- escaper wins", before, session)

    # ── 7. A hit hard enough to Stun AND Knock Out -- one id makes the trip ─
    rule("7. Vanguard takes 30 STUN in one hit (CON 15) -- the honest gap")
    changes = determine_status_changes(
        stun_before=30, stun_after=0, body_before=15, body_after=13,
        con=15, max_body=15,
    )
    print(f"  resolution/status.py computes: {changes}")
    print("  (stun_dealt 30 > CON 15 -> 'Stunned'; STUN at 0 -> 'Knocked Out')")

    before = session
    knocked_out_vanguard = dataclasses.replace(
        session.combatants["vanguard"], current_stun=0,
    )
    session = dataclasses.replace(
        session,
        combatants={**session.combatants, "vanguard": knocked_out_vanguard},
    )
    deltas = status_deltas(
        before, session, session_id=session.id,
        start_sequence=len(before.event_log) + 1,
    )
    for evt in deltas:
        print(f"  status stream:  {evt.combatant_id:10} "
              f"+[{', '.join(sorted(evt.added))}]  -[{', '.join(sorted(evt.removed))}]")
    print("\n  'Stunned' computed above never reaches this stream: nothing in")
    print("  the engine logs an attack resolution to persist it (see")
    print("  actions/base.py and kirby_combat/statuses.py's STUNNED note).")
    print("  Only 'knockedOut' -- read from current_stun directly -- toggles.")

    rule("END — a Foundry token toggles every id above without ever")
    print("  knowing what an Entangle, a Flash, or a Grab is.")


if __name__ == "__main__":
    main()
