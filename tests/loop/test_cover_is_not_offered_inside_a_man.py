"""Cover nobody can take is not offered.

The menu kept a covered spot off the menu only when another man stood
within `enumeration._SAME_SPACE_M` (0.5m) of it, while 0.27.0's moves stop
`placement.PERSONAL_SPACE_M` (1m) short of anybody. A spot 0.5-1m from a
man was offered and could not be reached: at the O.K. Corral (seed 59) men
declared `move_to_cover` 24 times and moved on 9 of them, spending the
other Phases standing still. One distance now decides both.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples"))


def test_every_move_to_cover_at_the_corral_moves_the_man():
    """A cover move that writes no movement is a Half Phase spent standing
    still: the offer could not be taken. (The move's row is written just
    before its declaration, with the END it cost between them.)"""
    import the_shootout_we_can_publish as corral

    _, result = corral.the_fight(corral.DEMO_SEED)
    log = result.encounter.sessions[0].event_log
    idle = [
        e.combatant_id for i, e in enumerate(log)
        if e.kind == "ActionDeclared" and e.action_type == "move_to_cover"
        and not any(x.kind == "MovementResolved" and x.combatant_id == e.combatant_id
                    for x in log[max(0, i - 3):i])
    ]
    assert idle == []
