"""One ancestor, and it enforces its contract at construction.

Why an ABC and not a Protocol: a runtime_checkable Protocol's isinstance()
checks ATTRIBUTE PRESENCE only -- not types, not signatures, not return
values. Measured 2026-08-25: a class with `id = 42`, `name = None`,
`state = "not a state object"` and `combat_stats(self, wrong, args, here)`
satisfies such a Protocol. In a codebase whose recurring defect is things that
look right and are not, a contract satisfiable by accident is the wrong
instrument.
"""
from __future__ import annotations

import pytest

from kirby_combat.participant import CombatParticipant, Stunnable


def test_the_base_declares_no_state_of_its_own():
    """A bare `state` annotation (or attribute) directly on
    CombatParticipant makes the __init_subclass__ guard vacuous: the MRO
    walk in participant.py finds "state" in vars(CombatParticipant), so
    EVERY subclass looks like it already provides one, whether it does or
    not. This is not hypothetical -- it is exactly the bug hit while
    building that guard: a `state: Any` annotation left on the base made
    `MissingState` (below) satisfy the check trivially, and only surfaced
    because a human re-ran test_an_incomplete_participant_cannot_be_
    constructed by hand. Pin it here so the next accidental re-add fails
    the suite instead of waiting for another manual catch."""
    own = vars(CombatParticipant)
    assert "state" not in own
    assert "state" not in own.get("__annotations__", {})


def test_an_incomplete_participant_cannot_be_constructed():
    """The whole point of the ABC. A Protocol would accept this silently."""
    class MissingState(CombatParticipant):
        def combat_stats(self):
            return None

    with pytest.raises(TypeError) as excinfo:
        MissingState()
    assert "abstract" in str(excinfo.value).lower()


def test_ko_is_defined_once_on_the_stunnable_mixin():
    """The KO rule lived in mental_blast.py AND recovery.py AND a docstring.
    It belongs to the participant that HAS a STUN track, not to whatever is
    resolving at the time -- and not to the shared base, which the breakable
    half of the hierarchy also inherits (see the door tests below)."""
    class _State:
        current_stun = 0

    class Downed(Stunnable, CombatParticipant):
        id = "d"
        name = "Downed"
        def combat_stats(self): return None
        @property
        def state(self): return _State()

    assert Downed().is_ko is True
    assert Downed().is_conscious is False


def test_a_standing_participant_is_conscious():
    class _State:
        current_stun = 12

    class Standing(Stunnable, CombatParticipant):
        id = "s"
        name = "Standing"
        def combat_stats(self): return None
        @property
        def state(self): return _State()

    assert Standing().is_ko is False
    assert Standing().is_conscious is True


def test_the_ko_boundary_is_at_zero_not_below_it():
    """6E: a character is KO'd at 0 STUN or less, not only below 0. An
    off-by-one here silently keeps unconscious characters acting."""
    class _State:
        current_stun = 0

    class AtZero(Stunnable, CombatParticipant):
        id = "z"
        name = "Zero"
        def combat_stats(self): return None
        @property
        def state(self): return _State()

    assert AtZero().is_ko is True


# ─────────────────────────────────────────────────────────────────────────
# The breakable half of the hierarchy has no STUN track (I1)
#
# `is_ko` was originally put on CombatParticipant, so EVERY participant
# carried it. Measured 2026-08-25, before the Stunnable split:
#
#     ObjectCombatant.make(material='wood')   # an intact door
#     -> current_stun=0  is_ko=True  is_conscious=False  is_destroyed=False
#
#     Vehicle.make(..., max_stun=0)           # an undamaged van
#     -> current_stun=0  is_ko=True
#
# These pin both halves: a thing with no STUN track is not unconscious, and
# a thing WITH one still is when its STUN hits zero.
# ─────────────────────────────────────────────────────────────────────────


def _door():
    from kirby_combat.breakables.object_combatant import ObjectCombatant
    return ObjectCombatant.make(id="door", name="Oak Door", material="wood")


def test_an_intact_door_is_not_knocked_out():
    """The I1 regression, stated directly."""
    door = _door()
    assert door.current_stun == 0        # objects have no STUN track at all
    assert door.is_destroyed() is False  # ...and this one is undamaged
    # `is_ko` is REMOVED, not answered: hasattr sees the AttributeError the
    # property raises, so shape-dispatch code cannot mistake a door for
    # something knock-out-able.
    assert not hasattr(door, "is_ko")
    assert not hasattr(door, "is_conscious")
    assert getattr(door, "is_ko", "absent") == "absent"


def test_asking_a_door_whether_it_is_ko_says_why_it_is_the_wrong_question():
    door = _door()
    with pytest.raises(AttributeError) as excinfo:
        door.is_ko
    assert "is_destroyed" in str(excinfo.value)


def test_a_stunned_character_is_still_knocked_out():
    """The other half: the Stunnable types kept the rule."""
    from kirby_combat.models import StatBlockCombatant

    def _fighter(current_stun: int) -> StatBlockCombatant:
        return StatBlockCombatant(
            id="f", name="Fighter",
            ocv=8, dcv=8, omcv=3, dmcv=3,
            spd=4, dex=20, ego=10, str_=20, con=20, pre=15, rec=8,
            pd=8, ed=8, rpd=0, red=0, md=0,
            power_defense=0, flash_defense=0,
            max_stun=40, max_body=12, max_end=40,
            current_stun=current_stun, current_body=12, current_end=40,
        )

    assert _fighter(20).is_ko is False
    assert _fighter(20).is_conscious is True
    assert _fighter(0).is_ko is True      # 6E: at zero, not merely below it
    assert _fighter(-5).is_ko is True
    assert _fighter(-5).is_conscious is False


def test_a_vehicle_without_a_stun_track_is_not_knocked_out():
    """Vehicle keeps Stunnable (HD vehicles may have STUN) and narrows it."""
    from kirby_combat.vehicles.vehicle import Vehicle

    def _van(max_stun: int, current_stun: int | None = None) -> Vehicle:
        v = Vehicle.make(
            id="v", name="Van", size=3, body=10, def_=4, pd=4, ed=4,
            speed=3, dex=10, str_=30, max_stun=max_stun, max_end=0,
            movement_inches={}, passengers=[],
        )
        if current_stun is not None:
            v.current_stun = current_stun
        return v

    assert _van(max_stun=0).is_ko is False       # no STUN track
    assert _van(max_stun=20).is_ko is False      # full STUN
    assert _van(max_stun=20, current_stun=0).is_ko is True
