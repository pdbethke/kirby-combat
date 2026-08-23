"""Mental duel — the OMCV/DMCV pipeline, which physical combat never touches.

HERO resolves mental attacks on a parallel track: OMCV against DMCV instead of
OCV against DCV, Mental Defense instead of PD/ED, and effect measured against
the target's EGO rather than as STUN and BODY. This demo runs that track.

Exercises:
  - resolve_mental_to_hit  (OMCV vs DMCV, and LOS is irrelevant)
  - resolve_mental_blast   (damage reduced by Mental Defense, not PD/ED)
  - resolve_mind_control   (effect rolled against EGO breakpoints)

No dependencies beyond the package: the combatants are built here rather than
loaded from a character file.

Run with:
    .venv/bin/python examples/mental_duel.py
"""
from __future__ import annotations

from kirby_combat.mental.mental_combat import resolve_mental_to_hit
from kirby_combat.mental.mental_blast import resolve_mental_blast
from kirby_combat.mental.mind_control import resolve_mind_control
from kirby_combat.models import Combatant


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def bar(c: Combatant, *, stun: int | None = None) -> str:
    cur = c.current_stun if stun is None else stun
    filled = max(0, min(20, round(20 * cur / max(1, c.max_stun))))
    return (f"   {c.name:10} STUN [{'▓' * filled}{'░' * (20 - filled)}] "
            f"{cur:>3}/{c.max_stun}   EGO {c.ego}  DMCV {c.dmcv}  MD {c.md}")


# ─────────────────────────────────────────────────────────────────────────────
# Cast — a telepath and a target with some mental resistance
# ─────────────────────────────────────────────────────────────────────────────

TELEPATH = Combatant(
    id="telepath", name="The Whisper",
    ocv=5, dcv=6, omcv=9, dmcv=8,
    spd=4, dex=15, ego=25, str_=10, con=15, pre=25, rec=6,
    pd=4, ed=4, rpd=0, red=0, md=10,
    power_defense=0, flash_defense=0,
    max_stun=30, max_body=10, max_end=40,
    current_stun=30, current_body=10, current_end=40,
    attacks=[], defenses=[], is_mentalist=True,
)

SOLDIER = Combatant(
    id="soldier", name="Sentry",
    ocv=8, dcv=7, omcv=3, dmcv=4,
    spd=4, dex=18, ego=13, str_=18, con=20, pre=15, rec=8,
    pd=8, ed=8, rpd=4, red=4, md=3,          # a little Mental Defense
    power_defense=0, flash_defense=0,
    max_stun=40, max_body=12, max_end=40,
    current_stun=40, current_body=12, current_end=40,
    attacks=[], defenses=[],
)


def main() -> None:
    rule(f"MENTAL DUEL — {TELEPATH.name} vs {SOLDIER.name}")
    print("  Mental combat runs on OMCV/DMCV and is not blocked by walls or")
    print("  darkness — only by range and the target's mental defences.")
    print(bar(TELEPATH))
    print(bar(SOLDIER))

    # ── 1. The mental to-hit roll ────────────────────────────────────────────
    rule("1. Reaching the mind — OMCV vs DMCV")
    hit = resolve_mental_to_hit(TELEPATH, SOLDIER, [3, 4, 4], distance_m=40.0)
    print(f"  {TELEPATH.name} OMCV {TELEPATH.omcv}  vs  "
          f"{SOLDIER.name} DMCV {SOLDIER.dmcv}")
    print(f"  rolled {sum([3, 4, 4])} on 3d6 at 40 m")
    verdict = "CONTACT" if hit.hit else "NO CONTACT"
    print(f"  → {verdict}  (needed {hit.target_number}, margin {hit.margin})")

    # ── 2. Mental Blast — reduced by Mental Defense, not PD/ED ───────────────
    rule("2. Mental Blast — Mental Defense is the only thing that helps")
    blast = resolve_mental_blast(TELEPATH, SOLDIER, [5, 5, 4, 6])
    raw = sum([5, 5, 4, 6])
    print(f"  4d6 Mental Blast rolled {raw}")
    print(f"  {SOLDIER.name}'s Mental Defense: {SOLDIER.md}")
    print(f"  → STUN through: {blast.stun_dealt}")
    print(f"     his PD {SOLDIER.pd} and ED {SOLDIER.ed} are irrelevant here")
    print(bar(SOLDIER, stun=SOLDIER.current_stun - blast.stun_dealt))

    # ── 3. Mind Control — effect measured against EGO ────────────────────────
    rule("3. Mind Control — the roll is measured against EGO, not STUN")
    for label, dice in (("a weak push", [2, 2, 3, 1]),
                        ("a hard shove", [6, 6, 5, 6])):
        mc = resolve_mind_control(TELEPATH, SOLDIER, dice)
        total = sum(dice)
        print(f"  {label:14} 4d6 → {total:>2}  vs EGO {SOLDIER.ego}"
              f"   (EGO+10 = {SOLDIER.ego + 10}, EGO+20 = {SOLDIER.ego + 20})")
        print(f"                 → margin {mc.margin:+d}  →  {mc.degree}")

    rule("END")
    print("  Physical position never entered any of the above: the same three")
    print("  calls resolve identically through a wall, in darkness, or across")
    print("  a room — which is what makes mental combat its own pipeline.\n")


if __name__ == "__main__":
    main()
