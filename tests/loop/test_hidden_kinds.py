"""The eight kinds a literal-only scan could not see.

`enumerate_actions` builds three of its offers with a COMPUTED kind:

    kind = "sweep" if is_hth else "multiple_attack"     # 6E2 p.56 / p.71
    for kind, label in _INTERACTION_SKILL_XMLIDS...     # charm, persuasion, ...
    for kind, rate, extra in (("climb", ...), ("climb_fast", ...))

So a scan matching `kind="literal"` counted 51 where the real total is 59,
and the test asserting "every offered kind has a resolver" passed against
that incomplete set for several commits.

IT SURFACED IN A REAL FIGHT, not in the suite. The O.K. Corral -- eight men,
historically armed from the HSEG prefabs -- spent 27 of 31 Phases picking
`multiple_attack` and having every one skipped, in a fight the count said
was fully covered. `ALL_ACTION_KINDS` is now declared by hand in
enumeration.py so the check cannot be fooled the same way twice.
"""
from __future__ import annotations

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import ALL_ACTION_KINDS, LegalAction
from kirby_combat.loop import registered_kinds
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()
HIDDEN = ("sweep", "multiple_attack", "climb", "climb_fast",
          "charm", "persuasion", "conversation", "trading")


def _session():
    return CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=8),
        combatants=[
            fighter("actor", side=Side.named("a"), dex=20),
            # TWO enemies: a Multiple Attack spreads its shots across
            # targets, so with one enemy there is only one shot to take.
            fighter("mark", side=Side.named("b"), dex=15),
            fighter("other", side=Side.named("b"), dex=14),
        ],
    ).start()


def _act(kind: str, **kw) -> LegalAction:
    return LegalAction(
        action_id=kw.pop("action_id", f"{kind}:mark"), kind=kind,
        target_id=kw.pop("target_id", "mark"),
        power_xmlid=None, power_name=None, summary=kind, **kw,
    )


def _resolve(action: LegalAction):
    session = _session()
    return resolve_chosen(
        session, session.combatants["actor"], action,
        template=TEMPLATE, roller=RandomRoller(seed=8),
    )


# ---- All eight are declared and registered ----

@pytest.mark.parametrize("kind", HIDDEN)
def test_the_hidden_kind_is_declared(kind):
    assert kind in ALL_ACTION_KINDS


@pytest.mark.parametrize("kind", HIDDEN)
def test_the_hidden_kind_is_registered(kind):
    assert kind in registered_kinds()


# ---- Sweep and Multiple Attack ----

@pytest.mark.parametrize("kind", ["sweep", "multiple_attack"])
def test_a_multi_target_attack_widens_the_ocv_penalty(kind):
    """6E2 p.56 / p.71 -- each successive target is at a worse OCV, and the
    whole Phase is spent at half DCV."""
    resolved = _resolve(_act(kind, _attack_view=blast("eb", dice=4)))
    payload = resolved.session.event_log[-1].result_payload
    ocvs = payload["per_target_ocv"]
    assert len(ocvs) == 2
    assert ocvs[0] > ocvs[1]
    assert payload["dcv_factor"] == 0.5


@pytest.mark.parametrize("kind", ["sweep", "multiple_attack"])
def test_a_multi_target_attack_ACTUALLY_ATTACKS(kind):
    """THE DEFECT THIS PINS. `Sweep.compute` and `MultipleAttack.compute`
    return the OCV LADDER -- they are modifier calculators, not resolvers.
    The first version of this resolver recorded that ladder and stopped, so
    a Multiple Attack hit NOBODY: the menu promised "hit all N enemies",
    the Phase was spent, and no damage moved.

    Found by running the O.K. Corral to a finish: the model picked
    `multiple_attack` in 139 of 143 Phases and the fight could never end.
    A test asserting the OCVs were recorded passed the whole time, which is
    why this one asserts damage instead."""
    session = _session()
    before = {c.id: c.state.current_stun for c in session.combatants.values()}
    resolved = resolve_chosen(
        session, session.combatants["actor"],
        _act(kind, _attack_view=blast("eb", dice=10)),
        template=TEMPLATE, roller=RandomRoller(seed=3),
    )
    payload = resolved.session.event_log[-1].result_payload
    assert payload["hits"] >= 1, "no shot landed across two targets"
    hurt = [
        c.id for c in resolved.session.combatants.values()
        if c.state.current_stun < before[c.id]
    ]
    assert hurt, "the Phase was spent and nobody took damage"


def test_sweep_and_multiple_attack_share_their_arithmetic():
    """`Sweep.compute` delegates to `MultipleAttack.compute`. They are two
    names because the book has two -- a Sweep is hand-to-hand, which
    enumeration has already gated on Reach."""
    a = _resolve(_act("sweep")).session.event_log[-1].result_payload
    b = _resolve(_act("multiple_attack")).session.event_log[-1].result_payload
    assert a["per_target_ocv"] == b["per_target_ocv"]


# ---- Climbing ----

@pytest.mark.parametrize("kind", ["climb", "climb_fast"])
def test_climbing_reports_the_6e2_modifiers(kind):
    """6E1 p.70 halves OCV *and* DCV; 6E2 p.48-49 halves DCV only and takes
    -2 DC. `climbing.py` resolves that contradiction in favour of 6E2, and
    this reads it rather than restating it."""
    resolved = _resolve(_act(kind, action_id=f"{kind}:wall-1", target_id=None))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["wall_id"] == "wall-1"
    assert payload["dcv_delta"] == -1
    assert payload["hurried"] is (kind == "climb_fast")


def test_climbing_without_a_wall_refuses():
    with pytest.raises(UnresolvableAction, match="climb"):
        _resolve(_act("climb", action_id="climb", target_id=None))


# ---- Interaction skills: sub-project B's fourth rule ----

@pytest.mark.parametrize("kind", ["charm", "persuasion", "conversation", "trading"])
def test_an_interaction_skill_is_a_contested_roll(kind):
    """Sub-project B named four rules with no engine home: trip, disarm,
    spread and INTERACTION. The first three were wired earlier; this is the
    last, and it was invisible to the count because enumeration builds
    these four offers from a loop variable."""
    resolved = _resolve(_act(kind))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["skill_target"] == 9 + 15 // 5      # 6E1 p.58, PRE-based
    assert payload["resistance"] == 9 + 15 // 5        # the target's EGO
    assert 3 <= payload["roll"] <= 18
    assert "margin" in payload, "the margin is the outcome, not a bare bool"


def test_the_interaction_rule_is_written_once_for_all_four():
    """One resolver, four kinds -- the rule is the same and only the Skill
    named changes."""
    from kirby_combat.loop.resolvers import INTERACTION_SKILLS

    assert set(INTERACTION_SKILLS) == {"charm", "persuasion", "conversation", "trading"}
