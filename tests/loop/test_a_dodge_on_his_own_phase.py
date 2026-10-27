"""A Dodge taken IN his own Phase uses that Phase, and only that one.

Pinned from kirby-app's 0.22.0 demo recording, which read as two defects
and is neither. GORGON, in his own Phase (Turn 1, Segment 12), made a
Presence Attack and then Dodged; the log carries an `AbortDeclared`
(`to_action: "dodge"`), and he then acted in his next Phase (Turn 2,
Segment 3). Both are the book:

* A Presence Attack takes No Time and is in addition to his action (6E2
  p.20, p.25), so the Phase is still his to spend --- here, on a Dodge.
* A Dodge is a Combat Maneuver he may take on his own Phase: "a SPD 3
  character who Dodges on his Phase in Segment 4 retains the Maneuver's +3
  DCV bonus until the beginning of his next Phase in Segment 8" (6E2
  p.56). It is not an Abort and does not cost the next Phase.

The engine records every Dodge through the one Abort door
(`actions/reactive/abort.mark_aborting`), which is why the row is named
`AbortDeclared`. For an own-Phase Dodge the Phase it records as given up
is THIS one (`abort_windows`: he has not spent this Segment's slot yet),
so his next Phase is untouched. An Abort proper --- out of turn, asked only
when an attack is coming at him (6E2 p.23-24, `loop/reactions.py`) --- is
pinned in `test_reactions_and_concealment.py` and
`session/test_abort_expiry.py`.
"""
from __future__ import annotations

from conftest import blast  # tests/loop/conftest.py
from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import RandomRoller

from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.encounter import Encounter
from kirby_combat.loop.run import run_phase
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate


class Ones:
    def roll_dice(self, n: int) -> list[int]:
        return [1] * n


def _man(id: str, side: str, *, dex: int, pre: int = 15):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=6, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=18, pre=pre, rec=6,
        pd=40, ed=40, rpd=40, red=40, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        side=Side.named(side), attacks=[blast(f"{id}-eb", dice=1)],
    )


class GorgonPlays:
    """Gorgon shouts, then Dodges (once), then attacks; Drago only ever holds
    (so no attack ever comes at Gorgon). Records out-of-turn questions."""

    def __init__(self) -> None:
        self.out_of_turn: list[tuple[str, str, str | None]] = []
        self.dodged = False

    def choose(self, situation) -> str:
        if situation.out_of_turn is not None:
            oot = situation.out_of_turn
            self.out_of_turn.append((
                situation.actor.id, oot.reason.value,
                getattr(oot.incoming, "target_id", None)))
            return situation.menu[0].action_id
        kinds = {a.kind: a.action_id for a in situation.menu}
        if situation.actor.id == "drago":
            return kinds["hold"]
        for wanted in ("presence_attack", "dodge", "attack"):
            if wanted == "dodge" and self.dodged:
                continue
            if wanted in kinds:
                self.dodged = self.dodged or wanted == "dodge"
                return kinds[wanted]
        raise AssertionError(sorted(kinds))


def _fight():
    session = CombatSession.create(
        id="s", combatants=[_man("gorgon", "red", dex=30, pre=25),
                            _man("drago", "blue", dex=10)],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


def _gorgon_rows(session):
    return [e for e in session.event_log
            if getattr(e, "combatant_id", None) == "gorgon"
            and e.kind in ("ActionDeclared", "AbortDeclared", "PhaseSpent")]


def test_a_shout_then_a_dodge_uses_this_phase_and_keeps_the_next():
    enc, chooser = _fight(), GorgonPlays()
    shout = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise")
    assert shout.kind == "presence_attack"
    dodge = run_phase(shout.encounter, chooser, roller=Ones(),
                      on_unresolvable="raise")
    assert (dodge.actor_id, dodge.kind) == ("gorgon", "dodge")
    session = dodge.session
    aborts = [e for e in session.event_log if e.kind == "AbortDeclared"]
    assert [(a.aborted_turn, a.aborted_segment) for a in aborts] == [(1, 12)], (
        "the Phase a Dodge on his own Phase uses is that Phase")
    # +3 DCV until the start of his next Phase, Turn 2 Segment 3 (6E2 p.56).
    assert [(a.bonus_until_turn, a.bonus_until_segment) for a in aborts] == [(2, 3)]
    assert Dodge.dcv_bonus(session, "gorgon") == 3

    enc = dodge.encounter
    for _ in range(8):
        enc = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise").encounter
    rows = [(e.kind, getattr(e, "action_type", None) or getattr(e, "reason", None),
             e.turn if hasattr(e, "turn") else None,
             e.segment if hasattr(e, "segment") else None)
            for e in _gorgon_rows(enc.sessions[0])]
    spent = [r for r in rows if r[0] == "PhaseSpent"]
    assert spent[0] == ("PhaseSpent", "acted", 1, 12)
    assert spent[1] == ("PhaseSpent", "acted", 2, 3), (
        "he acts in his next Phase: nothing was aborted out of turn")
    assert ("ActionDeclared", "attack", None, None) in rows


def test_only_the_man_being_attacked_is_asked_to_abort():
    """An Abort is to protect himself from an attack (6E2 p.23-24). Drago
    only holds, so Gorgon is never asked the Abort question; Drago is asked
    it only when Gorgon's attack is coming at him."""
    enc, chooser = _fight(), GorgonPlays()
    for _ in range(10):
        enc = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise").encounter
    asked = [q for q in chooser.out_of_turn if q[1] == "abort"]
    assert asked, "Gorgon attacked, so Drago was asked"
    assert all(who == "drago" and at == "drago" for who, _, at in asked), asked
