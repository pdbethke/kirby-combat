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

from kirby_combat.participant import CombatParticipant


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


def test_ko_is_defined_once_on_the_ancestor():
    """The KO rule lived in mental_blast.py AND recovery.py AND a docstring.
    It belongs to the participant, not to whatever is resolving at the time."""
    class _State:
        current_stun = 0

    class Downed(CombatParticipant):
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

    class Standing(CombatParticipant):
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

    class AtZero(CombatParticipant):
        id = "z"
        name = "Zero"
        def combat_stats(self): return None
        @property
        def state(self): return _State()

    assert AtZero().is_ko is True
