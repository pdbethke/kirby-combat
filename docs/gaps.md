# What the O.K. Corral does not reach

The shootout exists to FLEX the engine, not to reproduce 1881. Its seed is
chosen for how many distinct rule paths it exercises, and this file is the
other half of that measurement: what fifty-nine fights never touched.

Measured 2026-09-10 over seeds 1-59 of `examples/the_shootout_we_can_publish.py`.
Regenerate by re-running the probe described at the bottom.

## The headline

**Four of sixty-two action kinds are ever chosen.** Across 59 complete
fights and 772 resolved actions:

| kind | times chosen |
|---|---|
| `attack` | 525 |
| `move_to_cover` | 128 |
| `disengage` | 118 |
| `attack_construct` | 1 |

Everything else in the engine is either never offered here or offered and
never taken.

## Offered and never taken

These are on the menu and `TacticChooser` has never once picked them.
Counts are offers in a single opening menu across all nine men.

| kind | offers | chosen |
|---|---|---|
| `move_strike` | 48 | 0 |
| `presence_attack` | 40 | 0 |
| `block` | 40 | 0 |
| `move` | 40 | 0 |
| `rapid_fire` | 37 | 0 |
| `move_by` | 36 | 0 |
| `move_through` | 36 | 0 |
| `coordinate` | 32 | 0 |
| `dodge` | 9 | 0 |
| `set` | 9 | 0 |
| `hide` | 9 | 0 |
| `hold` | 9 | 0 |
| `presence_attack_group` | 9 | 0 |
| `multiple_attack` | 8 | 0 |
| `haymaker` | 7 | 0 |
| `spread` | 5 | 0 |
| `climb` / `climb_fast` | 2 each | 0 |

`move_strike` is the **most-offered action in the game** and has never been
taken. Two reasons, and only the second is a defect:

1. It wraps a MELEE attack, and every offer here wraps the bare STR
   Strike — so the chooser is being asked to walk up and punch a man it
   could shoot. Declining is correct.
2. There is no offer that closes the range to improve a RANGED shot, which
   is a real HERO tactic the engine cannot express at any distance.

`hide` never being taken is the one with the widest blast radius: it is the
only manoeuvre in the game that produces 6E2 p.52's Surprised, so the whole
Surprised path — half DCV, doubled STUN out of combat — is unreachable in
this fight even though it is wired.

## Never offered here at all

Forty-one kinds do not appear in the **opening menu** of this scene. Some
are legitimately absent — nobody has a mental power, an Entangle or a VPP,
and a state-dependent offer like `release_held` or `escape_str` cannot
appear before the state exists. Others are absences worth explaining:

- **`stabilize`** — built for 6E2 p.109 and offered only for a DYING ALLY.
  Nobody is dying at the start, so it cannot be in an opening menu; whether
  it is ever offered MID-fight is a separate measurement this file does not
  yet make. Doc Holliday carries Paramedics 11- specifically for it.
- **`push`** — correctly absent now: every weapon in the lot runs on
  Charges, and 6E2 p.135 forbids Pushing those. This was 37 illegal offers
  until 2026-09-10.
- **`grab`, `trip`, `disarm`, `strike`, `throw`** — melee, and gated off by
  distance the same way `move_strike` is gated on.
- **`reposition*`** — needs a vantage or a line-of-sight problem to solve,
  and this lot is flat and open.

## Rules that fire, and rules that do not

Reached by the chosen seed (59): eight Hit Locations including Head and
Vitals, both bleeding rules, Stunned, Knocked Out, Dying, a cover penalty,
and a shot whose Hit Location roll finds the cover instead of the man
(6E2 p.45).

Never reached in any of the 59:

- **Surprised** (6E2 p.52) — needs `hide`, which is never chosen.
- **The Range Modifier** — every shot in the lot is inside 8 m, so the
  penalty is always zero. The table is exercised only by unit tests.
- **Penetrating / Armor Piercing** — no weapon here has either.
- **Stabilize** — see above.

The Corral cannot test any of these. That is a limit of the SCENE, not of
the engine, and the honest fix is a second benchmark laid out for range and
concealment rather than stretching this one.

## Regenerating

The probe counts, per seed, the distinct rule paths an attack touches — it
spies on `AttackAction.resolve` for cover, surprise, range and Hit Location
audit lines, and folds `ActionResolved` kinds, `status_changes` and
`BleedingSuffered` rules out of the event log. Offers come from one opening
menu via `enumerate_actions`; **offers are an opening-menu count and choices
are a whole-fight count**, so the two columns are not directly comparable
and the table above says so.
