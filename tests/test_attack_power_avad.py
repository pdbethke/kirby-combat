import pytest

from kirby_combat.hero_view import HeroCombatant

HELIOS = "/home/pdbethke/PycharmProjects/Kirby/hero-designer-python/tests/fixtures/HELIOS-CV1.hdc"


def test_attacks_surface_avad_and_slot_identity():
    pytest.importorskip("hero_designer")
    hc = HeroCombatant.from_hdc(HELIOS)
    atks = hc.attacks
    nnd = [a for a in atks if a.avad]
    assert nnd, "Helios's NND slot should surface avad=True"
    assert nnd[0].avad_defense            # the named alternate defense (free text)
    assert nnd[0].framework_xmlid         # belongs to a framework
    assert nnd[0].slot_id                 # has a stable slot id
    # framework slots are named (no more name=None)
    framework_atks = [a for a in atks if a.framework_xmlid]
    assert framework_atks and all(a.name for a in framework_atks)


def test_non_framework_attack_has_empty_framework_fields():
    pytest.importorskip("hero_designer")
    # a plain top-level attack (no framework parent) keeps empty framework identity + avad False
    hc = HeroCombatant.from_hdc(HELIOS)
    plain = [a for a in hc.attacks if not a.framework_xmlid]
    # at least assert the fields exist and default cleanly (don't assume Helios has a plain attack)
    for a in plain:
        assert a.avad is False and a.framework_xmlid == "" and a.slot_id == ""
