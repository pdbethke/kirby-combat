"""STUN, BODY and END move in exactly one place: inside `apply_event`.

THE DEFECT THIS PINS. Every resolver in this engine used to change a
combatant BESIDE the event that described the change --- an attack folded
its damage onto `session.combatants` and logged an `ActionResolved` whose
payload was a free-form dict; an END spend was taken off the fighter and
logged nowhere at all. `apply_event` folded none of it, on purpose, and
said so in a comment. The consequence was that a consumer which persists
the rows and rebuilds the fight by replaying them rebuilt a fight in
which nobody had been hit.

So these tests are about WHO WRITES, not about arithmetic --- the
arithmetic has had one home (`vitals.apply_vitals_delta`) since 2026-09-06
and that was never the problem. The last test is the one that will fail
first: it walks the engine and refuses a second writer, rather than
listing the writers it knows about.
"""
from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant

from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import (
    BleedingSuffered, RecoveryTaken, VitalsChanged, make_author_engine,
)
from kirby_combat.template import CombatTemplate
from kirby_combat.vitals import record_vitals_change

TEMPLATE = CombatTemplate.default_6e_superheroic()

ENGINE = pathlib.Path(__file__).resolve().parent.parent.parent / "kirby_combat"

#: The only modules allowed to write a combatant's STUN, BODY or END.
#:
#: `vitals.py` holds the arithmetic and `session/apply.py` is the one
#: writer that calls it. The third is a NAMED FOLLOW-ON, not a general
#: exemption: `gm/overrides.py::apply_tier1_override` does
#: `replace(old, current_stun=value)` beside a `GMOverride` that
#: `apply_event` folds nothing of, and it has no caller anywhere in the
#: engine -- a second writer waiting for one. Making `GMOverride` fold is
#: a rule change about which GM tiers may write what, which was ruled a
#: separate task; until then it is listed here, in the diff, rather than
#: silently outside the gate's reach.
ALLOWED_WRITERS = frozenset({
    ENGINE / "vitals.py",
    ENGINE / "session" / "apply.py",
    ENGINE / "gm" / "overrides.py",
})


#: The three names a combatant's vitals live under. `vitals.py` dispatches
#: between the two combatant shapes; these are what both of them call them.
_VITAL_FIELDS = frozenset({"current_stun", "current_body", "current_end"})


def _writes_a_vital(path: pathlib.Path) -> bool:
    """Does this module WRITE a combatant's vitals, by any route?

    THE PROPERTY, not one route to it. This asked only about calls to
    `apply_vitals_delta` -- and a writer that reaches for
    `dataclasses.replace(c, current_stun=...)` instead passes such a
    check untouched. One exists in the tree (see the allow-list below), so
    this was not hypothetical: the next resolver could have taken the
    shorter road, written a vital outside the log, and left the gate green
    while the replay divergence this whole line of work closed reopened.

    Three shapes count:

      * a call to `apply_vitals_delta` (the fold itself),
      * a `dataclasses.replace` with a `current_stun` / `current_body` /
        `current_end` keyword -- the shortcut route,
      * an assignment to one of those attributes
        (`c.state.current_stun = 0`).

    NOT a constructor. `StatBlockCombatant(..., current_stun=40)` builds a
    man who has not been in a fight yet, which is the opposite of changing
    one mid-fight; `from_dict` and the synthetic fixtures do exactly that,
    and so does every hand-built `AttackPower`-shaped call that happens to
    take a `current_body` argument. The gate is about a CHANGE to a
    combatant already in a session.

    By AST rather than by grep, for the reason the docstrings give: the
    names are MENTIONED in half a dozen comments that explain this very
    rule, and a check that counts those can only be satisfied by deleting
    the explanation.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if name == "apply_vitals_delta":
                return True
            if (name in {"replace", "_replace"}
                    and any(kw.arg in _VITAL_FIELDS for kw in node.keywords)):
                return True
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in _VITAL_FIELDS:
                return True
    return False


def _calls_the_fold(path: pathlib.Path) -> bool:
    """Kept as the narrow question, for the negative control below."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "apply_vitals_delta":
            return True
    return False


def _fighter(id: str = "a"):
    return synthetic_combatant(
        id=id, name=id, spd=4, dex=20, rec=6,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
    )


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(combatants) or [_fighter()], scene=None,
        template=TEMPLATE, dice_roller=None,
    ).start()


def _event(cls, session, **kwargs):
    return cls(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        **kwargs,
    )


def _vitals(session, cid="a"):
    c = session.combatants[cid]
    return (c.state.current_stun, c.state.current_body, c.state.current_end)


# ---------------------------------------------------------------------------
# The folds
# ---------------------------------------------------------------------------

def test_vitals_changed_is_applied_by_the_dispatcher():
    session = _session()

    after = apply_event(session, _event(
        VitalsChanged, session, combatant_id="a",
        stun=-14, body=-3, end=-5, reason="damage",
    ))

    assert _vitals(after) == (26, 9, 35)
    assert _vitals(session) == (40, 12, 40), "the input session is untouched"


def test_the_deltas_are_deltas_and_they_accumulate():
    """Two hits take twice. A resulting-value reading would take once."""
    session = _session()
    for _ in range(2):
        session = apply_event(session, _event(
            VitalsChanged, session, combatant_id="a", stun=-10,
            reason="damage",
        ))

    assert _vitals(session)[0] == 20


def test_nothing_is_clamped_in_either_direction():
    """6E1 p.421 reads HOW FAR below zero a man fell. A clamp here would
    destroy the number the rule needs --- `vitals.py` says so, and this is
    the dispatcher honouring it."""
    session = _session()

    after = apply_event(session, _event(
        VitalsChanged, session, combatant_id="a", stun=-55, body=-30,
        reason="damage",
    ))

    assert _vitals(after)[:2] == (-15, -18)


def test_recovery_taken_gives_the_stun_and_end_back():
    """6E2 p.130 / p.131. The event has carried both numbers in typed
    fields since it was written; nothing applied them."""
    session = _session()
    session = apply_event(session, _event(
        VitalsChanged, session, combatant_id="a", stun=-20, end=-20,
        reason="damage",
    ))

    after = apply_event(session, _event(
        RecoveryTaken, session, combatant_id="a",
        stun_recovered=6, end_recovered=6,
    ))

    assert _vitals(after) == (26, 12, 26)


def test_bleeding_suffered_takes_what_it_says_it_took():
    """6E2 p.109 and p.115. Both fields are stated as LOSSES and the fold
    negates them, so the row stays readable as "he lost 1 BODY"."""
    session = _session()

    after = apply_event(session, _event(
        BleedingSuffered, session, combatant_id="a",
        body_lost=1, stun_lost=4, rule="wound",
    ))

    assert _vitals(after) == (36, 11, 40)


def test_a_change_addressed_to_a_stranger_raises():
    """Silence here is the failure this work exists to remove: a replay one
    man's damage lighter than the fight that ran, saying nothing."""
    session = _session()

    with pytest.raises(ValueError, match="ghost"):
        apply_event(session, _event(
            VitalsChanged, session, combatant_id="ghost", stun=-1,
            reason="damage",
        ))


def test_an_unknown_kind_still_raises():
    """The dispatcher stayed total through all of this."""
    class _Odd:
        kind = "NotAnEvent"
        sequence = 2

    with pytest.raises(TypeError, match="NotAnEvent"):
        apply_event(_session(), _Odd())


# ---------------------------------------------------------------------------
# The emitter
# ---------------------------------------------------------------------------

def test_the_emitter_records_and_applies_in_one_step():
    session, event = record_vitals_change(
        _session(), "a", stun=-7, reason="damage",
    )

    assert event.kind == "VitalsChanged"
    assert (event.combatant_id, event.stun, event.reason) == ("a", -7, "damage")
    assert session.event_log[-1] is event
    assert _vitals(session)[0] == 33


def test_a_change_of_nothing_is_not_a_row():
    """A miss is not a transaction, and a log full of zeroes buries the
    hits."""
    before = _session()

    after, event = record_vitals_change(before, "a", reason="damage")

    assert event is None
    assert after is before


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_nothing_outside_apply_writes_a_vital():
    """DERIVED, not enumerated: this walks the engine.

    `apply_vitals_delta` is the arithmetic; `session/apply.py` is the only
    thing allowed to call it, because a caller that calls it directly is
    writing a vital outside the log and that is precisely the defect.
    Everything else goes through `record_vitals_change`, which emits the
    row first.

    `vitals.py` itself is where both live. Tests are exempt: they build
    hurt fighters as FIXTURES, before any fight, which is not a change
    made during one.

    By AST rather than by grep: the name is MENTIONED in half a dozen
    docstrings that explain exactly this rule, and a check that counts
    those is a check that can only be satisfied by deleting the
    explanation. A CALL is the thing that writes.
    """
    offenders = sorted(
        str(path.relative_to(ENGINE.parent))
        for path in ENGINE.rglob("*.py")
        if path not in ALLOWED_WRITERS and _writes_a_vital(path)
    )

    assert offenders == [], (
        "these write a combatant's vitals outside `apply_event` -- emit a "
        f"VitalsChanged through `record_vitals_change` instead: {offenders}"
    )


def test_the_gate_could_actually_fail(tmp_path):
    """The negative control, one case per route the gate claims to cover.

    A gate is worth exactly what its negative control proves. Each of
    these is a real way to write a vital; each must be detected, and a
    file that merely TALKS about them must not be.
    """
    fold = tmp_path / "fold.py"
    fold.write_text("def f(c):\n    return apply_vitals_delta(c, stun=-1)\n")
    assert _writes_a_vital(fold) is True

    # The route the old gate missed, and the one that exists in the tree.
    shortcut = tmp_path / "shortcut.py"
    shortcut.write_text(
        "from dataclasses import replace\n"
        "def f(c, value):\n"
        "    return replace(c, current_stun=value)\n"
    )
    assert _writes_a_vital(shortcut) is True
    assert _calls_the_fold(shortcut) is False, (
        "this is precisely what the narrow check could not see")

    assign = tmp_path / "assign.py"
    assign.write_text("def f(c):\n    c.state.current_body = 0\n")
    assert _writes_a_vital(assign) is True

    augmented = tmp_path / "augmented.py"
    augmented.write_text("def f(c):\n    c.current_end -= 5\n")
    assert _writes_a_vital(augmented) is True

    talker = tmp_path / "talker.py"
    talker.write_text(
        '"""Never call apply_vitals_delta, never set current_stun."""\n'
        "def f(c):\n    return c.state.current_stun\n"
    )
    assert _writes_a_vital(talker) is False

    assert _writes_a_vital(ENGINE / "session" / "apply.py") is True


def test_the_allow_list_is_one_named_follow_on_and_nothing_else():
    """An allow-list is a place a defect hides, so it is asserted whole.

    Adding a file here is a decision somebody has to make on purpose and
    a reviewer can see in the diff, which is the opposite of a gate that
    quietly stops covering things.
    """
    assert set(ALLOWED_WRITERS) == {
        ENGINE / "vitals.py",
        ENGINE / "session" / "apply.py",
        ENGINE / "gm" / "overrides.py",
    }
    # And the carve-out is real: it still writes one.
    assert _writes_a_vital(ENGINE / "gm" / "overrides.py") is True
