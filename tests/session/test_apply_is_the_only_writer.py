"""A fighter's stats, his place on the board and his conditions move in
exactly one place: inside `apply_event`.

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

THE SAME DEFECT HAD TWO MORE FIELDS (2026-09-18, measured by Krackle's
checkpoint gate --- a replay of recorded fights against this engine's own
`state?at`). The vitals fold closed the STUN/BODY/END half and left the
other two open:

* WHERE A MAN STANDS. `scene/placement.py::commit_move` wrote the landing
  onto `scene.combatant_positions` IN PLACE and emitted a
  `MovementResolved` that `apply_event` did nothing with. A session
  rebuilt from its rows put everybody at his starting placement for ever
  --- all fourteen checkpoints of a recorded fight had Wyatt at
  (3.1, 3.7) although he moved at sequence 7. And `rewind_to_sequence`
  seeded its fresh session from the FINISHED scene, so a rewind to
  sequence 1 showed the fight's final placement instead.
* WHAT CONDITION HE IS IN. Nothing in this engine ever emitted a
  `StatusEffectsChanged`: its only door,
  `status_emission.apply_event_with_deltas`, had no caller anywhere, and
  `StatusChanged` had no producer at all. Knocked out, stunned, prone,
  held, entangled, flashed --- none of it reached the log, so a viewer
  could not know a man had gone down.

Three folds, three gates, one shape. Each gate walks the engine BY AST,
carries its own negative control, and asserts its allow-list whole.
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


#: The only modules allowed to take each ROUTE to moving somebody on the
#: board --- per route, not per file, because a file that is allowed to
#: bring a wall down is not thereby allowed to move a man.
#:
#: * `mutates` --- writing into a position map in place. `scene/scene.py`
#:   is the class that owns the map (`place_combatant` builds the new one
#:   an entry at a time). `scene/generate.py` stands the fighters up when
#:   an arena is BUILT, before the fight: the same carve-out the vitals
#:   gate makes for a fixture that builds a hurt man.
#: * `place_combatant` --- the bounds-checked setup door on `Scene`.
#:   `gm/spawn_despawn.py` is a NAMED FOLLOW-ON, the same kind of entry
#:   `gm/overrides.py` is on the vitals list: a mid-fight arrival folds
#:   through no event at all (ruled a separate task in A7, still true), so
#:   a fight with a spawn in it cannot be rebuilt from its rows whatever
#:   this gate says. Listed in the diff rather than silently out of reach.
#: * `rebuilds` --- constructing a board with somebody somewhere else.
#:   `scene/scene.py` is the class that OWNS the map: `place_combatant`,
#:   `with_position` (the what-if board `move_strike` and `Images` ask
#:   about a position nobody is at) and `snapshot` all live there, and a
#:   gate that refused them would refuse the Scene the right to describe
#:   itself.
#: * `installs` --- putting a Scene onto a session, which is the step that
#:   makes an altered board the FIGHT's board. `session/apply.py` is the
#:   fold. `collapse.py` brings a wall down and `darkness.py` raises a
#:   field: both swap the Scene for reasons that are not about people, and
#:   neither can move anybody without also taking one of the three routes
#:   above, which they are NOT allowed to take.
ALLOWED_PLACERS: dict[str, frozenset[pathlib.Path]] = {
    "mutates": frozenset({
        ENGINE / "scene" / "scene.py",
        ENGINE / "scene" / "generate.py",
    }),
    "place_combatant": frozenset({ENGINE / "gm" / "spawn_despawn.py"}),
    "rebuilds": frozenset({ENGINE / "scene" / "scene.py"}),
    "installs": frozenset({
        ENGINE / "session" / "apply.py",
        ENGINE / "collapse.py",
        ENGINE / "actions" / "darkness.py",
        ENGINE / "gm" / "spawn_despawn.py",
    }),
}


#: The only modules allowed to write `CombatSession.statuses`.
#:
#: `session/apply.py` folds the `StatusEffectsChanged` row.
#: `session/combat_session.py` is the dataclass that DEFINES the field and
#: seeds one empty frozenset per combatant in `__post_init__`, so that no
#: reader ever needs a default --- an empty set is "no conditions", a
#: missing key would be "nobody asked".
ALLOWED_STATUS_WRITERS = frozenset({
    ENGINE / "session" / "apply.py",
    ENGINE / "session" / "combat_session.py",
})


#: Where a combatant stands, and the attribute every reader goes through.
_POSITION_FIELD = "combatant_positions"

#: The session field that records what condition a man is in.
_STATUS_FIELD = "statuses"


def _names_bound_from(tree: ast.AST, attribute: str) -> set[str]:
    """Local names that were bound from an expression mentioning
    `attribute`.

    `commit_move` did `positions = getattr(scene, "combatant_positions",
    None)` and then `positions[combatant_id] = landing` --- an in-place
    write to the fight's own map, through a name that says nothing about
    what it holds. A gate that looked only for `scene.combatant_positions
    [x] = y` would have called that file clean, which is the whole
    failure this file is about: guard the property, not one spelling of
    it.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        if not targets or getattr(node, "value", None) is None:
            continue
        mentions = attribute in ast.dump(node.value)
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            # Bound from the attribute itself, or REBOUND FROM ITSELF ---
            # `positions = dict(positions)`, the one-line copy that is how
            # a tainted name survives. Deliberately no wider propagation
            # than that: an earlier version followed any name derived from
            # any bound name and reached `per_target_dc` in
            # `actions/area_of_effect.py`, four hops from a position and
            # not a position at all. A gate that cries wolf gets an
            # allow-list entry, and an allow-list entry is a blind spot.
            if mentions or (target.id in bound and target.id in names):
                bound.add(target.id)
    return bound


def _position_routes(path: pathlib.Path) -> frozenset[str]:
    """WHICH ROUTES to moving a man on the board does this module take?

    A set rather than a yes/no, because the allow-list is per route: a
    module that may bring a wall down is not thereby allowed to move a
    fighter, and one allow-list keyed by file would say it was.

      * `mutates` --- an assignment INTO a position map:
        `scene.combatant_positions[cid] = p`, or the same through a local
        bound from it. That second spelling is the route `commit_move`
        actually took, and a gate that only understood the first would
        have called that file clean while the replay divergence was live
        in it.
      * `place_combatant` --- a call to the `Scene` setup door.
      * `rebuilds` --- `replace(..., combatant_positions=...)`: a board
        with somebody somewhere else.
      * `installs` --- `replace(..., scene=...)` or an assignment to a
        `.scene` attribute: the step that makes a board the fight's.

    Building an altered board and installing one are separate routes
    ON PURPOSE. Either alone is legitimate somewhere; a module that does
    both is moving a man, and no module outside the fold is allowed both.
    """
    tree = ast.parse(path.read_text())
    local = _names_bound_from(tree, _POSITION_FIELD)
    routes: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if name == "place_combatant":
                routes.add("place_combatant")
            if name in {"replace", "_replace"}:
                keywords = {kw.arg for kw in node.keywords}
                if _POSITION_FIELD in keywords:
                    routes.add("rebuilds")
                if "scene" in keywords:
                    routes.add("installs")
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute):
                if target.attr == _POSITION_FIELD:
                    routes.add("mutates")
                if target.attr == "scene":
                    routes.add("installs")
            if not isinstance(target, ast.Subscript):
                continue
            holder = target.value
            if isinstance(holder, ast.Attribute) and holder.attr == _POSITION_FIELD:
                routes.add("mutates")
            elif isinstance(holder, ast.Name) and holder.id in local:
                routes.add("mutates")
    return frozenset(routes)


def _writes_a_status(path: pathlib.Path) -> bool:
    """Does this module write `CombatSession.statuses`?

    Three routes, the same three the vitals gate covers one field over: a
    `replace(..., statuses=...)`, an assignment to a `.statuses`
    attribute, and an assignment into one (`session.statuses[cid] = ...`).

    A MUTATING METHOD CALL counts too --- `.statuses.setdefault(...)`,
    `.update(...)`, `.pop(...)`, `.clear(...)`. A dict field invites that
    spelling and it is the one a fold-by-mutation would reach for; the
    seeding in `combat_session.py` was written that way first, and was
    rewritten as an assignment precisely so the gate could see it.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if (name in {"replace", "_replace"}
                    and any(kw.arg == _STATUS_FIELD for kw in node.keywords)):
                return True
            holder = getattr(node.func, "value", None)
            if (name in {"setdefault", "update", "pop", "clear", "__setitem__"}
                    and isinstance(holder, ast.Attribute)
                    and holder.attr == _STATUS_FIELD):
                return True
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == _STATUS_FIELD:
                return True
            if (isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == _STATUS_FIELD):
                return True
    return False


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


# ---------------------------------------------------------------------------
# The gate on the board
# ---------------------------------------------------------------------------

def test_the_position_gate_could_actually_fail(tmp_path):
    """The negative control, written before the gate was pointed at the
    engine, one case per route it claims to cover.

    The third case is the one that matters: it is the route
    `commit_move` really took, and a gate that only understood
    `scene.combatant_positions[cid] = p` would have called that file
    clean while the replay divergence was live in it.
    """
    attribute = tmp_path / "attribute.py"
    attribute.write_text(
        "def f(scene, cid, p):\n"
        "    scene.combatant_positions[cid] = p\n"
    )
    assert _position_routes(attribute) == {"mutates"}

    # THE ROUTE THE DEFECT TOOK: through a local that names nothing.
    laundered = tmp_path / "laundered.py"
    laundered.write_text(
        "def f(scene, cid, p):\n"
        '    positions = getattr(scene, "combatant_positions", None)\n'
        "    positions[cid] = p\n"
    )
    assert _position_routes(laundered) == {"mutates"}

    rebuilt = tmp_path / "rebuilt.py"
    rebuilt.write_text(
        "from dataclasses import replace\n"
        "def f(scene, cid, p):\n"
        "    return replace(scene, combatant_positions={cid: p})\n"
    )
    assert _position_routes(rebuilt) == {"rebuilds"}

    placer = tmp_path / "placer.py"
    placer.write_text(
        "def f(scene, cid, p):\n"
        "    return scene.place_combatant(cid, p)\n"
    )
    assert _position_routes(placer) == {"place_combatant"}

    installer = tmp_path / "installer.py"
    installer.write_text(
        "from dataclasses import replace\n"
        "def f(session, scene):\n"
        "    return replace(session, scene=scene)\n"
    )
    assert _position_routes(installer) == {"installs"}

    # Reading is not writing, and neither is talking about it.
    talker = tmp_path / "talker.py"
    talker.write_text(
        '"""Never write combatant_positions, never call place_combatant."""\n'
        "def f(scene, cid):\n"
        '    return (getattr(scene, "combatant_positions", None) or {}).get(cid)\n'
    )
    assert _position_routes(talker) == frozenset()

    # And the fold itself takes exactly the one route it is allowed.
    assert _position_routes(ENGINE / "session" / "apply.py") == {"installs"}


def test_nothing_outside_apply_puts_a_combatant_anywhere():
    """DERIVED, not enumerated: this walks the engine, per route.

    `MovementResolved` is the row and `apply_event` is what applies it.
    Everything else emits the row --- through `scene/placement.py`, which
    decides the landing and then says so --- and lets the fold write.
    """
    offenders = sorted(
        (route, str(path.relative_to(ENGINE.parent)))
        for path in ENGINE.rglob("*.py")
        for route in _position_routes(path)
        if path not in ALLOWED_PLACERS[route]
    )

    assert offenders == [], (
        "these decide where a combatant is standing outside `apply_event` "
        "-- emit a MovementResolved through `scene/placement.py` instead: "
        f"{offenders}"
    )


def test_no_module_outside_the_fold_may_both_build_a_board_and_install_one():
    """The two halves of a move, and nobody outside `apply_event` holds
    both. This is the claim the per-route allow-list is FOR: `collapse.py`
    may install a Scene and `scene/scene.py` may build one, and neither
    can move a man because neither can do the other half.
    """
    both = sorted(
        str(path.relative_to(ENGINE.parent))
        for path in ENGINE.rglob("*.py")
        if {"rebuilds", "installs"} <= _position_routes(path)
    )

    assert both == [], (
        f"these build an altered board AND put it on a session: {both}")


def test_the_placement_allow_list_is_asserted_whole():
    """An allow-list is a place a defect hides, so it is asserted whole."""
    assert ALLOWED_PLACERS == {
        "mutates": frozenset({
        ENGINE / "scene" / "scene.py",
        ENGINE / "scene" / "generate.py",
    }),
        "place_combatant": frozenset({ENGINE / "gm" / "spawn_despawn.py"}),
        "rebuilds": frozenset({ENGINE / "scene" / "scene.py"}),
        "installs": frozenset({
            ENGINE / "session" / "apply.py",
            ENGINE / "collapse.py",
            ENGINE / "actions" / "darkness.py",
            ENGINE / "gm" / "spawn_despawn.py",
        }),
    }
    # And every carve-out is real: each file still takes the route it is
    # listed for, so an entry cannot quietly outlive the code it covers.
    for route, paths in ALLOWED_PLACERS.items():
        for path in paths:
            assert route in _position_routes(path), (route, path)


def test_placement_no_longer_writes_the_board():
    """THE FIX, asserted where it happened. `scene/placement.py` is the
    module whose own docstring used to say it mutated the position map
    "deliberately, and only here"; it records the move now and writes
    nothing."""
    assert _position_routes(ENGINE / "scene" / "placement.py") == frozenset()


# ---------------------------------------------------------------------------
# The gate on the conditions
# ---------------------------------------------------------------------------

def test_the_status_gate_could_actually_fail(tmp_path):
    """The negative control, one case per route."""
    rebuilt = tmp_path / "rebuilt.py"
    rebuilt.write_text(
        "from dataclasses import replace\n"
        "def f(session, cid, held):\n"
        "    return replace(session, statuses={cid: held})\n"
    )
    assert _writes_a_status(rebuilt) is True

    attribute = tmp_path / "attribute.py"
    attribute.write_text("def f(session, s):\n    session.statuses = s\n")
    assert _writes_a_status(attribute) is True

    item = tmp_path / "item.py"
    item.write_text("def f(session, cid, held):\n    session.statuses[cid] = held\n")
    assert _writes_a_status(item) is True

    # The spelling a dict field invites, and the one the seeding used to
    # take -- it was rewritten as an assignment so this gate could see it.
    mutator = tmp_path / "mutator.py"
    mutator.write_text(
        "def f(session, cid):\n"
        "    session.statuses.setdefault(cid, frozenset())\n"
    )
    assert _writes_a_status(mutator) is True

    talker = tmp_path / "talker.py"
    talker.write_text(
        '"""Reads session.statuses and never writes it."""\n'
        "def f(session, cid):\n    return session.statuses[cid]\n"
    )
    assert _writes_a_status(talker) is False

    assert _writes_a_status(ENGINE / "session" / "apply.py") is True


def test_nothing_outside_apply_writes_a_condition():
    """DERIVED, not enumerated: this walks the engine.

    `kirby_combat.statuses.statuses_for` is the RULE --- what makes a
    condition true --- and it is a pure read. The RECORD is written by
    the fold alone, out of `StatusEffectsChanged` rows that
    `status_emission.record_status_changes` emits.
    """
    offenders = sorted(
        str(path.relative_to(ENGINE.parent))
        for path in ENGINE.rglob("*.py")
        if path not in ALLOWED_STATUS_WRITERS and _writes_a_status(path)
    )

    assert offenders == [], (
        "these write a combatant's conditions outside `apply_event` -- "
        "emit a StatusEffectsChanged through `record_status_changes` "
        f"instead: {offenders}"
    )


def test_the_status_allow_list_is_asserted_whole():
    assert set(ALLOWED_STATUS_WRITERS) == {
        ENGINE / "session" / "apply.py",
        ENGINE / "session" / "combat_session.py",
    }
    for path in ALLOWED_STATUS_WRITERS:
        assert _writes_a_status(path) is True, path
