"""A split names every slot of its Multipower, by an id that outlives the
process (6E1 p.404-406; spec §5.2).

`SlotsAllocated` names every slot of its framework, off at 0. So for an
OPENED framework a slot the split does not name is not "off": the split and
the build disagree, and every reader says so (`framework.share_of` raises
`KeyError` naming the slot) instead of reading it as 0. A framework not yet
opened is still the build as written.

A split is keyed on slot ids and outlives the process (the log, a snapshot),
so a framework with a slot that carries no id of its own --- whose slot id is
the process-local stand-in `_slot_id_of` makes up --- cannot be split: the
resolver refuses the opening and every re-split of it.

Ravel's Multipower "Maleable Sting Body" (corpus), ARMaments a variable
Hand-To-Hand Attack slot.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from kirby_combat.enumeration import LegalAction
from kirby_combat.hero_view import HeroCombatant, slot_id_is_stable
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_cost.services.power_builder import build_power_from_spec
from kirby_dice import RandomRoller

from fixtures.synthetic_hero import synthetic_combatant
from tests.corpus import require_authored

FRAMEWORK = "1648348957819"
ARMAMENTS = "1648351359965"
STRING = "1648356198397"


def _ravel(build=None) -> HeroCombatant:
    return HeroCombatant.from_build(build or require_authored("Ravel"))


def _every_slot_off(hero: HeroCombatant) -> dict[str, int]:
    return {s.slot_id: 0 for f in hero.framework_view()
            if f.framework_id == FRAMEWORK for s in f.slots}


def _opened(hero: HeroCombatant, split: dict[str, int]) -> HeroCombatant:
    return replace(hero, state=replace(hero.state, slot_points={FRAMEWORK: split}))


def _missing(hero: HeroCombatant, slot_id: str) -> HeroCombatant:
    split = {**_every_slot_off(hero), ARMAMENTS: 45}
    del split[slot_id]
    return _opened(hero, split)


# ── a slot missing from an opened split ────────────────────────────────────

def test_the_live_readers_refuse_a_split_that_leaves_a_slot_out():
    hero = _missing(_ravel(), STRING)
    with pytest.raises(KeyError, match=STRING):
        hero.combat_stats()
    with pytest.raises(KeyError, match=STRING):
        hero.powers_at_split({"STR"})


def test_the_attack_slot_left_out_is_refused_not_read_as_off():
    hero = _opened(_ravel(), {k: v for k, v in _every_slot_off(_ravel()).items()
                              if k != ARMAMENTS})
    with pytest.raises(KeyError, match=ARMAMENTS):
        hero.attacks


def test_the_upkeep_reader_refuses_it():
    from kirby_combat.upkeep import slot_still_allocated

    hero = _missing(_ravel(), STRING)
    foe = synthetic_combatant(id="foe", name="foe", side=Side.named("red"))
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
        combatants=[replace(hero, side=Side.named("blue")), foe]).start()
    string = next(p for p in hero._build().powers if str(p.id) == STRING)
    with pytest.raises(KeyError, match=STRING):
        slot_still_allocated(session, hero.id, string)


def test_the_mind_scan_reader_refuses_it():
    from kirby_combat.mental.continuing import ContinuingEffect, _scan_switched_off

    hero = _missing(_ravel(), STRING)
    foe = synthetic_combatant(id="foe", name="foe", side=Side.named("red"))
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
        combatants=[replace(hero, side=Side.named("blue")), foe]).start()
    scan = ContinuingEffect(
        effect_id="e", kind="mind_scan", attacker_id=hero.id, target_id="foe",
        order=None, illusion=None, reached=None, source_id=STRING,
        breakout_modifier=0)
    with pytest.raises(KeyError, match=STRING):
        _scan_switched_off(session, scan)


def test_a_rebuilt_combatant_refuses_it_too():
    import json

    from kirby_combat.serialization import from_dict, to_dict

    rebuilt = from_dict(json.loads(json.dumps(to_dict(_ravel()))))
    with pytest.raises(KeyError, match=STRING):
        _missing(rebuilt, STRING).attacks


def test_a_framework_not_yet_opened_is_the_build_as_written():
    hero = _ravel()
    assert hero.state.slot_points == {}
    assert hero.combat_stats().str_ == 10
    assert any(a.slot_id == ARMAMENTS for a in hero.attacks)


# ── a slot with no id of its own ───────────────────────────────────────────

def _with_an_idless_slot():
    """Ravel with a variable 12d6 Blast slot added that has no HD id."""
    build = require_authored("Ravel")
    framework = next(p for p in build.powers if str(p.id) == FRAMEWORK)
    power, _active, _real = build_power_from_spec(
        {"xmlid": "ENERGYBLAST", "levels": 12, "modifiers": []})
    power._id = ""
    power.name = "Nameless Bolt"
    power.ultra = False
    power.levels = 12
    power.parent = framework
    build.powers.append(power)
    framework.objects.append(power)
    return _ravel(build), power


def test_an_idless_slot_has_an_unstable_id():
    hero, _ = _with_an_idless_slot()
    ids = [s.slot_id for f in hero.framework_view() if f.framework_id == FRAMEWORK
           for s in f.slots]
    assert [sid for sid in ids if not slot_id_is_stable(sid)] == [
        sid for sid in ids if sid.startswith("ENERGYBLAST#")]
    assert slot_id_is_stable(ARMAMENTS)


def test_the_resolver_refuses_to_open_a_framework_with_an_idless_slot():
    hero, _ = _with_an_idless_slot()
    foe = synthetic_combatant(id="foe", name="foe", side=Side.named("red"))
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
        combatants=[replace(hero, side=Side.named("blue")), foe]).start()
    act = LegalAction(
        action_id=f"opening_split:{FRAMEWORK}:split={ARMAMENTS}@45",
        kind="opening_split", target_id=None, power_xmlid=None,
        power_name=None, summary="")
    with pytest.raises(UnresolvableAction) as caught:
        resolve_chosen(session, session.combatants[hero.id], act,
                       template=CombatTemplate.default_6e_superheroic(),
                       roller=RandomRoller(seed=1))
    assert "Nameless Bolt" in str(caught.value.__cause__)


def test_an_idless_variable_slots_attack_keeps_the_framework_views_slot_id():
    """Within one process the stand-in id still links the attack to its slot,
    including at a part share, where the attack is built from kirby-cost's
    priced COPY (whose own stand-in id would differ: `replace(slot_id=...)`)."""
    hero, power = _with_an_idless_slot()
    [sid] = [s.slot_id for f in hero.framework_view() if f.framework_id == FRAMEWORK
             for s in f.slots if not slot_id_is_stable(s.slot_id)]
    cut = _opened(hero, {**_every_slot_off(hero), sid: 20})
    [bolt] = [a for a in cut.attacks if a.name == "Nameless Bolt"]
    assert bolt.slot_id == sid
    assert bolt.damage_dice == 4               # 12d6 at 20 points (6E1 p.406)
