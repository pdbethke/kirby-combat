"""Pure-function tests for the combat driver's action enumeration.

No DB, no model — just synthetic combatants exercising the rules
that decide which actions get into the legal-action menu.
"""
from __future__ import annotations

import itertools
import pytest
from dataclasses import dataclass, field

from kirby_combat.enumeration import (
    LegalAction,
    enumerate_actions,
    is_down,
)
from kirby_combat.hero_view import HeroCombatant, HeroCombatState


# Synthetic powers still need identities: kirby indexes on ids, so a stub
# without one is not modelling a real power. Mirrors the engine, which
# assigns from a counter when the source supplies no ID.
_STUB_IDS = itertools.count(9_000_001)

# ── stub combatant fixture (mirrors tests/combat/test_tactics.py) ──────────


@dataclass
class _StubPower:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    input_value: str | None = None
    option_id: str | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)
    id: int = field(default_factory=lambda: next(_STUB_IDS))


@dataclass
class _StubChar:
    """A characteristic object. The bare STR Strike takes its identity from
    the STR characteristic's id, so a stub hero needs real objects here."""
    xmlid: str
    id: int = field(default_factory=lambda: next(_STUB_IDS))


@dataclass
class _StubHero:
    name: str = "Test"
    template_name: str = "synthetic.Test.hdt"
    powers: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    perks: list = field(default_factory=list)
    talents: list = field(default_factory=list)
    complications: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    _char_values: dict = field(default_factory=dict)
    characteristics: list = field(default_factory=lambda: [
        _StubChar("STR"), _StubChar("DEX"), _StubChar("CON"),
    ])

    def characteristic_value(self, xmlid: str) -> int:
        return self._char_values.get(xmlid.upper(), 0)

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        """No stub hero carries a conditional (Only-In-Hero-ID) purchase,
        so the temporal value is the base value whatever ``ctx`` says.
        combat_stats() reads this instead of characteristic_value()."""
        return self.characteristic_value(xmlid)


def _combatant(
    *, id: str, name: str = "", str_: int = 20, ocv: int = 8,
    dcv: int = 8, spd: int = 4, pre: int = 15, stun: int = 40,
    body: int = 12, end_: int = 40, pd: int = 10, ed: int = 10,
    powers: list | None = None,
    state_overrides: dict | None = None,
) -> HeroCombatant:
    chars = {
        "STR": str_, "DEX": 15, "CON": 15, "INT": 15, "EGO": 12, "PRE": pre,
        "OCV": ocv, "DCV": dcv, "OMCV": 3, "DMCV": 3, "SPD": spd,
        "PD": pd, "ED": ed, "REC": 5, "END": end_, "BODY": body, "STUN": stun,
        "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
    }
    hero = _StubHero(name=name or id, _char_values=chars, powers=powers or [])
    state_kwargs = dict(
        current_stun=stun, current_body=body, current_end=end_,
    )
    if state_overrides:
        state_kwargs.update(state_overrides)
    return HeroCombatant(
        id=id, hero=hero,  # type: ignore[arg-type]
        state=HeroCombatState(**state_kwargs),
        knockback_resistance=0,
    )


# ── tests ──────────────────────────────────────────────────────────────────


def test_is_down_handles_stun_and_body() -> None:
    actor = _combatant(id="alice")
    assert is_down(actor) is False
    actor.state.current_stun = 0
    assert is_down(actor) is True
    actor.state.current_stun = 40  # back up
    actor.state.current_body = -1
    assert is_down(actor) is True


def test_enumerate_actions_returns_empty_for_downed_actor() -> None:
    actor = _combatant(id="alice", state_overrides={"current_stun": 0})
    enemy = _combatant(id="bob")
    assert enumerate_actions(actor, [enemy]) == []


def test_enumerate_actions_filters_dead_enemies() -> None:
    """A dead enemy shouldn't generate an attack option."""
    eb = _StubPower(xmlid="ENERGYBLAST", name="Beam", levels=8)
    actor = _combatant(id="alice", powers=[eb])
    alive = _combatant(id="bob")
    dead = _combatant(id="cathy", state_overrides={"current_body": -1})

    actions = enumerate_actions(actor, [alive, dead])
    target_ids = {a.target_id for a in actions if a.target_id}
    assert "bob" in target_ids
    assert "cathy" not in target_ids, "dead enemy should be excluded"


def test_enumerate_actions_strikes_attack_each_enemy() -> None:
    """No listed attack powers + STR ≥ 5 → unarmed Strike per enemy."""
    actor = _combatant(id="alice", str_=20, powers=[])
    enemy_a = _combatant(id="bob")
    enemy_b = _combatant(id="cathy")
    actions = enumerate_actions(actor, [enemy_a, enemy_b])
    strike_targets = sorted(a.target_id for a in actions if a.kind == "strike")
    assert strike_targets == ["bob", "cathy"]


def test_enumerate_actions_includes_dodge_with_no_enemies() -> None:
    """A healthy actor with no enemies still gets Dodge.

    Dodge is self-targeted, so it needs nobody. This test also used to
    assert `set`, and that was asserting a defect: 6E2 p.81 says "A
    character must Set on a specific target (either an individual or an
    object); he can't just Set until a target presents itself", and the
    offer carried `target_id=None`. Set is now per-target and gated on
    having a Ranged attack, so an actor alone in an empty fight is
    correctly offered none.
    """
    actor = _combatant(id="alice")
    actions = enumerate_actions(actor, [])
    kinds = {a.kind for a in actions}
    assert "dodge" in kinds
    assert "set" not in kinds, "a Set with nobody to aim at is not legal"


def test_enumerate_actions_includes_recover_when_wounded() -> None:
    actor = _combatant(
        id="alice", stun=40,
        state_overrides={"current_stun": 10},  # < ½ max
    )
    actions = enumerate_actions(actor, [])
    assert any(a.kind == "recover" for a in actions)


def test_enumerate_actions_skips_recover_when_healthy() -> None:
    actor = _combatant(id="alice")  # default full HP
    actions = enumerate_actions(actor, [])
    assert all(a.kind != "recover" for a in actions)


def test_two_powers_sharing_xmlid_and_name_get_distinct_action_ids() -> None:
    """Identity is the power's object id, not the strings it displays.

    A character may legitimately carry two powers of the same type with the
    same name ("Blast" twice, differently modified). Keying the action_id on
    xmlid + name gave both the SAME token, so the picker could not express which
    one it wanted and the first match always won.
    """
    a = _StubPower(id=101, xmlid="ENERGYBLAST", name="Blast", levels=8)
    b = _StubPower(id=202, xmlid="ENERGYBLAST", name="Blast", levels=10)
    actor = _combatant(id="alice", powers=[a, b])
    enemy = _combatant(id="bob")

    attack_ids = [
        act.action_id for act in enumerate_actions(actor, [enemy])
        if act.kind == "attack"
    ]

    assert len(attack_ids) == 2, f"expected one offer per power, got {attack_ids}"
    assert len(set(attack_ids)) == 2, f"colliding action_ids: {attack_ids}"


def test_two_mental_attacks_sharing_xmlid_and_name_get_distinct_action_ids() -> None:
    """``mental_blast`` keyed on the same colliding strings as ``attack``."""
    a = _StubPower(id=101, xmlid="EGOATTACK", name="Mind Spike", levels=6)
    b = _StubPower(id=202, xmlid="EGOATTACK", name="Mind Spike", levels=8)
    actor = _combatant(id="alice", powers=[a, b])
    enemy = _combatant(id="bob")

    ids = [
        act.action_id for act in enumerate_actions(actor, [enemy])
        if act.kind == "mental_blast"
    ]

    assert len(ids) == 2, f"expected one offer per power, got {ids}"
    assert len(set(ids)) == 2, f"colliding action_ids: {ids}"


def test_two_decoy_attacks_sharing_xmlid_and_name_get_distinct_action_ids() -> None:
    """The decoy attack offer must disambiguate the same way the real one does.

    A decoy exists to be indistinguishable from the real foe, so its offers
    have to carry the same identity guarantees — otherwise the model can name
    an attack against the decoy that it cannot name against anything else.
    """
    a = _StubPower(id=101, xmlid="ENERGYBLAST", name="Blast", levels=8)
    b = _StubPower(id=202, xmlid="ENERGYBLAST", name="Blast", levels=10)
    actor = _combatant(id="alice", powers=[a, b])
    enemy = _combatant(id="bob")

    actions = enumerate_actions(
        actor, [enemy], has_scene=True, decoy_targets=[("decoy-1", "Gorgon")],
    )
    ids = [act.action_id for act in actions if act.target_id == "decoy-1"]

    assert len(ids) == 2, f"expected one offer per power, got {ids}"
    assert len(set(ids)) == 2, f"colliding action_ids: {ids}"


def test_attack_action_id_is_unchanged_by_a_rename() -> None:
    """Renaming a power must not change its handle.

    The token identifies the object; the readable label lives in ``summary``.
    """
    named = _StubPower(id=101, xmlid="ENERGYBLAST", name="Fire Bolt", levels=8)
    renamed = _StubPower(id=101, xmlid="ENERGYBLAST", name="Soul Lance", levels=8)
    enemy = _combatant(id="bob")

    def _attack_id(power: _StubPower) -> str:
        actor = _combatant(id="alice", powers=[power])
        return next(
            a.action_id for a in enumerate_actions(actor, [enemy])
            if a.kind == "attack"
        )

    assert _attack_id(named) == _attack_id(renamed)


def test_an_identityless_power_is_refused_not_keyed_on_its_xmlid() -> None:
    """There is no string fallback. A view with no id is a producer bug.

    Falling back to xmlid + name is exactly what made 630 corpus objects share
    a token while reporting success, so the builder refuses instead. Every
    real view carries an id — kirby-combat gives one even to the bare STR
    strike (from the STR characteristic).
    """
    from kirby_combat.enumeration import _power_action_id

    class _NoIdentity:
        xmlid = "ENERGYBLAST"
        name = "Fire Bolt"
        slot_id = ""

    with pytest.raises(ValueError, match="carries no id"):
        _power_action_id("attack", "bob", _NoIdentity())


def test_attack_action_ids_carry_the_power_id_when_present() -> None:
    """With real (id-bearing) powers the handle IS the object id."""
    eb = _StubPower(id=101, xmlid="ENERGYBLAST", name="Fire Bolt", levels=8)
    rka = _StubPower(id=202, xmlid="RKA", name="Soul Lance", levels=2)
    actor = _combatant(id="alice", powers=[eb, rka])
    enemy = _combatant(id="bob")
    actions = enumerate_actions(actor, [enemy])
    attack_ids = sorted(a.action_id for a in actions if a.kind == "attack")
    assert attack_ids == ["attack:bob:101", "attack:bob:202"]
