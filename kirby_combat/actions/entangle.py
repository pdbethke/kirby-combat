"""Entangle attack — applies an entanglement; victims escape via STR.

Note: Dorman's reference does not implement programmatic entangle escape;
the casual STR (str/10) and full STR (str/5) damage formulas are our
interpretation per HERO 6E2. RAW-verify before relying on this.

per HERO 6E1:
- Entangle creates a temporary obstruction with its own BODY, PD, ED
- Target inside the entangle has -2 OCV and -2 DCV
- Casual STR escape (half-phase): BODY damage = STR/10 minus entangle PD
- Full STR escape (full-phase): BODY damage = STR/5 minus entangle PD
- Once entangle BODY ≤ 0, target is free

State tracking: scan event log for EntangleApplied / EntangleEscape pairs.
No Combatant model changes; no apply.py extensions in this task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
from typing import Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, EntangleApplied, EntangleEscape,
    make_author_combatant,
)


def _modifier_list(power) -> list:
    return list(getattr(power, "assigned_modifiers", None)
                or getattr(power, "modifiers", None) or [])


def _levels_of(power, xmlid: str) -> int:
    """Total levels of a modifier across every instance on ``power``.

    HD writes stacked purchases either as one modifier with LEVELS=n (the
    corpus shape: "Cannot Be Escaped With Teleportation (x2; +1/2)") or as
    repeated modifier elements; both count, and a level-less instance counts
    as one level."""
    total = 0
    for m in _modifier_list(power):
        if (getattr(m, "xmlid", "") or "").upper() == xmlid:
            total += max(1, int(getattr(m, "levels", 0) or 0))
    return total


def noteleport_levels(power) -> int:
    """Levels of Cannot Be Escaped With Teleportation (NOTELEPORT) on a power.

    6E1 p220 (Entangle) / p175 (Barrier): the advantage stops the one escape
    route an Entangle normally leaves open — 6E1 p217 has an Entangle block
    every Movement Power EXCEPT Teleportation, and 6E1 p218 lists Teleporting
    out among the escape methods. Multiple levels may be bought to outbid an
    escaper's Armor Piercing (see ``can_teleport_escape``)."""
    return _levels_of(power, "NOTELEPORT")


def armor_piercing_levels(power) -> int:
    """Levels of Armor Piercing on a power (each cancels one NOTELEPORT
    level when the power is the Teleportation doing the escaping —
    6E1 p220/p175)."""
    return _levels_of(power, "ARMORPIERCING")


def can_teleport_escape(entangle_power, teleportation_power=None) -> bool:
    """May this Teleportation escape that Entangle/Barrier?

    6E1 p218: Teleportation is a normal escape route. 6E1 p220 (and p175 for
    an englobing Barrier): Cannot Be Escaped With Teleportation blocks it,
    UNLESS the Teleportation is Armor Piercing, which cancels the advantage —
    both sides stack levels, so the escape works when AP levels >= NOTELEPORT
    levels. ``teleportation_power=None`` means a plain teleport (0 AP)."""
    ap = armor_piercing_levels(teleportation_power) if teleportation_power is not None else 0
    return noteleport_levels(entangle_power) <= ap


class Transparency(str, Enum):
    """Takes No Damage From Attacks (6E1 p.221), HD's TAKESNODAMAGE options.

    * NONE --- an ordinary Entangle: an attack on the man inside hits the
      Entangle first (6E1 p.218), and anyone may target it.
    * LIMITED / ALL --- "transparent to certain types of attacks" (+1/4) /
      "to all attacks" (+1/2): attacks reach the man and leave it whole; "If
      an attacker targets the Entangle specifically (at -3 OCV), the damage
      affects the Entangle and then the Entangled character".
    * STR_ONLY --- +1: it "cannot be attacked, damaged, or affected by
      outside attackers at all - only the victim can break free, and he can
      only apply his STR (or EGO, for Mental Paralysis Entangles)".
    """

    NONE = "none"
    LIMITED = "limited"
    ALL = "all"
    STR_ONLY = "str_only"


#: HD's option ids -> the value.
_TRANSPARENCY_OPTIONS = {
    "LIMITED": Transparency.LIMITED,
    "ALL": Transparency.ALL,
    "STRONLY": Transparency.STR_ONLY,
}


def transparency_of(power) -> Transparency:
    """Read Takes No Damage From Attacks off an Entangle power.

    Raises on an option this module does not know rather than guessing one:
    each of the three changes who may do what to the Entangle.
    """
    from kirby_combat.power_modifiers import _find, _option

    mod = _find(power, "TAKESNODAMAGE")
    if mod is None:
        return Transparency.NONE
    option = _option(mod)
    try:
        return _TRANSPARENCY_OPTIONS[option]
    except KeyError:
        raise ValueError(
            f"Takes No Damage From Attacks option {option!r} on "
            f"{getattr(power, 'id', power)!r} is none of "
            f"{sorted(_TRANSPARENCY_OPTIONS)} (6E1 p.221)"
        ) from None


def both_take_damage(power) -> bool:
    """Entangle And Character Both Take Damage (6E1 p.220), HD's BOTHDAMAGE."""
    from kirby_combat.power_modifiers import _find

    return _find(power, "BOTHDAMAGE") is not None


def _stated(transparency) -> Transparency:
    """The Transparency an Entangle was bought with --- never assumed."""
    if not isinstance(transparency, Transparency):
        raise ValueError(
            f"an Entangle must state its Takes No Damage From Attacks "
            f"(a Transparency, 6E1 p.221); got {transparency!r}. Read it off "
            f"the power with `transparency_of`."
        )
    return transparency


#: 6E1 p217: an Entangled character is at DCV 0. The one authority for the
#: factor -- ``Entangle.modifiers`` and any row-based driver read THIS, so
#: the number cannot drift between the event-sourced and relational paths.
ENTANGLED_DCV_FACTOR: float = 0.0

#: 6E1 p218: breaking out of an Entangle "doesn't have to make an Attack
#: Roll" -- an escape attempt against the Entangle always connects. Drivers
#: consult this rather than encoding the absence of a to-hit themselves.
ENTANGLE_ESCAPE_AUTO_HITS: bool = True


def str_escape_end_cost(str_value: int, *, casual: bool = False) -> int:
    """END for a STR breakout attempt.

    6E2 p41: STR costs 1 END per 10 points USED. Casual Use is half the
    character's STR and pays only for the amount used (6E1 p134), so the
    casual attempt charges half's worth."""
    used = (str_value // 2) if casual else str_value
    return max(0, used // 10)


def entangle_default_defenses(dice: int) -> tuple[int, int]:
    """The Entangle's own PD and ED when the build states no split.

    6E1 p217: each 1d6 of Entangle has 1 PD and 1 ED (both Resistant), so a
    document that writes no PDLEVELS/EDLEVELS defends at (dice, dice)."""
    return max(0, dice), max(0, dice)


@dataclass(frozen=True)
class BreakoutResult:
    """One breakout attempt's outcome tier (6E2 p126)."""
    escaped: bool
    action_regained: str   # "full" | "half" | "none"


def breakout(damage_body: int, remaining_body: int) -> BreakoutResult:
    """The breakout-margin rule, 6E2 p126: damage of at least TWICE the
    Entangle's remaining BODY frees the victim with a Full Phase still to
    act; at least the remaining BODY frees with a Half Phase; anything
    less leaves them trapped with no more actions that Phase."""
    if remaining_body <= 0:
        return BreakoutResult(escaped=True, action_regained="full")
    if damage_body >= 2 * remaining_body:
        return BreakoutResult(escaped=True, action_regained="full")
    if damage_body >= remaining_body:
        return BreakoutResult(escaped=True, action_regained="half")
    return BreakoutResult(escaped=False, action_regained="none")


def stacked_entangle(
    existing_body: int, existing_pd: int, existing_ed: int,
    new_body: int, new_pd: int, new_ed: int,
) -> tuple[int, int, int]:
    """Combine a fresh Entangle hit with one already holding the target.

    6E1 p217: the combined Entangle has the HIGHEST BODY of all the
    Entangles, +1 BODY for each additional Entangle, and the highest PD
    and ED. With no live existing Entangle the new one applies as-is."""
    if existing_body <= 0:
        return new_body, new_pd, new_ed
    return (max(existing_body, new_body) + 1,
            max(existing_pd, new_pd), max(existing_ed, new_ed))


def str_escape_dice(str_value: int, *, casual: bool = False) -> int:
    """Normal-damage dice for a STR breakout attempt.

    Full STR: STR//5 dice (the standard STR-to-damage conversion). Casual
    STR is HALF the character's STR (6E1 p134), a Zero Phase attempt --
    win or lose, the character keeps their action (6E1 p133-134). The
    CALLER rolls these dice and counts BODY; this function never touches
    dice."""
    if casual:
        str_value = str_value // 2
    return max(0, str_value // 5)


def counted_body(dice_values) -> int:
    """Normal Damage BODY of a roll: "a 1 is 0 BODY; a 2-5 is 1 BODY, and a 6
    is 2 BODY" (6E2 p.100). An Entangle's own BODY is counted this way ("he
    rolls his Entangle dice and counts the Normal Damage BODY", 6E1 p.217),
    and so is the BODY a STR or EGO escape does. Delegates the per-die rule
    to the damage resolver so the two cannot disagree."""
    from kirby_combat.resolution.damage import _body_for_normal_die

    return sum(_body_for_normal_die(v) for v in dice_values)


def escape_body(body: int, defense: int) -> int:
    """What an escape attempt does to the Entangle: its BODY less the
    ENTANGLE's defense (6E1 p.218: enough BODY "to exceed the Entangle's
    defenses"), never the victim's."""
    return max(0, int(body) - int(defense))


def ego_escape_end_cost(ego: int) -> int:
    """END for breaking a Mental Paralysis with EGO: "this costs 1 END per 10
    Character Points of EGO used" (6E1 p.219). EGO is 1 Character Point a
    point (6E1 p.40), so 1 END per 10 EGO."""
    return max(0, int(ego) // 10)


class _ShieldedMind:
    """A man seen by a mental attack through the Mental Paralysis holding him.

    Everything is his except ``md``, which carries the paralysis's own:
    "This Mental Defense protects the Entangle if it's attacked, and also
    protects the Entangled character if anyone tries to attack him mentally"
    (6E1 p.219).
    """

    def __init__(self, inner, extra_md: int) -> None:
        self._inner = inner
        self._extra_md = int(extra_md)

    @property
    def md(self) -> int:
        return int(self._inner.md) + self._extra_md

    def __getattr__(self, name):
        return getattr(self._inner, name)


def mentally_shielded(session: CombatSession, target):
    """``target`` as a mental attack meets him: behind his Mental Paralysis's
    Mental Defense when one holds him (6E1 p.219), else himself."""
    hold = Entangle.held(session, target.id, mental_paralysis=True)
    if hold is None or hold.md <= 0:
        return target
    return _ShieldedMind(target, hold.md)


def ego_escape_dice(ego: int) -> int:
    """Mental Paralysis (6E1 p.219): "The victim uses EGO, not STR, to escape
    ... He rolls 1d6 per 5 points of EGO". Mental Defense adds nothing ("Mental
    Defense neither adds to the character's EGO for purposes of breaking out
    of, nor offers any other protection against, Mental Paralysis"), short of
    the -1/2 Limitation Mental Defense Adds To EGO, which no build here reads.

    The Casual EGO attempt (half EGO) p.219 also allows is not offered: like
    a Casual STR attempt it is a Zero Phase extra (6E1 p.133-134), and the
    loop gives a man one action a Phase.
    """
    return max(0, int(ego) // 5)


@dataclass(frozen=True)
class EntangleHold:
    """One live Entangle on a man, as the log has left it.

    ``mental_paralysis`` says which of the two separate Entangles a man can
    be in this is (6E1 p.219). A physical Entangle defends with ``pd``/``ed``;
    a Mental Paralysis with ``md``.
    """
    body: int
    pd: int
    ed: int
    md: int
    no_teleport: int
    mental_paralysis: bool
    #: Takes No Damage From Attacks (6E1 p.221). A Mental Paralysis "must be
    #: built with" it (6E1 p.219) and breaks with EGO or a Mental Blast, so
    #: it is recorded as ``ALL`` unless the build says ``STR_ONLY``.
    transparency: "Transparency"
    #: Entangle And Character Both Take Damage (6E1 p.220).
    both_take_damage: bool


@dataclass(frozen=True)
class EntangleResult:
    target_id: str
    method: str                          # "applied" | "casual_str" | "full_str"
    damage_to_entangle_body: int
    body_remaining: int
    escaped: bool
    #: What is left of his Phase after a break-out (6E2 p.126, `breakout`):
    #: "full" | "half" | "none". An Entangle applied leaves "none" --- it is
    #: not his Action.
    action_regained: str


class Entangle:
    name: str = "entangle"

    # ------------------------------------------------------------------ apply
    @staticmethod
    def apply(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        entangle_body: int,
        entangle_pd: int,
        entangle_ed: int,
        transparency: Transparency,
        both_take_damage: bool,
        no_teleport_levels: int = 0,
        attack_roll: "dict | None" = None,
    ) -> tuple[CombatSession, EntangleResult]:
        """Apply an entangle to target. Emits ActionDeclared + ActionResolved + EntangleApplied.

        ``attack_roll`` is the Attack Roll that landed it (6E1 p.217), as
        ``targeted_effects.roll_record`` writes it, merged into the row. None
        from a caller whose roll is recorded on a row of its own (an Area's
        use)."""
        from kirby_combat.session.apply import apply_event

        now = datetime.now(timezone.utc)

        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="entangle",
            targets=[target_id],
            parameters={
                "entangle_body": entangle_body,
                "entangle_pd": entangle_pd,
                "entangle_ed": entangle_ed,
                "no_teleport_levels": no_teleport_levels,
            },
        )
        s = apply_event(session, declared)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "entangle_attack",
                "success": True,
                "target_id": target_id,
                **(attack_roll or {}),
            },
        )
        s = apply_event(s, resolved)

        applied = EntangleApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            entangle_body=entangle_body,
            entangle_pd=entangle_pd,
            entangle_ed=entangle_ed,
            no_teleport_levels=no_teleport_levels,
            mental_paralysis=False,
            entangle_md=0,
            transparency=_stated(transparency).value,
            both_take_damage=bool(both_take_damage),
        )
        s = apply_event(s, applied)

        return s, EntangleResult(
            target_id=target_id,
            method="applied",
            damage_to_entangle_body=0,
            body_remaining=entangle_body,
            escaped=False,
            action_regained="none",
        )

    # ------------------------------------------------------------------ apply_mental_paralysis
    @staticmethod
    def apply_mental_paralysis(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        entangle_body: int,
        entangle_md: int,
        transparency: Transparency,
    ) -> tuple[CombatSession, EntangleResult]:
        """Bind ``target_id`` in a Mental Paralysis (6E1 p.219).

        ``transparency``: a Mental Paralysis is built with Takes No Damage
        From Attacks (p.219), so ``ALL`` unless the build bought ``STR_ONLY``
        ("only ... EGO, for Mental Paralysis Entangles", p.221).

        Emits ONLY the `EntangleApplied` --- the MCV Attack Roll and Effect
        Roll that put it there are the mental resolver's own `ActionResolved`.

        "The normal rules for affecting a character with multiple Entangles
        apply to Mental Paralysis, though physical Entangles don't add to
        Mental Paralysis Entangles": a second paralysis stacks onto a live
        one (`stacked_entangle`, 6E1 p.217), a physical one never does.
        """
        from kirby_combat.session.apply import apply_event

        live = Entangle.held(session, target_id, mental_paralysis=True)
        body, md, _ = stacked_entangle(
            live.body if live else 0, live.md if live else 0, live.md if live else 0,
            entangle_body, entangle_md, entangle_md,
        )
        applied = EntangleApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            entangle_body=body,
            entangle_pd=0,
            entangle_ed=0,
            no_teleport_levels=0,
            mental_paralysis=True,
            entangle_md=md,
            transparency=_stated(transparency).value,
            both_take_damage=False,
        )
        s = apply_event(session, applied)
        return s, EntangleResult(
            target_id=target_id, method="applied", damage_to_entangle_body=0,
            body_remaining=body, escaped=False, action_regained="none",
        )

    # ------------------------------------------------------------------ escape_attempt
    @staticmethod
    def escape_attempt(
        session: CombatSession,
        *,
        target_id: str,
        damage_body: int,
        escape_type: str,
    ) -> tuple[CombatSession, EntangleResult]:
        """Attempt to escape an entangle with BODY the CALLER already rolled.

        ``damage_body`` is the escape attempt's counted BODY with the
        Entangle's own defense already applied (escape damage soaks against
        the ENTANGLE's PD/ED, 6E1 p218 -- never the victim's). The margin
        rule decides the outcome (``breakout``, 6E2 p126). escape_type:
        "full" = the Phase's action; "casual" = the 6E1 p133-134 Zero Phase
        half-STR attempt (the caller keeps its action either way -- phase
        economy is the caller's job; this method only moves BODY).

        The PHYSICAL Entangle; a Mental Paralysis is
        `escape_paralysis_attempt`."""
        if escape_type not in ("casual", "full"):
            raise ValueError(f"unknown escape_type: {escape_type!r}")

        method = "casual_str" if escape_type == "casual" else "full_str"
        return Entangle._escape(session, target_id=target_id, damage_body=damage_body,
                                method=method, mental_paralysis=False)

    @staticmethod
    def escape_paralysis_attempt(
        session: CombatSession, *, target_id: str, damage_body: int, method: str,
    ) -> tuple[CombatSession, EntangleResult]:
        """Escape a Mental Paralysis with BODY the caller rolled and already
        soaked against the paralysis's Mental Defense (6E1 p.219): EGO
        (``method="full_ego"``) or a Mental Blast (``"attack"``)."""
        return Entangle._escape(session, target_id=target_id, damage_body=damage_body,
                                method=method, mental_paralysis=True)

    @staticmethod
    def _escape(
        session: CombatSession, *, target_id: str, damage_body: int, method: str,
        mental_paralysis: bool,
    ) -> tuple[CombatSession, EntangleResult]:
        from kirby_combat.session.apply import apply_event

        hold = Entangle.held(session, target_id, mental_paralysis=mental_paralysis)
        if hold is None:
            raise ValueError(f"{target_id} is not entangled; cannot escape")
        current_body = hold.body

        damage = max(0, damage_body)
        res = breakout(damage, current_body or 0)
        escaped = res.escaped
        body_remaining = 0 if escaped else max(0, (current_body or 0) - damage)

        evt = EntangleEscape(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            escaped=escaped,
            mental_paralysis=mental_paralysis,
        )
        s = apply_event(session, evt)

        return s, EntangleResult(
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            body_remaining=body_remaining,
            escaped=escaped,
            action_regained=res.action_regained,
        )

    @staticmethod
    def attacked_from_outside(
        session: CombatSession, *, attacker_id: str, target_id: str,
        damage_body: int, mental_paralysis: bool,
    ) -> tuple[CombatSession, EntangleResult]:
        """Someone else's attack on the Entangle holding ``target_id`` (6E1
        p.218-219), with BODY the caller rolled and already soaked against
        the Entangle's own defense.

        The same `EntangleEscape` row a break-out writes --- it moves the
        same BODY --- authored by the attacker, ``method="outside_attack"``.
        Destroyed when the BODY reaches the Entangle's remaining BODY (6E1
        p.218: "When he reduces the Entangle's BODY to 0, he is free"). The
        man inside gains no Action by it: it was not his.
        """
        from kirby_combat.session.apply import apply_event

        hold = Entangle.held(session, target_id, mental_paralysis=mental_paralysis)
        if hold is None:
            raise ValueError(f"{target_id} is not entangled; there is nothing to attack")
        damage = max(0, int(damage_body))
        escaped = damage >= hold.body
        s = apply_event(session, EntangleEscape(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(attacker_id),
            target_id=target_id, method="outside_attack",
            damage_to_entangle_body=damage, escaped=escaped,
            mental_paralysis=mental_paralysis,
        ))
        return s, EntangleResult(
            target_id=target_id, method="outside_attack",
            damage_to_entangle_body=damage,
            body_remaining=0 if escaped else hold.body - damage,
            escaped=escaped, action_regained="none",
        )

    # ------------------------------------------------------------------ teleport_escape
    @staticmethod
    def teleport_escape(
        session: CombatSession,
        *,
        target_id: str,
        teleport_ap_levels: int = 0,
    ) -> tuple[CombatSession, EntangleResult]:
        """Escape the entangle by Teleporting out of it.

        6E1 p218 lists Teleportation among an Entangle's escape routes; it
        needs no Attack Roll and does no BODY to the Entangle — the victim is
        simply elsewhere. 6E1 p220: an Entangle bought with Cannot Be Escaped
        With Teleportation refuses it, unless the Teleportation carries at
        least as many levels of Armor Piercing (``teleport_ap_levels``, from
        ``armor_piercing_levels`` on the escaper's TELEPORTATION power).

        A blocked attempt emits NO event and returns ``escaped=False`` with
        ``method="teleport_blocked"`` — nothing changed; callers should not
        have offered it (gate with ``can_teleport_escape``)."""
        from kirby_combat.session.apply import apply_event

        # The PHYSICAL Entangle only: from a Mental Paralysis a man may
        # Teleport, "but if so remains subject to the Mental Paralysis when
        # he appears at his destination" (6E1 p.219).
        hold = Entangle.held(session, target_id, mental_paralysis=False)
        if hold is None:
            raise ValueError(f"{target_id} is not entangled; cannot escape")
        current_body = hold.body
        ntl = hold.no_teleport

        if ntl > teleport_ap_levels:
            return session, EntangleResult(
                target_id=target_id,
                method="teleport_blocked",
                damage_to_entangle_body=0,
                body_remaining=current_body or 0,
                escaped=False,
                action_regained="none",
            )

        evt = EntangleEscape(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            method="teleport",
            damage_to_entangle_body=0,
            escaped=True,
            mental_paralysis=False,
        )
        s = apply_event(session, evt)
        return s, EntangleResult(
            target_id=target_id,
            method="teleport",
            damage_to_entangle_body=0,
            body_remaining=0,
            escaped=True,
            # Its time is the Half Move it is (`action_time.KIND_TIMES`).
            action_regained="half",
        )

    # ------------------------------------------------------------------ is_entangled
    @staticmethod
    def is_entangled(
        session: CombatSession, combatant_id: str,
    ) -> tuple[bool, Optional[int]]:
        """Whether ANY Entangle holds ``combatant_id`` --- physical or a Mental
        Paralysis, both of which are Entangles (6E1 p.219) with the same
        effects on him (DCV 0, escape first, p.217).

        Returns (True, body_remaining) when entangled --- the physical
        Entangle's BODY when there is one, else the paralysis's ---
        and (False, None) when not. Ask `held` for one Entangle by kind.
        """
        for paralysis in (False, True):
            hold = Entangle.held(session, combatant_id, mental_paralysis=paralysis)
            if hold is not None:
                return True, hold.body
        return False, None

    # ------------------------------------------------------------------ held
    @staticmethod
    def held(
        session: CombatSession, combatant_id: str, *, mental_paralysis: bool,
    ) -> Optional[EntangleHold]:
        """The live Entangle of one kind on ``combatant_id``, or None.

        Folded forward from `EntangleApplied` / `EntangleEscape`, each kind
        on its own (6E1 p.219: the two never add to each other).
        """
        hold: Optional[EntangleHold] = None
        for evt in session.event_log:
            kind = evt.kind
            if getattr(evt, "target_id", None) != combatant_id:
                continue
            if kind not in ("EntangleApplied", "EntangleEscape"):
                continue
            if bool(getattr(evt, "mental_paralysis", False)) != mental_paralysis:
                continue
            if kind == "EntangleApplied":
                hold = EntangleHold(
                    body=int(evt.entangle_body), pd=int(evt.entangle_pd),
                    ed=int(evt.entangle_ed), md=int(getattr(evt, "entangle_md", 0)),
                    no_teleport=int(getattr(evt, "no_teleport_levels", 0) or 0),
                    mental_paralysis=mental_paralysis,
                    transparency=Transparency(evt.transparency),
                    both_take_damage=bool(evt.both_take_damage),
                )
            elif hold is not None:
                body = 0 if evt.escaped else max(0, hold.body - evt.damage_to_entangle_body)
                hold = EntangleHold(**{**hold.__dict__, "body": body})
            if hold is not None and hold.body <= 0:
                hold = None
        return hold

    # ------------------------------------------------------------------ modifiers
    @staticmethod
    def modifiers(
        session: CombatSession, combatant_id: str,
    ) -> dict:
        """Return OCV/DCV multipliers while entangled; empty dict otherwise.

        Per Dorman + HERO 6E2: entangled characters have 0 DCV and 1/2 OCV.
        Modeled as multiplicative factors so callers compose: effective_dcv =
        base_dcv * dcv_factor; effective_ocv = base_ocv * ocv_factor.
        """
        is_e, _ = Entangle.is_entangled(session, combatant_id)
        return ({"ocv_factor": 0.5, "dcv_factor": ENTANGLED_DCV_FACTOR}
                if is_e else {})
