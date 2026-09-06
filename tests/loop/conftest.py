"""Shared fighters for the loop tests."""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.encounter import Encounter
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def blast(source_id: str, dice: int = 8) -> AttackPower:
    """An Energy Blast.

    ``source_id`` is REQUIRED, not decorative: enumeration builds an
    action_id from the source power's object id and raises rather than
    falling back to xmlid+name, because that fallback made 630 corpus
    objects share a token silently.
    """
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=dice,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id,
    )


def fighter(
    id: str, *, side=None, dex: int = 20,
    stun: int = 40, dice: int = 8, spd: int = 4, armed: bool = True,
):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=spd, dex=dex, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=stun, current_body=12, current_end=40,
        side=side, attacks=[blast(f"{id}-eb", dice)] if armed else [],
    )


def session_of(*combatants, seed: int = 7) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(combatants), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=seed),
    ).start()


def encounter_of(*combatants, seed: int = 7, segment: int = 12) -> Encounter:
    return Encounter(
        id="e", turn=1, segment=segment,
        sessions=[session_of(*combatants, seed=seed)],
    )


@pytest.fixture
def roller():
    return RandomRoller(seed=7)
