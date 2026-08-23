from kirby_combat.hero_view import HeroCombatant

from tests.corpus import require_authored


def test_attacks_surface_avad_and_slot_identity():
    hc = HeroCombatant.from_hdc(require_authored("Bokor"))
    atks = hc.attacks
    nnd = [a for a in atks if a.avad]
    assert nnd, "the AVAD attack should surface avad=True"
    assert nnd[0].avad_defense            # the named alternate defense (free text)
    assert nnd[0].framework_xmlid         # belongs to a framework
    assert nnd[0].slot_id                 # has a stable slot id
    # framework slots are named (no more name=None)
    framework_atks = [a for a in atks if a.framework_xmlid]
    assert framework_atks and all(a.name for a in framework_atks)


def test_non_framework_attack_has_empty_framework_fields():
    # A plain top-level attack (no framework parent) keeps empty framework
    # identity and avad False. This character HAS one, so the loop is not
    # vacuous — the old fixture only might have, and the test said so.
    hc = HeroCombatant.from_hdc(require_authored("Bokor"))
    plain = [a for a in hc.attacks if not a.framework_xmlid]
    assert plain, "expected at least one non-framework attack"
    for a in plain:
        assert a.avad is False and a.framework_xmlid == "" and a.slot_id == ""
