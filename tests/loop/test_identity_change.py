"""Out of costume he does not have what he bought for the costume.

6E1 p.388: "A character can only use a power with Only In Alternate Identity
('OIAID') while he's in an alternate identity." p.389: "the change must take
at least a Full Phase, if not longer (during which the character can do
nothing else)". p.272: Instant Change makes a change of form "a Zero Phase
Action".

THE DEFECT. `state.in_hero_id` gated Ravel's characteristics and nothing
else: as a civilian he fired the costumed Blast, wore the costumed Force
Field and flew. And nothing ever flipped it.

Ravel is the subject because nearly his whole sheet is OIAID: "String
Storm" (ENERGYBLAST), both Damage Reductions, two Force Fields, Flight.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import encounter_of, fighter          # tests/loop/conftest.py
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.identity import CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT
from kirby_combat.loop import run_phase
from kirby_combat.serialization import from_dict, to_dict
from kirby_combat.side import Side
from kirby_dice import RandomRoller
from tests.corpus import require_authored

STRING_STORM = "String Storm"


def _ravel(*, in_hero_id: bool) -> HeroCombatant:
    c = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    c = replace(c, side=Side.named("heroes"))
    c.state.in_hero_id = in_hero_id
    return c


class _Plays:
    """Changes identity when offered it (``change``), else fires String
    Storm when he has it, else dodges. Records Ravel's menus."""

    def __init__(self, *, change: bool):
        self.change = change
        self.menus: list[list] = []

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None) is not None:
            return situation.menu[0].action_id
        menu = situation.menu
        if situation.actor.id != "ravel":
            return next(a for a in menu if a.kind == "dodge").action_id
        self.menus.append(list(menu))
        if self.change:
            for a in menu:
                if a.kind in (CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT):
                    self.change = False
                    return a.action_id
        for a in menu:
            if a.kind == "attack" and a.power_name == STRING_STORM:
                return a.action_id
        return next(a for a in menu if a.kind == "dodge").action_id


def _storms(menu) -> list:
    return [a for a in menu if a.kind == "attack" and a.power_name == STRING_STORM]


def _until_ravel_acts(encounter, chooser, roller):
    while True:
        r = run_phase(encounter, chooser, roller=roller, on_unresolvable="raise")
        encounter = r.encounter
        if r.actor_id == "ravel":
            return r


def test_a_civilian_cannot_fire_the_costumed_blast_and_can_after_the_change():
    """THE SEAM: offered, resolved as a Full Phase, folded, and the next
    Phase's menu reads it."""
    enc = encounter_of(_ravel(in_hero_id=False),
                       fighter("thug", side=Side.named("thugs"), dex=5))
    chooser = _Plays(change=True)
    roller = RandomRoller(seed=3)

    first = _until_ravel_acts(enc, chooser, roller)
    assert _storms(chooser.menus[0]) == [], "a civilian fired String Storm"
    assert [a.kind for a in chooser.menus[0]
            if a.kind in (CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT)] == [CHANGE_IDENTITY]
    assert first.kind == CHANGE_IDENTITY
    changed = [e for e in first.events if e.kind == "IdentityChanged"]
    assert len(changed) == 1 and changed[0].in_hero_id is True
    assert not changed[0].zero_phase
    # A Full Phase: the change is all he did (6E1 p.389).
    assert [e.reason for e in first.events
            if e.kind == "PhaseSpent" and e.combatant_id == "ravel"] == ["acted"]
    assert first.session.combatants["ravel"].state.in_hero_id is True

    second = _until_ravel_acts(first.encounter, chooser, roller)
    assert _storms(chooser.menus[1]), "in costume and still no String Storm"
    assert second.kind == "attack"


def test_out_of_costume_he_owns_nothing_bought_for_it():
    hero, civilian = _ravel(in_hero_id=True), _ravel(in_hero_id=False)
    assert STRING_STORM in [a.name for a in hero.attacks]
    assert civilian.attacks == []
    assert hero.defenses and civilian.defenses == []
    assert hero.combat_stats().rpd > 0 and civilian.combat_stats().rpd == 0
    assert any(m.mode == "flight" for m in hero.movement_view())
    assert not any(m.mode == "flight" for m in civilian.movement_view())
    assert hero.framework_view() and civilian.framework_view() == []


def test_a_character_with_one_identity_is_not_offered_a_change():
    from kirby_combat.enumeration import enumerate_actions

    menu = enumerate_actions(fighter("a"), [fighter("b")])
    assert not [a for a in menu if a.kind in (CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT)]


def test_the_change_is_excluded_from_a_half_phase():
    from kirby_combat.pre_attacks.in_the_phase import HALF_PHASE_EXCLUDED

    assert CHANGE_IDENTITY in HALF_PHASE_EXCLUDED
    assert CHANGE_IDENTITY_INSTANT not in HALF_PHASE_EXCLUDED


@pytest.mark.parametrize("start", [True, False])
def test_a_rebuilt_ravel_changes_costume_the_way_the_live_one_does(start):
    """kirby-api rebuilds a fight from `to_dict` snapshots and replays the
    log, so the snapshot records BOTH identities and `IdentityChanged`
    flips a rebuilt combatant into the other one."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import IdentityChanged, make_author_engine

    live = _ravel(in_hero_id=start)
    rebuilt = from_dict(to_dict(live))
    assert rebuilt.has_alternate_identity()

    enc = encounter_of(rebuilt, fighter("thug", side=Side.named("thugs")))
    s = enc.sessions[0]
    s = apply_event(s, IdentityChanged(
        id="flip", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_engine(),
        combatant_id="ravel", in_hero_id=not start, zero_phase=False,
    ))
    flipped_rebuilt = s.combatants["ravel"]
    flipped_live = _ravel(in_hero_id=not start)

    assert flipped_rebuilt.attacks == flipped_live.attacks
    assert flipped_rebuilt.defenses == flipped_live.defenses
    assert flipped_rebuilt.movement_view() == flipped_live.movement_view()
    assert flipped_rebuilt.combat_stats() == flipped_live.combat_stats()


def _ravel_with_instant_change() -> HeroCombatant:
    """Ravel plus the Cosmetic Transform 6E1 p.307 names Instant Change, as
    eight corpus characters carry it."""
    from kirby_cost.io.build_json import build_from_json
    from tests.corpus import require_authored_doc

    doc = require_authored_doc("Ravel")
    doc = dict(doc, powers=list(doc["powers"]) + [{
        "id": "ic1", "xmlid": "TRANSFORM", "option_id": "COSMETIC",
        "name": "Instant Change", "levels": 1, "base_cost": 0.0,
        "alias": "Transform", "input": "any clothing to costume; reverses at will",
    }])
    c = HeroCombatant.from_build(build_from_json(doc), id="ravel")
    c = replace(c, side=Side.named("heroes"))
    c.state.in_hero_id = False
    return c


def test_with_instant_change_the_change_takes_no_time_and_he_fires_in_the_same_phase():
    enc = encounter_of(_ravel_with_instant_change(),
                       fighter("thug", side=Side.named("thugs"), dex=5))
    chooser = _Plays(change=True)
    roller = RandomRoller(seed=3)

    first = _until_ravel_acts(enc, chooser, roller)
    assert first.kind == CHANGE_IDENTITY_INSTANT
    assert [e.zero_phase for e in first.events if e.kind == "IdentityChanged"] == [True]
    assert not [e for e in first.events
                if e.kind == "PhaseSpent" and e.combatant_id == "ravel"]

    # The SAME Phase comes back to him: no second change, String Storm on it.
    again = run_phase(first.encounter, chooser, roller=roller,
                      on_unresolvable="raise")
    assert again.actor_id == "ravel"
    assert not [a for a in chooser.menus[-1]
                if a.kind in (CHANGE_IDENTITY, CHANGE_IDENTITY_INSTANT)]
    assert again.kind == "attack" and _storms(chooser.menus[-1])
