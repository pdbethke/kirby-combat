"""ObjectCombatant — inanimate objects with BODY/DEF."""
import pytest

from kirby_combat.breakables import ObjectCombatant
from kirby_combat.models import Combatant


def test_object_combatant_has_body_def_no_stun():
    o = ObjectCombatant.make(id="door1", name="Wooden Door", material="wood")
    assert isinstance(o, Combatant)
    assert o.max_body == 4
    assert o.rpd == 3
    assert o.red == 3
    assert o.max_stun == 0


def test_object_destroyed_at_zero_body():
    o = ObjectCombatant.make(id="vase", name="Vase", material="glass", body=2)
    assert o.is_destroyed() is False
    o2 = type(o)(**{**o.__dict__, "current_body": 0})
    assert o2.is_destroyed() is True


def test_object_cannot_dodge_or_abort():
    o = ObjectCombatant.make(id="rock", name="Rock", material="stone")
    assert o.can_dodge() is False
    assert o.can_abort() is False


def test_object_takes_normal_or_killing_damage_per_material():
    # Glass and metal have very different DEF/BODY — verify defaults
    glass = ObjectCombatant.make(id="g", name="Glass", material="glass")
    metal = ObjectCombatant.make(id="m", name="Metal", material="metal")
    assert metal.rpd > glass.rpd
    assert metal.max_body > glass.max_body
    assert glass.takes_damage_type("killing") is True


def test_object_hdc_fields_preserved():
    """Round-trip requirement: HDC source XML preserved on ObjectCombatant."""
    raw = "<EQUIPMENT><NAME>Test</NAME></EQUIPMENT>"
    o = ObjectCombatant.make(
        id="x", name="X", material="metal", hdc_source_xml=raw,
    )
    assert o.hdc_source_xml == raw
