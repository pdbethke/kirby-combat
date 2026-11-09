"""A purchase's parts live in THREE lists, and every walk must read all three.

kirby-cost keeps a framework's slots in ``sub_powers``, a List's contents in
``objects`` and a Compound Power's parts in ``powers``
(``kirby_cost/objects/powers/compound_power.py``). Eight walks in this engine
read ``sub_powers`` only, so anything bought inside a Compound Power was
invisible in combat.

Found 2026-11-09 on the corpus: Agent of UNTIL and Agent of VIPER carry their
Blaster Carbine (Blast, Autofire, Charges, OAF) as a Compound Power with Combat
Skill Levels, and ``attacks`` returned ``[]``. Thirty of them fought Talisman
unarmed; 353 local characters carry a Compound Power.

The stub mirrors kirby-cost's real shape: a COMPOUNDPOWER with ``powers`` and
NO ``sub_powers`` attribute at all.
"""
from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass, field

from kirby_combat.hero_view import HeroCombatant, HeroCombatState, _find_power
from kirby_combat.parts import parts_of

from tests.test_attack_view_multipower import StubHero, StubPower


@dataclass
class StubCompound:
    """kirby-cost's CompoundPower: parts in ``powers``, no ``sub_powers``."""
    xmlid: str = "COMPOUNDPOWER"
    name: str = ""
    powers: list = field(default_factory=list)
    assigned_modifiers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)


@dataclass
class StubList:
    """kirby-cost's power List: contents in ``objects``."""
    xmlid: str = "LIST"
    name: str = ""
    objects: list = field(default_factory=list)
    assigned_modifiers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)


_CHARS = {
    "STR": 10, "DEX": 10, "CON": 10, "INT": 10, "EGO": 10, "PRE": 10,
    "OCV": 5, "DCV": 5, "OMCV": 3, "DMCV": 3, "SPD": 4,
    "PD": 5, "ED": 5, "REC": 5, "END": 50, "BODY": 10, "STUN": 30,
    "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
}


def _combatant(powers) -> HeroCombatant:
    return HeroCombatant(
        id="agent", hero=StubHero(name="Agent", powers=powers, _char_values=dict(_CHARS)),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=30, current_body=10, current_end=50),
        knockback_resistance=0,
    )


def _carbine() -> StubCompound:
    return StubCompound(name="Blaster Carbine", powers=[
        StubPower(xmlid="ENERGYBLAST", name="Blaster Carbine", levels=8),
        StubPower(xmlid="COMBAT_LEVELS", levels=4),
    ])


def test_parts_of_reads_all_three_lists() -> None:
    eb = StubPower(xmlid="ENERGYBLAST")
    slot = StubPower(xmlid="RKA")
    held = StubPower(xmlid="HKA")
    assert parts_of(StubCompound(powers=[eb])) == [eb]
    assert parts_of(StubPower(xmlid="MULTIPOWER", sub_powers=[slot])) == [slot]
    assert parts_of(StubList(objects=[held])) == [held]
    assert parts_of(StubPower(xmlid="ENERGYBLAST")) == []


def test_attacks_include_a_blast_inside_a_compound_power() -> None:
    names = [a.name for a in _combatant([_carbine()]).attacks]
    assert names == ["Blaster Carbine"]


def test_attacks_include_a_blast_inside_a_list() -> None:
    gear = StubList(name="Gear", objects=[StubPower(xmlid="RKA", name="Pistol", levels=1)])
    assert [a.name for a in _combatant([gear]).attacks] == ["Pistol"]


def test_attack_view_by_name_finds_a_compound_part() -> None:
    view = _combatant([_carbine()]).attack_view("ENERGYBLAST", name="Blaster Carbine")
    assert view is not None and view.name == "Blaster Carbine"


def test_find_power_finds_a_compound_part() -> None:
    hero = StubHero(powers=[_carbine()])
    found = _find_power(hero, "ENERGYBLAST")  # type: ignore[arg-type]
    assert found is not None and found.name == "Blaster Carbine"


def test_defenses_include_armor_inside_a_compound_power() -> None:
    """The same armour reports the same defence whether or not it is wrapped."""
    def vest():
        return StubPower(xmlid="FORCEFIELD", name="Vest", levels=6)
    bare = _combatant([vest()]).defense_view()
    assert bare, "fixture: a bare FORCEFIELD must report a defence"
    wrapped = _combatant([StubCompound(name="Vest", powers=[vest()])]).defense_view()
    assert wrapped == bare


def test_is_mentalist_sees_a_mental_power_inside_a_compound_power() -> None:
    psi = StubCompound(name="Psi Rig", powers=[StubPower(xmlid="EGOATTACK", name="Psi Bolt", levels=2)])
    assert _combatant([psi]).is_mentalist


# ── The ratchet ──────────────────────────────────────────────────────────
_ENGINE = pathlib.Path(__file__).resolve().parents[1] / "kirby_combat"
_HOME = _ENGINE / "parts.py"
# dispel's wrapper OVERRIDES the attribute rather than walking it.
_ALLOWED = {_ENGINE / "actions" / "dispel.py"}


def test_no_walk_reads_a_single_part_list() -> None:
    """``getattr(x, "sub_powers" | "objects" | "powers", ...)`` on a
    PURCHASE belongs in ``kirby_combat.parts`` only. Reading
    ``hero.powers`` (the build's section) is fine and is not a part list;
    this test flags every other single-list read so a new walk cannot
    forget the Compound Power again."""
    offenders = []
    for path in _ENGINE.rglob("*.py"):
        if path == _HOME or path in _ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in {"sub_powers", "objects"}):
                offenders.append(f"{path.relative_to(_ENGINE)}:{node.lineno}")
    assert offenders == [], (
        "walk these through kirby_combat.parts.parts_of, which reads all "
        f"three part lists: {offenders}")
