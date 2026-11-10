"""Two doctrine lines read the fight before they advise.

Plague (2026-11-10) fired at a dodging agent in the open nine times on
`sustained_fire`'s word ("every blocked shot chips the wall" --- there was no
wall) and made three group Presence Attacks on `presence_attack_demoralize`'s
(the last two did nothing). Doctrine stays advice; it must at least be true.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from test_tactics_name_the_kind_they_mean import _situation, _situation_with_cover

from kirby_combat.tactics.catalog.presence_attack_demoralize import PresenceAttackDemoralize
from kirby_combat.tactics.catalog.sustained_fire import SustainedFire


def test_sustained_fire_is_not_advised_against_men_in_the_open():
    assert not SustainedFire().applicable(_situation())


def test_sustained_fire_names_the_man_behind_cover():
    situation = _situation_with_cover()
    assert SustainedFire().applicable(situation)
    assert SustainedFire().execute(situation).steps[0].target_id == "mark"


class _Pre:
    def __init__(self, cid, pre):
        self.id = cid
        self.pre = pre

    def combat_stats(self):
        return self


def _shouts(*tiers_each):
    from types import SimpleNamespace

    from kirby_combat.session.events import ActionResolved, make_author_combatant

    log = [ActionResolved(
        id=str(uuid.uuid4()), session_id="s", sequence=i + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_combatant("plague"),
        declaration_event_id="",
        result_payload={"kind": "presence_attack_group", "effects": dict(tiers)})
        for i, tiers in enumerate(tiers_each)]
    return SimpleNamespace(event_log=log)


def _presence_situation(session):
    from kirby_combat.tactics.base import Situation

    return Situation(actor=_Pre("plague", 20), allies=[],
                     enemies=[_Pre("a1", 10), _Pre("a2", 10)], session=session)


def test_presence_attack_is_not_advised_once_his_last_did_nothing():
    """Peter, 2026-11-10: "if he sees a PRE attack doesnt work he's less
    likely to redo". Plague shouted, impressed them, shouted to no effect,
    and the doctrine went on advising a third (it waited for two duds)."""
    tactic = PresenceAttackDemoralize()
    assert tactic.applicable(_presence_situation(None))
    worked = _shouts({"a1": "no_effect", "a2": "no_effect"}, {"a1": "impressed", "a2": "no_effect"})
    assert tactic.applicable(_presence_situation(worked))
    dud = _shouts({"a1": "impressed", "a2": "impressed"}, {"a1": "no_effect", "a2": "no_effect"})
    assert not tactic.applicable(_presence_situation(dud))


def test_the_presence_line_states_the_books_tiers():
    text = PresenceAttackDemoralize.narrative_summary
    assert "OCV/DCV drops" not in text
    assert "half DCV" in text and "0 DCV" in text
