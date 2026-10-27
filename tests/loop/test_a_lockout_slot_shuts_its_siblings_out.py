"""A Lockout slot in use shuts its framework siblings out — 6E1 p.388.

"A power with this Limitation prevents the character from using some or all
of his other powers when it's in use. It's most commonly taken for a slot in
a Power Framework that prevents the character from using other slots in the
Framework."

`enumerate_actions(blocked_lockout_ids=...)` has filtered sibling slots since
the kirby-api driver's PR-96, and `run_phase` never passed the set: a Lockout
limitation bought points off a power and cost nothing. These run the Phase,
so they fail on origin/main.

The case is p.388's own: a Mind Control "Lockout (cannot cast this spell or
other spells while maintaining Mind Control)". While psi's Mind Control
holds, the Mental Blast in the same Multipower is not on his menu.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.models import AttackPower, FrameworkView, SlotView
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.side import Side
from kirby_combat.synthetic import _SyntheticCombatant, synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


@dataclasses.dataclass
class _WithFramework(_SyntheticCombatant):
    """A synthetic caster whose Multipower is given, not derived. A FIELD,
    so it survives the `dataclasses.replace` the engine does on every
    vitals change."""

    _framework: list = dataclasses.field(default_factory=list)

    def framework_view(self):
        return self._framework


class _Power:
    def __init__(self, xmlid: str, levels: int, *, mods: tuple[str, ...] = ()):
        self.xmlid, self.name, self.alias = xmlid, xmlid.title(), xmlid.title()
        self.levels = levels
        self.id = f"src-{xmlid}"
        self.assigned_adders: list = []
        self.assigned_modifiers = [SimpleNamespace(xmlid=m) for m in mods]
        self.sub_powers: list = []


def _mental_blast() -> AttackPower:
    return AttackPower(
        xmlid="MENTALBLAST", name="Mind Blast", damage_dice=6,
        half_die=False, plus_one=False, damage_type="normal", defense_type="md",
        range_m=None, uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, source_id="src-MENTALBLAST", is_ranged=False,
    )


def _psi(*, lockout: bool):
    base = synthetic_combatant(
        id="psi", name="psi", ocv=6, dcv=5, omcv=8, dmcv=5, spd=4, dex=30,
        ego=15, str_=10, con=10, pre=10, rec=4, pd=3, ed=3,
        max_stun=30, max_body=10, max_end=40, side=Side.named("psi"),
        is_mentalist=True, attacks=[_mental_blast()],
    )
    base.hero.powers.append(
        _Power("MINDCONTROL", 12, mods=("LOCKOUT",) if lockout else ()))
    multipower = FrameworkView(
        framework_id="mp", xmlid="MULTIPOWER", name="Psionics",
        kind="multipower", reserve_or_pool=60,
        slots=[
            SlotView(slot_id="src-MINDCONTROL", name="Will", active_points=60,
                     variable=False, kind="attack"),
            SlotView(slot_id="src-MENTALBLAST", name="Mind Blast", active_points=60,
                     variable=False, kind="attack"),
        ],
    )
    fields = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}
    return _WithFramework(**fields, _framework=[multipower])


def _mark():
    return synthetic_combatant(
        id="mark", name="mark", ocv=6, dcv=5, omcv=3, dmcv=3, spd=2, dex=5,
        ego=10, str_=10, con=10, pre=10, rec=4, pd=3, ed=3,
        max_stun=30, max_body=10, max_end=40, side=Side.named("gang"),
    )


def _maintaining_mind_control(session: CombatSession) -> CombatSession:
    """psi's Mind Control on mark, in force: the payload `continuing.py`
    folds, written as `_resolve_mind_control` writes it."""
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("psi"), declaration_event_id="d",
        result_payload={
            "kind": "mind_control", "established": True, "hit": True,
            "attacker_id": "psi", "target_id": "mark", "order": "spare",
            "source_id": "src-MINDCONTROL", "breakout_modifier": 0,
        },
    ))


def _session(*, lockout: bool, maintaining: bool) -> CombatSession:
    session = CombatSession.create(
        id="s", combatants=[_psi(lockout=lockout), _mark()], scene=None,
        template=TEMPLATE, dice_roller=RandomRoller(seed=3),
    ).start()
    return _maintaining_mind_control(session) if maintaining else session


class _Records:
    def __init__(self):
        self.menu = []

    def choose(self, situation):
        self.menu = list(situation.menu)
        return next(a for a in situation.menu if a.kind == "dodge").action_id


def _psis_menu(session):
    chooser = _Records()
    result = run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]),
                       chooser, roller=RandomRoller(seed=21), on_unresolvable="raise")
    assert result.actor_id == "psi"
    return chooser.menu


def _blasts(menu):
    return [a for a in menu if a.kind == "mental_blast"]


def test_the_sibling_is_offered_while_the_lockout_slot_is_idle():
    """Guards the guard: nothing in use, nothing shut out."""
    assert _blasts(_psis_menu(_session(lockout=True, maintaining=False)))


def test_maintaining_the_lockout_slot_shuts_the_sibling_out():
    session = _session(lockout=True, maintaining=True)
    assert _blasts(_psis_menu(session)) == []
    from kirby_combat.lockout import blocked_lockout_ids
    assert blocked_lockout_ids(session, session.combatants["psi"]) == {"src-MENTALBLAST"}


def test_without_the_limitation_maintaining_one_slot_blocks_nothing():
    """It is the Limitation that locks, not the Multipower."""
    assert _blasts(_psis_menu(_session(lockout=False, maintaining=True)))
