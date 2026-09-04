"""DEF+BODY object destruction (spec §1.2). Reuses compute_damage for BODY."""
from kirby_combat.models import AttackPower, DiceValues
from kirby_combat.template import CombatTemplate
from kirby_combat.scene import Construct
from kirby_combat.resolution.object_damage import apply_attack_to_construct


def _power(dice=3, damage_type="normal"):
    return AttackPower(xmlid="BLAST", name="Blast", damage_dice=dice, half_die=False,
                       plus_one=False, damage_type=damage_type, defense_type="pd",
                       range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
                       penetrating=0, increased_stun_mult=0)


def _dice(values):
    return DiceValues(damage=list(values))


def _wall_construct(def_value, body):
    return Construct(obj_id="w1", kind="wall", segment=None, def_value=def_value, body=body)


def test_def_gate_blocks_small_hit():
    # 3 dice rolling [2,2,1] -> BODY 1+1+0 = 2. DEF 6 -> 0 through.
    tmpl = CombatTemplate(name="t")
    r = apply_attack_to_construct(_power(3), _dice([2, 2, 1]), _wall_construct(6, 8), tmpl)
    assert r.body_rolled == 2 and r.body_through == 0
    assert r.body_after == 8 and r.destroyed is False


def test_big_hit_chips_body():
    # [6,6,6] -> BODY 2+2+2 = 6. DEF 2 -> 4 through. 8 - 4 = 4.
    tmpl = CombatTemplate(name="t")
    r = apply_attack_to_construct(_power(3), _dice([6, 6, 6]), _wall_construct(2, 8), tmpl)
    assert r.body_rolled == 6 and r.body_through == 4
    assert r.body_before == 8 and r.body_after == 4 and r.destroyed is False


def test_destroys_at_zero():
    tmpl = CombatTemplate(name="t")
    r = apply_attack_to_construct(_power(3), _dice([6, 6, 6]), _wall_construct(2, 4), tmpl)
    assert r.destroyed is True and r.body_after == 0


def test_indestructible_construct_rejected():
    import pytest
    tmpl = CombatTemplate(name="t")
    with pytest.raises(ValueError):
        apply_attack_to_construct(_power(3), _dice([6, 6, 6]),
                                  Construct(obj_id="z", kind="hazard_zone"), tmpl)


def test_autofire_applies_def_per_shot():
    from kirby_combat.resolution.object_damage import apply_autofire_to_construct
    tmpl = CombatTemplate(name="t")
    # Each shot: [6,6,6] -> BODY 6, DEF 2 -> 4 through. Wood BODY 4 -> destroyed on shot 1.
    shots = [_dice([6, 6, 6]) for _ in range(5)]
    res = apply_autofire_to_construct(_power(3), shots, _wall_construct(2, 4), tmpl)
    assert res[0].destroyed is True
    assert len(res) == 1  # stops once destroyed; remaining shots not applied


def test_autofire_chips_steel_over_multiple_shots():
    from kirby_combat.resolution.object_damage import apply_autofire_to_construct
    tmpl = CombatTemplate(name="t")
    # DEF 9 steel: [6,6,6] -> BODY 6 < DEF 9 -> 0 through every shot; never falls.
    shots = [_dice([6, 6, 6]) for _ in range(5)]
    res = apply_autofire_to_construct(_power(3), shots, _wall_construct(9, 10), tmpl)
    assert len(res) == 5 and all(r.body_through == 0 for r in res)
    assert res[-1].body_after == 10 and res[-1].destroyed is False


def _brick() -> Construct:
    """6E2 p173: brick wall, 5 PD / 10 ED / 3 BODY."""
    return Construct(obj_id="brick", kind="wall", def_value=5, ed_value=10, body=3)


def _attack(defense_type: str, damage_type: str = "normal") -> AttackPower:
    return AttackPower(
        xmlid="TEST", name="Test", damage_dice=6, half_die=False, plus_one=False,
        damage_type=damage_type, defense_type=defense_type, range_m=100,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0,
    )


def _six_sixes() -> DiceValues:
    return DiceValues(to_hit=[3, 3, 3], damage=[6, 6, 6, 6, 6, 6])


def test_a_physical_attack_meets_pd():
    r = apply_attack_to_construct(_attack("pd"), _six_sixes(), _brick(),
                                  CombatTemplate.default_6e_superheroic())
    assert r.def_value == 5


def test_an_energy_attack_meets_ed():
    """The whole point of the split: the same wall, the same dice, a
    different defense."""
    r = apply_attack_to_construct(_attack("ed"), _six_sixes(), _brick(),
                                  CombatTemplate.default_6e_superheroic())
    assert r.def_value == 10


def test_killing_damage_ignores_a_non_resistant_defense():
    """6E2 p173's parenthesised defenses are Normal Defense. Glass is
    (1)/(1)/1 -- a knife goes straight through."""
    glass = Construct(obj_id="pane", kind="wall", def_value=1, ed_value=1,
                      body=1, resistant=False)
    r = apply_attack_to_construct(_attack("pd", damage_type="killing"),
                                  _six_sixes(), glass,
                                  CombatTemplate.default_6e_superheroic())
    assert r.def_value == 0
    assert r.destroyed is True


def test_a_resistant_defense_still_applies_to_killing_damage():
    """Guards the guard: if the resistant check were inverted, every wall
    would stop resisting Killing attacks and the test above would still
    pass."""
    r = apply_attack_to_construct(_attack("pd", damage_type="killing"),
                                  _six_sixes(), _brick(),
                                  CombatTemplate.default_6e_superheroic())
    assert r.def_value == 5


def test_a_wall_with_no_ed_stated_uses_pd_for_both():
    legacy = Construct(obj_id="old", kind="wall", def_value=6, body=5)
    pd_hit = apply_attack_to_construct(_attack("pd"), _six_sixes(), legacy,
                                       CombatTemplate.default_6e_superheroic())
    ed_hit = apply_attack_to_construct(_attack("ed"), _six_sixes(), legacy,
                                       CombatTemplate.default_6e_superheroic())
    assert pd_hit.def_value == ed_hit.def_value == 6
