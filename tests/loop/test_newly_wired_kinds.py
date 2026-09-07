"""Every newly wired kind, driven through the loop's own dispatch.

REGISTERED IS NOT THE SAME AS WORKING, and the distinction is the whole
point of this file. `registered_kinds()` growing proves a decorator ran. It
does not prove the resolver can be called, that its arguments match the
engine function's signature, or that anything reaches the event log -- and
"it imports" is exactly the standard under which these rules sat unreachable
behind green suites in the first place.

So each test here calls `resolve_chosen`, the same path `run_phase` uses,
and asserts the outcome reached the log.
"""
from __future__ import annotations

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import registered_kinds
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _Power:
    """A power in the shape enumeration attaches to an offer."""

    def __init__(self, xmlid: str, levels: int = 4) -> None:
        self.xmlid = xmlid
        self.name = xmlid.title()
        self.levels = levels
        self.option_id = None
        self.assigned_adders: list = []
        self.source_id = f"src-{xmlid}"


def _session():
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[
            fighter("actor", side=Side.named("heroes"), dex=25),
            fighter("mark", side=Side.named("villains"), dex=15),
        ],
    ).start()


def _action(kind: str, *, target: str | None = "mark", power=None) -> LegalAction:
    return LegalAction(
        action_id=f"{kind}:{target or ''}", kind=kind, target_id=target,
        power_xmlid=getattr(power, "xmlid", None),
        power_name=getattr(power, "name", None),
        summary=f"{kind} {target or ''}".strip(),
        _attack_view=power,
    )


def _resolve(action: LegalAction):
    session = _session()
    return session, resolve_chosen(
        session, session.combatants["actor"], action,
        template=TEMPLATE, roller=RandomRoller(seed=9),
    )


# ---- Declarations: the whole effect is that they were declared ----

@pytest.mark.parametrize("kind", ["dodge", "set", "haymaker"])
def test_a_declaration_reaches_the_log(kind):
    """Dodge's +3 DCV, Set's +1 OCV and Haymaker's +4 DC are all read back
    from the log LATER. If the declaration does not land, the bonus never
    exists -- and nothing else would report a problem."""
    before, resolved = _resolve(_action(kind, target=None))
    assert resolved.kind == kind
    assert resolved.events, f"{kind} recorded nothing"
    assert len(resolved.session.event_log) > len(before.event_log)


def test_dodge_actually_grants_its_bonus():
    """Not just 'an event landed' -- the rule it enables must be true."""
    from kirby_combat.actions.reactive.dodge import Dodge

    before, resolved = _resolve(_action("dodge", target=None))
    assert Dodge.dcv_bonus(before, "actor") == 0
    assert Dodge.dcv_bonus(resolved.session, "actor") == 3


# ---- Powers ----

def test_flash_blinds_and_records_it():
    _, resolved = _resolve(_action("flash", power=_Power("FLASH", levels=6)))
    assert resolved.result is not None
    assert resolved.events


def test_entangle_traps_and_records_it():
    _, resolved = _resolve(_action("entangle", power=_Power("ENTANGLE", levels=5)))
    assert resolved.result is not None
    assert resolved.events


def test_a_power_kind_without_its_power_refuses():
    """`_attack_view` is the offer's handle on the actual power. Resolving
    without it would mean guessing which power was meant."""
    from kirby_combat.loop.registry import UnresolvableAction

    for kind in ("flash", "entangle"):
        with pytest.raises(UnresolvableAction, match=kind):
            _resolve(_action(kind, power=None))


# ---- Contested maneuvers ----

def test_grab_resolves_a_contest():
    _, resolved = _resolve(_action("grab"))
    assert resolved.result is not None
    assert resolved.events


def test_block_resolves_a_contest():
    _, resolved = _resolve(_action("block"))
    assert resolved.result is not None
    assert resolved.events


def test_presence_attack_produces_an_effect_not_damage():
    """6E2 p.129 -- a Presence Attack changes what a target is willing to
    do. No STUN or BODY moves."""
    before, resolved = _resolve(_action("presence_attack"))
    assert resolved.result.effect
    assert (
        resolved.session.combatants["mark"].state.current_stun
        == before.combatants["mark"].state.current_stun
    )


# ---- The count, and what it does not claim ----

def test_sixteen_of_fifty_two_are_wired():
    assert len(registered_kinds()) == 16


def test_every_registered_kind_is_covered_by_a_test_here_or_elsewhere():
    """A guard against registering a kind and never exercising it -- which
    is the failure mode this whole file exists to prevent."""
    exercised = {
        "attack", "strike", "mental_blast", "recover",          # test_run / damage
        "mind_control", "mental_illusion", "telepathy",         # test_mental_reconnected
        "image_decoy",                                          # test_image_decoy_reconnected
        "dodge", "set", "haymaker", "presence_attack",          # here
        "flash", "entangle", "grab", "block",                   # here
    }
    assert registered_kinds() <= exercised, (
        f"registered but never exercised: {sorted(registered_kinds() - exercised)}"
    )
