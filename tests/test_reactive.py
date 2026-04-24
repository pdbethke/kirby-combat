"""Reactive defenses: Dodge, Block, Abort."""
import pytest
from datetime import datetime, timezone

from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.reactive.abort import is_aborting, mark_aborting
from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.actions.reactive.block import Block, BlockResult


def _c(id_: str, ocv: int = 8, dcv: int = 8, dex: int = 20) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=ocv, dcv=dcv, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("alice"), _c("bob")],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- Abort helpers -----------------------------------------------------------

def test_is_aborting_false_by_default():
    s = _session()
    assert is_aborting(s, "alice") is False


def test_mark_aborting_adds_to_set_and_returns_event():
    s = _session()
    s2, evt = mark_aborting(s, "alice", to_action="dodge")
    assert evt.combatant_id == "alice"
    assert evt.to_action == "dodge"
    assert is_aborting(s2, "alice") is True
    assert is_aborting(s, "alice") is False   # original unchanged


def test_mark_aborting_raises_if_already_aborted():
    s = _session()
    s2, _ = mark_aborting(s, "alice", to_action="dodge")
    with pytest.raises(ValueError, match="already aborted"):
        mark_aborting(s2, "alice", to_action="block")


# ---- Dodge -------------------------------------------------------------------

def test_dodge_declare_flags_combatant_aborted():
    s = _session()
    s2, evt = Dodge.declare(s, "alice")
    assert evt.to_action == "dodge"
    assert is_aborting(s2, "alice") is True


def test_dodge_dcv_bonus_is_3_when_active():
    s = _session()
    s2, _ = Dodge.declare(s, "alice")
    assert Dodge.dcv_bonus(s2, "alice") == 3


def test_dodge_dcv_bonus_is_0_when_not_active():
    s = _session()
    assert Dodge.dcv_bonus(s, "alice") == 0


# ---- Block -------------------------------------------------------------------

def test_block_declare_flags_combatant_aborted():
    s = _session()
    s2, evt = Block.declare(s, "alice")
    assert evt.to_action == "block"
    assert is_aborting(s2, "alice") is True


def test_block_resolve_success_when_blocker_higher_margin():
    # Attacker OCV 8, rolls [3,4,3]=10 → margin 8+11-10=9
    # Blocker OCV 10, rolls [3,3,3]=9 → margin 10+11-9=12
    # Blocker margin > attacker margin → block succeeds
    result = Block.resolve(
        attacker_ocv=8, attacker_dice=[3, 4, 3],
        blocker_ocv=10, blocker_dice=[3, 3, 3],
    )
    assert isinstance(result, BlockResult)
    assert result.success is True
    assert result.attacker_roll == 10
    assert result.blocker_roll == 9


def test_block_resolve_failure_when_attacker_higher_margin():
    # Attacker OCV 10, rolls [3,3,3]=9 → margin 10+11-9=12
    # Blocker OCV 8, rolls [4,4,4]=12 → margin 8+11-12=7
    # Attacker margin > blocker margin → block fails
    result = Block.resolve(
        attacker_ocv=10, attacker_dice=[3, 3, 3],
        blocker_ocv=8,  blocker_dice=[4, 4, 4],
    )
    assert result.success is False


def test_block_resolve_blocker_wins_ties():
    # Both have margin 10
    # Attacker OCV 10, rolls [4,4,3]=11 → margin 10+11-11=10
    # Blocker OCV 10, rolls [4,4,3]=11 → margin 10+11-11=10
    result = Block.resolve(
        attacker_ocv=10, attacker_dice=[4, 4, 3],
        blocker_ocv=10, blocker_dice=[4, 4, 3],
    )
    assert result.success is True
