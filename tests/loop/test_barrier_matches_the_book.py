"""A Barrier, as 6E1 p.171-173 has it.

  * p.172: "To place a Barrier in the desired Area at Range, the character
    must succeed with an Attack Roll against DCV 3" --- with the Range
    Modifier (6E2 p.40).
  * p.172: "Barrier is an Instant Power, so a character only pays END when
    he first creates a Barrier. A Barrier, once created, is a physical
    object that remains in existence until destroyed".
  * Nothing limits how many he raises; the one-wall guard this replaced had
    no page behind it (and looked for walls among the constructs, where a
    raised wall never is).

Scene: the caster (DEX 30, OCV 9) at the origin, the mark 20m out; the wall
goes 2m short of the mark, 18m away: -4 (6E2 p.40), so 9 + 11 - 3 - 4 = 13-.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace as NS

from shaped import TEMPLATE, Dice
from test_kept_up import _charges, _fight, _menu, _then, _until
from test_offered_means_resolves import _Power

COUNTED = replace(TEMPLATE, manage_endurance=True, manage_endurance_npc=True)


def _wall(**extra):
    power = _Power("FORCEWALL", 6, id="src-FORCEWALL")
    for k, v in extra.items():
        setattr(power, k, v)
    return power


def _walls(enc):
    return [w for w in enc.sessions[0].scene.walls if w.id.startswith("force-wall")]


def _raise(enc, roller):
    enc, r = _until(enc, _then("force_wall"), roller=roller)
    assert r.kind == "force_wall"
    return enc


def _row(enc):
    return [e.result_payload for e in enc.sessions[0].event_log
            if e.kind == "ActionResolved"
            and (e.result_payload or {}).get("kind") == "force_wall"][-1]


def test_a_hit_raises_it_at_range_and_it_costs_end():
    enc = _raise(_fight(_wall(), template=COUNTED), Dice(face=3))   # 9 vs 13-
    row = _row(enc)
    assert row["at_range"] and row["hit"] and row["target_number"] == 13
    assert row["range_modifier"] == -4
    assert len(_walls(enc)) == 1
    assert enc.sessions[0].combatants["caster"].state.current_end < 40


def test_a_miss_raises_nothing_but_the_end_is_spent():
    enc = _raise(_fight(_wall(), template=COUNTED), Dice(face=6))   # 18 vs 13-
    assert not _row(enc)["hit"]
    assert _walls(enc) == []
    assert enc.sessions[0].combatants["caster"].state.current_end < 40


def test_it_stays_and_he_may_raise_another():
    enc = _raise(_fight(_wall(), template=COUNTED, rec=0), Dice(face=3))
    end_after = enc.sessions[0].combatants["caster"].state.current_end
    assert "force_wall" in {a.kind for a in _menu(enc)}
    enc, _ = _until(enc, _then(), roller=Dice(face=3))              # he Dodges
    assert len(_walls(enc)) == 1, "an Instant Barrier stays"
    assert enc.sessions[0].combatants["caster"].state.current_end == end_after, \
        "and costs nothing to keep"


def test_charges_run_out():
    power = _wall(end_usage=0, assigned_modifiers=[_charges(1)])
    enc = _raise(_fight(power), Dice(face=3))
    assert "force_wall" not in {a.kind for a in _menu(enc)}


def test_one_bought_to_be_maintained_is_not_offered():
    """p.172 / p.376: Costs Endurance (to maintain) makes it a thing kept up
    by END and lost to a Stun --- not built, so not offered."""
    power = _wall(assigned_modifiers=[NS(xmlid="COSTSEND", option_id=None,
                                         assigned_adders=[], private=False)])
    assert "force_wall" not in {a.kind for a in _menu(_fight(power))}
