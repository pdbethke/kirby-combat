"""One Turn, driven — the acting order, the Segment-12 wrap, the Recovery.

Every prior example built state and inspected it at rest. This one turns
the crank: `Encounter.run_segment` is the first thing in this codebase
that resolves a real acting order and writes it onto a session's
timeline (see its docstring — Lightning Reflexes' Phase restriction and
Block's "acts first" priority had both stood as documented no-ops until
something drove the clock; this is that something).

6E2 p.18, "SEGMENT": "Characters who can perform an Action in a Segment
(i.e., who have a Phase in that Segment) do so in order of their DEX
values" — and DEX is counted among the characters PRESENT, not
per-fight, which is why `run_segment` resolves ONE scene-wide order
across every session in the Encounter even though this example only
uses one.

Three combatants, one Scene, one Encounter, one Turn:

  Vex     — SPD 4, DEX 16, with Lightning Reflexes (6E1 p.116) bought
            SINGLE-scope for "Shuriken" only. Electing the bonus is the
            book's own example: DEX 16 + 6 = effective 22, enough to act
            before a DEX 20 rival — Segment 3 shows that beat happening.
            Segment 6 shows the OTHER half of the same rule: electing
            the bonus for one Action forfeits the rest of the Phase
            ("no movement, acrobatics, or other Actions", 6E1 p.116(c)).
            Vex elects it, then a different action is declared anyway —
            `apply_event` raises, caught and printed here rather than
            left to crash the example, because the raise IS the point.
  Talon   — SPD 4, DEX 20. Vex's rival for the DEX-order comparison.
  Bruiser — SPD 3, DEX 13, and built already battered (STUN/END below
            max) so the Post-Segment 12 Recovery at the Turn wrap has
            something visible to restore.

The loop below drives Segments 1 through 12 of Turn 1 (a full Turn,
6E2 p.18: "a Turn consists of 12 Segments"), prints who has a Phase each
Segment (most are empty — SPD 3/4 combatants don't act every Segment),
then calls `Encounter.advance_segment` once more to show the Segment 12
-> Turn 2 Segment 1 wrap and the free Post-Segment 12 Recovery
(6E2 p.131) that fires on it.

Exercises:
  - Encounter.run_segment / Encounter.scene_acting_order / Encounter.acts_first
  - Encounter.advance_segment (the wrap + Post-Segment 12 Recovery)
  - ActionIntent(elect_lightning_reflexes=...), talents/lightning_reflexes.py
  - session.apply.apply_event raising on the Lightning Reflexes Phase
    restriction (6E1 p.116(c))
  - Campaign / World / Scene / Scene.place_combatant

May import kirby_cost (LightningReflexesAll, the real oracle-validated
Talent class) — never kirby_api.

Run with:
    .venv/bin/python examples/one_turn.py
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone

from lxml import etree

from kirby_cost.objects.talents.lightning_reflexes_all import LightningReflexesAll

from kirby_combat.campaign import Campaign
from kirby_combat.encounter import Encounter, SEGMENTS_PER_TURN
from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import StatBlockCombatant
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, make_author_combatant
from kirby_combat.session.timeline import ActionIntent, ordering_value
from kirby_combat.world import World


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


# ── A tiny, deterministic dice roller ────────────────────────────────────
#
# `CombatTemplate.tie_rule` defaults to `TieRule.DEX_ROLL` (6E2 p.21's own
# default rule), and `resolve_acting_order` calls its `roller` once per
# combatant with a Phase that Segment — regardless of whether a tie
# actually occurs (see timeline.py's docstring: "called exactly once per
# combatant... not once per sort comparison"). None of the three
# combatants below share a printed DEX, so no tie is ever actually broken
# here, but the roller must still be supplied on every `run_segment` call
# or resolution raises ValueError. `random` is avoided on purpose — this
# example's output must be stable across runs.
def roller() -> list[int]:
    return [3, 3, 3]


# ── A minimal LoadedHero stand-in ────────────────────────────────────────
#
# HeroCombatant wraps a real kirby-cost LoadedHero in production
# (`HeroCombatant.from_hdc`). This example needs only enough of that
# shape to carry ONE real Lightning Reflexes Talent object so
# `lightning_reflexes_bonus`/`restriction_for_slot` exercise the actual
# scope-reading code, not a re-description of it — the same reasoning
# `tests/talents/test_lightning_reflexes.py`'s `_hero_with_talent` and
# `tests/fixtures/synthetic_hero.py` follow. Built locally rather than
# importing that test fixture: examples run standalone (see
# `tests/test_examples.py`) and must not reach into `tests/`.
class _MinimalHero:
    def __init__(self, *, name: str, char_values: dict[str, int], talents: list) -> None:
        self.name = name
        self.template_name = "example.hdt"
        self._char_values = char_values
        self.powers: list = []
        self.skills: list = []
        self.perks: list = []
        self.talents = talents
        self.complications: list = []
        self.equipment: list = []

    def characteristic_value(self, xmlid: str) -> int:
        return self._char_values.get(xmlid.upper(), 0)

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        return self.characteristic_value(xmlid)


def _lightning_reflexes_talent(*, levels: int, option_id: str, option_alias: str):
    """A real ``LightningReflexesAll`` object built to the verbatim XML
    shape HD writes for this Talent (OPTION and OPTIONID always identical
    — confirmed against 76 real instances, see
    ``kirby_combat/talents/lightning_reflexes.py``'s module docstring).
    XMLID is ALWAYS ``LIGHTNING_REFLEXES_ALL``, even for a narrow-scoped
    purchase — the scope lives in OPTIONID, never the XMLID.
    """
    elem = etree.Element("TALENT")
    elem.set("XMLID", "LIGHTNING_REFLEXES_ALL")
    elem.set("LEVELS", str(levels))
    elem.set("ALIAS", "Lightning Reflexes")
    elem.set("OPTION", option_id)
    elem.set("OPTIONID", option_id)
    elem.set("OPTION_ALIAS", option_alias)
    return LightningReflexesAll(elem)


def _char_values(
    *, ocv, dcv, omcv, dmcv, spd, dex, ego, int_, str_, con, pre, rec,
    pd, ed, stun, body, end,
) -> dict[str, int]:
    return {
        "OCV": ocv, "DCV": dcv, "OMCV": omcv, "DMCV": dmcv, "SPD": spd,
        "DEX": dex, "EGO": ego, "INT": int_, "STR": str_, "CON": con,
        "PRE": pre, "REC": rec, "PD": pd, "ED": ed,
        "STUN": stun, "BODY": body, "END": end,
    }


def show_acting_order(encounter: Encounter, segment: int) -> None:
    print(f"\n  Segment {segment}:")
    if not encounter.scene_acting_order:
        print("    (no one has a Phase this Segment — SPD chart, 6E2 p.18)")
        return
    for i, slot in enumerate(encounter.scene_acting_order, start=1):
        bonus_note = ""
        if slot.intent is not None and slot.intent.elect_lightning_reflexes:
            eff = ordering_value(slot)
            bonus_note = f"  (effective DEX {eff}, Lightning Reflexes elected)"
        print(f"    {i}. {slot.combatant_id:8} DEX {slot.dex_at_phase:>2}{bonus_note}")


def show_vitals(label: str, combatant) -> None:
    st = combatant.state
    print(f"    {label:8} STUN {st.current_stun:>3}   END {st.current_end:>3}")


def main() -> None:
    rule("ONE TURN, DRIVEN — 12 Segments, a wrap, and a free Recovery")

    # ── 1. Build the three combatants ─────────────────────────────────────
    vex_hero = _MinimalHero(
        name="Vex",
        char_values=_char_values(
            ocv=6, dcv=6, omcv=3, dmcv=3, spd=4, dex=16, ego=10, int_=10,
            str_=13, con=15, pre=13, rec=6, pd=6, ed=6, stun=25, body=12, end=30,
        ),
        # 6E1 p.116, verbatim example: "A character with a base DEX of 16
        # and +6 Lightning Reflexes (total effective DEX 16 + 6 = 22) would
        # act before a character with a base DEX of 20." SINGLE scope, so
        # only "Shuriken" gets the bonus — and only "Shuriken" may be
        # declared in a Phase where the bonus is elected (6E1 p.116(c)).
        talents=[_lightning_reflexes_talent(
            levels=6, option_id="SINGLE", option_alias="Shuriken")],
    )
    vex = HeroCombatant(
        id="vex", hero=vex_hero,
        state=HeroCombatState(current_stun=25, current_body=12, current_end=30),
    )

    talon = StatBlockCombatant(
        id="talon", name="Talon",
        ocv=7, dcv=7, omcv=3, dmcv=3, spd=4, dex=20, ego=10, int_=10,
        str_=15, con=15, pre=13, rec=6,
        pd=6, ed=6, rpd=3, red=3, md=0, power_defense=0, flash_defense=0,
        max_stun=28, max_body=12, max_end=30,
        current_stun=28, current_body=12, current_end=30,
        attacks=[], defenses=[],
    )

    # Battered on purpose: STUN and END already spent (a prior Segment's
    # fighting, off-page) so the Post-Segment 12 Recovery has something
    # visible to restore (6E2 p.131).
    bruiser = StatBlockCombatant(
        id="bruiser", name="The Bruiser",
        ocv=5, dcv=4, omcv=2, dmcv=2, spd=3, dex=13, ego=10, int_=10,
        str_=25, con=20, pre=15, rec=8,
        pd=8, ed=6, rpd=4, red=2, md=0, power_defense=0, flash_defense=0,
        max_stun=35, max_body=15, max_end=40,
        current_stun=14, current_body=15, current_end=12,
        attacks=[], defenses=[],
    )

    # ── 2. Place them in a Scene, wire the Campaign/World/Encounter ──────
    # SceneBounds field order (min_x, min_y, min_z, max_x, max_y, max_z) —
    # copied from tests/test_aoe_scene_integration.py:27, per the brief's
    # warning that a hand-built box elsewhere got this order wrong.
    bounds = SceneBounds(0, 0, 0, 30, 30, 5)
    scene = Scene(
        id="rooftop", name="Warehouse rooftop",
        bounds=bounds, surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
    )
    scene = scene.place_combatant("vex", Position(5, 5, 0))
    scene = scene.place_combatant("talon", Position(20, 5, 0))
    scene = scene.place_combatant("bruiser", Position(12, 20, 0))

    session = CombatSession.create(
        id="rooftop-fight", combatants=[vex, talon, bruiser],
        scene=scene, template=Campaign(id="tmp", name="tmp").template,
    ).start()

    # Segment 1, not the usual Segment-12 combat-start default (6E2 p.20)
    # — this example wants to walk EVERY Segment of Turn 1 in order, and
    # Encounter.segment's own default exists for the more common case of
    # joining a fight already in progress.
    encounter = Encounter(id="rooftop-encounter", turn=1, segment=1, sessions=[session])
    scene = replace(scene, encounter=encounter)
    world = World(id="haven-city", name="Haven City", scenes=[scene])
    campaign = Campaign(id="campaign-1", name="Rooftop Showdown", worlds=[world])

    # `CombatSession.create` hardcodes its Timeline to Turn 1, Segment 12
    # (6E2 p.20's combat-start default) — but `Encounter.run_segment`
    # brings a session's `Timeline.segment`/`turn` into step with the
    # Encounter's own every time it runs (see `encounter.py`'s
    # `run_segment` docstring), so the very first `run_segment` call
    # below (for Segment 1) corrects that hardcoded 12 without this
    # example needing to do anything about it itself.

    print(f"\n  {vex.name} (SPD 4, DEX 16, Lightning Reflexes SINGLE/Shuriken +6)")
    print(f"  {talon.name} (SPD 4, DEX 20)")
    print(f"  {bruiser.name} (SPD 3, DEX 13) — enters battered: "
          f"STUN {bruiser.current_stun}/{bruiser.max_stun}, "
          f"END {bruiser.current_end}/{bruiser.max_end}")

    # ── 3. Drive Segments 1 through 12 of Turn 1 ─────────────────────────
    #
    # `run_segment` resolves the order for `encounter.segment` as it
    # stands — it does NOT advance the clock (that is `advance_segment`'s
    # job, see its docstring). So each loop iteration below explicitly
    # advances to the next Segment itself once it is done with the
    # current one; Segment 12 is left for section 4, where the wrap and
    # the free Recovery are the point.
    rule("TURN 1 — Segments 1 through 12")
    for segment in range(1, SEGMENTS_PER_TURN + 1):
        assert encounter.segment == segment
        intents: dict[str, ActionIntent] = {}
        if segment == 3:
            # The book's own example, live: Vex elects Lightning Reflexes
            # for "Shuriken" (effective DEX 16+6=22) against Talon's
            # printed DEX 20.
            intents["vex"] = ActionIntent("Shuriken", elect_lightning_reflexes=True)
            intents["talon"] = ActionIntent("Strike")
        elif segment == 6:
            # Same election again — this time to show the OTHER half of
            # 6E1 p.116(c) biting: electing the bonus for "Shuriken" costs
            # the rest of the Phase.
            intents["vex"] = ActionIntent("Shuriken", elect_lightning_reflexes=True)
            intents["talon"] = ActionIntent("Strike")

        # `campaign=` resolves the CombatTemplate (campaign -> encounter
        # override, per `resolve_template`); the Campaign/World/Scene
        # nesting itself is not read by `run_segment` beyond that, so it
        # is not rebuilt every iteration here — only `encounter` needs
        # rebinding each Segment (Encounter is immutable-by-convention;
        # `run_segment` returns a NEW Encounter, never mutates in place).
        encounter = encounter.run_segment(
            campaign=campaign, intents=intents, roller=roller,
        )

        show_acting_order(encounter, segment)

        if segment == 6:
            # 6E1 p.116(c): "he may only execute the specific Action or
            # maneuver he purchased Lightning Reflexes for... no movement,
            # acrobatics, or other Actions." Vex elected the bonus for
            # "Shuriken" above; declaring "Move" instead must be refused.
            fight = encounter.sessions[0]
            bad_declare = ActionDeclared(
                id=str(uuid.uuid4()), session_id=fight.id,
                sequence=len(fight.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_combatant("vex"),
                combatant_id="vex", action_type="Move",
            )
            print("\n    Vex elected Lightning Reflexes for \"Shuriken\" this "
                  "Phase, then tries to declare \"Move\" instead:")
            try:
                apply_event(fight, bad_declare)
            except ValueError as exc:
                print(f"      REFUSED (6E1 p.116(c)): {exc}")
            else:
                raise AssertionError(
                    "expected the Lightning Reflexes Phase restriction to fire"
                )

            # The elected action itself is legal — declare THAT instead,
            # and it goes through.
            good_declare = ActionDeclared(
                id=str(uuid.uuid4()), session_id=fight.id,
                sequence=len(fight.event_log) + 1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_combatant("vex"),
                combatant_id="vex", action_type="Shuriken",
            )
            fight = apply_event(fight, good_declare)
            print("    Declaring \"Shuriken\" instead — the elected Action — "
                  "goes through.")
            encounter = replace(encounter, sessions=[fight])

        if segment < SEGMENTS_PER_TURN:
            # Advance to the next Segment within Turn 1 — no wrap, no
            # Recovery, since `self.segment` (< 12) doesn't hit the wrap
            # branch in `advance_segment`. Segment 12 itself is advanced
            # separately below, where the wrap IS the point.
            encounter = encounter.advance_segment(campaign=campaign)
            # No further clock-syncing needed here: the NEXT `run_segment`
            # call (top of the next loop iteration) brings the session's
            # Timeline back into step with whatever Segment the Encounter
            # is now on -- see the comment above section 3's loop.

    # ── 4. The Segment 12 -> Turn 2 Segment 1 wrap ───────────────────────
    rule("THE WRAP — Segment 12 -> Turn 2, Segment 1 (6E2 p.18)")
    print(f"\n  Before: Turn {encounter.turn}, Segment {encounter.segment}")
    before = {c.id: c for c in encounter.sessions[0].combatants.values()}
    show_vitals("vex", before["vex"])
    show_vitals("talon", before["talon"])
    show_vitals("bruiser", before["bruiser"])

    # 6E2 p.131, "POST-SEGMENT 12 RECOVERY": "After Segment 12 each Turn,
    # all characters (even Stunned ones) get a free Post-Segment 12
    # Recovery." Fires as part of this one call, on the wrap branch only.
    encounter = encounter.advance_segment(campaign=campaign)

    print(f"\n  After:  Turn {encounter.turn}, Segment {encounter.segment}")
    after = {c.id: c for c in encounter.sessions[0].combatants.values()}
    print("\n  Post-Segment 12 Recovery — every combatant, even one who")
    print("  never had a Phase this Turn, gets REC added to STUN and END:")
    for cid in ("vex", "talon", "bruiser"):
        b, a = before[cid], after[cid]
        print(f"    {cid:8} STUN {b.state.current_stun:>3} -> {a.state.current_stun:>3}"
              f"     END {b.state.current_end:>3} -> {a.state.current_end:>3}")
    print("\n  Bruiser entered Segment 12 battered and comes out of the wrap")
    print("  measurably healthier — the free Recovery, not anyone's action.")

    rule("END")


if __name__ == "__main__":
    main()
