"""GM overrides — Tier 1/2/3 apply."""
import pytest

from kirby_combat.gm.overrides import (
    make_tier1_stun_adjust, make_tier1_status_application,
    make_tier2_dice_override, make_tier2_retroactive_abort,
    make_tier3_spawn, make_tier3_scene_mutation,
    apply_tier1_override, apply_tier3_spawn, apply_tier3_despawn,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import GMOverride
from kirby_combat.template import CombatTemplate
from kirby_combat.models import Combatant


def _ct(id_: str, current_stun: int = 30) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=current_stun, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    template = CombatTemplate.default_6e_superheroic()
    return CombatSession.create(
        id="s1", combatants=[_ct("alice", 30), _ct("bob", 30)],
        scene=None, template=template,
    )


def test_tier_1_stun_adjust_mutates_combatant_current_stun():
    s = _session()
    override = make_tier1_stun_adjust(s, "gm-pete", "alice", new_stun=12)
    assert override.tier == 1
    s2 = apply_tier1_override(s, override)
    assert s2.combatants["alice"].current_stun == 12


def test_tier_1_status_application_emits_statuschanged():
    s = _session()
    override = make_tier1_status_application(s, "gm-pete", "alice", "stunned")
    assert override.tier == 1
    assert override.patch["op"] == "apply_status"


def test_tier_2_dice_override_creates_replacement_event_not_mutation():
    s = _session()
    override = make_tier2_dice_override(
        s, "gm-pete", target_event_id="evt-3",
        new_dice_values=[3, 3, 3], justification="bad fudge",
    )
    assert override.tier == 2
    assert override.target_event_id == "evt-3"
    assert override.patch["op"] == "replace_dice"


def test_tier_2_retroactive_abort_reverses_snapshot_effects():
    s = _session()
    override = make_tier2_retroactive_abort(
        s, "gm-pete", target_event_id="evt-3", justification="shouldn't have hit",
    )
    assert override.tier == 2
    assert override.patch["op"] == "retroactive_abort"


def test_tier_3_spawn_despawn_modifies_combatants_dict():
    s = _session()
    new_npc = _ct("carol")
    override = make_tier3_spawn(s, "gm-pete", new_npc, justification="surprise")
    s2 = apply_tier3_spawn(s, override, new_npc)
    assert "carol" in s2.combatants
    s3 = apply_tier3_despawn(s2, "carol")
    assert "carol" not in s3.combatants


def test_tier_3_scene_mutation_updates_scene_snapshot():
    s = _session()
    override = make_tier3_scene_mutation(
        s, "gm-pete",
        scene_patch={"add_hazard_id": "lava1"},
        justification="dramatic moment",
    )
    assert override.tier == 3
    assert override.patch["add_hazard_id"] == "lava1"


def test_all_tiers_require_justification_for_tier_2_and_3():
    s = _session()
    with pytest.raises(ValueError, match="justification"):
        make_tier2_dice_override(s, "gm", "evt-1", [1, 2, 3], justification="")
    with pytest.raises(ValueError, match="justification"):
        make_tier3_spawn(s, "gm", _ct("ned"), justification="")


def test_override_author_always_gm_type():
    s = _session()
    o = make_tier1_stun_adjust(s, "gm-pete", "alice", new_stun=5)
    assert o.author.type == "gm"
    assert o.author.id == "gm-pete"
