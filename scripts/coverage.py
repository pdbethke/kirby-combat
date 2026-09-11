#!/usr/bin/env python3
"""How much of the engine a benchmark actually reaches.

WHY A SCRIPT AND NOT A NOTE. The first version of this measurement was a
throwaway heredoc, and its numbers went into `docs/gaps.md` where nobody
could reproduce or re-run them --- which is the same defect this whole
engine keeps growing: something computed once, correct, and delivered
nowhere. "Did that change help?" is only answerable against a baseline
you can regenerate.

WHAT IT COUNTS

  * **Kinds offered** and **kinds chosen**, both across EVERY menu of
    every fight. The heredoc counted offers from one opening menu and
    choices across whole fights, so the two columns were not comparable
    and the doc had to say so. Recording the chooser's own `situation`
    fixes that: the driver hands it the real menu on every Phase.
  * **Rule paths reached** --- Hit Locations, cover penalties, the range
    modifier, Surprised, both bleeding rules, status changes. These are
    what a benchmark is FOR: an engine's thin spots are the rules nothing
    ever runs.

THE POINT IS THE COMPARISON. `--chooser` swaps the thing under test, so
the same fight can be measured under doctrine and under a model. A
deterministic chooser reaching four kinds of sixty-two says something
about the chooser; a MODEL reaching four says something about what the
Brief is showing it, which is a different repair entirely.

    python scripts/coverage.py --seeds 20
    python scripts/coverage.py --seeds 20 --baseline docs/coverage.json
    python scripts/coverage.py --seeds 5 --chooser deliberate
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "examples"))


class Recorder:
    """Wraps a chooser and writes down everything it was offered.

    THE MENU IS ONLY VISIBLE HERE. `enumerate_actions` is called deep in
    `run_phase` and its result goes straight into the `PhaseSituation`;
    spying on the function gets the opening menu of one fight, spying on
    the CHOOSER gets every menu of every Phase, which is the number that
    can honestly be set beside the choices.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.offered: Counter[str] = Counter()
        self.chosen: Counter[str] = Counter()
        #: Findings against the decisions actually made, by kind.
        #: VARIETY WAS NEVER QUALITY. Everything above counts what was
        #: picked; this counts what was picked WRONG -- see
        #: `kirby_combat.critique`, and `docs/gaps.md`'s closing line.
        self.findings: Counter[str] = Counter()
        #: One example sentence per finding kind, so a count of
        #: "futile: 14" can be chased to the man and the gun.
        self.examples: dict[str, str] = {}

    def choose(self, situation) -> str:
        for action in situation.menu:
            self.offered[action.kind] += 1
        picked = self._inner.choose(situation)
        for action in situation.menu:
            if action.action_id == picked:
                self.chosen[action.kind] += 1
                break
        self._grade(situation, picked)
        return picked

    def _grade(self, situation, picked) -> None:
        """Grade the decision, and never let grading kill the fight.

        A grader is an OBSERVER. If it raises -- a target shape it cannot
        read, an id it cannot match -- the measurement loses one datum and
        the run continues; the alternative is a benchmark that dies on the
        thing it was built to find.
        """
        from kirby_combat.critique import critique

        try:
            found = critique(situation, picked)
        except Exception as exc:                        # noqa: BLE001
            self.findings["grader-error"] += 1
            self.examples.setdefault("grader-error", f"{type(exc).__name__}: {exc}")
            return
        for finding in found:
            self.findings[finding.kind] += 1
            self.examples.setdefault(finding.kind, finding.why)


def _rule_paths(session, attack_audits) -> set[str]:
    """Every distinct rule this fight actually ran."""
    from kirby_combat.serialization.to_dict import to_dict

    hits: set[str] = set(attack_audits)
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        payload = to_dict(event)
        if kind == "ActionResolved":
            for status in (payload.get("result_payload") or {}).get("status_changes", ()):
                hits.add(f"status:{status}")
        elif kind == "BleedingSuffered":
            hits.add(f"bleed:{payload.get('rule', '')}")
        elif kind == "MovementResolved":
            hits.add("moved")
            move = payload.get("move_type") or ""
            if move and move != "move":
                hits.add(f"move:{move}")
            a, b = payload.get("from_pos") or {}, payload.get("to_pos") or {}
            if a and b and abs((b.get("z") or 0) - (a.get("z") or 0)) >= 1.0:
                hits.add("changed-height")
        elif kind == "RecoveryTaken":
            hits.add("recovery")
    return hits


def _watch_height(seen: set) -> callable:
    """Note shots taken across a height difference.

    A SEPARATE SEAM, and it has to be: a combatant does not carry a
    position --- the SCENE does, in `combatant_positions` --- and
    `AttackAction.resolve` is handed neither. `resolve_attack_in_session`
    is the layer that holds both, which is exactly why cover is folded in
    there too.

    Without this the probe could not tell "there are rooftops in the
    scene file" from "anybody ever shot from one", and the second
    benchmark's whole reason for existing is the difference.
    """
    # PATCHED WHERE IT IS USED, not where it is defined. `loop.resolvers`
    # does `from ...recording import resolve_attack_in_session` at import
    # time, so rebinding the attribute on `recording` afterwards
    # intercepts nothing --- the first attempt saw zero calls while the
    # fight was plainly resolving attacks.
    import kirby_combat.loop.resolvers as recording

    original = recording.resolve_attack_in_session

    def spy(session, attack, template, **kwargs):
        scene = getattr(session, "scene", None)
        positions = getattr(scene, "combatant_positions", None) or {}
        here = positions.get(getattr(attack.attacker, "id", None))
        there = positions.get(getattr(attack.target, "id", None))
        if here is not None and there is not None and abs(here.z - there.z) >= 1.0:
            seen.add("shot-across-height")
        return original(session, attack, template, **kwargs)

    recording.resolve_attack_in_session = spy

    def restore() -> None:
        recording.resolve_attack_in_session = original

    return restore


def _watch_attacks() -> tuple[set, callable]:
    """Patch `AttackAction.resolve` to note which rules each attack ran."""
    import kirby_combat.actions.base as base

    seen: set[str] = set()
    original = base.AttackAction.resolve

    def spy(self, attack, template, *args, **kwargs):
        result = original(self, attack, template, *args, **kwargs)
        if attack.ocv_modifier:
            seen.add("cover-penalty")
        if getattr(attack, "surprise", None):
            seen.add("surprised")
        if attack.distance_m and attack.distance_m > 8:
            seen.add("range-penalty")

        for line in result.audit_trail:
            if line.startswith("Hit Location "):
                seen.add("loc:" + line.split()[2].rstrip(":"))
            if "finds the cover" in line:
                seen.add("shot-hit-cover")
            if "Penetrating" in line:
                seen.add("penetrating")
        return result

    base.AttackAction.resolve = spy
    restore_height = _watch_height(seen)

    def restore() -> None:
        base.AttackAction.resolve = original
        restore_height()

    return seen, restore


def _chooser(name: str):
    """The thing under test.

    The model choosers live in kirby-ai, which this engine does not depend
    on --- kirby-combat is Tier 1 pure and owns no network hop. Imported
    lazily and by name so a machine without kirby-ai can still run the
    doctrine baseline.
    """
    from kirby_combat.loop import TacticChooser

    if name == "tactic":
        return TacticChooser()

    # EVERYTHING ABOUT PROVIDERS LIVES IN kirby-ai. This module used to
    # assemble the client itself and had to name a base-URL variable, a
    # token variable and a provider to do it --- which
    # `tests/test_vocabulary.py` refused, correctly: "a library must not
    # name its consumers' internals". This engine is Tier 1 pure and owns
    # no network hop. It asks for a chooser BY NAME.
    #
    # DOCTRINE IS THE FALLBACK, never `FirstLegalChooser`: when the model
    # cannot answer, the next best thing is the catalogue tuned against
    # this same fight. It also means a run that cannot reach its provider
    # QUIETLY BECOMES the doctrine baseline instead of failing, which is
    # why `report` prints how many decisions the model actually answered.
    try:
        from kirby_ai import chooser_from_env
    except ImportError as exc:            # pragma: no cover - env-dependent
        raise SystemExit(
            f"--chooser {name} needs kirby-ai on the path ({exc})"
        ) from exc

    try:
        return chooser_from_env(name, fallback=TacticChooser())
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


#: The benchmarks, and what each is FOR. Two, because one scene cannot
#: exercise everything: the Corral is a knife-range brawl where cover,
#: Hit Locations and bleeding bite, and it has no range, no height and
#: nothing you can get out of sight behind. See `docs/gaps.md`.
SCENES = {
    "corral": "the_shootout_we_can_publish",
    "street": "the_long_street",
}


def measure(seeds: range, chooser_name: str, scene: str = "corral") -> dict:
    import importlib

    the_fight = importlib.import_module(SCENES[scene]).the_fight

    recorder = Recorder(_chooser(chooser_name))
    audits, restore = _watch_attacks()
    paths: set[str] = set()
    phases = 0
    decided = 0
    try:
        for seed in seeds:
            _, result = the_fight(seed, chooser=recorder)
            phases += result.phases
            decided += 1 if result.winner else 0
            paths |= _rule_paths(result.encounter.sessions[0], audits)
    finally:
        restore()

    from kirby_combat.enumeration import ALL_ACTION_KINDS

    # DID THE MODEL ACTUALLY ANSWER? A chooser that cannot reach its
    # provider does NOT fail --- it falls back to doctrine by design and
    # records the reason --- so a broken run produces a baseline identical
    # to the doctrine one and reads as a finished experiment. `ModelChooser`
    # carries every fallback in `.notes`; a run where that count equals the
    # decision count called nothing.
    inner = recorder._inner
    picks = list(getattr(inner, "picks", []) or [])
    fell_back = sum(1 for p in picks if getattr(p, "fell_back", False))
    notes = [n for n in (getattr(inner, "notes", []) or [])][:3]

    return {
        "chooser": chooser_name,
        "scene": scene,
        # WHICH PAGE THIS MEASURED. A baseline records the numbers and,
        # until now, nothing about the Brief that produced them --- so a
        # run with a switch flipped compared silently against one without
        # it and the diff read as a behaviour change. Every switch that
        # alters what a chooser SEES belongs here.
        # KIRBY_BRIEF_NO_DOCTRINE is the one that matters most: the page
        # ends with TacticChooser's own ranked answer, and a model shown
        # it agrees with it. Every model-versus-doctrine number taken
        # without recording this flag was comparing a chooser against its
        # own advice. Default "" because UNSET is the on state for this
        # one, unlike the others.
        "brief_switches": {
            "KIRBY_BRIEF_FORMATION": os.environ.get("KIRBY_BRIEF_FORMATION", "1"),
            "KIRBY_BRIEF_NO_DOCTRINE": os.environ.get("KIRBY_BRIEF_NO_DOCTRINE", ""),
        },
        "decisions": len(picks),
        "fell_back": fell_back,
        "first_fallback_notes": notes,
        "fights": len(list(seeds)),
        "phases": phases,
        "decided": decided,
        "kinds_total": len(ALL_ACTION_KINDS),
        "offered": dict(recorder.offered),
        "chosen": dict(recorder.chosen),
        # WHAT WAS PICKED WRONG. Counts only; each kind's example
        # sentence rides alongside so a number can be chased to the Phase
        # that produced it.
        "findings": dict(recorder.findings),
        "finding_examples": dict(recorder.examples),
        "rule_paths": sorted(paths),
    }


def report(m: dict) -> None:
    chosen, offered = m["chosen"], m["offered"]
    print(f"scene: {m.get('scene', 'corral')}   "
          f"chooser: {m['chooser']}   {m['fights']} fights, "
          f"{m['phases']} Phases, {m['decided']} decided")
    # ONLY FOR A MODEL RUN. `TacticChooser` records picks too, so this
    # printed "MODEL ANSWERED 69 of 69" for a run with no model in it --
    # true of the recording and false of the sentence.
    if m["chooser"] != "tactic" and m.get("decisions"):
        answered = m["decisions"] - m["fell_back"]
        print(f"MODEL ANSWERED {answered} of {m['decisions']} decisions "
              f"({m['fell_back']} fell back to doctrine)")
        for note in m.get("first_fallback_notes") or []:
            print(f"    fallback: {note}")
    print(f"\nKINDS CHOSEN: {len(chosen)} of {m['kinds_total']}")
    for kind, n in sorted(chosen.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:24} {n:5}   (offered {offered.get(kind, 0)})")

    dead = {k: v for k, v in offered.items() if not chosen.get(k)}
    print(f"\nOFFERED AND NEVER TAKEN: {len(dead)}")
    for kind, n in sorted(dead.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:24} offered {n:5}, chosen 0")

    # QUALITY, WHICH IS NOT VARIETY. Everything above says what was
    # chosen; this says what was chosen WRONG. A clean sweep is NOT a
    # good chooser -- these graders only ever indict, never endorse.
    findings = m.get("findings") or {}
    decisions = m.get("decisions") or 0
    total = sum(findings.values())
    print(f"\nBAD DECISIONS: {total}"
          + (f" of {decisions} ({100.0 * total / decisions:.1f}%)"
             if decisions else ""))
    if not findings:
        print("  none provable — NOT the same as none made")
    for kind, n in sorted(findings.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:24} {n:5}")
        example = (m.get("finding_examples") or {}).get(kind)
        if example:
            print(f"      e.g. {example}")

    print(f"\nRULE PATHS REACHED: {len(m['rule_paths'])}")
    print("  " + ", ".join(m["rule_paths"]))


def compare(now: dict, before: dict) -> None:
    print("\n--- against the baseline ---")
    was = before.get("brief_switches") or {}
    now_switches = now.get("brief_switches") or {}
    if was and was != now_switches:
        print(f"  ⚠ DIFFERENT PAGE: switches were {was}, now {now_switches}. "
              f"Any difference below may be the switch, not the chooser.")
    for field in ("fights", "phases"):
        print(f"  {field}: {before[field]} -> {now[field]}")
    gained = set(now["chosen"]) - set(before["chosen"])
    lost = set(before["chosen"]) - set(now["chosen"])
    print(f"  kinds chosen: {len(before['chosen'])} -> {len(now['chosen'])}"
          + (f"   NEW: {sorted(gained)}" if gained else "")
          + (f"   LOST: {sorted(lost)}" if lost else ""))
    was_bad = sum((before.get("findings") or {}).values())
    now_bad = sum((now.get("findings") or {}).values())
    print(f"  bad decisions: {was_bad} -> {now_bad}")

    gained_paths = set(now["rule_paths"]) - set(before["rule_paths"])
    lost_paths = set(before["rule_paths"]) - set(now["rule_paths"])
    print(f"  rule paths: {len(before['rule_paths'])} -> {len(now['rule_paths'])}"
          + (f"   NEW: {sorted(gained_paths)}" if gained_paths else "")
          + (f"   LOST: {sorted(lost_paths)}" if lost_paths else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--scene", default="corral", choices=tuple(SCENES),
                    help="which benchmark to measure")
    ap.add_argument("--chooser", default="tactic",
                    choices=("tactic", "model", "deliberate", "council"))
    ap.add_argument("--baseline", default=None,
                    help="compare against this file, and write it when absent")
    args = ap.parse_args()

    m = measure(range(args.first_seed, args.first_seed + args.seeds),
                args.chooser, args.scene)
    report(m)

    if args.baseline:
        path = pathlib.Path(args.baseline)
        if path.exists():
            compare(m, json.loads(path.read_text()))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(m, indent=1))
            print(f"\nwrote the baseline to {path}")


if __name__ == "__main__":
    main()
