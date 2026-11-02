"""A squad takes cover --- eight minor hits and one very strong man, no database.

The worked example the import-surface ratchet owes for the squad-tactics
names: `squads_of`, `leader_of`, `orders_for`, `order_fit`, `validate_orders`,
`threat_picture`, `powers_seen` and `answers_to`, and the types they pass
around (`Squad`, `SquadOrders`, `FireTeam`, `TeamTask`, `KEEP_ORDERS`,
`KeepOrders`, `OrdersPage`, `OrdersChooser`, `InvalidOrders`, `Defence`,
`ThreatPicture`, `ThreatLine`).

THE SITUATION. Two squads of four, ALPHA and BRAVO, each fighter a
`minor_hits=1` extra, face the Warlord and his Lieutenant on a generated arena that has cover
on it (`ArenaGenerator.WITH_COVER`). The Warlord's one attack is a 4 m
Explosion, so a bunched-up squad is exactly what it was bought to punish.
The GM declares the squads (a name on each man, like `minor_hits`); the
engine never infers them from the roster.

WHAT HAPPENS, in the order it is printed:

  1. `squads_of` lists the squads and `leader_of` names each leader. The
     engine picks him from the builds (best Tactics roll, then INT, then PRE,
     then seating) and records `SquadLeaderNamed`, so a viewer sees who comes
     out on top. RULING, no book page: HERO has no squad leader.
  2. At the top of the leader's own Phase his seat is asked `give_orders`
     (`OrdersChooser`). Giving orders is a Zero Phase action (6E2 p.25's Time
     Chart: speaking is "variable", an order is a few words), so he still
     acts in the same Phase. The seat answers with a `SquadOrders` (every
     standing man in exactly one `FireTeam`, each with one `TeamTask`) or
     with `KEEP_ORDERS`, which records nothing. `validate_orders` is what the
     engine refuses bad orders with; this seat asks it first and prints
     the `InvalidOrders` message if it fails.
  3. Each man's page carries his team's order (`orders_for`), and
     `order_fit` says whether an offer on his menu carries it out. It is a
     fact for his seat, never a cut of his menu: following it is his choice.
  4. Once the Warlord has used his Explosion, each man gets a `ThreatPicture`:
     one `ThreatLine` per power an enemy has been SEEN using, whether it
     reaches him now, how big the area is, how many of his own squad one use
     would catch, and which `Defence`s answer it (`answers_to`). Powers an
     enemy has not shown are not in it (`powers_seen`).

The squad's cover choice is the one the picture ranks (`kirby_world.cover`),
and a man ordered to TAKE_COVER is told how many metres he can reach.

Run with:
    .venv/bin/python examples/a_squad_takes_cover.py
"""
from __future__ import annotations

import random

from kirby_dice import RandomRoller
from kirby_world.generate import ArenaGenerator, arena_for

from kirby_combat import (
    KEEP_ORDERS, FireTeam, InvalidOrders, KeepOrders, OrdersChooser, OrdersPage,
    SquadOrders, TeamTask, ThreatPicture, answers_to, leader_of, order_fit,
    orders_for, powers_seen, squads_of, threat_picture, validate_orders,
)
from kirby_combat.encounter import Encounter
from kirby_combat.loop import TacticChooser, run_encounter
from kirby_combat.models import AttackPower
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_HEROIC

SEED = 5
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")


def a_rifle(cid: str) -> AttackPower:
    """An ordinary 1d6 killing rifle, written for this file."""
    return AttackPower(
        xmlid="RKA", name="Rifle", damage_dice=1, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=60.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id=f"rifle-{cid}", charges=12, active_points=15,
    )


def the_explosion() -> AttackPower:
    """The Warlord's Explosion: 4d6 Energy Blast, a 4 m radius area."""
    area = AreaSpec(shape=AreaShape.RADIUS, size_m=4.0,
                    targeting=AreaTargeting.STANDARD, explosion=False,
                    personal_immunity=False, width_m=2.0, height_m=2.0,
                    thin_cone=False, unbuilt=())
    return AttackPower(
        xmlid="ENERGYBLAST", name="Bolt of ruin", damage_dice=4,
        half_die=False, plus_one=False, damage_type="normal",
        defense_type="ed", range_m=80.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=True, source_id="warlord-bolt", area=area,
        active_points=60,
    )


def a_man(cid: str, squad: str, *, tactics_dex: int):
    """One soldier: a minor-hits extra in a named squad. ``tactics_dex``
    only varies his DEX so the squads do not act in lock-step."""
    return synthetic_combatant(
        id=cid, name=cid, ocv=6, dcv=4, omcv=3, dmcv=3, spd=3,
        dex=tactics_dex, ego=10, int_=10, str_=10, con=12, pre=10, rec=4,
        pd=2, ed=2, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=25, max_body=10, max_end=25, current_stun=25,
        current_body=10, current_end=25, side=HEROES,
        attacks=[a_rifle(cid)], minor_hits=1, squad=squad,
    )


def the_warlord():
    return synthetic_combatant(
        id="Warlord", name="Warlord", ocv=10, dcv=6, omcv=5, dmcv=5, spd=5,
        dex=20, ego=18, int_=14, str_=30, con=30, pre=25, rec=14,
        pd=12, ed=12, rpd=6, red=6, md=0, power_defense=0, flash_defense=0,
        max_stun=120, max_body=30, max_end=80, current_stun=120,
        current_body=30, current_end=80, side=VILLAINS,
        attacks=[the_explosion()],
    )


def the_lieutenant():
    """A second foe, so that cover which hides a man from the Warlord can
    still leave him a line to shoot: a spot that blinds him to EVERY enemy is
    not offered or listed (`enumeration.can_shoot_from`), because cover is
    somewhere to fire from."""
    return synthetic_combatant(
        id="Lieutenant", name="Lieutenant", ocv=8, dcv=5, omcv=4, dmcv=4,
        spd=4, dex=15, ego=12, int_=12, str_=15, con=18, pre=15, rec=8,
        pd=6, ed=6, rpd=2, red=2, md=0, power_defense=0, flash_defense=0,
        max_stun=60, max_body=15, max_end=40, current_stun=60,
        current_body=15, current_end=40, side=VILLAINS,
        attacks=[a_rifle("Lieutenant")],
    )


def the_cast():
    men = [a_man(f"{squad[0]}{i}", squad, tactics_dex=14 - i)
           for squad in ("alpha", "bravo") for i in range(1, 5)]
    return men + [the_warlord(), the_lieutenant()]


class SquadSeat(TacticChooser):
    """`TacticChooser`'s picks, and a real answer to `give_orders`.

    The doctrine catalogue has no tactic for a squad's teams, so the stock
    chooser leaves the orders as they are. This seat (an `OrdersChooser`)
    gives them: ALPHA focuses fire on the Warlord when its leader perceives
    him (a man with a wall across his line has no attack on the Warlord
    to make, and his fit is 0 of N: the engine offers `reposition_vantage`
    instead), BRAVO splits into a team that takes cover and a team that spreads
    out, and either squad takes cover whole when it sees nobody to shoot.
    """

    def __init__(self) -> None:
        super().__init__()
        self.told_order: set[str] = set()
        self.shown: set[str] = set()

    def give_orders(self, page: OrdersPage) -> SquadOrders | KeepOrders:
        if page.current is not None:
            return KEEP_ORDERS
        men = page.standing
        if page.squad.name == "alpha" and "Warlord" in page.targets:
            teams = (FireTeam(member_ids=men, task=TeamTask.FOCUS_FIRE,
                              target_id="Warlord", radius_m=None, position=None),)
        elif page.squad.name == "bravo" and len(men) > 1:
            half = len(men) // 2
            teams = (
                FireTeam(member_ids=men[:half], task=TeamTask.TAKE_COVER,
                         target_id=None, radius_m=None, position=None),
                FireTeam(member_ids=men[half:], task=TeamTask.SPREAD_OUT,
                         target_id=None, radius_m=5.0, position=None),
            )
        else:
            teams = (FireTeam(member_ids=men, task=TeamTask.TAKE_COVER,
                              target_id=None, radius_m=None, position=None),)
        orders = SquadOrders(teams=teams)
        try:
            validate_orders(page, orders)
        except InvalidOrders as why:
            print(f"  {page.leader_id} gave orders the engine refuses: {why}")
            return KEEP_ORDERS
        print(f"  {page.leader_id} orders squad {page.squad.name}:")
        for team in orders.teams:
            print(f"    {', '.join(team.member_ids)} -> {team.task.value}"
                  + (f" {team.target_id}" if team.target_id else "")
                  + (f" ({team.radius_m:g} m apart)" if team.radius_m else ""))
        return orders

    def choose(self, situation) -> str:
        picked = super().choose(situation)
        man = situation.actor.id
        if getattr(situation.actor, "squad", None) is None:
            return picked
        team = orders_for(situation.session, man)
        if team is not None and man not in self.told_order:
            self.told_order.add(man)
            carrying = sorted({a.kind for a in situation.menu
                               if order_fit(situation, a)})
            print(f"  {man} is under '{team.task.value}'; "
                  f"{len([a for a in situation.menu if order_fit(situation, a)])}"
                  f" of {len(situation.menu)} offers carry it out"
                  + (f" ({', '.join(carrying)})" if carrying else ""))
        picture = threat_picture(situation)
        if picture.lines and man not in self.shown:
            self.shown.add(man)
            self.print_picture(man, picture, situation)
        return picked

    def print_picture(self, man: str, picture: ThreatPicture, situation) -> None:
        print(f"  {man}'s threat picture "
              f"(seen: {', '.join(sorted({n for line in picture.lines for n in powers_seen(situation.session, line.enemy_id)}))}):")
        for line in picture.lines:
            area = ("" if line.area_radius_m is None
                    else f", {line.area_radius_m:g} m area")
            catches = ("" if not line.squadmates_it_would_catch
                       else f", would catch {line.squadmates_it_would_catch} "
                            "of his squad")
            answers = ", ".join(sorted(d.value for d in line.answered_by))
            print(f"    {line.enemy_id}'s {line.power_name} ({line.kind}): "
                  f"{'reaches him' if line.can_reach_me else 'out of reach'}"
                  f"{area}{catches}; answered by {answers or 'nothing'}")
        if picture.cover:
            spot = picture.cover[0]
            print(f"    best cover: {spot.feature_id}, {spot.distance_m:.1f} m away, "
                  f"{'reachable' if spot.reachable_this_phase else 'out of reach'} "
                  "this Phase")


def main() -> None:
    assert issubclass(SquadSeat, OrdersChooser)
    cast = the_cast()
    scene = arena_for(random.Random(SEED), cast,
                      generator=ArenaGenerator.WITH_COVER)
    roller = RandomRoller(seed=SEED)
    session = CombatSession.create(
        id="squad-takes-cover", combatants=cast, scene=scene,
        template=RAW_HEROIC, dice_roller=roller).start()

    print("Squads declared:")
    for squad in squads_of(session):
        print(f"  {squad.name} ({squad.side}): {', '.join(squad.member_ids)}")

    seat = SquadSeat()
    result = run_encounter(
        Encounter(id="squad-takes-cover", turn=1, segment=12,
                  sessions=[session], template=RAW_HEROIC),
        seat, roller=roller, on_unresolvable="skip", max_turns=3)
    session = result.encounter.sessions[0]

    print("Leaders named:")
    for squad in squads_of(session):
        print(f"  {squad.name}: {leader_of(session, squad.name, squad.side)}")

    given = [e for e in session.event_log if e.kind == "SquadOrdersGiven"]
    named = [e for e in session.event_log if e.kind == "SquadLeaderNamed"]
    print(f"{len(named)} SquadLeaderNamed, {len(given)} SquadOrdersGiven "
          f"in {result.phases} Phases.")
    print("What answers the Explosion: "
          + ", ".join(sorted(d.value for d in answers_to(
              session.combatants["Warlord"].attacks[0], kind="attack"))))
    assert given, "the leaders were never asked for orders"


if __name__ == "__main__":
    main()
