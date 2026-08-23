"""Every view this engine hands out is identified by an id, never by a string.

Kirby indexes on ids. The xmlid is a TYPE ("this is an Energy Blast") and the
name is a display string; a character may legitimately carry several powers
agreeing on both, so any key built from them collides — silently, which is how
AOE / TRIGGER / SIDEEFFECTS / INCREASEDEND stayed dead in combat for the whole
corpus.

The views here handed out three such keys:
  * ``MartialManeuverView.maneuver_id`` was ``"{xmlid}:{name}"``
  * ``AttackPower.slot_id`` fell back to ``"{XMLID}#{id(power)}"`` — a Python
    memory address, which is not even stable within a process once an object
    is freed and its address reused
  * ``FrameworkView`` was identified by its xmlid, ambiguous for the 113
    corpus characters carrying two or more frameworks

An id also has to survive a reload to be worth holding: these tests load the
same file twice and require the ids to match.
"""
from kirby_combat.hero_view import HeroCombatant

from tests.corpus import require_authored


def _framework_character() -> str:
    """A character carrying a framework with slots."""
    return require_authored("Bokor")


def _martial_artist() -> HeroCombatant:
    """A character carrying martial maneuvers — maneuver_id names those."""
    return HeroCombatant.from_hdc(require_authored("Ravel"))


def _first_framework(path: str):
    return next(f for f in HeroCombatant.from_hdc(path).framework_view()
                if f.slots)


class TestSlotIdentity:
    def test_slot_id_is_the_slot_power_id(self):
        """Not a decorated xmlid, and never a memory address."""
        fw = _first_framework(_framework_character())
        for s in fw.slots:
            assert s.slot_id, "every slot must carry an id"
            assert "#" not in s.slot_id, (
                f"slot_id {s.slot_id!r} fell back to the memory-address form"
            )
            assert str(s.slot_id).isdigit(), (
                f"slot_id {s.slot_id!r} is not an object id"
            )

    def test_slot_ids_survive_a_reload(self):
        first = [s.slot_id for s in _first_framework(_framework_character()).slots]
        second = [s.slot_id for s in _first_framework(_framework_character()).slots]
        assert first == second


class TestFrameworkIdentity:
    def test_framework_carries_its_own_id(self):
        fw = _first_framework(_framework_character())
        assert getattr(fw, "framework_id", None), (
            "FrameworkView must carry the framework object's id — xmlid is a "
            "type, and 113 corpus characters carry two or more frameworks"
        )

    def test_framework_id_survives_a_reload(self):
        assert _first_framework(_framework_character()).framework_id == \
            _first_framework(_framework_character()).framework_id


class TestManeuverIdentity:
    def test_maneuver_id_is_the_maneuver_object_id(self):
        mvs = _martial_artist().maneuver_view()
        assert mvs, "Cheshire fights with his art — he must have maneuvers"
        for mv in mvs:
            assert ":" not in str(mv.maneuver_id), (
                f"maneuver_id {mv.maneuver_id!r} still encodes xmlid:name"
            )
            assert str(mv.maneuver_id).isdigit()

    def test_maneuver_ids_are_distinct(self):
        mvs = _martial_artist().maneuver_view()
        ids = [mv.maneuver_id for mv in mvs]
        assert len(set(ids)) == len(ids), f"colliding maneuver_ids: {ids}"

    def test_maneuver_ids_survive_a_reload(self):
        first = [m.maneuver_id for m in _martial_artist().maneuver_view()]
        second = [m.maneuver_id for m in _martial_artist().maneuver_view()]
        assert first == second


class TestAttackIdentity:
    def test_every_attack_view_carries_a_source_id(self):
        hc = _martial_artist()
        for ap in hc.attacks:
            assert ap.source_id is not None, (
                f"attack {ap.xmlid}/{ap.name} has no source id — consumers "
                f"would be forced back onto xmlid + name"
            )

    def test_str_strike_view_carries_a_source_id(self):
        """The bare Strike is built from STR, and STR is an object with an id.

        It was the one view with no identity at all, which is what forced the
        action_id builder to keep a string fallback.
        """
        hc = _martial_artist()
        assert hc.str_strike_view().source_id is not None


class TestFrameworkSlotLinkage:
    def test_a_framework_slot_carries_its_framework_id(self):
        """The reserve gate keys slot allocation by framework.

        It keyed on framework_xmlid, which is a type: two Multipowers on one
        character share it, so their reserves were pooled under one key.
        """
        hc = HeroCombatant.from_hdc(_framework_character())
        slotted = [a for a in hc.attacks if a.slot_id]
        assert slotted, "_framework_character() carries a multipower with attack slots"
        for ap in slotted:
            assert ap.framework_id, (
                f"{ap.xmlid}/{ap.name} is in a framework but names it only by "
                f"xmlid {ap.framework_xmlid!r}"
            )
            assert str(ap.framework_id).isdigit()

    def test_the_slot_framework_id_matches_the_framework_view(self):
        """Both sides must agree, or the gate silently finds no allocation."""
        hc = HeroCombatant.from_hdc(_framework_character())
        fw_ids = {f.framework_id for f in hc.framework_view()}
        for ap in (a for a in hc.attacks if a.slot_id):
            assert ap.framework_id in fw_ids, (
                f"slot names framework {ap.framework_id!r}, "
                f"framework_view offers {sorted(fw_ids)}"
            )
