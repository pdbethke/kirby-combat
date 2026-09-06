"""A fight that actually ends — damage applied, blow after blow, to a KO.

WHAT THIS DEMONSTRATES, AND WHY IT COULD NOT BE WRITTEN BEFORE.
Until 2026-09-06 the engine resolved attacks but never applied them:
`resolve_attack_in_session` computed `stun_dealt`, recorded it on the event
log, and left `current_stun` exactly where it was. Every consumer had to
subtract the damage itself — the kirby-api driver did it at fifteen separate
call sites — so an engine-only fight could resolve one exchange and then
repeat it forever against a target that never got hurt.

`resolve_attack_in_session` now folds the damage onto `session.combatants`.
That single change is what turns the pieces this repo already had — the
resolver, the enumerator, the roles, the tactic catalogue, the acting order
— into a fight with an ending. The loop below is the proof: two combatants,
alternating Phases, until one of them is Knocked Out. Nothing here holds a
STUN total of its own.

READ THE COMBATANTS FROM THE SESSION, EVERY PHASE. The engine is immutable:
each call returns a NEW session with a NEW combatant folded in. A handle
grabbed before an exchange is stale immediately after it, which is why the
loop re-reads `session.combatants[...]` each time round rather than reusing
the objects it built at the start. Passing a stale handle is not silently
wrong either — damage lands on whoever the session holds for that id, so the
ledger stays right even if a caller's handle drifts.

NO DATABASE, NO WEB SERVICE, NO NETWORK. This runs on kirby-combat plus its
leaf packages (kirby-cost, kirby-dice) and nothing else.

Exercises:
  - resolve_attack_in_session applying damage to session.combatants
  - apply_vitals_delta (the single fold every vitals change goes through)
  - Stunnable.is_ko — `current_stun <= 0`, true the moment damage lands
  - statuses_for — Stunned and Knocked Out, read off the same session
  - STUN going negative rather than clamping, which is what 6E needs
"""
from __future__ import annotations

from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.models import AttackInput, AttackPower, DiceValues, StatBlockCombatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.statuses import statuses_for
from kirby_combat.template import CombatTemplate
from kirby_combat.vitals import apply_vitals_delta
from kirby_dice import RandomRoller

#: A plain 8d6 Energy Blast for both fighters, so the fight is about the
#: ledger rather than about anyone's build.
BLAST = AttackPower(
    xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=8,
    half_die=False, plus_one=False,
    damage_type="normal", defense_type="ed", range_m=100,
    uses_str=False, str_min=0,
    armor_piercing=0, penetrating=0, increased_stun_mult=0,
)


def _fighter(id: str, name: str) -> StatBlockCombatant:
    """A flat stat-block combatant — no HDC file needed to run a fight.

    ``StatBlockCombatant`` keeps its vitals in flat ``current_*`` fields,
    where ``HeroCombatant`` (the shape a real imported character takes) keeps
    them on a separate ``state`` dataclass. ``apply_vitals_delta`` handles
    both, so this example's fight loop would read identically either way.
    """
    return StatBlockCombatant(
        id=id, name=name,
        ocv=8, dcv=6, omcv=4, dmcv=4,
        spd=4, dex=20, ego=13, str_=15, con=20, pre=15, rec=6,
        pd=6, ed=6, rpd=4, red=4, md=3,
        power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        attacks=[BLAST],
    )


def main() -> None:
    roller = RandomRoller(seed=20260906)
    template = CombatTemplate.default_6e_superheroic()

    session = CombatSession.create(
        id="finish", scene=None, template=template, dice_roller=roller,
        combatants=[_fighter("vex", "Vex"), _fighter("talon", "Talon")],
    ).start()

    print("A FIGHT TO THE FINISH — no database, no web service.\n")
    for c in session.combatants.values():
        print(f"  {c.name:<6} STUN {c.current_stun:>3}   BODY {c.current_body:>3}")
    print()

    attacker_id, target_id = "vex", "talon"
    phase = 0

    while phase < 50:
        # Stale handles are the one real trap here: re-read both fighters
        # from the session, because the previous exchange returned new ones.
        attacker = session.combatants[attacker_id]
        target = session.combatants[target_id]

        if attacker.is_ko or target.is_ko:
            break

        phase += 1
        session, result = resolve_attack_in_session(
            session,
            AttackInput(
                attacker=attacker, target=target, power=BLAST,
                distance_m=10, aim=None,
                dice=DiceValues(
                    to_hit=roller.roll_dice(3),
                    damage=roller.roll_dice(BLAST.damage_dice),
                ),
            ),
            template,
        )

        hurt = session.combatants[target_id]
        if result.hit:
            note = ", ".join(result.status_changes) or "still standing"
            print(
                f"  Phase {phase:>2}  {attacker.name} hits {target.name} "
                f"for {result.stun_dealt:>2} STUN / {result.body_dealt} BODY "
                f"-> {hurt.current_stun:>4} STUN  ({note})"
            )
        else:
            print(f"  Phase {phase:>2}  {attacker.name} misses {target.name}")

        attacker_id, target_id = target_id, attacker_id

    # ---- The fight is over because the ENGINE says so, not the caller ----
    print()
    for c in session.combatants.values():
        print(
            f"  {c.name:<6} STUN {c.current_stun:>4}   "
            f"KO={c.is_ko}   statuses={sorted(statuses_for(session, c.id))}"
        )

    loser = next(c for c in session.combatants.values() if c.is_ko)
    print(f"\n  {loser.name} is down after {phase} Phases.")

    # STUN below zero is kept, not clamped: 6E reads how far under a
    # character went to decide how long they stay under. A fold that
    # clamped at zero would throw that number away.
    assert loser.current_stun <= 0
    print(f"  Final STUN {loser.current_stun} — negative, and deliberately not clamped.")

    # ---- The same fold, used directly, is how a driver applies anything
    # ---- else: an END cost, a Drain, a healing effect.
    patched = apply_vitals_delta(loser, stun=+25, end=-3)
    print(
        f"\n  apply_vitals_delta(+25 STUN, -3 END) -> STUN {patched.current_stun}, "
        f"END {patched.current_end}, KO={patched.is_ko}"
    )


if __name__ == "__main__":
    main()
