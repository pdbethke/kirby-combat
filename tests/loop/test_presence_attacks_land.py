"""A Presence Attack somebody CHOSE now does what the book says it does.

Ported from the parked consumer's driver (deleted in kirby-api 70ad60f).
On origin/main every behaviour pinned here was missing:

* the resolvers rolled the attack and logged the tier, and never applied it
  (6E2 p.139), so `can_act`, the DCV seam and the hesitation saw nothing;
* the attack spent the Phase, though 6E2 p.25 rates it No Time;
* `yields_to_id` (impressed, "the attacker may act before him") and
  `PresenceTier.half_phase` (very impressed, "only a Half Phase Action")
  were folded and never read;
* PRE Defense was taken off the dice, which 6E does not do (6E1 p.178).

Every seam test drives `run_phase(on_unresolvable="raise")` or
`resolve_chosen`, the doors a consumer uses.
"""
from __future__ import annotations

from types import SimpleNamespace

from conftest import blast                       # tests/loop/conftest.py
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.encounter import Encounter
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import run_phase
from kirby_combat.action_time import FULL_PHASE_KINDS
from kirby_combat.pre_attacks.landing import pre_defense_of
from kirby_combat.pre_attacks.presence_effects import PresenceEffects, can_act
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.effects import presence_state
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


class Sixes:
    """Every die a six: a Presence Attack whose result is arithmetic."""

    def roll_dice(self, n: int) -> list[int]:
        return [6] * n


class Ones:
    def roll_dice(self, n: int) -> list[int]:
        return [1] * n


def _man(id: str, side: str, *, pre: int = 15, dex: int = 20, spd: int = 4):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=6, omcv=5, dmcv=5,
        spd=spd, dex=dex, ego=15, str_=15, con=18, pre=pre, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        side=Side.named(side), attacks=[blast(f"{id}-eb")],
    )


def _encounter(*men, segment: int = 12) -> Encounter:
    session = CombatSession.create(
        id="s", combatants=list(men), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    return Encounter(id="e", turn=1, segment=segment, sessions=[session])


class Picks:
    """Takes the first offer of the wanted kind, else the first offer; and
    remembers every menu it was shown, by actor."""

    def __init__(self, *kinds: str) -> None:
        self.kinds = kinds
        self.menus: list[tuple[str, list]] = []

    def choose(self, situation) -> str:
        # Out of turn (an Abort, a Held Action: `loop/reactions.py`) is not
        # his Phase menu: decline, and do not record it.
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.menus.append((situation.actor.id, list(situation.menu)))
        for kind in self.kinds:
            for offer in situation.menu:
                if offer.kind == kind:
                    return offer.action_id
        return situation.ordered_menu[0].action_id


def _kinds(events):
    return [getattr(e, "kind", "") for e in events]


# ---- it lands ---------------------------------------------------------------

def test_a_chosen_presence_attack_is_applied_to_its_target():
    """PRE 60 rolls 12d6, -1d6 in combat (6E2 p.138): eleven sixes are 66
    against PRE 10, which is PRE+56 --- overwhelmed. On origin/main nothing
    was applied and Virgil could act."""
    enc = _encounter(_man("tom", "a", pre=60, dex=30), _man("virgil", "b", pre=10))
    result = run_phase(enc, Picks("presence_attack"), roller=Sixes(),
                       on_unresolvable="raise")
    assert result.kind == "presence_attack"
    assert result.result.effective_dice == 11, "PRE/5 dice, -1d6 in combat"
    applied = [e for e in result.events if e.kind == "PresenceApplied"]
    assert [(e.target_id, e.tier) for e in applied] == [("virgil", "overwhelmed")]
    session = result.session
    assert presence_state(session, "virgil").tier == "overwhelmed"
    assert can_act(session, "virgil") is False


def test_a_group_presence_attack_lands_on_every_enemy():
    enc = _encounter(
        _man("tom", "a", pre=60, dex=30),
        _man("virgil", "b", pre=10), _man("wyatt", "b", pre=40),
    )
    result = run_phase(enc, Picks("presence_attack_group"), roller=Sixes(),
                       on_unresolvable="raise")
    assert result.kind == "presence_attack_group"
    tiers = {e.target_id: e.tier for e in result.events if e.kind == "PresenceApplied"}
    # One roll, 66, judged against each PRE (6E2 p.137): +56 and +26.
    assert tiers == {"virgil": "overwhelmed", "wyatt": "awed"}


def test_a_stunned_target_is_immune():
    """6E2 p.106. The resolver never passed `target_stunned`."""
    from kirby_combat.enumeration import LegalAction
    import kirby_combat.statuses as statuses

    enc = _encounter(_man("tom", "a", pre=60), _man("virgil", "b", pre=10))
    session = _stun(enc.sessions[0], "virgil")
    assert statuses.stunned_or_recovering_for(session, "virgil")
    offer = LegalAction(action_id="presence_attack:virgil", kind="presence_attack",
                        target_id="virgil", power_xmlid=None, power_name=None,
                        summary="")
    resolved = resolve_chosen(session, session.combatants["tom"], offer,
                              template=session.template, roller=Sixes())
    assert resolved.result.effect == "no_effect"
    assert not [e for e in resolved.events if e.kind == "PresenceApplied"]


def _stun(session, combatant_id):
    """Stun him the way an attack does (tests/loop/test_a_stunned_man_takes_no_action.py)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_engine

    return apply_event(session, ActionResolved(
        id="stun", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=session.event_log[-1].timestamp, author=make_author_engine(),
        declaration_event_id="",
        result_payload={"kind": "attack", "target_id": combatant_id,
                        "status_changes": ["Stunned"]},
    ))


# ---- No Time ----------------------------------------------------------------

def test_a_presence_attack_does_not_spend_the_phase():
    """6E2 p.25: "Make a Presence Attack --- No Time". Then he acts."""
    enc = _encounter(_man("tom", "a", pre=20, dex=30), _man("virgil", "b", pre=30))
    chooser = Picks("presence_attack", "attack")
    first = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise")
    assert first.kind == "presence_attack"
    assert not [e for e in first.events
                if e.kind == "PhaseSpent" and e.combatant_id == "tom"]

    second = run_phase(first.encounter, chooser, roller=Ones(),
                       on_unresolvable="raise")
    assert second.actor_id == "tom", "the same Phase came back to him"
    assert second.kind == "attack"
    shown = chooser.menus[-1][1]
    assert not [a for a in shown if a.kind.startswith("presence_attack")], (
        "one free Presence Attack a Phase (ruling)"
    )
    assert [e for e in second.events
            if e.kind == "PhaseSpent" and e.combatant_id == "tom"]


# ---- impressed, very impressed --------------------------------------------

def _shouted_at(enc, tier):
    session, _ = PresenceEffects.apply(
        enc.sessions[0], target_id="virgil", attacker_id="tom", tier=tier,
    )
    return Encounter(id=enc.id, turn=enc.turn, segment=enc.segment, sessions=[session])


def test_an_impressed_man_lets_the_attacker_act_first():
    """6E2 p.139. Virgil (DEX 30) would act before Tom (DEX 10)."""
    enc = _shouted_at(_encounter(_man("tom", "a", dex=10), _man("virgil", "b", dex=30)),
                      "impressed")
    chooser = Picks("attack")
    order = []
    for _ in range(3):
        result = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise")
        enc = result.encounter
        order.append((result.actor_id, result.kind))
    assert order[0] == ("virgil", None), order
    assert "PresenceYielded" in _kinds(enc.sessions[0].event_log)
    assert order[1] == ("tom", "attack")
    assert order[2] == ("virgil", "attack"), "and then he acts, once"


def test_without_the_hesitation_he_goes_first():
    """The control: no shout, DEX order."""
    enc = _encounter(_man("tom", "a", dex=10), _man("virgil", "b", dex=30))
    result = run_phase(enc, Picks("attack"), roller=Ones(), on_unresolvable="raise")
    assert (result.actor_id, result.kind) == ("virgil", "attack")


def test_a_very_impressed_man_takes_only_a_half_phase_action():
    """6E2 p.139, PRE+10. Set and Rapid Fire are Full Phase; an attack is not."""
    enc = _shouted_at(_encounter(_man("tom", "a", dex=10), _man("virgil", "b", dex=30)),
                      "very_impressed")
    chooser = Picks("attack")
    for _ in range(4):
        result = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise")
        enc = result.encounter
    first = next({a.kind for a in menu} for actor, menu in chooser.menus
                 if actor == "virgil")
    assert "attack" in first
    assert not (first & FULL_PHASE_KINDS), first


def test_the_half_phase_limit_lasts_one_phase():
    enc = _shouted_at(_encounter(_man("tom", "a", dex=10), _man("virgil", "b", dex=30)),
                      "very_impressed")
    chooser = Picks("attack")
    for _ in range(12):
        result = run_phase(enc, chooser, roller=Ones(), on_unresolvable="raise")
        enc = result.encounter
    virgil_menus = [{a.kind for a in m} for actor, m in chooser.menus if actor == "virgil"]
    assert len(virgil_menus) >= 2
    assert "set" not in virgil_menus[0]
    assert "set" in virgil_menus[1], "his NEXT Phase only (6E2 p.139)"


# ---- PRE Defense --------------------------------------------------------------

def _limited_pre(levels: int, *, counted: bool):
    return SimpleNamespace(
        xmlid="PRE", levels=levels, affect_total=counted,
        assigned_modifiers=[SimpleNamespace(
            xmlid="LIMITEDPOWER", alias="Only To Protect Against Presence Attacks")],
    )


def test_pre_defense_raises_the_bar_and_takes_no_dice():
    """6E1 p.178's Presence Defense is "+20 PRE; Only To Protect Against
    Presence Attacks". Bought outside the total, it adds when resisting."""
    from kirby_combat.enumeration import LegalAction

    virgil = _man("virgil", "b", pre=10)
    virgil.hero.powers = [_limited_pre(20, counted=False)]
    assert pre_defense_of(virgil) == 20
    enc = _encounter(_man("tom", "a", pre=30), virgil)
    session = enc.sessions[0]
    offer = LegalAction(action_id="presence_attack:virgil", kind="presence_attack",
                        target_id="virgil", power_xmlid=None, power_name=None,
                        summary="")
    resolved = resolve_chosen(session, session.combatants["tom"], offer,
                              template=session.template, roller=Sixes())
    # 6d6 -1d6 = 5 sixes = 30, all rolled; against PRE 10 + 20 = 30.
    assert resolved.result.effective_dice == 5
    assert resolved.result.resisting_pre == 30
    assert resolved.result.effect == "impressed"


def test_pre_defense_already_in_his_total_is_not_counted_twice():
    virgil = _man("virgil", "b", pre=30)
    virgil.hero.powers = [_limited_pre(20, counted=True)]
    assert pre_defense_of(virgil) == 0
