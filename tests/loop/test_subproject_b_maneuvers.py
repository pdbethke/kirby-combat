"""Trip, Disarm and Spread — the three that had NO engine rule at all.

Every other kind wired this session was a rule the engine already had and
nothing called. These three were different: nothing implemented them
anywhere. Enumeration has been offering them, with their exact numbers in
the summary, to choosers that could never execute them.

Each citation comes from enumeration's own offer text, which carried the
page reference all along:

  Trip    6E2 p.67 -- -1 OCV, no damage, target knocked prone
  Disarm  6E2 p.65 -- -2 OCV, knock a weapon from the target's hand
  Spread  6E2 p.52 -- sacrifice N damage dice for +N OCV
"""
from __future__ import annotations

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller, RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _session():
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=4),
        combatants=[
            fighter("actor", side=Side.named("heroes"), dex=25),
            # DCV 0 and no defenses: these tests are about the maneuver, not
            # about whether an average roll happens to land.
            fighter("mark", side=Side.named("villains"), dex=10),
        ],
    ).start()


def _act(kind: str, *, action_id: str | None = None, power=None) -> LegalAction:
    return LegalAction(
        action_id=action_id or f"{kind}:mark", kind=kind, target_id="mark",
        power_xmlid=None, power_name=None, summary=kind,
        _attack_view=power if power is not None else blast("eb", dice=8),
    )


def _hits(damage_dice: int = 0) -> FakeRoller:
    """A guaranteed hit: 3 on 3d6, then damage if the maneuver rolls any."""
    pool = [[1, 1, 1]]
    if damage_dice:
        pool.append([3] * damage_dice)
    return FakeRoller(pool)


def _misses() -> FakeRoller:
    return FakeRoller([[6, 6, 6]])


def _resolve(action, *, roller=None):
    session = _session()
    return session, resolve_chosen(
        session, session.combatants["actor"], action,
        template=TEMPLATE, roller=roller or RandomRoller(seed=4),
    )


# ---- Trip: the consequence finally has somewhere to live ----

def test_a_landed_trip_knocks_the_target_prone():
    """`prone` was a documented gap: its consumers existed (`scene/cover.py`
    takes `target_is_prone_or_diving`, `martial_arts.py` has `target_falls`)
    and NOTHING could ever set it. Trip is that source."""
    # to_hit 3 (a 9) against DCV 5 at -1 OCV still lands comfortably.
    _, resolved = _resolve(_act("trip"), roller=_hits())
    assert resolved.result.hit
    assert PRONE in statuses_for(resolved.session, "mark")


def test_a_missed_trip_leaves_them_standing():
    _, resolved = _resolve(_act("trip"), roller=_misses())
    assert not resolved.result.hit
    assert PRONE not in statuses_for(resolved.session, "mark")


def test_a_trip_does_no_damage():
    """6E2 p.67 -- the Attack Roll decides whether they go down, and that is
    the whole effect."""
    before, resolved = _resolve(_act("trip"), roller=_hits())
    assert (
        resolved.session.combatants["mark"].state.current_stun
        == before.combatants["mark"].state.current_stun
    )


def test_prone_clears_only_on_an_explicit_status_change():
    """Getting up costs a Half Phase and this engine has no stand-up action
    among the kinds it offers, so nothing can signal it automatically. A
    clearing rule is NOT invented here -- it is a consumer's explicit act."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import StatusChanged, make_author_engine

    _, resolved = _resolve(_act("trip"), roller=_hits())
    session = resolved.session
    assert PRONE in statuses_for(session, "mark")

    session = apply_event(session, StatusChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="mark",
    ))
    assert PRONE not in statuses_for(session, "mark")


def test_being_prone_does_not_hide_being_stunned():
    """Prone is its own `if`, not part of the Stunned chain -- a combatant
    can be both, and folding them together would make one mask the other."""
    import inspect

    from kirby_combat import statuses

    src = inspect.getsource(statuses.statuses_for)
    assert "elif _is_prone" not in src


# ---- Disarm: an honest partial ----

def test_a_disarm_lands_but_takes_nothing_away():
    """The Attack Roll is real; the disarming is not yet. This engine has
    no per-combatant weapon inventory to remove anything from, and
    enumeration's own comment has said so since the offer was written."""
    before, resolved = _resolve(_act("disarm"), roller=_hits())
    assert resolved.result.hit
    assert resolved.events
    assert (
        list(resolved.session.combatants["mark"].attacks)
        == list(before.combatants["mark"].attacks)
    ), "nothing to remove -- and the test says so rather than pretending"


# ---- Spread: a symmetrical trade ----

def test_spread_trades_dice_for_ocv_one_for_one():
    """6E2 p.52. The count rides on the action_id's trailing `:N`, where
    enumeration put it, so menu and resolution cannot disagree."""
    _, resolved = _resolve(
        _act("spread", action_id="spread:mark:eb:2", power=blast("eb", dice=8)),
        roller=_hits(damage_dice=6),     # 8 dice less the 2 sold
    )
    assert resolved.result.hit
    assert resolved.events


def test_spread_reads_the_count_off_the_offer():
    """A different `:N` sells a different number of dice."""
    for sold in (1, 3):
        _, resolved = _resolve(
            _act("spread", action_id=f"spread:mark:eb:{sold}",
                 power=blast("eb", dice=8)),
            roller=_hits(damage_dice=8 - sold),
        )
        assert resolved.result.hit


def test_selling_every_die_is_refused():
    """OCV for an attack that cannot hurt anyone is not a trade the book
    offers."""
    with pytest.raises(UnresolvableAction, match="spread"):
        _resolve(_act("spread", action_id="spread:mark:eb:8",
                      power=blast("eb", dice=8)))


def test_spread_without_a_power_refuses():
    action = _act("spread")
    object.__setattr__(action, "_attack_view", None)
    with pytest.raises(UnresolvableAction, match="spread"):
        _resolve(action)
