"""Dispel turns a power off, and its owner turns it back on (6E1 p.195).

origin/main rolled the Dispel dice, recorded the total and turned nothing
off; its offer said "one of his defenses" and named none.

Power Lad's "Body Like Iron" is a 69-Active-Point Force Field (25 rPD / 20
rED) beside 20 points of Power Defense, which comes off a Dispel roll
(p.195: "subtracts the target's Power Defense"). A real build, because the
point is that every reader of his powers --- here the defences
`combat_stats()` totals --- loses the dispelled one.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from conftest import fighter                             # tests/loop/conftest.py
from corpus import require_authored
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
FORCE_FIELD = "1727273798229"
HIT = [1, 1, 1]


class _Dispel:
    def __init__(self, levels: int, input: str):
        self.xmlid, self.name, self.alias = "DISPEL", f"Dispel {input}", "Dispel"
        self.id = "src-dispel"
        self.levels, self.level_value = levels, 1.0
        self.input = input
        self.range, self.range_value = "Yes", 10 * 3 * levels
        self.active_cost = 3 * levels
        self.assigned_adders: list = []
        self.assigned_modifiers: list = []
        self.sub_powers: list = []


def _fight(*, levels: int = 16, input: str = "Force Field") -> CombatSession:
    lad = replace(HeroCombatant.from_build(require_authored("PowerLad"), id="lad"),
                  side=Side.named("heroes"))
    nullifier = fighter("null", side=Side.named("villains"), dex=5)
    nullifier.hero.powers.append(_Dispel(levels, input))
    return CombatSession.create(
        id="s", combatants=[lad, nullifier], scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


def _dispel_offer(session):
    menu = enumerate_actions(session.combatants["null"], [session.combatants["lad"]])
    return [a for a in menu if a.kind == "dispel"]


def _dispel(session, dice):
    (offer,) = _dispel_offer(session)
    return resolve_chosen(session, session.combatants["null"], offer,
                          template=TEMPLATE, roller=FakeRoller(dice))


def test_the_offer_names_the_power():
    (offer,) = _dispel_offer(_fight())
    assert offer.action_id.endswith(f":power={FORCE_FIELD}")
    assert "Body Like Iron" in offer.summary


def test_a_dispel_that_beats_the_active_points_turns_the_force_field_off():
    session = _fight()
    before = session.combatants["lad"].combat_stats()
    resolved = _dispel(session, [HIT, [6] * 16])          # 96 - 20 PD = 76 > 69
    assert resolved.result["dispelled"] is True
    after = resolved.session.combatants["lad"].combat_stats()
    assert (after.rpd, after.red) < (before.rpd, before.red)
    assert any(e.kind == "PowerDispelled" for e in resolved.events)


def test_a_tie_does_not_dispel():
    """"If the remaining total EXCEEDS the Active Point total". The driver
    this replaces dispelled on a tie."""
    resolved = _dispel(_fight(), [HIT, [6] * 14 + [2, 3]])   # 89 - 20 = 69
    assert resolved.result["dispelled"] is False
    assert not any(e.kind == "PowerDispelled" for e in resolved.events)


def test_a_dispel_that_misses_does_nothing():
    resolved = _dispel(_fight(), [[6, 6, 6]])
    assert resolved.result["hit"] is False
    assert resolved.session.combatants["lad"].combat_stats().rpd == 25


class _Dodges:
    def choose(self, situation):
        return next(a for a in situation.menu if a.kind == "dodge").action_id


def test_he_turns_it_back_on_at_his_next_phase():
    """6E2 p.20: activating a Power is a Zero Phase Action at the start of a
    Phase. `run_phase` makes it for him before he chooses."""
    dispelled = _dispel(_fight(), [HIT, [6] * 16]).session
    assert dispelled.combatants["lad"].combat_stats().rpd < 25
    enc = Encounter(id="e", turn=1, segment=12, sessions=[dispelled])
    result = run_phase(enc, _Dodges(), roller=RandomRoller(seed=4),
                       on_unresolvable="raise")
    assert result.actor_id == "lad"
    back = result.encounter.sessions[0]
    assert back.combatants["lad"].combat_stats().rpd == 25
    assert any(e.kind == "PowerRestarted" for e in back.event_log)


def test_a_dispel_naming_a_special_effect_group_is_not_offered():
    """"Fire" names no power a build records as Fire."""
    assert _dispel_offer(_fight(input="Fire")) == []


def test_a_characteristic_cannot_be_dispelled():
    """6E1 p.195: "Dispel cannot affect Characteristics"."""
    assert _dispel_offer(_fight(input="STR")) == []
