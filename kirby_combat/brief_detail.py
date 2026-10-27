"""What the page says about each person, and what bears on this Phase.

WHY THIS EXISTS. The fight's page used to be built outside this engine, by a
situation builder and a page renderer in the consumer that the 2026-09-17
harness refactor deleted. That page carried, per combatant: SPD, PD/ED and
their resistant halves, PRE, EGO, OMCV/DMCV, MD and INT; the character's
powers by their authored names; a health and status rung; held actions;
attacks already taken this Turn; Mind Control, Mental Illusion and Entangle
state; Damage Reduction and Negation; Drains and Aids; Trigger and Limited
Power texts; and every combatant's complications. After it, per enemy, a
reach-or-range line with elevation and the movement mode that closes; a
speed-and-toughness matchup; the mental-lock line for a mind you can reach
but cannot see; the Flashed and can't-swim warnings; and the frameworks
block. The engine's own Brief kept STUN, BODY, END, OCV, DCV, role and DOWN.
Everything else had gone, and a reader was choosing blind to most of what
the rules were about to use against it.

This module is the port. Each section reads a fold or a view the rules
already use --- `statuses_for`, `entangle_state`, `adjustments_for`,
`HeldAction.get_pending`, `continuing_effects`, `perceive`, `movement_reach`,
`framework_view`, `allocation_for` --- and derives no rule of its own.

FACTS, NOT ADVICE. The old page told its reader what to do ("close and
trade", "do NOT trade blows", "press a melee fight"). That is judgement, and
judgement is not the rules engine's to give: this page states what is so and
what is offered, and a chooser elsewhere decides what it means. So the
matchup section says how hard each side hits and who acts more often; the
reach section says who is in reach and which of your movement modes gets
there; neither says what to do about it.

WHAT YOU CANNOT PERCEIVE YOU CANNOT READ. The anti-metagaming line in this
engine is perception (`kirby_combat.perception`). An enemy the actor
perceives --- physically, or mentally through a Mind Scan lock --- is shown
as freely as the actor: the old page did exactly that, and withholding some
numbers from a man you are looking at would be inconsistent rather than
principled. An enemy he cannot perceive at all is named, and nothing about
his condition is: his STUN, his Entangle and his held action are things you
learn by looking.

THE PAGE NEVER ROLLS. Perceiving a hidden or Invisible man can be a contest
(a Fringe PER roll, Stealth against PER --- 6E1 p.340, 6E2 p.13). The menu
already made that roll when it was enumerated; rolling it again here could
give a different answer, and the page would then contradict the menu it
lists. So where `perceive` would roll, this reads the menu instead: he is
perceived iff an offer the perception gate keeps names him.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.loop.chooser import PhaseSituation


# ─────────────────────────────────────────────────────────────────────────
# Perception, without dice
# ─────────────────────────────────────────────────────────────────────────

class _WouldRoll(Exception):
    """`perceive` asked for dice. The menu holds the answer instead."""


class _NoDice:
    """A roller that refuses. See the module docstring: the page never rolls."""

    def roll_dice(self, count, sides=6):
        raise _WouldRoll()

    def roll(self, *args, **kwargs):
        raise _WouldRoll()


@dataclass(frozen=True)
class Sighting:
    """What the actor perceives of one enemy, as the menu's gate does."""

    enemy_id: str
    #: A Targeting Sense reaches him: physical offers against him survive.
    physical: bool
    #: His mind is in reach: sight gives that, and so does a Mind Scan lock.
    mental: bool
    #: Mental reach comes ONLY through a Mind Scan lock (6E1 p.263-265).
    through_lock: bool

    @property
    def perceived(self) -> bool:
        return self.physical or self.mental


def _gate_kinds() -> tuple[frozenset[str], frozenset[str]]:
    """The kinds the perception gate treats as mental, and the movement
    kinds it lets through ungated. Read from enumeration, not restated, so
    the page and the gate cannot disagree about a kind."""
    from kirby_combat.enumeration import _MENTAL_ACTION_KINDS, _MOVEMENT_ACTION_KINDS

    return _MENTAL_ACTION_KINDS, _MOVEMENT_ACTION_KINDS


def sightings(situation: "PhaseSituation") -> dict[str, Sighting]:
    """Every enemy's and every standing ally's `Sighting`, keyed by id.

    The same inputs `run_phase` hands the menu's gate --- the scene, the
    concealment map folded from the fight, the Mind Scan locks --- so the
    two answer the same question the same way.
    """
    from kirby_combat.concealment import concealment_for
    from kirby_combat.mental.continuing import mind_scan_locks
    from kirby_combat.perception import perceive
    from kirby_combat.sense_penalties import as_sensing_observer

    session = situation.session
    actor = situation.actor
    scene = getattr(session, "scene", None) if session is not None else None
    conceal = (concealment_for(session, observer_id=actor.id)
               if session is not None else {})
    locks = mind_scan_locks(session, actor.id) if session is not None else frozenset()
    observer = as_sensing_observer(actor)

    out: dict[str, Sighting] = {}
    # Allies too: an Invisible friend is as unseen as an Invisible foe.
    for enemy in [*situation.enemies, *situation.allies]:
        invisible, hidden = conceal.get(enemy.id, (False, False))
        locked = enemy.id in locks
        try:
            p = perceive(
                observer, enemy, scene,
                target_invisible=bool(invisible), target_hidden=bool(hidden),
                mind_scan_locked=locked, roller=_NoDice(),
            )
        except _WouldRoll:
            out[enemy.id] = _sighting_from_menu(situation, enemy.id, locked)
            continue
        out[enemy.id] = Sighting(
            enemy_id=enemy.id,
            physical=bool(p.targetable_physical),
            mental=bool(p.targetable_mental),
            through_lock=bool(p.targetable_mental) and not p.targetable_physical,
        )
    return out


def _sighting_from_menu(situation, enemy_id: str, locked: bool) -> Sighting:
    """The contest's answer, read off the offers it left standing.

    A movement offer names a man without perceiving him (the gate passes
    those untouched), and a ``blind`` offer is the gate saying he is NOT
    perceived and is being struck at anyway, so neither counts as seeing.
    """
    mental_kinds, movement_kinds = _gate_kinds()
    named = [a for a in situation.menu
             if a.target_id == enemy_id and not getattr(a, "targets_construct", False)
             and a.kind not in movement_kinds]
    physical = any(a.kind not in mental_kinds and not getattr(a, "blind", False)
                   for a in named)
    mental = physical or any(a.kind in mental_kinds for a in named)
    return Sighting(enemy_id=enemy_id, physical=physical, mental=mental,
                    through_lock=mental and not physical and locked)


def perception_lines(situation: "PhaseSituation",
                     seen: dict[str, Sighting]) -> list[str]:
    """One line per enemy the actor cannot target physically.

    A clear view is the ordinary case and says nothing worth a line; the
    old page left those out too. What it carried, and what this carries,
    is the two cases a reader would otherwise get wrong: a mind you can
    reach through a Mind Scan lock though you cannot see the man (6E1
    p.265), and a man you cannot perceive at all, who is not a legal target
    for anything that needs to perceive him.
    """
    out: list[str] = []
    for enemy in situation.enemies:
        s = seen.get(enemy.id)
        if s is None or s.physical:
            continue
        name = _name(enemy)
        if s.mental:
            out.append(
                f"{name}: out of sight, so no physical attack reaches him; "
                f"his mind is in reach through your Mind Scan lock (6E1 p.265)"
                if s.through_lock else
                f"{name}: out of sight, so no physical attack reaches him; "
                f"his mind is in reach"
            )
        else:
            out.append(
                f"{name}: you cannot perceive him; nothing that needs to "
                f"perceive its target is offered against him"
            )
    return out


# ─────────────────────────────────────────────────────────────────────────
# One combatant
# ─────────────────────────────────────────────────────────────────────────

def _name(combatant) -> str:
    return getattr(combatant, "name", None) or combatant.id


def _stat(stats, name: str) -> int:
    return int(getattr(stats, name, 0) or 0)


#: Powers shown by their authored names, at most this many per combatant.
#: The old page's cap, for its reason: Slug carries 27 named powers, and a
#: page shared by ten combatants is not improved by one of them owning it.
MAX_POWER_NAMES = 8

#: How many of a combatant's complications, Limited Power texts and Trigger
#: conditions are listed before the rest are counted.
MAX_LISTED = 6


def stat_line(combatant) -> str:
    """The numbers the rules use against and for this combatant, beyond
    the vitals and CVs the head of the line already carries.

    SPD says how often he acts; PD/ED with their resistant halves say what
    gets through; PRE is the number a Presence Attack is measured against
    (6E2 p.138); EGO, OMCV, DMCV and MD say whether a mind is worth
    attacking and whether he can attack one; INT makes his INT Roll.
    """
    s = combatant.combat_stats()
    return (
        f"SPD {_stat(s, 'spd')}, PD {_stat(s, 'pd')}/{_stat(s, 'rpd')}r, "
        f"ED {_stat(s, 'ed')}/{_stat(s, 'red')}r, PRE {_stat(s, 'pre')}, "
        f"EGO {_stat(s, 'ego')}, OMCV {_stat(s, 'omcv')}/DMCV {_stat(s, 'dmcv')}, "
        f"MD {_stat(s, 'md')}, INT {_stat(s, 'int_')}"
    )


def power_names(combatant) -> list[str]:
    """The character's powers by the names their designer wrote.

    80% of corpus villain powers carry one --- 'Devolutionized Body',
    'Eyes In The Darkness' --- and a name is the character in a nutshell.
    Recursive into frameworks and compound powers; a name shared by several
    pieces (PD, ED and a modifier all called 'Body Like Iron') is listed
    once.
    """
    names: list[str] = []
    seen: set[str] = set()

    def walk(powers) -> None:
        for p in powers or ():
            n = (getattr(p, "name", None) or "").strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                names.append(n)
            walk(getattr(p, "sub_powers", None))

    walk(getattr(getattr(combatant, "hero", None), "powers", None))
    return names


def _capped(items: list[str], cap: int) -> str:
    shown = items[:cap]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; +{more} more" if more > 0 else "")


def _modifiers(power) -> list:
    return list(getattr(power, "assigned_modifiers", None)
                or getattr(power, "modifiers", None) or [])


def _walk_powers(combatant):
    seen: set[int] = set()

    def walk(powers):
        for p in powers or ():
            if id(p) in seen:
                continue
            seen.add(id(p))
            yield p
            yield from walk(getattr(p, "sub_powers", None))

    yield from walk(getattr(getattr(combatant, "hero", None), "powers", None))


def trigger_conditions(combatant) -> list[str]:
    """What sets off each Triggered power (6E1 p.364), as the sheet words it."""
    out: list[str] = []
    for p in _walk_powers(combatant):
        for m in _modifiers(p):
            if (getattr(m, "xmlid", "") or "").upper() != "TRIGGER":
                continue
            cond = (getattr(m, "input_value", None) or getattr(m, "input", None)
                    or getattr(m, "notes", None) or "").strip()
            label = (getattr(p, "name", None) or getattr(p, "xmlid", "") or "").strip()
            out.append(f"{label}: {cond}" if cond else label)
    return out


def limited_powers(combatant) -> list[str]:
    """Each Limited Power limitation's text (6E1 p.384), ``power: text``.

    A Limited Power is restricted "in some way defined by character", so
    its text IS the rule, and only the sheet knows it. A limitation with
    no text says nothing a reader could act on and is left out.
    """
    out: list[str] = []
    for p in _walk_powers(combatant):
        for m in _modifiers(p):
            if (getattr(m, "xmlid", "") or "").upper() != "LIMITEDPOWER":
                continue
            alias = (getattr(m, "alias", None) or "").strip()
            notes = (getattr(m, "notes", None) or "").strip()
            text = (getattr(m, "input_value", None) or getattr(m, "input", None) or "").strip()
            said = f"{alias}: {notes}" if alias and notes else (text or notes)
            if not said:
                continue
            label = (getattr(p, "name", None) or getattr(p, "xmlid", "") or "").strip()
            out.append(f"{label}: {said}")
    return out


def reductions(combatant) -> list[str]:
    """Damage Reduction and Damage Negation, from the defenses the damage
    roll reads (6E1 p.185, p.186)."""
    out: list[str] = []
    for d in combatant.defense_view() if hasattr(combatant, "defense_view") else []:
        # An empty class is what `resolution/defense.py` applies to EVERY
        # class, so the page says so rather than guessing which one the
        # sheet meant.
        cls = getattr(d, "damage_class", "") or "any class"
        if getattr(d, "damage_reduction_pct", 0):
            resistant = "resistant" if getattr(d, "dr_resistant", True) else "normal"
            line = f"Damage Reduction {d.damage_reduction_pct}% vs {cls} ({resistant})"
        elif getattr(d, "damage_negation", 0):
            line = f"Damage Negation -{d.damage_negation} DC vs {cls}"
        else:
            continue
        if line not in out:
            out.append(line)
    return out


def _complication_label(comp) -> str:
    """One complication, in the labels the actor's own "What drives you"
    section uses --- one vocabulary for the actor and the people he faces."""
    from kirby_combat.brief import _KINDS, _readable

    text = (getattr(comp, "name", "") or getattr(comp, "alias", "")
            or getattr(comp, "notes", "")).strip()
    severity = (getattr(comp, "adders", None) or {}).get("INTENSITY")
    if severity:
        text = f"{text} ({severity.title()})"
    return f"{_KINDS.get(comp.xmlid, _readable(comp.xmlid))}: {text}" if text else ""


def complication_lines(combatant) -> list[str]:
    from kirby_combat.complications import complications_of

    return [line for line in (_complication_label(c) for c in complications_of(combatant))
            if line]


#: Statuses that are conditions a reader can SEE, in reading order, with the
#: words the page uses. Entangled and Holding have lines of their own with
#: their numbers; Flashed is the actor's own warning, and is not something
#: you can see on another man.
def _status_words(session, combatant_id: str) -> list[str]:
    from kirby_combat import statuses as st

    have = st.statuses_for(session, combatant_id)
    words = [
        (st.DEAD, "dead"),
        (st.KNOCKED_OUT, "knocked out"),
        (st.STUNNED, "Stunned (6E2 p.106)"),
        (st.RECOVERING_FROM_STUNNED, "recovering from being Stunned (6E2 p.107)"),
        (st.PRONE, "prone"),
        (st.GRAB, "grabbed"),
        (st.ABORTED, "aborted to a defensive action"),
    ]
    return [w for key, w in words if key in have]


def _attacks_this_turn(session, combatant_id: str) -> int:
    """Attacks resolved against him since this Turn began.

    The Turn begins at the last ``SegmentAdvanced`` out of Segment 12 (6E2
    p.18). An attack is a resolution whose payload names him as its target
    and says whether it hit --- counted hit or miss, because being shot at
    is what it witnesses.
    """
    start = 0
    log = list(getattr(session, "event_log", None) or [])
    for i, evt in enumerate(log):
        if getattr(evt, "kind", None) == "SegmentAdvanced" and getattr(evt, "from_segment", 0) == 12:
            start = i
    count = 0
    for evt in log[start:]:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        p = getattr(evt, "result_payload", None) or {}
        if p.get("target_id") == combatant_id and "hit" in p:
            count += 1
    return count


def condition_lines(session, combatant, *, viewer_id: str) -> list[str]:
    """What is happening TO this combatant, as the fight's folds record it.

    Each line reads the fold the rules themselves read, so the page cannot
    say a man is Entangled when the escape ladder thinks otherwise.

    WHAT ONLY THE CASTER KNOWS. Mental Powers "are by default invisible"
    (6E1 p.151): a man under Mind Control, or believing a Mental Illusion,
    looks like a man making his own choices. So those two are shown on
    another man's line only to the one who cast them. Mental Paralysis is
    an Entangle bought as a Mental Power (6E1 p.219) and is shown to its
    victim, who knows he cannot move, and to nobody else.
    """
    if session is None:
        return []
    from kirby_combat.actions.entangle import Entangle
    from kirby_combat.actions.held_action import HeldAction
    from kirby_combat.mental.continuing import continuing_effects
    from kirby_combat.session.effects import adjustments_for, presence_state

    cid = combatant.id
    out: list[str] = []
    is_self = cid == viewer_id

    physical = Entangle.held(session, cid, mental_paralysis=False)
    if physical is not None:
        out.append(
            f"Entangled: BODY {physical.body}, DEF {physical.pd}/{physical.ed}; "
            f"DCV 0 while held (6E1 p.217)"
        )
    if is_self:
        paralysis = Entangle.held(session, cid, mental_paralysis=True)
        if paralysis is not None:
            out.append(
                f"Mentally Paralysed: BODY {paralysis.body}, MD {paralysis.md}; "
                f"no mental powers until free (6E1 p.219)"
            )

    for adj in adjustments_for(session, cid):
        word = "aided" if adj.net_delta > 0 else "drained"
        out.append(f"{adj.stat} {word} {adj.net_delta:+d}")

    pa = presence_state(session, cid)
    if pa.is_active:
        out.append(f"Presence Attack: {pa.tier} (6E2 p.138)")

    for held in HeldAction.get_pending(session, cid):
        what = getattr(held, "for_action", None)
        trigger = (getattr(held, "trigger_condition", "") or "").strip()
        bits = "holding an action"
        if what:
            bits += f" ({what})"
        if trigger:
            bits += f" until: {trigger}"
        out.append(bits)

    taken = _attacks_this_turn(session, cid)
    if taken:
        out.append(f"attacked {taken} time{'s' if taken != 1 else ''} this Turn")

    if not is_self:
        for effect in continuing_effects(session):
            if effect.target_id != cid or effect.attacker_id != viewer_id:
                continue
            if effect.kind == "mind_control":
                obeying = "obeying" if effect.attempts else "not yet obeying"
                out.append(f"under your Mind Control, order {effect.order!r} "
                           f"({obeying}; 6E1 p.258)")
            elif effect.kind == "mental_illusion":
                from kirby_combat.mental.mental_illusion import illusion_named

                believes = "believes" if effect.attempts else "has not yet tested"
                out.append(f"{believes} your Mental Illusion: "
                           f"{illusion_named(effect.illusion).shows}")
    return out


def identity_line(combatant) -> str | None:
    """Which identity he is in, for a character the question matters to.

    Only a character who bought something Only In Alternate Identity (HD's
    ``OIHID``, 6E1 p.388) has an identity worth naming: those purchases
    work in one of them only, and `combat_stats` reads them through
    ``state.in_hero_id``. A costume is a thing you see.
    """
    from kirby_cost.model.modifiers import has_modifier

    bound = [p for p in _walk_powers(combatant) if has_modifier(p, "OIHID")]
    if not bound:
        return None
    where = "in his Hero identity" if combatant.state.in_hero_id else "out of his Hero identity"
    return (f"{where}; {len(bound)} of his purchases work only in it "
            f"(Only In Alternate Identity, 6E1 p.388)")


def sheet_lines(combatant) -> list[str]:
    """What the character sheet says about him that the rules read: his
    powers by name, his reductions, and the texts of his Triggers and
    Limited Powers."""
    out: list[str] = []
    identity = identity_line(combatant)
    if identity:
        out.append(identity)
    names = power_names(combatant)
    if names:
        shown = names[:MAX_POWER_NAMES]
        more = len(names) - len(shown)
        out.append("powers: " + ", ".join(shown) + (f", +{more} more" if more > 0 else ""))
    red = reductions(combatant)
    if red:
        out.append("; ".join(red))
    triggers = trigger_conditions(combatant)
    if triggers:
        out.append("Triggered: " + _capped(triggers, MAX_LISTED))
    limited = limited_powers(combatant)
    if limited:
        out.append("Limited Power: " + _capped(limited, MAX_LISTED))
    return out


def health_words(session, combatant) -> list[str]:
    """The health rung and the visible conditions.

    The rung is `health.classify_health` --- this engine's own half-STUN
    and quarter-STUN judgement, stated once there and read by every
    consumer, the narrator and the tactics included. A page that computed
    its own would be the seventh copy that module exists to prevent.
    """
    from kirby_combat.health import classify_health

    words = [classify_health(combatant)]
    if session is not None:
        words.extend(_status_words(session, combatant.id))
    return words


def detail_lines(situation: "PhaseSituation", combatant, *,
                 complications: bool) -> list[str]:
    """Everything below the head line for one perceived combatant.

    ``complications`` is False for the actor, whose own section ("What
    drives you") already lists them in full.
    """
    session = situation.session
    lines = [stat_line(combatant), "condition: " + ", ".join(health_words(session, combatant))]
    lines.extend(condition_lines(session, combatant, viewer_id=situation.actor.id))
    lines.extend(sheet_lines(combatant))
    if complications:
        comps = complication_lines(combatant)
        if comps:
            lines.append("complications: " + _capped(comps, MAX_LISTED))
    return lines


# ─────────────────────────────────────────────────────────────────────────
# The actor's own situation
# ─────────────────────────────────────────────────────────────────────────

def order_lines(situation: "PhaseSituation") -> list[str]:
    """The Mind Control order the actor is obeying, and what it does to
    his menu.

    WHY THE PAGE SAYS SO. The engine bends his Phase to the order
    (`mental/continuing.obey`): under ``spare`` the controller's side drops
    off his list of enemies, under ``turn`` his own side becomes it, under
    ``withdraw`` the menu is cut to what fleeing allows (6E1 p.256). A
    reader shown that menu with no reason for it sees a fight that has
    stopped making sense.

    RULING: the page is the player's, not the character's. 6E1 p.255 says
    the target "won't know he's experiencing Mind Control until he succeeds
    with a Breakout Roll" --- the CHARACTER does not know. The player at a
    table is told the command his character must carry out, and 6E1 p.258
    has him choose how: "he has to fight as effectively as he does when
    he's under his own control". This is that telling, and no more: it
    names the order and its effect, and it does not hand the choice to the
    controller.

    CORRECTED FROM THE OLD PAGE, which told its reader "This combatant is
    YOUR PUPPET ... as controller you may target either side" and graded
    the instruction by degree (ego_push / simple / contrary / violent).
    The engine since 0.21 gives Mind Control an ORDER chosen when it lands,
    obeyed after a failed Breakout Roll (6E1 p.258), and the victim keeps
    his own chooser. A page telling him to act as the controller would
    describe a rule the engine does not run.
    """
    session = situation.session
    if session is None:
        return []
    from kirby_combat.mental.continuing import mind_control_orders

    out: list[str] = []
    for effect in mind_control_orders(session, situation.actor.id):
        controller = session.combatants.get(effect.attacker_id)
        who = _name(controller) if controller is not None else effect.attacker_id
        if effect.order == "spare":
            out.append(
                f"You are under orders (Mind Control, 6E1 p.256): leave {who} "
                f"and his side alone. Nobody on that side is listed as your enemy."
            )
        elif effect.order == "turn":
            out.append(
                "You are under orders (Mind Control, 6E1 p.256): attack your own "
                "side. Your side-mates are listed as your enemies, and you have no allies."
            )
        elif effect.order == "withdraw":
            out.append(
                "You are under orders (Mind Control, 6E1 p.256): flee the combat. "
                "Nothing that attacks anybody is on your menu."
            )
        else:
            raise ValueError(
                f"Mind Control order {effect.order!r} has no wording on the page; "
                f"add it to brief_detail.order_lines"
            )
    return out


#: Metres within which a hazard zone is worth a warning even when you are
#: not in it: the old page's figure, and roughly one Phase of Running.
HAZARD_NEAR_M = 10.0


def warning_lines(situation: "PhaseSituation") -> list[str]:
    """The two conditions the old page put in capitals: your senses are
    Flashed, and deep water you cannot survive is underfoot or near.

    Facts, not instructions. The old Flash warning went on to say "press a
    melee fight ... or wait to recover"; that is a reader's call, and the
    rules part --- you perceive nothing through that group --- is what is
    kept.
    """
    session = situation.session
    if session is None:
        return []
    from kirby_combat.actions.flash import Flash

    out: list[str] = []
    actor = situation.actor
    _, flashed = Flash.is_flashed(session, actor.id)
    for group, segments in sorted(flashed.items()):
        out.append(
            f"You are Flashed in the {group.title()} Group for {segments} more "
            f"Segment{'s' if segments != 1 else ''} (6E1 p.228): you perceive "
            f"nothing through it, and an opponent you cannot perceive another way "
            f"carries 6E2 p.9's penalties."
        )
    out.extend(_drowning(session, actor))
    return out


def _drowning(session, actor) -> list[str]:
    """Deep water the actor is in or near and cannot survive.

    A suffocation zone is decided by `construct_effects.resolve_construct_effect`:
    Life Support's Self-Contained Breathing is immune and a swimmer treads
    water, so only a man with neither is warned --- the same test, asked of
    the same two methods.
    """
    scene = getattr(session, "scene", None)
    if scene is None:
        return []
    from kirby_world.construct import constructs_containing
    from kirby_world.occupancy import position_of

    here = position_of(scene, actor.id)
    if here is None:
        return []
    zones = [c for c in (getattr(scene, "constructs", None) or [])
             if c.kind == "hazard_zone" and c.effect is not None
             and c.effect.kind == "suffocation"]
    if not zones:
        return []
    if actor.has_self_contained_breathing() or actor.can_swim():
        return []
    inside = {id(c) for c in constructs_containing(here, zones)}
    out: list[str] = []
    for zone in zones:
        if id(zone) in inside:
            where = "you are in it"
        else:
            poly = zone.polygon_xy or []
            if not poly:
                continue
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            d = ((here.x - cx) ** 2 + (here.y - cy) ** 2) ** 0.5
            if d > HAZARD_NEAR_M:
                continue
            where = f"{d:.0f}m away"
        out.append(f"Deep water ({zone.obj_id}): {where}. You cannot swim and you "
                   f"need to breathe.")
    return out


# ─────────────────────────────────────────────────────────────────────────
# Reach, elevation and the movement that closes
# ─────────────────────────────────────────────────────────────────────────

def reach_lines(situation: "PhaseSituation", seen: dict[str, Sighting]) -> list[str]:
    """Per perceived enemy: within reach, a half-move away, or neither ---
    and when neither, how far up or down he is and which of your movement
    modes reaches him this Phase.

    Reach is the engine's (`combat_stats().reach_m`, 6E2 p.56 plus
    Stretching) and the band is `within_reach`, the question the melee
    gate itself asks. The movement modes are asked through `movement_reach`
    with the full combat move, the same call the menu's movement block
    makes, so the page never names a mode the menu would refuse.
    """
    session = situation.session
    scene = getattr(session, "scene", None) if session is not None else None
    if scene is None:
        return []
    from kirby_combat.actions.reach import within_reach
    from kirby_combat.enumeration import is_down
    from kirby_combat.reach import movement_reach
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    actor = situation.actor
    here = position_of(scene, actor.id)
    if here is None:
        return []
    reach = float(actor.combat_stats().reach_m)
    modes = {}
    for cap in actor.movement_view():
        if cap.combat_m > modes.get(cap.mode, 0.0):
            modes[cap.mode] = float(cap.combat_m)
    half_run = modes.get("running", 0.0) / 2.0

    out: list[str] = []
    for enemy in situation.enemies:
        if is_down(enemy) or not seen[enemy.id].perceived:
            continue
        there = position_of(scene, enemy.id)
        if there is None:
            continue
        d = distance_3d(here, there)
        verdict = within_reach(d, reach)
        name = _name(enemy)
        if verdict.in_reach:
            out.append(f"{name}: {d:.1f}m, within your {reach:.0f}m reach")
            continue
        if half_run >= verdict.shortfall_m:
            out.append(f"{name}: {d:.1f}m; a half-move of Running ({half_run:.0f}m) "
                       f"brings him within reach")
            continue
        dz = there.z - here.z
        elev = (f", {dz:.0f}m above you" if dz >= 1.0
                else f", {-dz:.0f}m below you" if dz <= -1.0 else "")
        reaching = []
        for mode, metres in sorted(modes.items(), key=lambda kv: kv[1]):
            if mode == "running":
                continue
            outcome = movement_reach(mode, here, there, metres, scene,
                                     combatant_id=actor.id, session=session)
            if outcome.reachable:
                reaching.append(f"{mode.title()} ({metres:.0f}m)")
        if reaching:
            out.append(f"{name}: {d:.1f}m{elev}; Running does not close, "
                       f"{' or '.join(reaching)} reaches him this Phase")
        else:
            out.append(f"{name}: {d:.1f}m{elev}; none of your movement reaches "
                       f"him this Phase")
    return out


# ─────────────────────────────────────────────────────────────────────────
# The matchup
# ─────────────────────────────────────────────────────────────────────────

#: The average of one d6 (STUN per die of a normal attack). A blunt measure
#: of a hit, the same one `enumeration._is_fragile_vs` uses, so the facts on
#: the page are the ones the defensive-reposition offer was decided on.
_STUN_PER_DIE = 3.5


def matchup_lines(situation: "PhaseSituation", seen: dict[str, Sighting]) -> list[str]:
    """Speed and toughness against the most dangerous perceived enemy.

    The old page drew two conclusions from these numbers: "kite and
    grapple" for a faster fighter one hit could ruin, "close and trade" for
    a slower one who could not be hurt. The conclusions were advice and
    stay out; the numbers they were drawn from are facts and are here ---
    who acts more often, what each side's heaviest attack averages through
    the other's worst defense, and what share of a STUN track that is.
    Shown only when one of the two old asymmetries holds, as before, so an
    even fight carries no line.
    """
    from kirby_combat.enumeration import _biggest_attack_dice, _is_fragile_vs, is_down

    actor = situation.actor
    candidates = [e for e in situation.enemies
                  if not is_down(e) and seen[e.id].perceived]
    if not candidates:
        return []
    enemy = max(candidates, key=_biggest_attack_dice)
    a, e = actor.combat_stats(), enemy.combat_stats()
    a_def = min(a.pd + a.rpd, a.ed + a.red)
    e_def = min(e.pd + e.rpd, e.ed + e.red)
    a_stun = max(1, int(a.max_stun))
    e_net = max(0.0, _biggest_attack_dice(enemy) * _STUN_PER_DIE - a_def)
    a_net = max(0.0, _biggest_attack_dice(actor) * _STUN_PER_DIE - e_def)
    slower = a.spd < e.spd or (a.spd == e.spd and a.dex < e.dex)
    name = _name(enemy)

    if _is_fragile_vs(actor, enemy):
        tools = []
        try:
            maneuvers = list(actor.maneuver_view())
        except AttributeError:
            maneuvers = []
        dodges = [m.name for m in maneuvers if getattr(m, "is_dodge", False)]
        throws = [m.name for m in maneuvers if getattr(m, "target_falls", False)]
        if dodges:
            tools.append(f"a Dodge ({', '.join(dodges)})")
        if throws:
            tools.append(f"a throw ({', '.join(throws)})")
        return [
            f"{name} acts less often than you (SPD {e.spd} to your {a.spd}); "
            f"his heaviest attack averages about {e_net:.0f} STUN through your "
            f"worst defense of {a_def}, {100 * e_net / a_stun:.0f}% of your "
            f"{a_stun} STUN in one hit. You have {' and '.join(tools)}."
        ]
    if slower and (e_net / a_stun) < 0.18 and a_net > 0:
        return [
            f"{name} acts at least as often as you (SPD {e.spd} to your {a.spd}); "
            f"his heaviest attack averages about {e_net:.0f} of your {a_stun} STUN "
            f"through your defense, and yours about {a_net:.0f} through his."
        ]
    return []


# ─────────────────────────────────────────────────────────────────────────
# Frameworks
# ─────────────────────────────────────────────────────────────────────────

_FRAMEWORK_KINDS = {
    "multipower": ("Multipower", "reserve"),
    "elemental_control": ("Elemental Control", "pool"),
    "vpp": ("Variable Power Pool", "pool"),
}


def framework_lines(situation: "PhaseSituation") -> list[str]:
    """The actor's frameworks: reserve or pool, each slot with its cost and
    whether it is fixed or variable, which are switched on in this fight,
    and the attack a slot fires --- its dice and, for an NND, the defense
    that stops it (6E1 p.328).

    The old page said "~Nd6" for every slot by dividing Active Points by
    five, which is the damage of a Blast and the damage of nothing else; a
    slot that is an attack now reports the attack's own dice from the view
    resolution uses, and a slot that is not reports its Active Points.

    Switching slots and rebuilding a pool are named only when the menu
    offers them, because an offer that is not on the menu is not a fact
    about this Phase.
    """
    from kirby_combat.framework import allocation_for

    actor = situation.actor
    views = list(getattr(actor, "framework_view", lambda: [])() or [])
    if not views:
        return []
    session = situation.session
    allocation = (allocation_for(session, actor) or {}) if session is not None else {}
    out: list[str] = []
    for fw in views:
        label, unit = _FRAMEWORK_KINDS.get(fw.kind, (fw.kind.replace("_", " ").title(), "pool"))
        active = set(allocation.get(fw.framework_id, (0, 0, set(), {}))[2])
        out.append(f"{fw.name} ({label}, {fw.reserve_or_pool}-point {unit}):")
        if not fw.slots:
            out.append("  nothing in it yet")
        for slot in fw.slots:
            bits = [f"{slot.active_points} AP", "variable" if slot.variable else "fixed"]
            atk = slot.attack
            if atk is not None:
                dice = f"{atk.damage_dice}{'½' if atk.half_die else ''}d6"
                if atk.plus_one:
                    dice += "+1"
                kind = "killing" if atk.damage_type == "killing" else "normal"
                bits.append(f"{dice} {kind}")
                if atk.avad:
                    bits.append(f"NND, stopped only by {atk.avad_defense or 'its named defense'}")
            if slot.slot_id in active:
                bits.append("switched on")
            out.append(f"  {slot.name}: {', '.join(bits)}")
    kinds = {a.kind for a in situation.menu}
    if "reallocate" in kinds:
        out.append("Switching slots is on the menu (reallocate).")
    if "reconfigure_vpp" in kinds:
        out.append("Rebuilding a pool is on the menu (reconfigure_vpp).")
    return out

