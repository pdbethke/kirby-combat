"""Miss one, miss the rest --- 6E2 p.73's other half.

The page charges a Multiple Attack twice. `tests/test_multiple_attack_raw.py`
covers the first charge, the flat (N-1) x -2 on every roll. This is the
second: miss ANY Attack Roll and every remaining attack in the sequence
automatically misses.

It lives beside the loop tests because it drives the real resolver ---
asking "what happens on a miss" is a question about the sequence, not
about the arithmetic, and the only honest way to ask it is to make a
shot miss and count what follows.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


class _Rigged(RandomRoller):
    """Hands out dictated to-hit totals in order; everything else random.

    "A 3d6 request is a to-hit roll" WAS the rule here, and it stopped
    being true the day `resolvers._attack_dice` began rolling a Hit
    Location --- also 3d6, also once per attack (6E2 p.110 step 1). The
    queue was then consumed twice per shot, so a sequence dictated to
    hit, hit, hit spent its second total on a location roll and missed.

    So the double now tracks the attack, not the die count. One attack
    draws to-hit 3d6, damage, location 3d6, then the STUN Multiplier
    1/2d6 (6E2 p.100). The single-die draw is the boundary: it re-arms
    the queue for the next shot, and only the first 3d6 after it is
    treated as the to-hit.
    """

    def __init__(self, totals):
        super().__init__(seed=1)
        self._to_hit = list(totals)
        self._armed = True

    def roll_dice(self, n):
        if n == 1:
            self._armed = True                  # end of one attack's dice
            return super().roll_dice(n)
        if n == 3 and self._armed and self._to_hit:
            self._armed = False
            base, rem = divmod(self._to_hit.pop(0), 3)
            return [base + (1 if i < rem else 0) for i in range(3)]
        return super().roll_dice(n)


def _sequence(to_hit_totals, enemies: int = 3):
    template = CombatTemplate.default_6e_superheroic()
    session = CombatSession.create(
        id="s", scene=None, template=template, dice_roller=RandomRoller(seed=8),
        combatants=[fighter("actor", side=Side.named("a"), dex=20)]
        + [fighter(f"mark{i}", side=Side.named("b"), dex=10)
           for i in range(enemies)],
    ).start()
    action = LegalAction(
        action_id="multiple_attack:self:all", kind="multiple_attack",
        target_id=None, power_xmlid=None, power_name=None,
        summary="multiple attack",
    )
    return resolve_chosen(session, session.combatants["actor"], action,
                          template=template, roller=_Rigged(to_hit_totals))


def test_every_shot_is_taken_when_none_miss():
    """Three enemies, three hits: three shots resolved."""
    resolved = _sequence([3, 3, 3])
    assert len(resolved.result) == 3
    assert all(r.hit for _t, r in resolved.result)


def test_a_miss_stops_the_sequence():
    """The page works exactly this: a character attacking three targets
    hits the first, misses the second, and does not get to attack the
    third at all. Two rolls happen, not three."""
    resolved = _sequence([3, 18, 3])
    assert len(resolved.result) == 2
    assert [r.hit for _t, r in resolved.result] == [True, False]


def test_missing_the_first_shot_ends_it_immediately():
    """Nothing after the first roll is taken."""
    resolved = _sequence([18, 3, 3])
    assert len(resolved.result) == 1
    assert not resolved.result[0][1].hit


def test_the_record_says_how_many_shots_were_actually_taken():
    """`target_ids` names everyone the maneuver was declared against, so
    the count of shots RESOLVED has to be recorded separately or a reader
    cannot tell a stopped sequence from a completed one."""
    resolved = _sequence([3, 18, 3])
    payload = next(
        (e.result_payload for e in reversed(resolved.events)
         if getattr(e, "result_payload", None)
         and e.result_payload.get("kind") == "multiple_attack"),
        None,
    )
    assert payload is not None, "no multiple_attack outcome recorded"
    assert payload["shots_taken"] == 2
    assert len(payload["target_ids"]) == 3
