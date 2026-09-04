"""Andarra recovers from being Stunned — 6E2 p.107, reproduced.

This is not an illustration. It is a conformance check that happens to be
readable: the rulebook's own worked example is quoted verbatim below, the
engine is driven through it, and every number the book states is ASSERTED
against what the engine produced. If the engine ever stops agreeing with the
book, this script exits non-zero and `tests/test_examples.py` fails with it.

That matters here more than most places. An earlier version of this engine
got this exact example wrong -- it refused Aborts the book grants by name in
Segments 9, 10 and 11, and halved a DCV the book explicitly restores --
because the design cited 6E2 p.39 and p.106 for a claim that lives on p.107.
Every test passed the whole time. Quoting the page in full, and then running
the page, is what caught it.

THE BOOK'S SCENARIO (6E2 p.107, "RECOVERING FROM BEING STUNNED"),
PARAPHRASED -- this project ships no rules text; open your own copy:

    A character with DEX 20 and SPD 3 is Stunned by an attack in Segment 6.
    Her next Phase falls in Segment 8, and she must spend it recovering. She
    recovers when her DEX comes up in that Segment -- regaining her full DCV,
    with Placed Shot modifiers back to normal -- but still cannot take any
    other Action until her next Phase in Segment 12. The book states she MAY
    Abort that Segment 12 Phase during Segments 8 (after her DEX), 9, 10
    or 11.

WHERE THIS ENGINE IS APPROXIMATE, STATED PLAINLY: the book restores Andarra's
DCV partway through Segment 8, at her DEX. `statuses_for` folds an event log
and has no intra-Segment DEX position, so the engine's edge is the END of
Segment 8 rather than DEX 20 within it. The assertions below therefore cover
Segments 9, 10 and 11 -- where the book is unambiguous and no approximation
applies -- and the Segment 8 case is reported rather than asserted on DCV
(the status id and the Abort denial ARE asserted there too, since those are
whole-Segment facts this engine's fold gets exactly right).

Run with:
    .venv/bin/python examples/raw_andarra.py
"""
from __future__ import annotations

from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_dice import FakeRoller
from kirby_combat.models import AttackInput, AttackPower, DiceValues, StatBlockCombatant
from kirby_combat.session import CombatSession
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import SegmentAdvanced, make_author_engine
from kirby_combat.statuses import (
    RECOVERING_FROM_STUNNED, STUNNED, statuses_for,
)
from kirby_combat.template import CombatTemplate

import uuid
from datetime import datetime, timezone


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


BASHER = StatBlockCombatant(
    id="basher", name="Basher",
    ocv=8, dcv=8, omcv=5, dmcv=5,
    spd=4, dex=15, ego=15, str_=15, con=15, pre=15, rec=5,
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

# DEX 20, SPD 3 -- Andarra's own stated stats. CON 15, no defenses, a
# generous current STUN (well above the 20 this hit deals) so this example
# demonstrates Stunned-while-conscious cleanly, the same choice
# `examples/stunned.py` makes for the same reason.
ANDARRA = StatBlockCombatant(
    id="andarra", name="Andarra",
    ocv=8, dcv=9, omcv=5, dmcv=7,
    spd=3, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
    pd=0, ed=0, rpd=0, red=0, md=5,
    power_defense=0, flash_defense=0,
    max_stun=40, max_body=15, max_end=30,
    current_stun=40, current_body=15, current_end=30,
    attacks=[],
    defenses=[],
)


def _advance(session: CombatSession, to_segment: int, to_turn: int) -> CombatSession:
    """Same recipe as `tests/test_stunned_enforcement.py::_advance` --
    appends the `SegmentAdvanced` event `Encounter.advance_segment` would,
    without needing a live `Encounter`."""
    evt = SegmentAdvanced(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        from_segment=session.timeline.segment,
        to_segment=to_segment,
        to_turn=to_turn,
    )
    return apply_event(session, evt)


def main() -> None:
    rule("ANDARRA RECOVERS FROM BEING STUNNED — 6E2 p.107")

    session = CombatSession.create(
        id="s1",
        combatants=[BASHER, ANDARRA],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()

    # ── Segment 6: the Stunning hit ─────────────────────────────────────
    rule("Segment 6 — Andarra is Stunned by an attack")

    # Fixed dice: to-hit [3,3,3] -> roll 9, 8+11-9=10 >= DCV 9, hits.
    # Damage dice sum to 20 STUN, no defenses -- over CON 15 (Stunned),
    # well under current STUN 40 (not Knocked Out -- keeps this example
    # about Stunned recovery alone, the same isolation `stunned.py` uses).
    attack = AttackInput(
        attacker=BASHER, target=ANDARRA, power=BASHER.attacks[0],
        distance_m=0, aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[3, 2, 3, 2, 3, 2, 1, 2, 1, 1],
        ),
    )
    session, result = resolve_attack_in_session(session, attack, session.template)
    print(f"  Basher's Energy Blast hits Andarra for {result.stun_dealt} STUN "
          f"(CON {ANDARRA.con}) -> status_changes={result.status_changes}")
    assert "Stunned" in result.status_changes

    # ── Walk Segments 7 through 12, asserting the book's own claims ────
    #
    # SPD 3 -> Phases at Segments 4, 8, 12 (tables.py SPEED_TO_SEGMENTS).
    # Segment 8 is Andarra's own next full Phase after Segment 6 -- her
    # recovery Phase, exactly as the book states.
    expectations = {
        # segment: (status ids expected, Abort allowed)
        #
        # Segment 8's Abort is the one cell where this engine's coarse,
        # Segment-granularity fold cannot match the book: the book allows
        # the Abort "after her DEX occurs" WITHIN Segment 8, but this
        # fold has no intra-Segment DEX position (see this file's module
        # docstring's "WHERE THIS ENGINE IS APPROXIMATE" section and
        # `statuses.py::stunned_or_recovering_for`'s own docstring) --
        # RECOVERING_FROM_STUNNED, and the Abort denial gated on it, cover
        # the WHOLE of Segment 8. So the engine denies the Abort for all
        # of Segment 8, which is over-conservative for the post-DEX
        # portion the book grants it in -- exactly the residual error
        # both docstrings name. Segments 9, 10, 11 are NOT approximated:
        # the book is unambiguous there and this asserts against it
        # exactly.
        7: ({STUNNED}, False),
        8: ({RECOVERING_FROM_STUNNED}, False),   # book: True after her DEX; approximated
        9: (set(), True),
        10: (set(), True),
        11: (set(), True),
        12: (set(), True),   # her NEXT Phase -- fully clear either way
    }

    for segment in range(7, 13):
        session = _advance(session, to_segment=segment, to_turn=1)

        rule(f"Segment {segment}")
        ids = statuses_for(session, "andarra")
        dcv = effective_dcv_for(session, "andarra")
        try:
            Dodge.declare(session, "andarra")
            abort_allowed = True
        except ValueError:
            abort_allowed = False

        print(f"  statuses_for = {{{', '.join(sorted(ids)) or '— none —'}}}")
        print(f"  effective DCV = {dcv} (base {ANDARRA.dcv})")
        print(f"  Abort to Dodge allowed: {abort_allowed}")

        expected_ids, expected_abort = expectations[segment]
        assert ids == expected_ids, (segment, ids, expected_ids)
        assert abort_allowed == expected_abort, (segment, abort_allowed)

        if segment == 8:
            # The one Segment the book itself splits in two (before/after
            # Andarra's own DEX) -- this engine's fold has no intra-Segment
            # DEX position, so it reports rather than asserts this one
            # value; see this file's module docstring.
            print("  (book restores full DCV partway through this Segment, at "
                  "her DEX -- reported, not asserted)")
        elif STUNNED in ids or RECOVERING_FROM_STUNNED in ids:
            assert dcv < ANDARRA.dcv, (segment, dcv, ANDARRA.dcv)
        else:
            assert dcv == ANDARRA.dcv, (
                f"Segment {segment}: expected full DCV {ANDARRA.dcv}, got {dcv}"
            )

    rule("END — Andarra's book-stated Segments 9, 10, 11 confirmed: full DCV, "
         "Abort allowed, matching 6E2 p.107 exactly.")


if __name__ == "__main__":
    main()
