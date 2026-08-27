"""Replay a fight from its log alone — what recording outcomes buys a client.

Before this branch, ``CombatSession``'s event log recorded almost nothing
about what an attack or a Block actually DID. ``ActionDeclared`` said what
someone tried; nothing said whether it landed, how much STUN and BODY it
dealt, or whether it Stunned or dropped its target. A client rebuilding a
combat's conditions from the log alone — the normal shape for a published
combat, since a Foundry token toggles status effects rather than
recomputing damage — had no way to answer "is this combatant Stunned right
now?" from the log, because nothing about a hit was ever written to it.

Three things changed (see this repo's 2026-08-27 record-outcomes plan):

  - ``Encounter.advance_segment`` now emits ``SegmentAdvanced`` onto every
    session it carries, per Segment — before this, the log held no
    evidence that time had passed at all (Task 1).
  - ``resolve_attack_in_session`` (``actions/recording.py``) records an
    attack's outcome as ``ActionResolved``, whose payload carries
    ``status_changes`` (plus ``kind``/``hit``/``stun_dealt``/``body_dealt``)
    — the pure ``resolve_attack`` calculator computes all of this but had
    no session to hand it to, so every caller before this either discarded
    it or (kirby-api) hand-rolled its own recording (Task 2).
  - ``kirby_combat.statuses.statuses_for`` folds ``stunned`` out of that
    payload: SET when a recorded hit's ``status_changes`` names
    "Stunned", CLEAR on the first ``SegmentAdvanced`` afterward that lands
    on this combatant's own Phase — 6E2 p.107, "RECOVERING FROM BEING
    STUNNED": "Recovering from being Stunned requires a Full Phase... he
    recovers from being Stunned when his DEX occurs in the Segment" of his
    next Phase (Task 4).

That is the headline this example exists to show: **``stunned`` appearing,
then clearing**, read out of the event log by ``statuses_for`` — not out of
any live combatant object. To make the "from the log alone" claim precise
rather than hand-wavy, this reconstructs two historical points using
``session.rewind.rewind_to_sequence`` (truncate the log to a sequence
number, replay every event through ``apply_event`` from scratch) and shows
``statuses_for`` agrees, at each point, with what was observed live as the
fight happened.

HONEST LIMIT, stated rather than papered over: **this does NOT show state
equality on STUN/BODY.** ``apply_event`` deliberately treats
``ActionResolved``, ``RecoveryTaken``, ``MovementResolved``, the ``Status*``
events, ``Entangle*`` and ``Flash*`` as log-only — see ``session/apply.py``,
directly above the set of kinds handled that way: "Rewind correctness
depends on this — combatant stat mutations in apply would force log replay
to mirror combatant state, which is more brittle." So a rebuilt session's
combatants keep whatever STUN/BODY they started with; only the DERIVED
conditions (``statuses_for``'s output) are what replay is claimed to
reconstruct, and that is exactly what a client publishing a combat needs,
since it toggles status effects rather than recomputing damage itself.

A second limit, also real: a **mental** Stunned is not recorded here.
``mental/mental_blast.py``'s own ``target_stunned`` computation has no
recording path — ``resolve_attack_in_session`` wraps only the physical
attack resolver — so ``statuses_for``'s ``stunned`` id today only ever
reflects a physical Stun. This example's attack is a physical Energy
Blast, deliberately, so it exercises the path that actually exists.

Exercises:
  - Encounter.advance_segment (SegmentAdvanced, and RecoveryTaken on the
    Segment-12 wrap, 6E2 p.131)
  - actions.recording.resolve_attack_in_session (ActionResolved with
    status_changes)
  - kirby_combat.statuses.statuses_for (stunned appearing and clearing)
  - session.rewind.rewind_to_sequence (reconstruction from a truncated log)

No dependencies beyond the package.

Run with:
    .venv/bin/python examples/replay_a_fight.py
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.actions import resolve_attack
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.dice import FakeRoller
from kirby_combat.encounter import Encounter
from kirby_combat.models import AttackInput, AttackPower, DiceValues, StatBlockCombatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.statuses import STUNNED, statuses_for
from kirby_combat.template import CombatTemplate


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


HERO = StatBlockCombatant(
    id="hero", name="Arclight",
    ocv=9, dcv=7, omcv=4, dmcv=4,
    spd=4, dex=20, ego=15, int_=13, str_=20, con=18, pre=20, rec=8,
    pd=6, ed=6, rpd=0, red=0, md=5,
    power_defense=0, flash_defense=0,
    max_stun=35, max_body=15, max_end=40,
    current_stun=35, current_body=15, current_end=40,
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

# SPD 4 -> Phases at Segments 3, 6, 9, 12 (segments_for_spd, tables.py).
# CON 15 -> a 10d6 EB against 0 defenses deals well over CON in STUN, so the
# hit qualifies as Stunned (resolution/status.py: stun_dealt > CON).
VILLAIN = StatBlockCombatant(
    id="villain", name="Silver Hand",
    ocv=7, dcv=6, omcv=4, dmcv=4,
    spd=4, dex=17, ego=13, int_=10, str_=15, con=15, pre=15, rec=6,
    pd=0, ed=0, rpd=0, red=0, md=3,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=14, max_end=30,
    current_stun=30, current_body=14, current_end=30,
    attacks=[], defenses=[],
)


def _hitting_attack(attacker, target) -> AttackInput:
    # to_hit rolls 9 (well inside range); damage dice are chosen so the
    # 10d6 Normal EB totals 36 STUN — no rolled variance, no ``random``.
    return AttackInput(
        attacker=attacker, target=target, power=attacker.attacks[0],
        distance_m=0, aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
        ),
    )


def print_log(session: CombatSession) -> None:
    """The log as a sequence a client could replay — kind, and the fields
    that matter, in event order."""
    for e in session.event_log:
        if e.kind == "ActionDeclared":
            print(f"   [{e.sequence:>2}] ActionDeclared   "
                  f"{e.combatant_id} -> {e.action_type} on {e.targets}")
        elif e.kind == "ActionResolved":
            p = e.result_payload
            print(f"   [{e.sequence:>2}] ActionResolved   "
                  f"kind={p['kind']!r} hit={p['hit']} "
                  f"stun_dealt={p['stun_dealt']} body_dealt={p['body_dealt']} "
                  f"status_changes={p['status_changes']}")
        elif e.kind == "SegmentAdvanced":
            print(f"   [{e.sequence:>2}] SegmentAdvanced  "
                  f"{e.from_segment} -> {e.to_segment} (Turn {e.to_turn})")
        elif e.kind == "RecoveryTaken":
            print(f"   [{e.sequence:>2}] RecoveryTaken    "
                  f"{e.combatant_id} +{e.stun_recovered} STUN "
                  f"+{e.end_recovered} END")
        else:
            print(f"   [{e.sequence:>2}] {e.kind}")


def show_statuses(session: CombatSession, combatant_id: str, label: str) -> None:
    ids = sorted(statuses_for(session, combatant_id))
    print(f"   {label:32} {combatant_id}: {ids if ids else '(none)'}")


def main() -> None:
    rule("REPLAY A FIGHT — reconstructing conditions from the log alone")

    template = CombatTemplate.default_6e_superheroic()
    session = CombatSession.create(
        id="s1", combatants=[HERO, VILLAIN], scene=None,
        template=template, dice_roller=FakeRoller([]),
    ).start()

    # Combat begins on Segment 12 (6E2 p.20) — one of the villain's own
    # Phases (SPD 4 -> 3/6/9/12), so the hit below lands on his Phase.
    encounter = Encounter(id="e1", turn=1, segment=12, sessions=[session])

    # ── 1. Contrast: an attack that records nothing ──────────────────────────
    rule("1. Before this branch — an attack the log never heard about")
    attack = _hitting_attack(HERO, VILLAIN)
    bare_result = resolve_attack(attack, template)
    print(f"  resolve_attack (pure) says: hit={bare_result.hit} "
          f"stun_dealt={bare_result.stun_dealt} "
          f"status_changes={bare_result.status_changes}")
    print("  That calculation is correct and immediately thrown away — the")
    print("  session above never sees it, so statuses_for still reports:")
    show_statuses(session, VILLAIN.id, "no ActionResolved on log ->")
    print("  STUNNED does not appear, even though the hit plainly stunned him.")
    print("  This is the gap resolve_attack_in_session closes.")

    # ── 2. Record the same hit on the session's own log ──────────────────────
    rule("2. The same hit, recorded")
    live_session, result = resolve_attack_in_session(
        encounter.sessions[0], attack, template,
    )
    assert "Stunned" in result.status_changes  # sanity: the hit really qualifies
    encounter = replace(encounter, sessions=[live_session])
    sequence_at_hit = len(encounter.sessions[0].event_log)

    show_statuses(encounter.sessions[0], VILLAIN.id, "right after ActionResolved ->")
    assert STUNNED in statuses_for(encounter.sessions[0], VILLAIN.id)
    print("  stunned now appears — folded out of ActionResolved.status_changes,")
    print("  not read from any live combatant field.")

    # ── 3. Time passes — SegmentAdvanced, then the clear edge ────────────────
    rule("3. Time passes — Encounter.advance_segment")
    print("  12 -> 1 wraps the Turn (6E2 p.18): everyone gets a free")
    print("  Post-Segment 12 Recovery first (6E2 p.131), THEN SegmentAdvanced")
    print("  is logged for the Segment that just ended.")
    encounter = encounter.advance_segment()          # 12 -> 1 (wrap + Recovery)
    show_statuses(encounter.sessions[0], VILLAIN.id, "after 12 -> 1 (not his Phase) ->")
    assert STUNNED in statuses_for(encounter.sessions[0], VILLAIN.id)

    encounter = encounter.advance_segment()          # 1 -> 2
    show_statuses(encounter.sessions[0], VILLAIN.id, "after 1 -> 2  (not his Phase) ->")
    assert STUNNED in statuses_for(encounter.sessions[0], VILLAIN.id)
    print("  Segment 12 is one of the villain's Phases too, but that Phase")
    print("  already happened — it takes his NEXT one (Segment 3) to clear.")

    encounter = encounter.advance_segment()          # 2 -> 3 (his Phase)
    show_statuses(encounter.sessions[0], VILLAIN.id, "after 2 -> 3  (HIS Phase) ->")
    assert STUNNED not in statuses_for(encounter.sessions[0], VILLAIN.id)
    print("  stunned clears exactly on the Segment that is a Phase for HIM")
    print("  (6E2 p.107) — not on the first Segment to pass, and not by")
    print("  magic: apply_event never mutates a combatant to make this true,")
    print("  statuses_for derives it fresh from the log every time.")

    sequence_at_clear = len(encounter.sessions[0].event_log)

    # One more Segment for the log to carry past the clear point, so the
    # reconstruction below is a real truncation, not a same-length no-op.
    encounter = encounter.advance_segment()          # 3 -> 4
    final_session = encounter.sessions[0]

    # ── 4. The log, in order ──────────────────────────────────────────────────
    rule("4. The log as a replayable sequence")
    print_log(final_session)

    # ── 5. Reconstruct two historical points from the log alone ─────────────
    rule("5. Reconstruction — rewind_to_sequence + statuses_for agree with live")
    print("  rewind_to_sequence truncates the log to a sequence number, builds")
    print("  a FRESH session, and replays every kept event through apply_event")
    print("  from scratch. What is asserted below is that statuses_for reads")
    print("  the SAME condition set off that rebuilt session as was observed")
    print("  live at the same point — not that STUN/BODY match (they don't")
    print("  have to: apply_event treats ActionResolved/RecoveryTaken as")
    print("  log-only, by design — see this file's module docstring).")

    reconstructed_at_hit = rewind_to_sequence(final_session, sequence_at_hit)
    at_hit = statuses_for(reconstructed_at_hit, VILLAIN.id)
    print(f"\n  reconstructed @ seq {sequence_at_hit} (right after the hit): "
          f"{sorted(at_hit)}")
    assert STUNNED in at_hit
    print("  stunned is there — rebuilt from a truncated log with no")
    print("  Post-Segment-12 Recovery or SegmentAdvanced events at all.")

    reconstructed_at_clear = rewind_to_sequence(final_session, sequence_at_clear)
    at_clear = statuses_for(reconstructed_at_clear, VILLAIN.id)
    print(f"  reconstructed @ seq {sequence_at_clear} (his next Phase): "
          f"{sorted(at_clear)}")
    assert STUNNED not in at_clear
    print("  stunned is gone — reconstructed from a log that ends one Segment")
    print("  before the final one printed above, and still agrees with what")
    print("  was observed live at that same sequence number.")

    rule("END")


if __name__ == "__main__":
    main()
