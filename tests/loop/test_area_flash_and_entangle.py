"""An Area Flash blinds, and an Area Entangle binds, everyone in it.

The Flash and Entangle offers carry the BUILD's power (`enumeration.py`
reads them off ``hero.powers``), and Batch C's shape filter read only an
attack view's fields --- so an Area Flash (27 in the corpus) and an Area
Entangle (8) were offered and resolved as if they hit the one man named.
Now the filter reads the build (`attack_shapes.shape_of`), and an Area one
is made like any Area use (`area_attack.area_use`: one roll against the
target point, scatter, END, the use's row) and lands on everyone in it
(`actions/area_effects.py`; 6E1 p.220, p.228, p.321, p.326).

Scene as in `test_an_area_hits_everyone_in_it.py`: a at the origin, b 8m
out, c 3m past b, a's own ally e beside b, d 12m past b.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shaped import TEMPLATE, Dice, armed, encounter_on, scene_with
from kirby_combat.actions.flash import Flash
from kirby_combat.attack_shapes import offer_is_buildable
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (11, 0, 0),
             "e": (9, 1, 0), "d": (20, 0, 0)}


@dataclass
class _Mod:
    xmlid: str
    levels: float = 0
    option_id: str | None = None
    assigned_adders: list = field(default_factory=list)
    assigned_modifiers: list = field(default_factory=list)


_IDS = iter(range(9000, 10000))


@dataclass
class _Power:
    xmlid: str
    name: str
    levels: int
    active_cost: float = 30.0
    option_id: str | None = None
    assigned_modifiers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)
    id: int = field(default_factory=lambda: next(_IDS))


def _area(size=7, *adders):
    return _Mod("AOE", levels=size, option_id="RADIUS",
                assigned_adders=[_Mod(a) for a in adders])


def _fight():
    people = [armed("a", None, side=VILLAINS, dex=30),
              armed("b", None, side=HEROES), armed("c", None, side=HEROES),
              armed("e", None, side=VILLAINS), armed("d", None, side=HEROES)]
    return encounter_on(scene_with(POSITIONS), *people)


def _offer(kind, power, target="b"):
    return LegalAction(action_id=f"{kind}:{target}:{power.id}", kind=kind,
                       target_id=target, power_xmlid=power.xmlid,
                       power_name=power.name, summary="", _attack_view=power)


def test_an_area_flash_blinds_everyone_in_it():
    """Seam: 6d6 Sight Flash, 7m Radius. 3d6 of 3s = 9 hits the target point
    (DCV 3); 6d6 of 3s is 6 Normal Damage BODY (6E1 p.228: "counts the
    Normal Damage BODY") --- 6 Segments blind for b, c and a's own e; d,
    12m off, sees."""
    flare = _Power("FLASH", "Flare", 6, assigned_modifiers=[_area()])
    enc = _fight()
    s = enc.sessions[0]
    assert offer_is_buildable(s, "a", _offer("flash", flare))
    resolved = resolve_chosen(s, s.combatants["a"], _offer("flash", flare),
                              template=TEMPLATE, roller=Dice(face=3))
    out = resolved.session
    for who in ("b", "c", "e"):
        assert Flash.is_flashed(out, who, "sight")[0], who
    assert not Flash.is_flashed(out, "d", "sight")[0]
    use = [e.result_payload for e in out.event_log if e.kind == "ActionResolved"
           and (e.result_payload or {}).get("area_use")]
    assert len(use) == 1 and use[0]["target_dcv"] == 3


def test_an_explosion_flash_loses_a_die_per_2m():
    """6E1 p.228: "loses 1d6 of effect per 2m out from the center". d at 4m
    from the point of a 7m Explosion keeps 6 - 1 dice: 5 BODY at 3s."""
    flare = _Power("FLASH", "Flare", 6,
                   assigned_modifiers=[_area(7, "EXPLOSION")])
    enc = _fight()
    s = enc.sessions[0]
    resolved = resolve_chosen(s, s.combatants["a"], _offer("flash", flare, target="c"),
                              template=TEMPLATE, roller=Dice(face=3))
    rows = {e.target_id: e for e in resolved.session.event_log
            if e.kind == "FlashApplied"}
    # Point on c (11, 0): b is 3m off (one die lost), c is on it (none).
    assert rows["c"].segments - rows["b"].segments == 1


def test_an_area_entangle_binds_everyone_in_it():
    """6E1 p.321 with p.217: one Entangle roll, 4d6 of 3s = 4 BODY, PD/ED 4,
    on everyone in the 7m Radius."""
    from kirby_combat.session.effects import entangle_state

    glue = _Power("ENTANGLE", "Glue Grenade", 4, assigned_modifiers=[_area()])
    enc = _fight()
    s = enc.sessions[0]
    resolved = resolve_chosen(s, s.combatants["a"], _offer("entangle", glue),
                              template=TEMPLATE, roller=Dice(face=3))
    out = resolved.session
    for who in ("b", "c", "e"):
        st = entangle_state(out, who)
        assert st.is_entangled and st.body_remaining == 4 and st.entangle_pd == 4, who
    assert not entangle_state(out, "d").is_entangled


def test_a_constant_area_flash_is_still_not_offered():
    """A Constant Flash re-blinds a man "as soon as he can perceive again"
    (6E1 p.228): nothing keeps that, so it is not offered --- and before the
    filter read the build, it was, as a one-target Flash."""
    flare = _Power("FLASH", "Blinding Light Field", 6,
                   assigned_modifiers=[_area(), _Mod("CONTINUOUS")])
    enc = _fight()
    assert not offer_is_buildable(enc.sessions[0], "a", _offer("flash", flare))


def test_a_damage_over_time_drain_is_not_offered_as_one_drain():
    """18 corpus Drains are Damage Over Time ("Cause Disease"). The Drain
    resolver adjusts once; offered, it was one Drain."""
    disease = _Power("DRAIN", "Cause Disease", 2, assigned_modifiers=[
        _Mod("DAMAGEOVERTIME", assigned_adders=[
            _Mod("INCREMENTS", option_id="4"), _Mod("TIMEBETWEEN", option_id="TURN")])])
    enc = _fight()
    assert not offer_is_buildable(enc.sessions[0], "a", _offer("drain", disease))
