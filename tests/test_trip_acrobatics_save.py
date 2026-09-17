"""A tripped man with Acrobatics may keep his feet.

Trip itself is 6E2 p.67 (-1 OCV, no damage, target knocked prone). The SAVE
is not in the book: it is a house rule carried in from the consuming
application's Spec C section 3, and it is labelled as one in the resolver so
that deleting it is a one-line decision.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import FakeRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: `resolvers._attack_dice` draws to-hit 3d6, then damage (none, for a
#: maneuver that does none), then Hit Location 3d6 and the STUN Multiplier.
#: The save's 3d6 comes after all of them.
_LOCATION = [3, 3, 3]
_STUN_MULT = [1]


def _blast(source_id: str) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id, is_ranged=True,
    )


def _man(id: str, *, side, skills: dict[str, int] | None = None):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40,
        side=side, attacks=[_blast(f"{id}-eb")], skills=skills or {},
    )


def _fight(*, target_skills: dict[str, int] | None) -> CombatSession:
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=FakeRoller([]),
        combatants=[
            _man("brute", side=Side.named("villains")),
            _man("mark", side=Side.named("heroes"), skills=target_skills),
        ],
    ).start()


def _trip() -> LegalAction:
    return LegalAction(
        action_id="trip:mark", kind="trip", target_id="mark",
        power_xmlid=None, power_name=None, summary="trip",
        _attack_view=_blast("brute-eb"),
    )


def _resolve(session, roller):
    return resolve_chosen(
        session, session.combatants["brute"], _trip(),
        template=TEMPLATE, roller=roller,
    )


def _roller(to_hit: list[int], save: list[int] | None) -> FakeRoller:
    pool = [to_hit, _LOCATION, _STUN_MULT]
    if save is not None:
        pool.append(save)
    return FakeRoller(pool)


def test_a_successful_acrobatics_roll_keeps_feet():
    """Hit by a small margin, then make the roll: the man stays standing."""
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [1, 1, 1]))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    save = payload["acrobatics_save"]
    assert save is not None
    assert save["rolled"] is True
    assert save["roll"] == 3
    assert save["kept_feet"] is True
    # The penalty is the margin by which the Trip landed, never a bonus.
    assert save["target"] == 15 - max(0, resolved.result.to_hit.margin)
    assert payload["is_prone_after"] is False
    assert PRONE not in statuses_for(resolved.session, "mark")


def test_a_failed_roll_falls():
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [6, 6, 6]))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    assert payload["acrobatics_save"]["kept_feet"] is False
    assert payload["is_prone_after"] is True
    assert PRONE in statuses_for(resolved.session, "mark")


def test_a_man_without_acrobatics_simply_falls():
    """No skill, no roll: the payload says so rather than inventing a save."""
    session = _fight(target_skills=None)
    resolved = _resolve(session, _roller([4, 4, 4], None))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is True
    assert payload["acrobatics_save"] is None
    assert payload["is_prone_after"] is True
    assert PRONE in statuses_for(resolved.session, "mark")


def test_a_missed_trip_rolls_no_save_at_all():
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([6, 6, 6], None))
    payload = resolved.session.event_log[-1].result_payload

    assert payload["hit"] is False
    assert payload["acrobatics_save"] is None
    assert payload["is_prone_after"] is False
    assert PRONE not in statuses_for(resolved.session, "mark")


# ---------------------------------------------------------------------------
# The row a consumer persists is the finished row
# ---------------------------------------------------------------------------

def _replayed(session: CombatSession) -> CombatSession:
    """A fresh session rebuilt from the rows AS THEY WERE EMITTED.

    This is the whole point: a consumer persists each event when it comes
    out of the resolver, not by re-reading the session's log afterwards.
    Replaying `session.event_log` would hide an edit made to a committed
    row, because the edit is in the log the test just read.
    """
    from kirby_combat.session.apply import apply_event

    rebuilt = CombatSession.create(
        id=session.id,
        combatants=list((session.initial_combatants or {}).values()),
        scene=session.scene, template=session.template,
        dice_roller=session.dice_roller,
    )
    for event in session.event_log:
        rebuilt = apply_event(rebuilt, event)
    return rebuilt


def test_the_trip_row_is_finished_before_it_is_applied():
    """THE DEFECT. The resolver used to run the attack through
    `apply_event` and THEN `dataclasses.replace` the payload on
    `event_log[-1]`, so a consumer that persisted the row when it was
    emitted stored a payload with no `kind="trip"`, no save and no
    `is_prone_after` at all --- and `statuses._is_prone` folds exactly
    those.

    Asserted against the event OBJECT the resolver handed out on its
    `ResolvedAction`, which is what a consumer holds, rather than against
    the session's log, which is where the edit landed.
    """
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [6, 6, 6]))

    emitted = [e for e in resolved.events if e.kind == "ActionResolved"]
    assert len(emitted) == 1
    payload = emitted[0].result_payload

    assert payload["kind"] == "trip"
    assert payload["is_prone_after"] is True
    assert payload["acrobatics_save"]["kept_feet"] is False
    # And it IS the same object the session holds -- one row, not two
    # versions of one row.
    assert emitted[0] is resolved.session.event_log[-1]


def test_a_replayed_trip_leaves_the_same_man_prone():
    """The consequence, end to end."""
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [6, 6, 6]))

    assert PRONE in statuses_for(resolved.session, "mark")
    assert PRONE in statuses_for(_replayed(resolved.session), "mark")


def test_a_replayed_trip_leaves_the_man_who_kept_his_feet_standing():
    """The other side of it, so the test above cannot pass by PRONE being
    true for everybody."""
    session = _fight(target_skills={"ACROBATICS": 15})
    resolved = _resolve(session, _roller([4, 4, 4], [1, 1, 1]))

    assert PRONE not in statuses_for(resolved.session, "mark")
    assert PRONE not in statuses_for(_replayed(resolved.session), "mark")


def _edits_the_log(path) -> bool:
    """Does this module write into an event log after the fact?

    Two shapes: an index assignment onto a list that is the log
    (`log[-1] = ...`), and handing a replacement log to
    `dataclasses.replace` (`replace(session, event_log=...)`). The trip
    resolver did both.
    """
    import ast

    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript)
                        and _names_the_log(target.value)):
                    return True
        if isinstance(node, ast.Call):
            name = (getattr(node.func, "id", None)
                    or getattr(node.func, "attr", None))
            if name in {"replace", "_replace"} and any(
                    kw.arg == "event_log" for kw in node.keywords):
                return True
    return False


def _names_the_log(node) -> bool:
    import ast

    if isinstance(node, ast.Attribute):
        return node.attr == "event_log"
    if isinstance(node, ast.Name):
        return "log" in node.id
    return False


def test_the_committed_row_gate_could_actually_fail(tmp_path):
    """The negative control, both ways --- and against the real old code.

    The third case is the resolver as it stood at `4df17c30`, copied
    verbatim: if the detector does not flag that, it is guarding nothing.
    """
    indexed = tmp_path / "indexed.py"
    indexed.write_text(
        "def f(session):\n"
        "    log = list(session.event_log)\n"
        "    log[-1] = 1\n"
    )
    assert _edits_the_log(indexed) is True

    swapped = tmp_path / "swapped.py"
    swapped.write_text(
        "from dataclasses import replace\n"
        "def f(session, log):\n"
        "    return replace(session, event_log=log)\n"
    )
    assert _edits_the_log(swapped) is True

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        '"""Never assign to event_log[-1]."""\n'
        "def f(session):\n"
        "    return len(session.event_log) + 1\n"
    )
    assert _edits_the_log(innocent) is False


def test_no_resolver_edits_a_committed_row():
    """DERIVED, not enumerated: this walks the engine by AST.

    Writing to `event_log[...]` or passing `event_log=` to a
    `dataclasses.replace` is how a row gets edited after `apply_event` has
    committed it, and a consumer that persisted the row already holds the
    version before the edit. `apply_event` itself builds the new log, and
    `rewind.py` truncates one; everything else must let the row stand.
    """
    import pathlib

    engine = pathlib.Path(__file__).resolve().parent.parent / "kirby_combat"
    allowed = {engine / "session" / "apply.py", engine / "session" / "rewind.py"}

    offenders = sorted(
        str(p.relative_to(engine.parent))
        for p in engine.rglob("*.py")
        if p not in allowed and _edits_the_log(p)
    )

    assert offenders == [], (
        "these edit an event log a consumer may already have persisted -- "
        f"build the finished row before applying it: {offenders}"
    )
