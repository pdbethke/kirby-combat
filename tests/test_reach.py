"""attack_view exposes is_ranged + reach_m; combat_stats carries base reach (reach spec §1).

Stretching factor verified against Main6E.hdt: LVLCOST="1" LVLVAL="1"
→ 1 CP per 1 metre of Stretching → LEVELS = metres of stretch.
Total combat reach = _BASE_REACH_M (1m, 6E2 p56 / 6E2 p40 / 6E1 p231)
+ LEVELS * 1.0 m/level.
Evidence: Ravel.hdc LEVELS="8" → 8m stretch + 1m base = 9m total reach.
"""
from dataclasses import dataclass, field

from kirby_combat.hero_view import HeroCombatant, HeroCombatState


@dataclass
class _Pow:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)


@dataclass
class _Hero:
    name: str = "T"
    template_name: str = "synthetic.T.hdt"
    powers: list = field(default_factory=list)
    _cv: dict = field(default_factory=dict)

    def characteristic_value(self, xmlid: str) -> float:
        return float(self._cv.get(xmlid.upper(), 0))


def _combatant(*, powers=None, cv=None):
    base = {
        "STR": 20, "DEX": 13, "OCV": 7, "DCV": 7,
        "RUNNING": 12, "STUN": 30, "BODY": 12, "END": 40,
        "OMCV": 3, "DMCV": 3, "SPD": 3, "EGO": 11,
        "CON": 15, "PRE": 10, "REC": 5,
    }
    base.update(cv or {})
    hero = _Hero(powers=powers or [], _cv=base)
    return HeroCombatant(
        id="t",
        hero=hero,
        state=HeroCombatState(current_stun=30, current_body=12, current_end=40),
        knockback_resistance=0,
    )


def test_melee_attack_is_not_ranged_and_reach_is_base_1m():
    # 6E2 p56 sets a character's base Reach at one metre; 6E1 p231 agrees
    # for the no-Growth case.
    # Was 2.0, an uncited hex-adjacency inference.
    c = _combatant(powers=[_Pow("HANDTOHANDATTACK", "Punch", levels=8)])
    ap = c.attack_view("HANDTOHANDATTACK")
    assert ap.reach_m == 1.0
    assert ap.is_ranged is False


def test_ranged_attack_is_ranged():
    c = _combatant(powers=[_Pow("ENERGYBLAST", "Blast", levels=6, active_cost=30)])
    ap = c.attack_view("ENERGYBLAST")
    assert ap.is_ranged is True


def test_stretching_extends_reach():
    # LVLCOST="1" LVLVAL="1" in Main6E.hdt → 1 CP per 1m → _STRETCH_M_PER_LEVEL = 1.0
    # 3 levels → reach = 1 (base Reach, 6E2 p56) + 3*1.0 = 4.0 m
    c = _combatant(powers=[
        _Pow("HANDTOHANDATTACK", "Punch", levels=8),
        _Pow("STRETCHING", "Stretch", levels=3),
    ])
    ap = c.attack_view("HANDTOHANDATTACK")
    assert ap.reach_m == 4.0


def test_combat_stats_carries_base_reach():
    # 6E2 p56 sets base Reach at one metre (6E2 p40, 6E1 p231 agree), so 3 levels of
    # Stretching give 4.0m and a bare character 1.0m.
    c_stretch = _combatant(powers=[_Pow("STRETCHING", "Stretch", levels=3)])
    assert c_stretch.combat_stats().reach_m == 4.0
    assert _combatant().combat_stats().reach_m == 1.0
