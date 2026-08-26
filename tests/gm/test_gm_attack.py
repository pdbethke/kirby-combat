"""GM attack — NPC or absent-PC attacks authored by the GM."""
import pytest

from kirby_combat.gm.gm_attack import (
    make_gm_attack, can_actor_pay_end, GMAttackDeclaration,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from tests.fixtures.synthetic_hero import synthetic_combatant


def _ct(id_: str, current_end: int = 30):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=current_end,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_ct("alice"), _ct("npc-thug"), _ct("absent-bob")],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
    )


def test_gm_attack_on_behalf_of_npc_uses_npc_stats():
    s = _session()
    gma = make_gm_attack(s, "gm-pete", "npc-thug", ["alice"])
    assert gma.declaration.combatant_id == "npc-thug"
    assert gma.declaration.targets == ["alice"]


def test_gm_attack_author_is_gm_type_with_user_id():
    s = _session()
    gma = make_gm_attack(s, "gm-pete", "npc-thug", ["alice"])
    assert gma.declaration.author.type == "gm"
    assert gma.declaration.author.id == "gm-pete"


def test_gm_attack_for_absent_player_pc_sets_on_behalf_of_field():
    s = _session()
    gma = make_gm_attack(
        s, "gm-pete", "absent-bob", ["alice"],
        on_behalf_of="absent-bob",
    )
    assert gma.on_behalf_of == "absent-bob"
    assert gma.declaration.parameters["on_behalf_of"] == "absent-bob"


def test_gm_attack_respects_npc_current_end_for_gating():
    npc = _ct("npc-thug", current_end=2)
    assert can_actor_pay_end(npc, end_cost=5) is False
    assert can_actor_pay_end(npc, end_cost=2) is True


def test_gm_attack_flows_through_normal_resolution_pipeline():
    s = _session()
    gma = make_gm_attack(s, "gm-pete", "npc-thug", ["alice"], action_type="attack")
    # The declaration is a vanilla ActionDeclared; the engine pipeline
    # treats it identically to a player-authored declaration.
    assert gma.declaration.kind == "ActionDeclared"
    assert gma.declaration.action_type == "attack"
