"""The MCV Attack Roll, on the live path --- one door for every Mental Power.

6E1 p.150: "Characters target Mental Powers with Mental Combat Value (MCV),
using an MCV Attack Roll"; p.151: "Once a character makes a successful MCV
Attack Roll, he makes an Effect Roll." The arithmetic has lived in
``mental_combat.resolve_mental_to_hit`` for a long time and was called by its
unit tests and nothing else, so every Mental Blast, Mind Control, Telepathy
and Mental Illusion the engine ever resolved hit automatically.

ONE FUNCTION, because this engine's dominant defect is a rule at one door
and not the others (`actions/recording.py::_fold_session_cvs`). The CVs are
the folded ones --- `cv_modifiers.effective_omcv_for` / `effective_dmcv_for`,
so a Stunned target's halved DMCV (6E2 p.106) and an Aid or Drain to either
value apply here exactly as they do to an OCV. The pure arithmetic is still
``resolve_mental_to_hit``'s; this hands it the modifiers as deltas.

No Range Modifier (6E1 p.150: "The Range Modifier does not apply to Mental
Powers").
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.mental.mental_combat import MentalToHitResult, resolve_mental_to_hit

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def mental_attack_roll(
    session: "CombatSession", attacker, target, roller, *,
    omcv_modifier: int = 0,
) -> MentalToHitResult:
    """Roll 3d6 against 11 + OMCV - DMCV with this fight's conditions folded.

    ``omcv_modifier`` is a situational modifier the CALLER knows about and
    the session does not --- Mind Scan's number-of-minds penalty is the one
    caller today. A combatant the session does not know is rolled on his
    bare values, the same courtesy `_fold_session_cvs` extends.
    """
    from kirby_combat.cv_modifiers import effective_dmcv_for, effective_omcv_for

    ocv_delta = int(omcv_modifier)
    dcv_delta = 0
    if attacker.id in session.combatants:
        ocv_delta += effective_omcv_for(session, attacker.id) - int(attacker.omcv)
    if target.id in session.combatants:
        dcv_delta += effective_dmcv_for(session, target.id) - int(target.dmcv)
    return resolve_mental_to_hit(
        attacker, target, roller.roll_dice(3),
        ocv_modifier=ocv_delta, dcv_modifier=dcv_delta,
    )


def mind_scan_omcv_modifier(minds: int) -> int:
    """The Mind Scan Modifiers Table's OMCV penalty for ``minds`` (6E1 p.263).

    The table prints one row per power of ten: 1 mind 0, 10 minds -2, 100
    minds -4 ... "and so forth", -2 a step. RULING: a row is read as an
    UPPER BOUND, so 2-10 minds take -2 and 11-100 take -4. The book prints no
    in-between rows; reading them as lower bounds would let a scanner treat
    nine minds as one, which is the generous reading, and generosity is how a
    sim makes everyone better than they paid for.
    """
    if minds < 1:
        raise ValueError(f"a Mind Scan searches for at least one mind, got {minds}")
    steps = 0
    bound = 1
    while bound < minds:
        bound *= 10
        steps += 1
    return -2 * steps
