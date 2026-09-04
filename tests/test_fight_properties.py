"""Randomized fights: the same seed replays, and a fight ends.

**Why these can exist now.** A randomized test is only worth running if a
failure can be reproduced. Until `kirby-dice` gave `RandomRoller` a seed it
could hand back, an unseeded roller drew unrecoverable OS entropy: a red
build here would have told you a fight broke and given you no way back to
it. `RandomRoller().seed` is what makes the loop closeable, so every failure
message below prints the seed that produced it.

**An honest limit, stated rather than papered over.** The engine does NOT
apply damage to combatant state. `resolve_attack_in_session` computes and
records `stun_dealt` but leaves `current_stun` untouched — kirby-api's
driver subtracts it by hand (`llm_driver.py` ~2886 and ~6551), and applies
Recovery by hand too. So `_apply_damage` below is this harness mirroring the
wrapper, not the engine's own ledger, and the termination property is only
as good as that mirror. What it genuinely exercises is the RESOLUTION path —
thousands of real attacks through `resolve_attack`, the recording wrapper
and the event log — which is where the interesting behaviour lives.

These are deliberately the two cheapest properties. Determinism comes first
because every other property worth writing depends on it being true.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

#: How many phases a fight may take before we call it stuck. Two fighters
#: throwing 8d6 at 2 rPD have an expected ~26 STUN a hit against 40 STUN, so
#: a normal fight ends in a handful of exchanges. 200 is far past "slow".
PHASE_CAP = 200

#: Seeds per property. Enough to be worth calling randomized; small enough
#: that the file stays under a second.
SEEDS = range(300)

_ATTACK = AttackPower(
    xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=8, half_die=False,
    plus_one=False, damage_type="normal", defense_type="ed", range_m=200,
    uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
    increased_stun_mult=0,
)


def _fighter(id_: str):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=6, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=2, ed=2, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=40,
        current_stun=40, current_body=15, current_end=40,
        attacks=[_ATTACK],
    )


def _apply_damage(target, result) -> None:
    """What kirby-api's driver does after a resolved attack. See module doc:
    this is the wrapper's job today, not the engine's."""
    if result.hit:
        target.state.current_stun -= result.stun_dealt
        target.state.current_body -= result.body_dealt


def _run_fight(seed: int) -> dict:
    """One fight, driven entirely by `seed`. Returns what it did."""
    roller = RandomRoller(seed=seed)
    a, b = _fighter("a"), _fighter("b")
    session = CombatSession.create(
        id="fight", combatants=[a, b], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller,
    ).start()

    phases = 0
    attacker, target = a, b
    while phases < PHASE_CAP:
        if target.state.current_stun <= 0 or attacker.state.current_stun <= 0:
            break
        attack = AttackInput(
            attacker=attacker, target=target, power=_ATTACK,
            distance_m=0, aim=None,
            dice=DiceValues(
                to_hit=roller.roll_dice(3),
                damage=roller.roll_dice(_ATTACK.damage_dice),
            ),
        )
        session, result = resolve_attack_in_session(session, attack, session.template)
        _apply_damage(target, result)
        phases += 1
        attacker, target = target, attacker

    return {
        "seed": roller.seed,
        "phases": phases,
        "over": a.state.current_stun <= 0 or b.state.current_stun <= 0,
        "log": [(e.kind, repr(getattr(e, "result_payload", None))) for e in session.event_log],
        "final": (a.state.current_stun, a.state.current_body,
                  b.state.current_stun, b.state.current_body),
    }


# ---------------------------------------------------------------------------
# Determinism -- the property everything else rests on
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1234, 99999])
def test_the_same_seed_replays_the_same_fight(seed):
    """Record the seed, get the fight back: same event log, same final stats."""
    first, second = _run_fight(seed), _run_fight(seed)
    assert first["log"] == second["log"], f"event logs diverged for seed {seed}"
    assert first["final"] == second["final"], f"final state diverged for seed {seed}"
    assert first["phases"] == second["phases"]


def test_different_seeds_actually_produce_different_fights():
    """Guards the guard. If every seed produced the same fight, the
    determinism test above would pass while proving nothing."""
    logs = {tuple(_run_fight(s)["log"]) for s in range(20)}
    assert len(logs) > 1, "every seed produced an identical fight"


def test_a_fight_is_reproducible_from_an_unseeded_roller_s_own_seed():
    """The production shape: nobody chose the seed, and the fight still
    replays — which is the whole point of recording it."""
    discovered = RandomRoller().seed
    assert _run_fight(discovered)["log"] == _run_fight(discovered)["log"]


# ---------------------------------------------------------------------------
# Termination
# ---------------------------------------------------------------------------

def test_every_fight_terminates():
    """Across 300 seeded fights, each one ends — nobody swings forever."""
    stuck = [r["seed"] for r in (_run_fight(s) for s in SEEDS) if not r["over"]]
    assert stuck == [], f"fights that hit the {PHASE_CAP}-phase cap, by seed: {stuck}"


def test_the_cap_is_not_doing_the_work():
    """Guards the guard. If fights ended AT the cap the test above would be
    asserting nothing but the cap's existence, so pin the real distribution:
    two 8d6 blasters resolve this in single digits, not hundreds."""
    lengths = [_run_fight(s)["phases"] for s in SEEDS]
    assert max(lengths) < PHASE_CAP // 4, f"longest fight took {max(lengths)} phases"
    assert max(lengths) >= 2, "every fight ended in one blow; the test is trivial"
