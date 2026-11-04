"""Squads and who leads them (squad tactics spec, section 4).

A fight's seating may declare squads: each combatant's `squad` names the one
he fights in, or is None for a man in no squad. The GM declares them, like
`minor_hits`; nothing is inferred from the roster and there is no default
squad size. A squad is a name on a SIDE: the same name on two sides is two
squads.

THE LEADER is decided by the engine from the builds, so that anyone watching
can see who comes out on top. RULING (no book page; HERO has no squad
leader): among the members still standing, the best Tactics roll leads
(`skill_roll_value("TACTICS")`; a man without the Skill ranks below any
roll), then the higher INT, then the higher PRE, then the member seated
first. A contested roll is the alternative, which adds dice and no
difference anybody could see.

When the leader goes down the rule is applied again at once to the men still
standing, in the same step, so `SquadLeaderNamed` follows the row that downed
him. The new leader can give orders on his own next Phase.

"Standing" is the Roster's: not `is_down` (6E1 p.421) and not gone from the
field.

ORDERS. At the top of his own Phase the leader's seat is asked
`OrdersChooser.give_orders(page)` (`loop/run.py`), before his ordinary pick.
An order puts every standing member in exactly one `FireTeam`, each with one
`TeamTask`; `validate_orders` refuses anything else, and the engine records
what passes as `SquadOrdersGiven`. `KEEP_ORDERS` records nothing. Every
member reads his team's order (`orders_for`), and `order_fit` says whether
an offer carries it out. The order is a fact on his page, never a cut of
his menu: following it is his seat's choice.

RULING, Zero Phase: giving orders takes no time. 6E2 p.25's Time Chart
lists "Speaking (conversation): Variable"; an order is a few words, so it
is Zero Phase, and the leader still takes his ordinary action in the same
Phase. Asked once a Phase, at its top, never out of turn.

RULING, reach: every member hears every order (the spec's v1 call; a squad
of agents carries radios). Orders stand until the next ones, and after the
leader who gave them falls; a man who was down when they were given is in
no team of them, so he has none until the next.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from kirby_world.scene import Position

from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_world.cover import CoverSpot

    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.chooser import PhaseSituation
    from kirby_combat.threat_picture import ThreatPicture

#: Below any roll a man can have, for a member with no Tactics.
_NO_TACTICS = -1


@dataclass(frozen=True)
class Squad:
    """A named squad on one side, its members in seating order."""

    name: str
    #: The object, not its id (objects, not strings: `kirby_combat.side`);
    #: the events carry ``side.id``, as every event does.
    side: Side
    member_ids: tuple[str, ...]


def squads_of(session: Any) -> tuple[Squad, ...]:
    """Every squad the seating declares, grouped by ``(side, squad)``.

    In the order each squad's first member was seated; members in seating
    order. A squad name used on two sides is two squads.
    """
    groups: dict[tuple[Side, str], list[str]] = {}
    for combatant in session.combatants.values():
        name = getattr(combatant, "squad", None)
        if name is None:
            continue
        groups.setdefault((Side.of(combatant), name), []).append(combatant.id)
    return tuple(Squad(name=name, side=side, member_ids=tuple(ids))
                 for (side, name), ids in groups.items())


def leader_rule(session: Any, squad: Squad) -> str | None:
    """Who should lead ``squad`` now: the best of the men still standing by
    Tactics, then INT, then PRE, then seating order; None if none stand."""
    up = _standing_ids(session)
    best: str | None = None
    best_key: tuple[int, int, int] | None = None
    for member_id in squad.member_ids:
        if member_id not in up:
            continue
        member = session.combatants[member_id]
        tactics = member.skill_roll_value("TACTICS")
        key = (_NO_TACTICS if tactics is None else int(tactics),
               int(member.int_), int(member.pre))
        # Strictly greater, so a full tie keeps the man seated first.
        if best_key is None or key > best_key:
            best, best_key = member_id, key
    return best


def _standing_ids(session: Any) -> set[str]:
    from kirby_combat.roster import Roster

    return {i for ids in Roster(session).standing.values() for i in ids}


def _latest(session: Any, kind: str, squad_name: str, side: Side):
    if not isinstance(side, Side):
        raise TypeError(
            f"squad {squad_name!r}: side={side!r} is not a Side; pass the "
            "object (Side.of(combatant), or Squad.side), not its id")
    for event in reversed(session.event_log):
        if (getattr(event, "kind", "") == kind
                and event.squad == squad_name and event.side == side.id):
            return event
    return None


def _latest_naming(session: Any, squad_name: str, side: Side):
    return _latest(session, "SquadLeaderNamed", squad_name, side)


def leader_of(session: Any, squad_name: str, side: Side) -> str | None:
    """The squad's leader as the log last named him; None if nobody leads it
    (none standing, or no `SquadLeaderNamed` yet)."""
    named = _latest_naming(session, squad_name, side)
    return None if named is None else named.leader_id


def name_leaders(session: Any) -> Any:
    """Write a `SquadLeaderNamed` for each squad whose leader is not what the
    rule now says, and return the session. Squads that are unchanged write
    nothing, so an all-down squad records ``leader_id=None`` once.

    Called when the fight begins and at the end of every Phase and step
    (`loop/run.py`). The reason is "fight began" for a squad never named,
    else "<old id> went down", or "<id> came to" when a squad with no one
    standing has a man standing again. Naming happens only inside
    `run_phase`, so a leader downed outside it (a GM override, a direct
    apply) is replaced at the next `run_phase`.
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import SquadLeaderNamed, make_author_engine

    for squad in squads_of(session):
        named = _latest_naming(session, squad.name, squad.side)
        leader = leader_rule(session, squad)
        if named is None:
            reason = "fight began"
        elif named.leader_id is None:
            # Nobody led. If a man has come to (Recovery lifts him above
            # 0 STUN), he is named; otherwise the squad stays leaderless.
            if leader is None:
                continue
            reason = f"{leader} came to"
        elif named.leader_id == leader:
            continue
        elif named.leader_id in _standing_ids(session):
            # He is still up: the Skill or INT moving under him (a Drain) is
            # not a reason to take the squad from him.
            continue
        else:
            reason = f"{named.leader_id} went down"
        session = apply_event(session, SquadLeaderNamed(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            squad=squad.name, side=squad.side.id, leader_id=leader, reason=reason,
        ))
    return session


# ── Orders ──────────────────────────────────────────────────────────────────


class TeamTask(str, Enum):
    """What a fire team is told to do (squad tactics spec, section 4)."""

    #: Coordinate on one target (6E2 p.46, `coordination.py`). Needs ``target_id``.
    FOCUS_FIRE = "focus_fire"
    #: Move to within reach of the target. Needs ``target_id``.
    CLOSE = "close"
    #: Get into the best cover and fire from there.
    TAKE_COVER = "take_cover"
    #: Keep ``radius_m`` from each other.
    SPREAD_OUT = "spread_out"
    #: Move to a ``position``.
    FLANK = "flank"
    #: Hold an action (6E2 p.22).
    HOLD = "hold"
    #: Fall back.
    WITHDRAW = "withdraw"


#: The one field each task uses; None for a task that uses none. A field a
#: task does not use must be None, so an order says one thing.
_TASK_FIELD: dict[TeamTask, str | None] = {
    TeamTask.FOCUS_FIRE: "target_id", TeamTask.CLOSE: "target_id",
    TeamTask.SPREAD_OUT: "radius_m", TeamTask.FLANK: "position",
    TeamTask.TAKE_COVER: None, TeamTask.HOLD: None, TeamTask.WITHDRAW: None,
}
_TEAM_FIELDS = ("target_id", "radius_m", "position")


@dataclass(frozen=True)
class FireTeam:
    """Some of a squad's members and the one task they are given."""

    member_ids: tuple[str, ...]
    task: TeamTask
    #: For FOCUS_FIRE and CLOSE: an enemy the leader perceives.
    target_id: str | None
    #: For SPREAD_OUT: how far apart, in metres, more than 0.
    radius_m: float | None
    #: For FLANK: where to go.
    position: Position | None

    def to_dict(self) -> dict[str, Any]:
        """The team as `SquadOrdersGiven.teams` carries it (JSON)."""
        p = self.position
        return {
            "member_ids": list(self.member_ids), "task": self.task.value,
            "target_id": self.target_id, "radius_m": self.radius_m,
            "position": None if p is None else {"x": p.x, "y": p.y, "z": p.z},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FireTeam:
        p = d["position"]
        return cls(
            member_ids=tuple(d["member_ids"]), task=TeamTask(d["task"]),
            target_id=d["target_id"], radius_m=d["radius_m"],
            position=None if p is None else Position(p["x"], p["y"], p["z"]),
        )


@dataclass(frozen=True)
class SquadOrders:
    """A leader's orders: every standing member in exactly one team."""

    teams: tuple[FireTeam, ...]


class KeepOrders:
    """The answer "the orders stand": records nothing. A sentinel, so no
    `SquadOrders` (not even one with no teams) can be mistaken for it."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "KEEP_ORDERS"


#: What `give_orders` returns to leave the orders as they are, including
#: when none have been given yet.
KEEP_ORDERS = KeepOrders()


class InvalidOrders(ValueError):
    """Orders the engine refuses; the message names the problem."""


@dataclass(frozen=True)
class OrdersPage:
    """What a leader is shown when he is asked for orders.

    ``pictures`` holds each standing member's `ThreatPicture` (so only
    powers seen in use); ``targets`` the enemies the leader himself
    perceives, which are the only ones an order may name; ``cover`` the
    leader's own best spots (his picture's).
    """

    squad: Squad
    leader_id: str
    standing: tuple[str, ...]
    current: SquadOrders | None
    pictures: dict[str, ThreatPicture]
    targets: tuple[str, ...]
    cover: tuple[CoverSpot, ...]

    def render(self) -> str:
        """The engine's own wording for a seat that reads text, in judged
        terms: who stands, the orders standing, and for each man what the
        enemy has shown, whether it reaches him, and his best cover."""
        lines = [
            f"You lead squad {self.squad.name}. Standing: {', '.join(self.standing)}.",
            "Enemies you can see: "
            + (", ".join(self.targets) if self.targets else "none") + ".",
            "Orders standing: " + (_say_orders(self.current)
                                   if self.current is not None else "none") + ".",
        ]
        for man in self.standing:
            lines.append(f"{man}: " + _say_picture(self.pictures[man]))
        return "\n".join(lines)


def _say_team(team: FireTeam) -> str:
    task = team.task.value.replace("_", " ")
    if team.target_id is not None:
        task += f" on {team.target_id}"
    elif team.radius_m is not None:
        task += f" {team.radius_m:g} m apart"
    elif team.position is not None:
        task += f" to ({team.position.x:g}, {team.position.y:g})"
    return f"{', '.join(team.member_ids)} {task}"


def _say_orders(orders: SquadOrders) -> str:
    return "; ".join(_say_team(t) for t in orders.teams)


def _say_picture(picture: ThreatPicture) -> str:
    said: list[str] = []
    for line in picture.lines:
        what = (f"a {line.area_radius_m:g} m area ({line.power_name})"
                if line.area_radius_m is not None else line.power_name)
        s = f"{line.enemy_id} has shown {what}, which "
        s += "can reach you now" if line.can_reach_me else "cannot reach you now"
        if line.squadmates_it_would_catch:
            s += (f"; one would catch you and {line.squadmates_it_would_catch} "
                  f"more of the squad")
        said.append(s)
    if not said:
        said.append("no enemy you can see has shown a power that acts on a man")
    if picture.cover:
        best = picture.cover[0]
        hidden = sum(1 for lv in best.cover_by_threat.values() if lv > 0)
        said.append(
            f"best cover behind {best.feature_id}, {best.distance_m:.0f} m away"
            + ("" if best.reachable_this_phase else ", not reachable this Phase")
            + f", hiding you from {hidden} of {len(best.cover_by_threat)}")
    return "; ".join(said) + "."


def _current_orders(session: Any, squad: Squad) -> SquadOrders | None:
    given = _latest(session, "SquadOrdersGiven", squad.name, squad.side)
    if given is None:
        return None
    return SquadOrders(teams=tuple(FireTeam.from_dict(t) for t in given.teams))


def orders_page(session: Any, squad: Squad, leader_id: str, *,
                situation_for: Any) -> OrdersPage:
    """The page ``leader_id`` is asked for orders from.

    ``situation_for(session, member_id)`` is the loop's own builder of a
    man's Phase (`loop.run._situation_for`), handed in as `ask_holders`
    takes it, so each member's picture is read off the situation his own
    Phase would show him and nothing here builds one a second way.
    """
    from kirby_combat.brief_detail import sightings
    from kirby_combat.threat_picture import threat_picture

    up = _standing_ids(session)
    standing = tuple(m for m in squad.member_ids if m in up)
    if leader_id not in standing:
        raise ValueError(f"{leader_id!r} is not standing in squad {squad.name!r}")
    situations = {m: situation_for(session, m) for m in standing}
    pictures = {m: threat_picture(situations[m]) for m in standing}
    lead = situations[leader_id]
    # The enemies HE perceives, by the same reading the page and the
    # picture make (`brief_detail.sightings`). RULING: his enemies as his own
    # Phase sees them, after Mind Control and rage (`obey`, `rage_menu` in
    # `_situation_for`): a controlled or enraged leader gives the orders he
    # would give, against the men he now fights.
    sees = sightings(lead)
    targets = tuple(e.id for e in lead.enemies if sees[e.id].perceived)
    return OrdersPage(
        squad=squad, leader_id=leader_id, standing=standing,
        current=_current_orders(session, squad), pictures=pictures,
        targets=targets, cover=pictures[leader_id].cover,
    )


def validate_orders(page: OrdersPage, orders: Any) -> Any:
    """Return ``orders`` if the engine accepts them, else raise `InvalidOrders`.

    Every standing member in exactly one team, and no one else (no unknown
    id, no man who is down); every task a `TeamTask`, with the field it uses
    set and the others None; a target the leader perceives; a radius above
    0. `KEEP_ORDERS` is always accepted.
    """
    if orders is KEEP_ORDERS:
        return orders
    if not isinstance(orders, SquadOrders):
        raise InvalidOrders(
            f"give_orders must return SquadOrders or KEEP_ORDERS, not "
            f"{type(orders).__name__}")
    squad = page.squad
    standing, members = set(page.standing), set(squad.member_ids)
    team_of: dict[str, int] = {}
    for i, team in enumerate(orders.teams):
        if not isinstance(team, FireTeam):
            raise InvalidOrders(f"team {i} is a {type(team).__name__}, not a FireTeam")
        if not isinstance(team.task, TeamTask):
            raise InvalidOrders(f"team {i}: task {team.task!r} is not a TeamTask")
        if not team.member_ids:
            raise InvalidOrders(f"team {i} ({team.task.name}) has no members")
        # Types before any set test, so a wrong-typed id is refused here
        # rather than escaping as a TypeError from the hash.
        if (not isinstance(team.member_ids, tuple)
                or not all(isinstance(m, str) for m in team.member_ids)):
            raise InvalidOrders(
                f"team {i}: member_ids must be a tuple of ids (str), got "
                f"{team.member_ids!r}")
        if team.target_id is not None and not isinstance(team.target_id, str):
            raise InvalidOrders(
                f"team {i}: target_id must be an id (str), got {team.target_id!r}")
        for m in team.member_ids:
            if m not in members:
                raise InvalidOrders(f"team {i}: {m!r} is not in squad {squad.name!r}")
            if m not in standing:
                raise InvalidOrders(
                    f"team {i}: {m!r} is down; orders go to the men standing")
            if m in team_of:
                raise InvalidOrders(
                    f"{m!r} is in more than one team ({team_of[m]} and {i})")
            team_of[m] = i
        uses = _TASK_FIELD[team.task]
        for name in _TEAM_FIELDS:
            value = getattr(team, name)
            if name == uses and value is None:
                raise InvalidOrders(f"team {i}: {team.task.name} needs {name}")
            if name != uses and value is not None:
                raise InvalidOrders(
                    f"team {i}: {team.task.name} does not use {name}; leave it None")
        if uses == "target_id" and team.target_id not in page.targets:
            raise InvalidOrders(
                f"team {i}: target {team.target_id!r} is not an enemy the leader "
                f"perceives ({', '.join(page.targets) or 'none'})")
        if uses == "radius_m" and (
                isinstance(team.radius_m, bool)
                or not isinstance(team.radius_m, (int, float))
                or not team.radius_m > 0):
            raise InvalidOrders(f"team {i}: radius_m must be a number of metres "
                                f"more than 0, got {team.radius_m!r}")
        if uses == "position" and not isinstance(team.position, Position):
            raise InvalidOrders(f"team {i}: position must be a Position, "
                                f"got {type(team.position).__name__}")
    missing = [m for m in page.standing if m not in team_of]
    if missing:
        raise InvalidOrders(
            f"{', '.join(repr(m) for m in missing)} standing but in no team; "
            "every standing member needs exactly one")
    return orders


def record_orders(session: Any, squad: Squad, leader_id: str,
                  orders: SquadOrders) -> Any:
    """Write ``orders`` as `SquadOrdersGiven` and return the session. The
    loop calls it only with orders `validate_orders` has passed."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import SquadOrdersGiven, make_author_engine

    return apply_event(session, SquadOrdersGiven(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        squad=squad.name, side=squad.side.id, leader_id=leader_id,
        teams=[t.to_dict() for t in orders.teams],
    ))


def orders_for(session: Any, member_id: str) -> FireTeam | None:
    """His team in the latest orders for his squad and side; None when he
    is in no squad, no orders have been given, or he was down when they
    were (he is in none of their teams)."""
    member = session.combatants[member_id]
    name = getattr(member, "squad", None)
    if name is None:
        return None
    given = _latest(session, "SquadOrdersGiven", name, Side.of(member))
    if given is None:
        return None
    for team in given.teams:
        if member_id in team["member_ids"]:
            return FireTeam.from_dict(team)
    return None


def order_fit(situation: PhaseSituation, action: LegalAction, *,
              perceived: list[Any] | None = None) -> bool:
    """Whether ``action`` carries out the order ``situation.actor`` is under.

    A fact for his seat, never a cut of his menu. A man with no order fits
    nothing. RULINGS (the book has no squad orders; the engine reads each
    task in its own terms):

    * FOCUS_FIRE: an attack (`defences.threatens_a_man`) or a Coordinated
      Attack join (``coordinate``, 6E2 p.46) on the target, or a
      ``reposition_vantage`` or ``reposition_strike`` aimed at him: getting
      a line on the target is how a man who cannot see it obeys.
    * CLOSE: a move that ends closer to the target than he stands now.
    * TAKE_COVER: ``move_to_cover``, or an attack while he is in cover where
      he stands (`enumeration.cover_where_he_stands`) against the enemies he
      perceives.
    * SPREAD_OUT: a move that ends at least ``radius_m`` from every other
      man of his team, where each stands now.
    * FLANK: a move that ends closer to ``position`` than he stands now.
    * HOLD: ``hold``, or keeping a Held Action.
    * WITHDRAW: a move that ends farther from the nearest enemy he
      perceives than he stands now.

    ONLY WHAT HE PERCEIVES. Every enemy this reads is one he perceives
    (`brief_detail.sightings`, physical, as `threat_picture` filters): the
    seat is shown this fit, and an unseen man must not move it (perception
    governs combat; no metagaming).

    A MOVE is an offer that names where it goes (``reposition_dest``), or a
    ``move`` / ``half_move`` toward a man, which ends where the move itself
    would land (`resolvers.closing_move`, `placement.landing_of`). With no
    map nothing is a move. An Abort question fits nothing: an Abort is a
    defence against the man attacking him, not a task.

    ``perceived`` is the enemies he perceives (`_perceived`), for a caller
    asking about every offer of one page (the Brief) to work them out once;
    None works them out here.
    """
    from kirby_combat.loop.chooser import OutOfTurnReason
    from kirby_combat.loop.reactions import KEEP_HOLDING

    team = situation.squad_order
    if team is None:
        return False
    oot = situation.out_of_turn
    if oot is not None and oot.reason is OutOfTurnReason.ABORT:
        return False
    task, kind = team.task, action.kind
    if kind == KEEP_HOLDING:
        return task is TeamTask.HOLD
    if task is TeamTask.HOLD:
        return kind == "hold"
    if task is TeamTask.FOCUS_FIRE:
        aimed = (action.target_id == team.target_id
                 or team.target_id in action.target_ids)
        return aimed and (kind in ("coordinate", "reposition_vantage")
                          or _is_attack(kind))
    if task is TeamTask.TAKE_COVER:
        if kind == "move_to_cover":
            return True
        return _is_attack(kind) and _in_cover(situation, perceived)
    # The rest are moves.
    from kirby_world.geometry import distance_3d

    from kirby_combat.placement import position_of

    scene = getattr(situation.session, "scene", None)
    here = position_of(scene, situation.actor.id) if scene is not None else None
    end = _move_end(situation, action) if here is not None else None
    if end is None:
        return False
    if task is TeamTask.CLOSE:
        there = position_of(scene, team.target_id)
        return there is not None and distance_3d(end, there) < distance_3d(here, there)
    if task is TeamTask.FLANK:
        return distance_3d(end, team.position) < distance_3d(here, team.position)
    if task is TeamTask.SPREAD_OUT:
        mates = [p for m in team.member_ids if m != situation.actor.id
                 and (p := position_of(scene, m)) is not None]
        return all(distance_3d(end, p) >= team.radius_m for p in mates)
    if task is TeamTask.WITHDRAW:
        foes = [p for e in (_perceived(situation) if perceived is None
                            else perceived)
                if (p := position_of(scene, e.id)) is not None]
        if not foes:
            return False
        nearest = min(foes, key=lambda p: distance_3d(here, p))
        return distance_3d(end, nearest) > distance_3d(here, nearest)
    raise ValueError(f"order_fit: no rule for {task!r}")


def _is_attack(kind: str) -> bool:
    from kirby_combat.defences import threatens_a_man

    return threatens_a_man(kind)


def _in_cover(situation: PhaseSituation, perceived: list[Any] | None) -> bool:
    from kirby_combat.enumeration import cover_where_he_stands
    from kirby_combat.placement import position_of

    scene = getattr(situation.session, "scene", None)
    here = position_of(scene, situation.actor.id) if scene is not None else None
    if here is None:
        return False
    threats = {e.id: p for e in (_perceived(situation) if perceived is None
                                else perceived)
               if (p := position_of(scene, e.id)) is not None}
    return cover_where_he_stands(scene, here, threats) > 0


def _perceived(situation: PhaseSituation) -> list[Any]:
    """The enemies he perceives, filtered as `threat_picture` filters them."""
    from kirby_combat.brief_detail import sightings

    sees = sightings(situation)
    return [e for e in situation.enemies
            if sees[e.id].perceived and sees[e.id].physical]


def _move_end(situation: PhaseSituation, action: LegalAction) -> Position | None:
    """Where ``action`` would leave him, or None when it is not a move. See
    `order_fit`'s MOVE."""
    if action.reposition_dest is not None:
        return Position(*action.reposition_dest)
    from kirby_combat.half_phase_offers import HALF_MOVE

    if action.kind not in ("move", HALF_MOVE) or action.target_id is None:
        return None
    from kirby_combat.loop.resolvers import closing_move
    from kirby_combat.placement import landing_of

    closing = closing_move(situation.session, situation.actor, action)
    if closing is None:
        return None
    destination, mode, allowance = closing
    landing = landing_of(situation.session, situation.actor.id, destination,
                         mode=mode, distance_m=allowance)
    return None if landing is None else landing.landing
