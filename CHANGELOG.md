# Changelog

## 0.25.0 — 2026-10-30

**No default combat template, anywhere** (Peter's no-defaults rule). Which optional rules a fight plays by is the campaign's decision; a default was the engine making it silently. Found the hard way: an Encounter with no template ran under `DEFAULT_TEMPLATE` (Superheroic) whatever its fights were created with, so a heroic sweep charged no END (2026-10-29). Tests: `tests/test_no_default_template.py`. The event schema does not change (templates are not in it).

**Breaking:**
- `CombatTemplate` has no field defaults: every switch is stated by whoever builds one (`dataclasses.replace(RAW_SUPERHEROIC, ...)` for a variant). It is now **frozen**: one template is shared by every campaign and fight that names it, and a change made in place was a change to all of them. `allowed_hit_locations` is a tuple.
- `DEFAULT_TEMPLATE` is gone. So is `CombatTemplate.custom_rules`, an untyped dict nothing read: a house rule is a named field the engine reads, or it is not a rule.
- `Campaign.template` is required (it defaulted to a deep copy of `DEFAULT_TEMPLATE`).
- `Encounter` resolves its template from a Campaign, else its own `template`, else the one template its fights were created with. Fights under different templates, an Encounter template that contradicts a fight's, or nothing to read at all, **raise**. An Encounter with no fights needs no template to advance.
- `compute_knockback(body, dice, *, kb_resistance_m, template, impact_target=None)`: `knockback_multiplier` is read off the template (it was a second argument beside it, and every caller passed `template.knockback_multiplier`); `kb_resistance_m` and `template` are required.
- `effect_for(location, *, template)`, `uses_hit_locations(template, target)` and `endurance.tracks_endurance(template, combatant)` take a template, never None (None used to mean "no restriction", "no hit locations" and "count END").
- `critique` grades a shot under the situation's own fight's template, so a `PhaseSituation` it grades must carry its `session`; it was graded under `DEFAULT_TEMPLATE`.

Flagged, not changed: `one_hit_wonder_enabled` / `one_hit_wonder_pct` are read by nothing, so switching One-Hit Wonder on does nothing. They are required like every other field until the rule is built or the switch is dropped.

## 0.24.1 — 2026-10-30

- **Out of END, he pays in STUN** (6E2 p.133: "A character who runs out of END ... and still wishes to perform Actions may use STUN as END. The character takes 1d6 STUN Only damage for every 2 'END' (or fraction thereof) used, and no defense is allowed ... Characters cannot spend END below 0"). `endurance.spend_end` spends what he has, then rolls the rest off the session's dice as STUN (`VitalsChanged` reason `stun_for_end`); he is Knocked Out when it takes him to 0, as any STUN loss does. It used to clamp at 0 and charge nothing more, so a man out of END attacked for free for the rest of the fight: found when kirby-api moved to 0.24.0, where most seeded random fights ran to the turn cap (Bullet emptied his END in Turn 10 and kept blasting every Phase). An Endurance Reserve still never pays in STUN (6E1 p.208). A session with no `dice_roller` that owes STUN raises. Seam tests: `tests/loop/test_stun_for_end.py`. No new event kind; the schema changes only its version.

## 0.24.0 — 2026-10-30

Movement and END. **Behaviour changes** for every consumer: superheroic fights now spend END on attacks, movement, Pushes and Constant powers; every move costs END; fliers and teleporters actually move; a man knocked off the map comes back instead of leaving. Requires **kirby-cost >= 0.6.3** (the build doc says which powers run off an Endurance Reserve). Two new event kinds, `ForcedOffTheBoard` and `EnduranceReserveChanged` (schema regenerated; Krackle needs folds for both). **Breaking:** `MovementCapability.end_per_10m` → `end_cost`; `placement.move_toward` requires `template=`; `recording._spend_attack_end` requires `power=`.

- **Knocked off the board, and coming back** (Peter's ruling, 2026-10-29). Knockback, a Throw or a shove past the map's edge used to put a man out of the fight for good (`Roster.has_left`), after a fall to the bounds' floor that nobody took (4 of 6 demo seeds). New module `off_board.py`; new event kind `ForcedOffTheBoard` (schema regenerated). Seam tests: `tests/loop/test_off_the_board.py`.
  - Beyond the edge the ground goes on at the height where he crossed it, so there is no phantom fall. A real one (off a roof at the edge) still lands him.
  - He comes back to the point where he crossed, at COMBAT speed (6E2 p.25-26). Getting up first takes half of his first Phase (6E2 p.116).
  - He uses the mode that gets him back in the fewest Phases, of running, leaping, flight and teleportation. A tie goes to the cheaper trip in END, then to that order. The trip back pays END like any move (6E1 p.158), from the pool the mode draws on; a mode an empty Endurance Reserve runs is not a way back. A man in the air flies or teleports.
  - `ForcedOffTheBoard` records the exit point, distance, mode, metres per Phase, Phases and the Turn/Segment he is due back. His Phases are spent moving him back, with no menu. Each one is worked out again, so a Stun delays him. A return using half his movement or less leaves him a Half Phase to act from the edge (6E2 p.26).
  - While he is off the board he is no target, ally or patient (`Roster.on_the_board`). He has not left (`Roster.is_off_board`), so his side is not beaten. A man with no way back has left, and walking off is still leaving.
- **Endurance Reserves** (6E1 p.207-208). 61 of 989 corpus characters own one (power packs, fuel tanks) and combat never read it: every power paid from the character. New event kind `EnduranceReserveChanged` (schema regenerated); `HeroCombatant.reserves()` / `models.EnduranceReserve`; `AttackPower.uses_end_reserve`, `MovementCapability.uses_end_reserve`; snapshots carry `reserves`. Seam tests: `tests/loop/test_endurance_reserves.py`.
  - A power bought to draw on a Reserve (HD's USE_END_RESERVE) is paid from it and never from him; every other spend is his. One door, `endurance.pay_end` (`spend_from` for Pushes, which are always paid, from the pushed power's pool). `_spend_attack_end` now requires `power=`; STR and EGO escapes pass None (his own END).
  - An empty battery runs nothing: a reserve power the Reserve cannot pay for is not offered ("cannot spend STUN in the place of Endurance Reserve END"). RULING: a reserve-powered movement mode is offered only while the Reserve can pay for a full move. Lingering and Constant powers stop when their pool cannot pay.
  - It Recovers its REC at the Post-Segment 12 Recovery, up to its storage, even with its owner Knocked Out. Extra Time on the REC slows it to its Time Chart step (a 1 Day REC never Recovers in a fight). RULING: Limited Recovery never Recovers in a fight. Free-text custom Limitations are not read for timing.
  - RULING on "can choose whichever one he wants": with two Reserves he draws on the fullest.
  - `StatBlockCombatant.reserves()` is empty: a stat block is not a build.
  - Needs kirby-cost with USE_END_RESERVE in the build doc (kirby-cost #2): a doc from an earlier kirby-cost says no power draws on a Reserve.

- **Superheroic counts END** (Peter's ruling, 2026-10-29). `RAW_SUPERHEROIC` (`6e-superheroic`, the template every fight used) shipped `manage_endurance=False` as "END optional", so nobody ever paid END for anything. 6E2 p.133: "In Superheroic campaigns, many characters pay END just to maintain their Powers, so END is very important." Both flags are now True, for player characters and NPCs. A table that hand-waves END says so with its own template. **Behaviour change** for every consumer: attacks, movement, Pushes and Constant powers now spend END in superheroic fights.
- **Moving costs END** (6E1 p.158). Nothing in the loop charged it: closing, repositioning, the Half Move, move-and-strike, Move By/Through and climbing all went through `placement.move_toward`, which took no END; only a Push's extra was ever paid. Seam tests: `tests/loop/test_movement_costs_end.py`.
  - A full move costs 1 END per 10 Active Points of the movement, free Running 12m included. A movement power's figure is the cost engine's own END column (`end_usage`: Reduced Endurance ½/0, Increased Endurance Cost and Charges already in it). Running and Leaping bought as characteristics price their metres at the template's rate (Running 1 point/m, Leaping 1 per 2m). The book's sheets agree: Running 14m and Leaping 8m are each 1 END (6E2 p.180).
  - A part move pays its share ("half the power's full END cost when making a Half Move"), rounded as 6E1 p.132 rounds END, at least 1. Metres past a full move are a Push and are paid by the Push.
  - Charged only where the campaign counts END (`manage_endurance`), as attacks are. `tracks_endurance` and the clamped, logged `spend_end` moved to `endurance.py` (lift and shift from `recording.py` / `resolvers.py`).
  - RULING: Climbing costs no END (a Skill; the book prints none).
  - **Breaking:** `MovementCapability.end_per_10m` is replaced by `end_cost` (a full move's END). The old table (2 per 10m for Teleportation, Leaping priced as Running) was not 6E and nothing read it. `move_toward` now requires `template=`.
  - **Fixed: fliers never flew.** `resolvers._move_capacity` read the mode as a characteristic (`characteristic_value("FLIGHT")`), 0 for Flight, Teleportation, Swimming and Tunneling, which are powers; every full or half move by them went 0m while the menu kept offering it. It now reads `movement_view`, the view the offer comes from.
  - **Fixed:** Running or Leaping never bought up is absent from the .hdc (kirby-cost seeds the base from the template), and pricing its END raised. Its rate now comes from the same template (`HDTTemplateProvider`).
  - **Fixed:** `move`, `move_to_cover` and `disengage` left their own `MovementResolved` (and now the END row) out of `ResolvedAction.events`, the defect `_reposition` had already fixed for itself. `run_phase`'s events, read off the log, were unaffected.

## 0.23.0 — 2026-10-28

- **Knockback, throws, climbing and Adjustment: the pieces #10 and #13 left unbuilt** (follow-up K2b). New action kind `roll_with_punch`. `AdjustmentApplied` gains `fade_interval_turns` and `AdjustmentFaded` gains `adjustment_id`, both defaulted, so rows written before them replay as before (schema regenerated). Seam tests: `tests/loop/test_knockback_throw_climb_extras.py`, `tests/loop/test_adjustment_extras.py`.
  - Knockback: a man knocked into a wall he shatters flies on through it. A wall that holds still takes the impact, and he takes half the metres of the whole knockback. Double Knockback doubles the BODY before the roll. Does Knockback lets an attack that does no BODY knock him back (not yet on a Mental Blast, which moves nobody). Underwater adds a die, and so does Clinging unless it was bought unable to resist knockback.
  - **Roll With The Punch** (`actions/reactive/roll_with_punch.py`): he takes half, the knockback roll loses a die, and it costs nothing when the blow misses.
  - Throws (`throw_effects.py`): the thrower acts first when their next Phases share a Segment; otherwise the priority lapses. Acrobatics at -3 keeps his feet, and the fall alone can Stun him.
  - Climbing (`climbing_state.py`): a difficult face is ½ DCV and an easy one -1 DCV. A Climbing roll sheds the penalties. From a difficult face his attacks lose 2 DCs, and knockback takes him off the wall. A long fall is read off the velocity, not capped.
  - A Furnishing's face is the Furnishing: knocked into a wagon, he meets its PD + BODY and the wagon takes the damage, not one plank. Through it, he passes its far side too. Each wall impact on the way is checked for Stun on its own (6E2 p.105).
  - **Fixed (pre-existing on main):** a Furnishing brought down by any attack stayed on the board, its edges still blocking movement and giving cover. `collapse._off_the_board` now removes the Furnishing and its faces.
  - Adjustment: two Drains, or two Aids, on one stat fade separately (6E1 p.139). Delayed Return Rate fades on its own clock (6E1 p.142). Healing heals a Drained characteristic and it stays healed (6E1 p.234), and it is offered when a Drain is his only loss.
  - Area Drain hits everyone in the Area with one roll (6E1 p.143). Area Mind Control gives one order and makes one Effect Roll, OMCV against DMCV 3 (6E1 p.154), and each victim meets a Mental Paralysis's Mental Defense as well (6E1 p.219). Not offered: an Explosion Drain, or a Constant, Damage Over Time, Surface or Any Area Drain or Mind Control.

- **The seat is told how much of the Phase is left** (`PhaseSituation.halves_left`, 6E2 p.20). Since the Half Phase economy the same Phase comes back after a Half Phase Action with the menu cut, and nothing told the seat why. A derived property over `action_time` (nothing stored, so nothing to drift): own Phase 2 then 1 (1 all along for a very impressed man, 6E2 p.139); a Held Action question 1 when he Holds only the second half (6E2 p.22), else 2; an Abort question None (it costs his NEXT Phase, 6E2 p.24); no fight behind the situation raises. The Brief says it: "This is the second half of your Phase: you have taken a Half Phase Action (half move) ..." and, for a held half, "What you Hold is only a Half Phase". Seam test: `tests/loop/test_the_page_says_which_half.py`.
- **A Phase in halves: the Half Phase action economy** (follow-up K2a; 6E2 p.20-26). New module `action_time.py`; new event kinds `PhaseTimeUsed` and `ConcentrationBegan`; `EntangleApplied` gains `transparency` and `both_take_damage` (schema regenerated). New action kinds `half_move`, `snap_out_of_rage`, `attack_entangle`. Seam tests: `tests/loop/test_half_phase_economy.py`.
  - The loop gave one action a Phase. Every kind is now priced in `action_time.KIND_TIMES` (No Time, Zero, Half, Attack Action, Full, Hold, Break-out), each with its page. `time_of` raises on a kind nobody priced, and a test holds the table to the resolver registry. After an Action that leaves the Phase his, `run_phase` writes `PhaseTimeUsed` and does not spend the slot. The next `run_phase` hands him the same Phase, and `rest_of_phase` cuts the menu to what fits: after one Half Phase Action, no Full Phase Action. One declaration per `run_phase` call, as before.
  - Unified: the four hand-written Zero Phase exits (Instant Change, reallocation, Damage Shield, Presence Attack) and the very-impressed limit (6E2 p.139: one Half Phase instead of two) are the same fold. `phase_already_begun` reads `PhaseTimeUsed` too, so Breakout and rage rolls are not owed twice. `in_the_phase.HALF_PHASE_EXCLUDED` / `limit_to_half_phase` are gone; `action_time.FULL_PHASE_KINDS` replaces the table.
  - Half Phase now: `half_move` (new: one per Full Move offered, half the distance, 6E2 p.26), `stand_up` (6E2 p.25), `pick_up_weapon`, `pickup` (ruling), `move_to_cover`, `hide` and the interaction skills (6E2 p.20 "most ... Skill Rolls"), `escape_teleport` (ruling).
  - A Hold after a Half Phase Action holds a Half Phase (6E2 p.22). Released out of turn, its menu is only what fits in a half.
  - Break-outs are priced by 6E2 p.126. An Entangle broken by twice its BODY takes no time; by its BODY, a Half Phase is left; short of it, the Phase ends. A Grab broken by twice the Grabber's BODY takes no time; otherwise the Phase ends. `EntangleResult.action_regained` and the Grab escape's payload `outcome` record it.
  - **Correction to the brief:** Casual STR is a **Zero** Phase Action (6E2 p.25 "Use STR or a power Casually: 0 Phase"), not a Half Phase one. It is once a Segment (6E1 p.134). 6E2 p.66 makes it a Half Phase only when Contortionist or movement bonuses are added, which nothing here adds.
- **Concentration** (6E1 p.374-375). `power_modifiers.concentration_of` reads HALF/ZERO, OBLIVIOUS and CONTINUOUSCONCENTRATION onto `AttackPower.concentration`. Using such a power writes `ConcentrationBegan`. Until the next Segment in which he has a Phase, or until STUN or BODY damage reaches him, `concentration.concentrating` folds ½ or 0 DCV into `cv_modifiers`, and `reactions.may_abort` refuses him ("nor may he Dodge"). No Concentration power is offered in a Phase whose first half moved him ("may not move more than 2m per Phase"). Rulings: damage always breaks it (the EGO Roll is GM discretion, not taken). Throughout on an Instant power is the one-Phase kind. Throughout on a Constant power is not built, so it is not offered.
- **Entangle loose ends** (6E1 p.217-221).
  - `EntangleApplied` records Takes No Damage From Attacks (`entangle.Transparency`: none / limited / all / str_only, read off TAKESNODAMAGE) and Both Take Damage. The +1 STR-only level removes `escape_attack` (and a paralysis's Mental Blast escape). `Entangle.apply` / `apply_mental_paralysis` now require them.
  - Escaping costs END: 1 per 10 STR used, half Casually (6E1 p.43, p.134), for Entangles and Grabs; EGO escapes 1 per 10 EGO (6E1 p.219). Not built: p.43's "once per Phase" for STR END.
  - `attack_entangle`: a friend targets the Entangle, not the man (6E1 p.218): -3 OCV against DCV 0, BODY against its PD/ED. A Mental Paralysis is hit by a Mental Blast against DMCV 3, BODY counted as Normal against its MD (p.219). **Correction to the brief:** the book gives a physical Entangle DCV 0 at -3 OCV, not DCV 3. Not offered against transparent or Both Take Damage Entangles (the overflow onto the man inside is not built) or STR-only ones (p.221). Ruling: offered for allies only.
  - A Mental Paralysis's MD adds to its victim's against every mental attack (p.219: it "also protects the Entangled character if anyone tries to attack him mentally").
- **Rage loose ends** (6E1 p.424). Ruling: an Enraged man "mindlessly attacks", so he is not offered `hold`. He is not offered Concentration powers (p.424). `snap_out_of_rage` is a Half Phase Action for an ally: the raging man rolls to recover (`RecoveryOccasion.SNAPPED_OUT`), and that counts as his attempt for the Turn's free Post-Segment 12 roll.
- **Prone** was already applied outside cover (`cv_modifiers._ground_cv_modifiers`, 6E2 p.129: ½ DCV against a standing attacker, -2 OCV). A seam test now proves it reaches the attack roll.

- **A target may Abort against Autofire, Flash and Entangle** (6E2 p.24). Since #22 a burst and a spray roll at the attack door, and a one-target Flash or Entangle rolls to hit (6E1 p.228, p.217) through the same CV fold a Dodge is read at, so `autofire`, `autofire_spray`, `flash` and `entangle` join `REACTABLE_KINDS`. **Every man an attack is announced against is asked** (`defenders_of`): a spray carries no single `target_id`, and a Sweep or Multiple Attack asked only its first man. `react_to_attack` now returns `(session, [(defender, reaction), ...])`. Seam test: `tests/loop/test_abort_against_autofire_flash_entangle.py`.
- **The facts a player's Held Action order needs** (Peter, 2026-10-27: an order names its action by power or maneuver plus a target rule). `threat.last_attacker_of(session, target_id)`: the last combatant whose attack roll was made against him, attributed as `harm_witnessed` attributes harm; and `threat.last_attacker_perceived(session, target_id, observer_id=, roller=)`, the same IF the observer perceives him now at the menu's own gate (`concealment.perceives` plus the Mind Scan locks), else None, never an earlier attacker he did see (perception governs combat). `loop.reactions.nameable_powers(combatant)`: the sheet's names an order may name, a superset of every `LegalAction.power_name` the menu carries; the standard maneuver names and the Interaction Skill table are lifted to `enumeration` constants (same values, same sites) so both read one list. Tests: `tests/loop/test_who_attacked_him.py`, `tests/loop/test_nameable_powers.py` (Ravel, Bokor, PowerLad at melee and range).
- **The Abort question says what is coming** (`OutOfTurn.attack`, a new `IncomingAttack`). A seat answering "he is attacking you, do you Abort?" from a player's standing order ("Dodge any Killing attack", "Block his punches") has to test two rules about the attack: is it hand-to-hand (6E2 p.59, the test that puts Block on the menu) and does it do Killing Damage (6E1 p.98). `IncomingAttack` carries `attacker_id`, `action_id`, `kind`, `power_name`, `summary`, `hand_to_hand` (the same `_is_hth` `reaction_menu` uses, so it can never disagree with the menu) and `killing` (the damage family of the offer's power or maneuver; an offer with neither, such as Trip, Disarm, Push or a thrown object, is not killing). `OutOfTurn.attack` is required, with no default, and is None exactly when `incoming` is (the Held Action question). No new event kind, no change to the menu or to any outcome. Seam test: `tests/loop/test_the_incoming_attack_is_described.py`.
- **The Abort offers name the attacker** ("Don't Abort: take Drago's attack...", "Abort to Block: roll OCV+0 against Drago's OCV"). They printed his combatant id, which in a kirby-api fight is a uuid, beside a Brief that names him. A player now reads these offers as his question. Same seam test file.
- **Offered means resolvable, and Autofire is built** (follow-up K1). No new event kinds; two new action kinds, `autofire` and `autofire_spray`. Seam tests: `tests/loop/test_offered_means_resolves.py`, `tests/loop/test_autofire_bursts.py`.
  - `force_wall` was offered with no power on the offer and with nowhere to put it, so every one raised (99 of 99 in a 20-fight sweep). It is now offered with its power, and only when the caster and an enemy are both on the map (`placing.has_a_place_near_an_enemy`, the resolver's own question). `darkness_zone` and `image_decoy` place the same way and now ask the same.
  - `rapid_fire` / `attack_construct` held at a wall that came down before the Held Action went off (6E2 p.22) raised. Ruling: the shots go into the rubble and nothing is damaged (`constructs.already_destroyed`). An id the fight never hit still raises.
  - A one-target Flash and Entangle now make their Attack Roll (6E1 p.228, p.217) through `adjust.attack_roll`, folded by `_fold_session_cvs` like every other roll. A miss records `hit: false` and rolls no effect dice. Flash counts Normal Damage BODY instead of summing pips (a 6d6 Flash averaged about 21 Segments; the book's count gives about 7). The Area versions from #21 already rolled and counted this way.
  - **Autofire** (6E1 p.329; 6E2 p.44-45). It was never read: 62 corpus attack views carry it. `power_modifiers.autofire_of` reads the shots (TWO/THREE/FIVE, and FIVE's DOUBLE adder at x2 per level). `autofire` fires the whole burst at one man: one Attack Roll, one hit plus one per 2 points of margin, at most the shots fired. Each hit goes through the attack door on its own, against defenses and for the Stunned check (6E2 p.44). END and Charges are paid for every shot fired (6E1 p.329; `charges.spent_charges` reads `shots_fired`). Knockback is rolled once, from the largest hit's BODY plus 1 per other hit (6E1 p.329, which agrees with 6E2 p.116), and that hit is applied last. `autofire_spray` puts one shot on each man along a line. Each man gets his own roll at the whole line's -1 OCV per 2m. The burst needs a shot per 2m of line and at least one per man. A miss does not stop the rest.
  - Autofire Areas (10 corpus views) are no longer refused. At one target point the roll decides how many landings happen. Each landing is an Area use with its own damage roll; a total miss scatters once (6E2 p.45). `area_attack.area_use` takes the burst's roll through `AttackInput.fixed_to_hit`.
  - Corrected: `actions/autofire.resolve_autofire_multi_target` charged each man only the line up to him. The page charges the whole line on every roll.
  - Autofire powers are no longer offered as Rapid Fire, Multiple Attack or Sweep (6E2 p.77: not without Rapid Autofire, which is not modelled). One shot of an Autofire power is still the plain `attack` (6E1 p.329: "even just one shot").
  - Rulings: the menu offers the full burst (the power's shots, cut to the Charges left) and the single shot, not each count in between. A spray line runs nearest-first from the shooter. A part of a 2m area at the end of the line takes a shot.
  - Still not offered: an Autofire Area sprayed over several points, hand-to-hand Autofire (6E2 p.59's one Block roll against several hits), Autofire at objects, and Autofire Constant or Damage Over Time (6E2 p.44). Shaped powers at constructs stay unoffered: the construct door makes no Attack Roll (6E2 p.172's DCV 3 is the documented divergence).
  - Open for the owner of `loop/reactions.py`: `autofire`, `autofire_spray`, `flash` and `entangle` all reach a DCV-folded roll now, but they are not in `REACTABLE_KINDS`, so a target is not asked whether he Aborts to a Dodge against them.

- **Standing areas: Constant and Damage Over Time Areas, auras and Damage Shields** (follow-up I to Batch C). New module `standing_areas.py`; new event kinds `StandingAreaEstablished` / `StandingAreaEnded` (schema regenerated). New action kind `raise_damage_shield` (Zero Phase).
  - A Constant Area stays where it landed (6E1 p.129): the owner pays END at his Phase start and everyone in it takes the dose; whoever walks into it takes it in that Segment, once per the owner's Phase; it ends on no END, lost Line Of Sight to its point, the owner Stunned/KO'd (6E1 p.347), the slot switched off, or a Recovery (6E2 p.131). Selective zones roll for a newcomer and Nonselective ones roll every Phase (6E1 p.326). A No Range zone moves with its owner and catches what it sweeps (6E1 p.326).
  - A Damage Over Time Area does nothing on the use, then doses everyone in it on its own clock, and entrants on entry (6E1 p.331-332).
  - Damage Shields (Constant personal Surface, 6E1 p.323-324) hurt whoever lands a HTH blow or a Grab on the wearer and whoever he hits or Grabs, and a man he holds on each of his Phases. Persistent shields and Persistent No Range auras are up from the first Segment (6E1 p.130) and never offered as attacks. A ranged Surface is rolled at the target's own DCV, maintained as a Constant attack, and burns anyone who touches him.
  - No Range is read at last (`NORANGE`, 6E1 p.131): such powers are HTH range, and a No Range Area is offered against any enemy inside it.
  - Killing Explosions lose a die per 6m (6E1 p.325, first method). Environment-only Side Effects happen and hurt nobody (6E1 p.396). Area Flash and Area Entangle hit everyone in the area from one roll (`actions/area_effects.py`; 6E1 p.220, p.228, p.326).
  - Multiple Attack, Rapid Fire and Sweep may use shaped powers (6E2 p.76); Spread may not (6E1 p.321). The shape filter now reads build powers too, so Area/Constant/DoT Drains, Transforms and Mind Control are no longer offered as one-target powers.
  - Corrected: a second use of a Constant power is a second maintained effect (6E1 p.129), not a replacement. Recovery: none while holding breath (6E2 p.132), and STUN lost to a running Damage Over Time is held back (6E1 p.333). Status hazard zones apply Prone; any other status is recorded as changing nothing.
  - Still not offered: Uncontrolled (6E1 p.354), Autofire Areas, Any Area, Mobile, Hole In The Middle, Constant plus DoT, DoT Surfaces, Mental Surfaces and mental Areas, recipient-only Side Effects, Constant/DoT Flash or Entangle, shaped Drain/Aid/Transform, shaped powers at constructs.
- **Reallocating a Multipower is a Zero Phase Action, once a Phase** (6E1 p.410). Until now it spent the whole Phase, so a man who switched slots never fired the slot he switched to. In kirby-api's benchmark fight a first-offer seat had Bullet reallocate every Phase from Turn 4 until the cap, and the fight never ended. The Phase now stays his (as after a No-Time Presence Attack or an Instant Change), and the reallocate offer leaves the menu for the rest of it (`framework.reallocated_this_phase`). No new event kind. Seam test: `tests/loop/test_reallocate_is_zero_phase.py`.
- **Weapons are tracked, and a Disarm takes one.** An Accessible Focus (OAF/IAF, 6E1 p.379) is a thing in a hand (`kirby_combat.weapons`): Bokor's Mojo Hand, Brainchild's OAF Multipower pistol. A Disarm is offered per weapon in the target's hand, rolls 6E2 p.62's STR contest (the attacker wins ties), and knocks the weapon 1d6+1m along the line of the blow. Takeaway wrenches it into the attacker's hand (6E2 p.69; 6E1 p.379, "more BODY" to win). Anyone within reach or a Half Move can pick it up (`pick_up_weapon`, 6E2 p.25 and p.62). A weapon out of its owner's hand is off his sheet for every reader, through the fold a Dispel uses, which now also reaches a slot inside a framework. Ruling: in somebody else's hand it is no use to him (6E1 p.382; HD records no Personal/Universal choice). **New event kind: `WeaponMoved`** (where it ended up, absolute); `schema/events.json` regenerated. A Disarm against a man holding nothing is no longer offered.
- **The martial maneuvers PR #5 stopped offering are built** (`actions/martial_resolution.py`, `martial_fmove.py`, `martial_offers.py`):
  - FMove (Flying Tackle, Passing Strike/Throw/Disarm, Charge, Flying Grab, Sacrifice Lunge): the Move By / Move Through charge (6E2 p.72) around the maneuver's own blow, +1 DC per full 10m of velocity (6E2 p.101). Rulings: the maneuver's CVs replace Move By's, there is no recoil, and a Grab or "You Fall" stops where it hit.
  - Must Follow Block (Counterstrike): offered only in his next Phase after a successful Block of that attacker (6E2 p.59-60, `reactive.blocking.block_follow_ups`).
  - Must Follow Grab: Crush is the later-Phase Squeeze and Grappling Throw is a Throw of the man he holds (6E2 p.64). Ruling: a Grappling Throw ends the hold.
  - Takeaway and Disarming Throw; Shove (6E2 p.81, 1m per 5 STR, damage only from a wall); Martial Flash against its INPUT Sense Group (6E1 p.228); a Grab that also does damage, as the same-Segment Squeeze (6E2 p.64); a free-text "+10 STR" that matches the costed DCs.
  - Martial Escape adds its STR to a full Grab break-out (6E2 p.94). Grappling Block takes hold and Defensive Throw throws when the Block succeeds.
  - Choke Hold's NND is stopped by Life Support (Self-Contained Breathing) (6E2 p.86).
  - A maneuver's Attack Roll now takes the Grab's CV (6E2 p.64-66), as the plain attack does.
  - Still refused, so not offered: Bind (no 6E core mechanic), Joint Break's Disable (optional Hit Location rules, 6E2 p.111-113), a Strike with damage type NONE (HD: no damage), and hand-written STR or dice figures HD never costed. Reversal's grab-after-escape is not read.
- **A held man may always struggle.** The perception gate dropped a Grab's escape whenever the grabber was Invisible, so a man held by Ravel was offered no way out. Escape kinds no longer pass that gate.
- `MartialManeuverView` gains `hd_defense` and `sense_input` (HD's DEFENSE and INPUT). Seam tests: `tests/loop/test_maneuvers_complete.py`.

## 0.22.1 — 2026-10-27

**Four findings from kirby-app's 0.22.0 demo recording (Drago vs GORGON), two of them defects.**
Each one is pinned by a seam test through `run_phase`.

- **BODY that gets through costs STUN** (6E2 p.105: "1 STUN for every 1 point of BODY damage
  that gets through his defenses"). Nothing applied this floor. A killing attack against a man
  with no resistant defense took his BODY and left his STUN alone: in the demo, GORGON (ED 35,
  rED 0) went to -1 BODY having lost 1 STUN. `resolution.damage.stun_for_body_taken` is now
  applied last at every door that subtracts defenses: the attack pipeline (`actions/base.py`),
  lingering doses, impact/fall damage, and collapse. The payload's `stun_dealt` and
  `VitalsChanged` always agreed with each other; both were below the rule.
  `test_dr_50_normal_does_not_apply_to_killing` had asserted the defect (STUN 0 with 4 BODY
  through) and is corrected.
- **A repeated Presence Attack rolls a die less each time** (6E2 p.140: "-1d6 on the second
  attack, -2d6 on the third attack, and so forth"), counted per target from the fight's log
  (`pre_attacks.landing.repeats_against`), so a group roll is judged on each target's own dice.
  A shout down to 0d6 is no longer offered (`without_spent_shouts`), since it can affect nobody.
  GORGON rolled 4d6 in all eight Phases; the repeats now fall 4, 3, 2, 1 and then the offer is
  gone. His eight "no effect" results were correct (every total was under Drago's PRE 20; 6E2
  p.139). The one-free-Presence-Attack-a-Phase ruling already stopped a chooser from spending a
  Phase on shouts alone; that is now pinned too.
- **Not defects, now pinned:** GORGON's "Abort to Dodge" right after his own action was a Dodge
  taken in his own Phase, after a No-Time Presence Attack (6E2 p.20, p.25, p.56). The engine
  records every Dodge through the Abort door, so the row is `AbortDeclared`, but the Phase it
  gives up is that Phase (T1 S12). So acting again at T2 S3 was right, and the +3 DCV ran until
  then. The Abort question out of turn is still asked only of a man with an attack coming at
  him. The demo's run of Holds is the recorder's first-offer chooser, not the engine.

## 0.22.0 — 2026-10-27

**The lift-and-shift the harness refactor skipped.** kirby-api's `70ad60f`
(2026-09-17) deleted the 12,970-line combat driver, saying each rule "has a home elsewhere", and
never checked them one by one. This release ports what was lost into the live path. Each item has a
seam test through `run_phase` / `resolve_chosen`, and each is checked against the book: where
the driver was wrong it is corrected (noted per item), not copied.

- Martial-arts maneuvers resolve (#5).
- Mental Illusions, Mental Paralysis, the physical Entangle loop, and Rapid Fire at constructs (#6).
- Presence Attacks land, take No Time, and impress; Enraged/Berserk (#7).
- Defender Abort, Block, Held Actions, Hide breaking, and Image decoys (#8).
- The Brief carries the combatant detail again (#9).
- Knockback, falls, footing, throws, climbing, and standing up (#10).
- Area Of Effect, Constant, Damage Over Time, hazard zones, Move By/Through, Side Effects, and Increased END (#12).
- Aid, Drain, Healing, Dispel, Lockout, the Force Wall event, and half dice (#13).
- Flash recovery and the Flash menu gate, DR/DN by class, the alternate identity, and the out-of-turn Brief (#14).
- kirby-world >=0.1.1, where long falls take the velocity at impact (#11).

New event kinds:
- `PresenceYielded`, `RageRolled`, `RageTargeted`;
- `LingeringAttackApplied`, `LingeringAttackEnded`;
- `BarrierRaised`, `PowerDispelled`, `PowerRestarted`;
- `IdentityChanged`.

New action kinds: 67 in all. The details per PR follow.


**Flash, Damage Reduction class, and the Hero ID flip (the lift-and-shift port, batch H).**
- **A Flash ends.** Nothing called `Flash.recover`, so a Flashed man was blind
  for the rest of the fight. 6E1 p.228 counts a Flash in Segments, starting in
  the Segment it lands, so `Encounter.advance_segment` now winds
  `Flash.tick_all` on both branches beside the Presence clock: a 3-Segment
  Flash in Segment 12 blinds through 12, 1 and 2 and is gone in 3. The
  module docstring's "1 segment recovers per phase" was wrong and is corrected.
- **A second Flash on a Flashed Sense Group has no further effect** (6E1
  p.228). `Flash.is_flashed` overwrote with the second count and
  `effects.flash_state` added it (citing a "6E2 §Flash" that says no such
  thing); both now keep the first until it wears off.
- **The Flash narrows the menu.** `run_phase` now passes
  `observer_flashed_groups` to `enumerate_actions`, so a Sight-Flashed man is
  offered only adjacent HtH against an opponent he cannot perceive (6E2 p.9,
  p.127).
- **Damage Reduction and Damage Negation stop only their class.** Both read
  `power.input_value` (the api column) where a loaded power carries `input`,
  so every one applied to every attack: Ravel's Physical and Energy DR halved
  Mental Blasts. DR's class is the INPUT, or Mental on HD's `LVLnnMENTAL`
  options; an unknown class raises. Damage Negation is one `DefenseItem` per
  PHYSICAL / ENERGY / MENTAL Adder with its own DCs (it took DCs from OPTIONID
  digits DN does not have), Resistant unless it carries NONRESISTANT (6E1
  p.185). NAKEDMODIFIER's "for X PD/ED" read the same wrong field. The Brief
  says "vs Physical attacks" rather than "vs any class".
- **Only In Alternate Identity respects the identity** (6E1 p.388). New
  `kirby_combat/identity.py`: `build_in_play(combatant)` is the build as it
  stands in his identity, and every reader of purchases goes through it ---
  attacks, defenses, the power-derived defenses and reach in `combat_stats`,
  movement, senses, maneuvers, frameworks, skills/CSLs, mentalist status,
  the menu's power offers (Flash, Darkness, Images, Force Wall, Aid, Drain,
  Healing, Dispel ...), Invisibility and Danger Sense in perception,
  coordination's skills, and Dispel's targets. A civilian Ravel has no String
  Storm, no Force Field, no DR and no Flight.
- **Changing identity is an action.** New kinds `change_identity` (Full
  Phase, 6E1 p.389; excluded from a Half Phase) and `change_identity_instant`
  (Zero Phase, Instant Change, 6E1 p.272/p.281/p.307: the Phase goes on, once
  per Phase). Offered both ways to a character with an OIHID purchase.
  **New event kind `IdentityChanged`** (`combatant_id`, `in_hero_id` absolute,
  `zero_phase`), folded by `apply_event` onto `state.in_hero_id`;
  `schema/events.json` regenerated.
- **A snapshot records both identities.** `CombatantSnapshot` gains
  `in_hero_id` and `other_identity` (`IdentityRecord`: the other identity's
  views, its characteristics and whether the change is instant); `to_dict`
  writes `other_identity` (null for one identity), so a combatant rebuilt from
  a snapshot changes costume the way the live one did. A recording made
  before this has one identity and is not offered the change.
- **Out-of-turn pages say so.** The Brief a chooser reads for an Abort names
  the incoming attack (attacker, power, kind, OCV/OMCV, whether he can
  perceive the attacker) and what the Abort costs (his next Phase, or his
  Held Action, 6E2 p.23-24); for a Held Action it says whose Phase is starting
  and what he is holding for (6E2 p.22).

**Adjustment powers and loose ends (the lift-and-shift port, batch E).**
- **Aid, Drain and Healing change the stat they are bought against.** Every
  Adjustment was recorded as `stat="STUN"` and divided by 5; Aid and Healing
  were offered with no target and applied to the user; Drain rolled no Attack
  Roll; Healing healed nobody. Now (6E1 p.137-143, p.169, p.197, p.234):
  - `AdjustmentApplied.delta` is **Character Points** and the row carries the
    target's `cost_per_point` (new field, read off his build's LVLCOST/LVLVAL);
    whole increments only (p.140); half effect on CON, DCV, DMCV, PD, ED, REC,
    END, BODY, STUN (p.143); Aid stops at its maximum effect (p.169); Drain on
    an Attack Roll, less Power Defense (p.197); a power's dice by its Active
    Points per die (p.139). Rows written before have `cost_per_point=0` and
    change nothing, as they never did.
  - `apply_event` projects the fold onto `state.drains` / `state.aids` / new
    `state.adjusted_dice`, so **every** reader of the stat sees it: CV, the
    Stunning check, SPD, STR damage, PD/ED, a power's dice. The CV-path overlay
    is removed (it would double count). The fade now runs in Character Points:
    -3 DCV comes back a point a Turn, not all at once.
  - STUN/BODY/END: the current value moves with the maximum (p.138); returning
    Drain points come back to both, a fading Aid cuts back to the new maximum.
  - Healing restores BODY/STUN/END up to full, half effect, never fades, and a
    repeat heals only the margin over earlier rolls (p.234); Simplified Healing
    (p.236); Healing BODY stops Bleeding.
  - Offers name their target: the actor and each ally within reach (No Range),
    enemies within Drain's 10m x Base Points. **Not offered:** inputs naming a
    special-effect group, a ratio split without Expanded Effect, Healing of a
    Drained characteristic, Healing on someone who has lost nothing.
- **Dispel** turns the named power off (6E1 p.195): Attack Roll, dice less
  Power Defense must exceed its Active Points (doubled per Difficult To Dispel,
  p.335; the driver dispelled on a tie). New events **`PowerDispelled`** /
  **`PowerRestarted`**; the off set is folded into the target's build, and
  `run_phase` restarts it as a Zero Phase Action at his next Phase he can act
  in (6E2 p.20). Group inputs, characteristics and snapshot-rebuilt targets are
  not offered.
- **Lockout** (6E1 p.388): `run_phase` passes `blocked_lockout_ids`; a framework
  slot bought with Lockout shuts its siblings out while a continuing effect it
  established holds, or in the Segment it fired. `AttackPower.lockout` (new).
- **Force Wall** is a new **`BarrierRaised`** event folded onto the scene; it
  was appended to `scene.walls` in place, so replays and rewinds had no wall.
- **Half dice** (6E2 p.100): a ½d6 is the face halved and rounded UP (was
  down) and does 1 BODY on 4-6 (was 5-6); a killing ½d6 adds 1-3 BODY. Every
  attack site rolled one die too few for a half-die attack (the half die was
  never rolled, so the last whole die was read as it); `_with_half_die` fixes
  all of them.

**Attack shapes resolve: Area Of Effect, Constant, Damage Over Time, Move
By / Move Through, hazard zones, Side Effects, Increased END.** Ported from
the deleted api driver (kirby-api 70ad60f) into the live path and corrected
against the book. New modules: `power_modifiers.py` (reads the modifiers off
the build into `AttackPower.area` / `.constant` / `.damage_over_time` /
`.side_effects` / `.increased_end`), `actions/area_attack.py`,
`lingering.py`, `zone_effects.py`, `actions/velocity_maneuvers.py`,
`attack_shapes.py` (the offer filter). New event kinds:
`LingeringAttackApplied`, `LingeringAttackEnded`.
- **Area Of Effect** (6E1 p.321-326, 6E2 p.42): one Attack Roll against the
  target point (DCV 3, or 0 within 2m / No Range), Range Modifier to the
  point, one damage roll for every character AND destructible construct in
  the Radius / Cone / Line, friend or foe, the attacker too when it is
  centred on him (unless Personal Immunity). A miss scatters 2m per point
  (max half the distance, d6 direction). Explosion drops the largest die per
  2m past the first 2m; Selective / Nonselective roll again per target;
  Accurate hits one. One use = one Charge, one END. The driver hit every
  living enemy on the map, each with his own roll, at Multiple Attack's -2
  OCV steps --- corrected.
- **Constant** (6E1 p.129-130, p.347): a hit is maintained; at the start of
  each of the attacker's Phases he pays the END and the target takes the
  damage again, no Attack Roll and no Action, until he cannot pay, is
  Stunned/KO'd, loses LOS, switches the slot off, or uses it again.
- **Damage Over Time** (6E1 p.330-333): the hit does no damage; doses fall
  due on their own clock at the top of each Segment, through the full damage
  pipeline (AVAD/NND included); Lock Out takes the offer away while it runs;
  "defenses only apply once" spends one defense pool across the doses
  (p.332's acid example). The driver's CON "shake-off" (it cited 6E1 p.102)
  is in no book and is not ported.
- **Hazard zones** (`resolve_construct_effect` finally has a caller): fire
  every Segment as an automatic-hit attack; drowning per 6E2 p.132-133 (1
  END a Phase at SPD 2+, then 1d6 STUN as END, then -1 BODY a Phase), not
  the old flat 1 BODY a Segment.
- **Move By / Move Through** (6E2 p.72-74): the charge runs (refused if it
  cannot end in contact), the Attack Roll is made at the maneuver's OCV, the
  DCV holds until his next Phase, the target takes the damage and Knockback,
  and the attacker takes 1/3 (By) or 1/2, full with no Knockback (Through), of
  the ROLLED damage against his own defenses. Move By finishes its Full Move
  past the target. Halved STR keeps its half die (`strike_dice`). The offer
  gate for Move By is now a Full Move (6E2 p.72).
- **Side Effects** (6E1 p.395-397): on a failed Activation Roll, or every use
  if "always occurs"; sized by the table, applied as Normal Damage at 5 AP a
  die with no defenses (labelled ruling, from p.397's Arkelos example).
- **Increased Endurance Cost** (6E1 p.376): END x the bought multiple; the
  driver charged x2 whatever the build said.
- **Not offered any more** (cannot be built faithfully): Surface / Any Area /
  Mobile / Autofire / Hole In The Middle Areas; Constant or Damage Over Time
  Areas (standing zones); Explosion on a non-Normal attack; Constant + DoT
  together; environment-only, recipient-only, after-use, specific-act and
  predefined-damage Side Effects; circumstantial Increased END; a shaped power
  on any kind other than attack / strike / push / move_strike /
  reposition_strike (so not as Rapid Fire, Sweep, Spread, Multiple Attack,
  Haymaker or `attack_construct`, and not as Flash, Entangle or the mental
  kinds).

**Bodies move: Knockback, falls, footing, Throws, climbing and getting up.**
Ported from the deleted api driver into the live path (batch B of the
2026-09-17 lift-and-shift sweep) and checked against the book. A new action
kind, `stand_up`; no new event kinds (moves are `MovementResolved` with
`move_type` "knockback"/"fall"/"thrown", impact damage is `VitalsChanged` with
`reason` "knockback"/"falling", who went down is the attack row's
`statuses.FELL`). New fields: `AttackPower.no_knockback` (HD's NOKB, 6E1
p.147), `AttackInput.damage_taken_factor`, `AttackResult.knockback_owed`,
`KnockbackResult.knocked_down`, `WallCollision.pd`/`.body`;
`enumerate_actions(prone=)`.
- **Knockback is applied** (`kirby_combat.impact`, called from
  `recording.resolve_attack_in_session`): the 2d6 roll is made at the door
  (+1d6 Killing, +1d6 martial maneuver, -1d6 target in the air, -1d6 zero
  gravity, 6E2 p.117); he travels away from the attacker; into a wall he
  stops and takes 1d6 per 2m capped at its PD + BODY; off an edge he falls
  and takes falling damage instead of the ground impact (RULING); in the air
  he takes nothing (p.118); otherwise 1d6 per 4m, which Breakfall at -1 per
  4m avoids (p.119); a 0 result Knocks him Down (p.116). He ends Prone. KO
  blow's Knockback does 2x STUN (p.108).
- **Knockback used BODY dealt and an empty pool** (`actions/base.py`): it
  now uses BODY rolled (6E2 p.116) and nothing when no pool was rolled,
  instead of BODY x 2m on every hit.
- **`compute_impact_damage_dice` had 6E2 p.118 inverted** (a small
  Knockback passed through a wall, a large one stopped). Corrected; the
  book's Mechanon example is the test.
- **Falls** (`impact.fall`): 1d6 per full 2m (6E2 p.142) with Breakfall
  halving, or nothing when made by half (6E1 p.68).
- **Footing**: a man hit on a precarious surface rolls DEX or Acrobatics or
  falls (GM RULING, ported); a narrow surface is -2 DCV (6E2 p.39).
- **Prone bites and clears**: 1/2 DCV against anybody standing, -2 OCV
  attacking from the ground (6E2 p.51, p.129); `stand_up` (Half Phase, takes
  the Phase here -- no Half Phase economy) and a Breakfall Zero Phase
  stand-up at the top of his Phase (6E1 p.68).
- **Throwing a grabbed man** (`resolvers._throw_grabbed`): an Attack Roll
  (6E2 p.64; the driver auto-hit), STR damage capped by a wall's PD + BODY,
  Breakfall halves it (p.85), a Standing Throw's distance from p.83's table,
  he lands prone and can fall, and the Grab ends hit or miss. Before, it
  rolled 1d6 at him as an object and left him held.
- **Climbing moves** (`resolvers._climb`): a Climbing roll on a difficult
  face, none on an ordinary one (the driver made the skilled roll for a
  ladder), the move up the face, and a fall on a miss by 5+ (RULING, 6E1
  p.70). `climb_fast` is offered only with the Skill.
- **Not built**: a shattered wall letting him "continue through the hole";
  the wall's own damage; Autofire/Multiple Attack KB aggregation (each hit
  rolls its own); Double Knockback, Does Knockback; Rolled With The Punch,
  underwater, Clinging; the Thrower acting first; climbing CV penalties.

**Presence Attacks land, take No Time, and are felt.** Ported from the
deleted api driver and checked against the book.
- A chosen `presence_attack` / `presence_attack_group` is now APPLIED
  (`PresenceEffects.apply`, via the new `pre_attacks/landing.py`), so
  `can_act`, the half/zero DCV and the rules below read it. Dice are PRE/5
  with "In combat -1d6" (6E2 p.137-138); a Stunned target is immune
  (6E2 p.106). The driver's invented bonus dice (outnumbering, a PRE ratio,
  a recent takedown) are not on 6E2 p.138's table and were not ported.
- **No Time** (6E2 p.25, p.20): a Presence Attack does not spend the Phase;
  the next `run_phase` hands the same man the same Phase. RULING: one per
  Phase (the book says "as often as he wishes").
- **Impressed** (6E2 p.139): at his next Phase the target steps behind the
  attacker if the attacker still has a Phase this Segment (`PresenceYielded`).
  **Very impressed**: that Phase is a Half Phase Action only
  (`pre_attacks/in_the_phase.HALF_PHASE_EXCLUDED`, each kind cited).
- **PRE Defense corrected.** `resolve_presence_attack(target_pre_defense=)`
  used to subtract dice 1-for-1, which is not a 6E rule; it now raises the PRE
  the roll is judged against (6E2 p.137; 6E1 p.178 "Presence Defense" is
  "+20 PRE, Only To Protect Against Presence Attacks"). `PresenceAttackResult`
  gains `resisting_pre`; `effective_dice` is now every die rolled.

**Enraged / Berserk roll and bite** (`kirby_combat/rage.py`, 6E1 p.424-425).
The go roll is made every Phase the character's own circumstance holds; the
engine reads three circumstance classes it can observe (in combat, he took
BODY, he was attacked) and leaves every other text to the GM. Raging, he
fights only his target (Berserk: the nearest combatant, friend or foe),
helps nobody, and has no Dodge, Block, Hide, Disengage, cover move, defensive
reposition or Abort. He rolls to recover when his target is down, when he is
out of END, and free in Post-Segment 12 if he has not tried that Turn. The
driver rolled to go on any wound whatever the sheet said, rolled to recover
every Phase, and defaulted missing rolls to 11-; all three are corrected.

**Schema change: needs a MINOR bump.** New event kinds `PresenceYielded`,
`RageRolled`, `RageTargeted` (`schema/events.json` regenerated).

**The Brief carries what the deleted page carried.** The consumer-side page
builder removed in the 2026-09-17 harness refactor showed far more than the
engine's Brief kept (STUN, BODY, END, OCV, DCV, role, DOWN). Ported into
`kirby_combat/brief_detail.py`, each section reading the fold or view the
rules already use:
- **Per perceived combatant** (actor, allies, enemies): SPD, PD/rPD, ED/rED,
  PRE (6E2 p.138), EGO, OMCV/DMCV, MD, INT; the health rung from
  `health.classify_health` and the visible statuses from `statuses_for`
  (Stunned 6E2 p.106, recovering p.107, prone, grabbed, aborted, knocked out,
  dead); physical Entangle (6E1 p.217) and, to its victim only, Mental
  Paralysis (6E1 p.219); Drains and Aids; an active Presence Attack; held
  actions; attacks taken this Turn; Damage Reduction / Negation; Trigger and
  Limited Power texts; the identity a character with Only In Alternate
  Identity purchases is in (6E1 p.388); powers by their authored names
  (capped at 8); and, for allies and enemies, their complications.
- **Perception governs the page as it governs the menu.** An enemy (or ally)
  the actor cannot perceive is named and nothing more. The page never rolls:
  where `perceive` would need a Fringe or Stealth roll, it reads the menu the
  gate already built. "What you perceive" carries the mental-lock line (a
  mind in reach through a Mind Scan lock, 6E1 p.265) and the unperceived line.
  Mind Control and Mental Illusion on another man show only to their caster
  (Mental Powers are invisible by default, 6E1 p.151).
- **The victim's Mind Control order** (spare / withdraw / turn, 6E1 p.256),
  and what it does to his menu. RULING: the page is the player's, so the
  order is told as a GM tells the player (the character himself does not know,
  6E1 p.255), and he still chooses how (6E1 p.258). CORRECTION: the old page
  told its reader to act as the controller ("YOUR PUPPET ... you may target
  either side"); the engine since 0.21 gives the victim his own chooser, so
  that instruction is not ported.
- **Warnings**: Flashed, per Sense Group with Segments left (6E1 p.228, 6E2
  p.9); deep water a man who can neither swim nor do without air is in or
  within 10 m of (the same immunity test `resolve_construct_effect` makes).
- **Reaching them**: per perceived enemy, within reach (6E2 p.56, via
  `within_reach`), a half-move of Running away, or neither --- then elevation
  and which movement modes `movement_reach` says get there this Phase.
- **The matchup**: the old kite/outmuscle asymmetries as numbers only (SPD,
  average STUN through the worst defense, share of the STUN track). The old
  page's advice ("do NOT trade blows", "close and trade") is not ported: it is
  judgement, and belongs to a chooser.
- **Frameworks**: reserve or pool, each slot's Active Points, fixed or
  variable, switched on in this fight, and an attack slot's own dice --- the
  old page's AP/5 "dice" was only ever right for a Blast --- with an NND's
  defense (6E1 p.328). Switching and rebuilding are named only when offered.
- **Reading order**: the page lists `PhaseSituation.ordered_menu` (scenery
  last), the order both shipped choosers already read. `Brief.menu` follows.
No new event kinds, no schema change.

**Acting out of turn, Blocks that stop blows, Hides that end, Images that draw
fire.** Ported from the deleted api driver (`_maybe_abort`, `_resolve_block`,
`_resolve_release_held`, `_break_hide_on_attack`, `_decoy_targets_for`,
`_resolve_attack_decoy`) onto the live path, and checked against the book:
- **The out-of-turn Abort** (`loop/reactions.py`): when a man is attacked,
  `run_phase` asks HIS chooser, before anything is rolled, whether he Aborts to
  Dodge or (against hand-to-hand) Block (6E2 p.24). The first offer is always
  `no_abort`, so a first-legal chooser behaves as before. Refused while down,
  inside an Abort's lockout, Stunned (6E2 p.106), after using his Phase this
  Segment, or Surprised (6E2 p.24). A man Holding an Action Aborts with it and
  loses no further Phase (6E2 p.24, `mark_aborting_with_held`). The driver
  gated the Abort on an INT Roll and decided it with an expected-damage
  picker; neither is a rule, so both are gone and the chooser decides.
- **A Block stops the blow** (`actions/reactive/blocking.py`): a standing
  Block is rolled at the attack door against the attacker's OCV as modified by
  the attack (6E2 p.59); a success records the attack as `blocked` with no
  damage and no Knockback, the attacker still paying END. Hand-to-hand only,
  not against an attacker he cannot perceive, further Blocks at a cumulative
  -2, none after a miss (6E2 p.60). The own-Phase `block` resolver now
  declares the Block instead of rolling a contest against nothing.
- **Martial Dodge and Martial Block feed the plain maneuvers**
  (`actions/reactive/martial.py`): +5 DCV for a Martial Dodge, OCV +2 on the
  Block roll and +2 DCV for a Martial Block (6E2 p.93). Block's DCV is general
  (6E2 p.59) and folded at the CV door. Corrects the driver, which put a Martial
  Block's DCV into the Block roll.
- **Held Actions are used** (`loop/reactions.py`): before every Phase, anyone
  Holding is asked (out of turn) whether he acts first; his choices are his
  ordinary menu. A contested DEX Roll decides who goes first (6E2 p.22;
  RULING: a tie goes to the man whose Phase it is); a defensive Action goes
  first without a roll. A Held Action lapses when the holder's next Phase
  Segment begins (6E2 p.22), through the existing
  `HeldAction.expire_for_combatant_next_phase`.
- **Hide ends when the hider attacks** (`concealment.break_hide`,
  `REVEALING_KINDS`): RULING, recorded in code, grounded in 6E2 p.52 and 6E1
  p.127. The attack out of hiding is still Surprised; the break is recorded
  after it.
- **Images draw fire** (`actions/decoys.py`): an enemy's standing Image that a
  man still believes is offered to him as a target; shooting it spends the
  attack on nothing and he rolls to see through it (6E1 p.238-239). A caster
  with an Image standing is not offered another.
- `PhaseSituation.out_of_turn` (`OutOfTurn`, `OutOfTurnReason`) tells a
  chooser why it is being asked outside the actor's Phase. A chooser that
  calls a model is now asked once more per attack on a man who may Abort.
- With the Presence/Rage line: the Rage and very-impressed narrowings bind a
  holder's menu too (all menu narrowing is in `run._situation_for`); a raging
  man is not offered an Abort (6E1 p.424-425, 6E2 p.23); a No-Time Presence
  Attack made from a Hold does not use the Held Action (6E2 p.25), and the
  one-free-PA window (`in_the_phase._in_this_phase`) is bounded by the
  Segment so it does not leak into his next Phase.
- No new event kinds. New `ActionResolved` payload kinds: `hide_broken`; an
  attack payload may carry `blocked: true`.

**Martial maneuvers resolve.** Every `maneuver` the menu offered raised
`UnresolvableAction` (a 500 on kirby-api's `/run`): the resolver looked the
offer's `power_xmlid="MANEUVER"` up in the static table and refused it, and
for a table id it only declared modifiers nothing read. A maneuver is now the
attack itself, resolved in the Phase it is chosen, ported from the deleted api
driver's `_resolve_maneuver` and corrected against the book:
- **OCV** on its own Attack Roll; **DCV until the actor's next Phase**
  (6E2 p.68), folded at the one CV door (`recording._fold_session_cvs`, via
  `martial_arts.maneuver_dcv_delta`). The driver recorded the DCV and applied
  it to nothing.
- **Damage** (`actions/maneuver_effects.py`): STR + DCs as Normal Damage
  (6E2 p.93, p.101); Killing Strike at 3 DC per die with STR added as to an
  HKA (6E2 p.93, p.99; 6E1 p.244); NND at 1/2d6 per DC, no STR, STUN only,
  defense Resistant PD / rigid armour (6E2 p.94, p.99, p.101). Extra DCs add
  to every maneuver (+5 STR to a STR-bonus one, 6E2 p.94). END is the STR's
  only (6E2 p.93).
- **Effects**: Target Falls / You Fall set Prone (6E2 p.94; new `statuses.FELL`
  payload key); Grab maneuvers write the Grab row `Grab.is_grabbed` folds, and
  a Martial Grab's holding STR reaches the escape contest
  (`Grab.holding_str_bonus`, 6E2 p.94); Martial Disarm rolls like Disarm and
  records its contest STR.
- **Not offered any more** — HD elements with no faithful rule here: FMove,
  Must Follow Block/Grab, Crush, Bind, Shove, Grab Weapon, Disable, Flash,
  Grab + Normal/Killing damage, free-text STR, custom maneuvers whose damage
  type is NONE.
- `MartialManeuverView.damage_type` is now the decoded family
  (`ManeuverDamage`, a str Enum: Killing Strike reads `killing`, Nerve Strike
  `nnd`), and `dc_bonus` includes Extra DCs. `LegalAction._maneuver_view` is new.
**Schema change: needs a MINOR bump (0.22.0).** `EntangleApplied` gains
`mental_paralysis` and `entangle_md`, `EntangleEscape` gains
`mental_paralysis` (`schema/events.json` regenerated). A new action kind,
`escape_ego`. No new event kinds.

**Rapid Fire at a construct resolves.** Offered as `rapid_fire:<wall>:…:3`
and refused by its resolver (it looked the wall up among the combatants):
34–46 skipped Phases per 20 random fights, now 0. Each shot rolls its own BODY
and the object's defense comes off each (6E2 p.172,
`apply_autofire_to_construct`), the damage folds into
`constructs.damage_by_object`, and a destroyed wall collapses. The to-hit stays
the single shot's (auto-hit, the documented 6E2 p.172 DCV 3 divergence), so
the two doors cannot disagree.

**Mental Illusions change what the victim does** (6E1 p.250–253). The illusion
is named before the roll, one offer per (target × illusion × power) in
`LegalAction.order`, from `mental.mental_illusion.ILLUSIONS`:
`friends_as_foes` EGO+10, `vanish` EGO+10, `phantom_attack` EGO+20,
`peaceful_meadow` EGO+20, `phantom_wound` EGO+30, `lost_in_illusion` EGO+30.
`resolve_mental_illusion` takes `illusion=` and `power_active_points=`
(required). An established illusion is a continuing effect with Breakout Rolls
(`mental/continuing.py`), believed from the first failed one: the illusionist
vanishes from his enemies, his friends join them, he has no enemies, or he
stands still at ½ DCV (`PhaseSpent(reason="entranced")`). A harmful illusion
strikes once at that first failed roll: min(Effect Roll, power AP)/5 d6 Normal
Damage against ED, STUN only or STUN and BODY, recorded as `VitalsChanged` and
an `ActionResolved` of kind `mental_illusion_damage`.

**Mental Entangle is a real Entangle: Mental Paralysis** (6E1 p.219). BODY is
the Normal Damage count of the dice (6E1 p.217), the target's Mental Defense
takes nothing off it, and it has one point of Resistant Mental Defense per die.
It binds through `Entangle.apply_mental_paralysis`: DCV 0, and the menu is the
escape ladder — `escape_ego` (1d6 per 5 EGO) or the victim's own Mental Blast,
both against its MD. No STR, physical attack or Teleport escape. It never
stacks with a physical Entangle. `mental.mental_entangle` is rewritten
(`roll_mental_paralysis`); the old `apply_mental_entangle` /
`attempt_mental_escape` encoded rules the book does not have and are gone.

**The physical Entangle binds in the loop, too.** `run_phase` never passed
`physical_entangle`, so an Entangled man had his whole menu, and nothing put
him at DCV 0. Both are wired now (`_entangle_holds`, a new CV source). The
escape resolvers counted pips as BODY and soaked nothing. They now count
Normal Damage BODY less the Entangle's PD/ED (6E1 p.218), and a Casual STR
attempt uses half STR. An Entangle's own BODY is the counted BODY, with 1 PD/1
ED per die (6E1 p.217). Before, it was the pip sum, used for BODY, PD and ED.

Still open: `EntangleApplied` does not record Takes No Damage From Attacks, so
a physical Entangle bought with it is still offered `escape_attack`. Casual
escapes still cost the Phase (one action per Phase in the loop). The END for a
breakout is not charged. `mental.attempt_disbelief` (a per-Phase roll at
−margin) is not the RAW route and has no caller.

## 0.21.0 — 2026-10-26

Prod fight 33bf8bee (five villains, a generated map) showed a mentalist whose
powers never missed, whose Mind Control changed nothing, who was offered mental
attacks on four enemies he could not see, and who never flew; fighters who
chose to close and strike and stood still; and Stunned fighters who acted.
Spec: `kirby/docs/superpowers/specs/2026-10-26-mental-combat-design.md`.

**Mental combat.**
- Every Mental Power makes an **MCV Attack Roll** first (6E1 p.150), through
  one door (`mental/attack_roll.py`) on the folded OMCV/DMCV — a Stunned mind
  is at half DMCV (6E2 p.106). A miss rolls no Effect Roll.
- **Mental Defense comes off** the Mind Control, Telepathy and Mental Illusion
  Effect Rolls (6E1 p.151, p.255). Their results carry `effect_rolled` (the
  dice) and `effect_total` (after MD).
- **Mind Control carries an order.** `LegalAction.order` (new) is one of
  `mental.mind_control.ORDERS`: `spare` EGO+10, `withdraw` EGO+20, `turn`
  EGO+30, each from 6E1 p.256's own combat example; `resolve_mind_control`
  takes `order=` (required) and reports `required_total` / `established` /
  `breakout_modifier`. An established order is a **continuing effect**
  (`mental/continuing.py`): the target makes one **Breakout Roll** at the top
  of his first Phase (6E1 p.151), then rolls again only on the Time Chart
  (+1 after a Turn, +2 after a Minute, p.152); failing it, he obeys — `spare`
  removes the controller's side from his enemies, `turn` makes his own side
  his enemies, `withdraw` cuts his menu to non-hostile kinds.
- **Mind Scan is a lock, not a sense you own.** New kind `mind_scan`: an MCV
  Attack Roll at the Mind Scan Modifiers Table penalty, then an Effect Roll for
  a lock-on (6E1 p.263-266). `perceive(..., mind_scan_locked=)` gives mental
  line of sight only through a lock (two-way, p.265); the lock breaks on a
  Breakout, when the scanner goes down or switches the Multipower slot off.
  Mind Control through a lock alone needs the TELEPATHIC Advantage (p.266).
- New event **`BreakoutRolled`**; `cv_modifiers.effective_omcv_for`.

**Rolls.** 3 always hits and 18 always misses on both to-hits (6E2 p.37); a
Breakout Roll of 3 always succeeds (6E1 p.57).

**Movement.** `run_phase` now passes the actor's `movement_view()` to
enumeration. It never had, so the movement block — every mode a character owns
through `movement_reach`, and the only `move_strike` that checks the path —
never ran in a real fight: a flier was offered a run. `move_strike` is offered
only from that block (the straight-line offers from the attack, maneuver and
bare-STR blocks are gone), one per melee attack plus the bare-handed Strike,
carrying its attack and the landing it checked (`reposition_dest`). A step
toward an enemy is offered when it gets closer, not only when it arrives. A
move whose strike could not follow reports its `MovementResolved`.

**Stunned.** A Stunned or recovering man spends his next Phase recovering
(6E2 p.106-107), recorded as `PhaseSpent(reason="stunned")` — which the Stun
folds read, so a man Stunned before his DEX in the same Segment loses that
Phase and only that one.

**Not done, and named:** Mental Illusion and Mental Entangle still change
nothing after the roll; Psychological Complication modifiers to Mind Control;
the `maneuver` resolver only declares (real offers carry `power_xmlid
"MANEUVER"` and raise `UnresolvableAction`), and `modifiers_for_pending_attack`
has no reader; `rapid_fire` is offered at constructs its resolver refuses.

## 0.20.2 — 2026-10-26

**Trip and Disarm roll with the character's bare-handed Strike.** Both are
STR maneuvers (6E2 p.58's maneuver table; p.62: "To use Disarm, the character
makes an Attack Roll"), and enumeration offers them to anyone with STR 5+.
The resolver instead borrowed the first entry of `actor.attacks`, so:

- a fighter with no attack powers raised `UnresolvableAction` for a Disarm or
  Trip the menu had just offered him (prod fight 075ba1ca, 2026-10-26: the
  whole `/run` answered 500), and
- a fighter whose only power was a blast rolled the maneuver through the blast.

`_maneuver_attack` now takes the power from its caller (`power=` is
required): Trip and Disarm pass `str_strike_view()`, Spread passes the power
on its offer as before. `StatBlockCombatant` gains `str_strike_view()` (STR
through kirby-cost's `strike_dice`, base 1 m reach), so stat blocks can roll
them too — and enumeration, which already asked every combatant for that view
and swallowed the AttributeError, now offers a stat block its bare-handed
Strike. `BASE_REACH_M` moves to `kirby_combat.models` so both combatant types
share the one value.

Disarm's STR Versus STR contest (p.62) is still not rolled: the engine tracks
no weapons to knock loose, as before.

## 0.20.1 — 2026-10-20

**The event registry is on the front door.** `BaseEvent` (was the private
`_BaseEvent`) and `EVENT_KINDS` are exported from `kirby_combat`. kirby-api
imported the private class to learn the base fields and walked
`session.events` itself to find the kinds, so it had to pin this engine
EXACTLY and was still on 0.18.5 while 0.19.0 and 0.20.0 shipped their fixes.
With the names public a consumer can take a compatible range.

The private name is removed, not aliased. Nothing in a consumer's history
breaks: the only one that reached it pins `==0.18.5`.

No behaviour change; the shipped schema differs only in its version stamp.

## 0.20.0 — 2026-10-03

**Places move to their own package: kirby-world.** `Scene`, `World` and the
geometry inside them (surfaces, walls, furnishings, hazards, constructs,
cover, falling, visibility, movement reachability, arena generation) now
live in `kirby-world` 0.1.0, a new dependency that imports nothing of the
fight. A house with five people in it no longer needs a combat engine.

*No behaviour change.* The suite is the same 2,796 tests with the same
result, unmodified except two architecture guards that had to name the new
file locations, and nine scripted example fights produce byte-identical
output before and after.

*Nothing for a consumer to change.* `kirby_combat.scene` and
`kirby_combat.world` are PERMANENT re-exports, not deprecated: the pure
modules are the very same module objects as kirby-world's, and the two
functions that took a fight's `session` keep their signatures here.

*What stayed in the fight, and why.*

- `kirby_combat.reach.movement_reach(..., session=)` — whether the mover
  may move at all (Stunned or recovering, 6E2 p.106) is a rule about him;
  it is asked here and passed to the world as `mover_can_move`.
- `kirby_combat.constructs.constructs_in(scene, session)` — what a fight has
  done to a building is folded from its event log (one fold,
  `damage_by_object`; `damage_taken` reads it) and passed as `damage=`.
- `kirby_combat.placement` (committing a move) and
  `kirby_combat.construct_effects` (a hazard's effect on the person in it)
  moved up out of `scene/`; the old paths still import.

New code should import places from `kirby_world` directly.

## 0.19.0 — 2026-10-01

**Eight defects from an outside review, all under a green suite.** Codex
reviewed this engine on 2026-09-23 and every finding held up. Most were
something computed correctly and delivered to nobody, or a duplicate input
that the resolution path read from the wrong place.

*Behaviour changes a consumer will see.*

- **An Abort spends one Phase, and it ends** (6E2 p.24, "How to Abort an
  Action"). `aborted_this_phase` was a one-way latch: one Dodge kept its
  +3 DCV for the rest of the fight, locked the man out of aborting again,
  and never took the Phase he gave up. Now the lockout lasts until the
  aborted Phase has passed, the bonus lasts until his next Phase after
  that, and the aborted Phase is forfeit (`PhaseSpent(reason="aborted")`).
  Fights in which anyone dodges or blocks will play out differently.
  `AbortDeclared` carries four new fields (`aborted_turn`,
  `aborted_segment`, `bonus_until_turn`, `bonus_until_segment`);
  `Timeline.aborts` replaces the stored set, and `aborted_this_phase` is
  now a read-only property derived from it.
- **A saved `CombatSession` restores.** `from_dict(to_dict(session))`
  raised `unknown type 'CombatTemplate'`. Restoring also brought back
  every timestamp as a str, and nested frozensets and bare tuples as
  lists; all three now come back as what went out.
  `CombatSession.dice_roller` is **no longer written to the wire**. It
  went out with no seed and no state, so it could only have come back as
  a lie. Whoever resumes a fight supplies the dice.
- **`run_phase` and `run_encounter` refuse an Encounter holding more than
  one session.** They used to keep the first fight and silently delete
  the rest.

*Resolution fixes.*

- A Sweep strikes only the enemies it offered (`LegalAction.target_ids`),
  and every shot of a Multiple Attack pays its range modifier.
- Every action resolves under the caller's `CombatTemplate` and rolls the
  caller's dice. Four resolvers read the session's copy instead.
- Hide is offered next to a `Surface`. A tuple-vs-flat-list misread
  raised inside a bare `except` and became "no cover". Adjacency is now
  measured to the nearest part of a wall or surface, not its midpoint or
  centroid.

## 0.18.5 — 2026-09-18

**Positions and statuses are in the log, and the one-writer gate covers
them.** Task A7 made a fighter's vitals fold only through `apply_event`.
Two fields were left outside it, and Krackle's checkpoint gate — a replay
of recorded fights against this engine's own `state?at` — measured both.

*Where a man stands.* `apply_event` treated `MovementResolved` as
log-only while `scene/placement.py::commit_move` wrote the landing onto
`scene.combatant_positions` in place beside it. A session rebuilt from
its rows — and therefore `state_view` and `rewind_to_sequence` — put
every fighter at his starting placement for ever: all fourteen
checkpoints of a recorded fight had Wyatt at (3.1, 3.7) although he moved
at sequence 7. `apply_event` folds the row now and `commit_move` writes
nothing, so the live path and the replayed path move a man in the same
one place. `rewind_to_sequence` seeded its fresh session from the
FINISHED Scene, which is the same defect from the other end — a rewind to
sequence 1 showed the fight's last placement — so `CombatSession` carries
`initial_scene`, the board as the fight found it, exactly as it already
carried `initial_combatants`.

*What condition he is in.* Nothing in this engine ever emitted a
`StatusEffectsChanged`: its only door,
`status_emission.apply_event_with_deltas`, had no caller anywhere, and
`StatusChanged` had no producer at all. Knocked out, stunned, prone,
held, entangled, flashed — none of it reached the log, so a viewer
reading the rows could not know a man had gone down.
`status_emission.record_status_changes` is the one emitter now: it diffs
the RULE (`statuses.statuses_for`) against the RECORD
(`CombatSession.statuses`, folded by `apply_event` out of these rows) and
writes down what moved. `run_phase` — this engine's one step door —
calls it on every exit, so the rows are among the events a Phase hands
back. `session/state_view.py` reads the folded record rather than
deriving a second answer.

*The gate.* `tests/session/test_apply_is_the_only_writer.py` (renamed
from `..._of_vitals.py`) walks the engine by AST for two more properties:
nothing outside the fold decides where a combatant is standing, and
nothing outside it writes `CombatSession.statuses`. The placement gate is
keyed PER ROUTE rather than per file — mutating a position map, calling
`place_combatant`, building a board with `replace(..., combatant_positions=)`,
and installing one with `replace(..., scene=)` are four separate
allow-lists — so a module that may bring a wall down is not thereby
allowed to move a fighter. Both gates carry their own negative controls
and assert their allow-lists whole.

**Wire changes.**

* `MovementResolved.from_pos` and `.to_pos` now carry `facing` alongside
  `x`/`y`/`z` — the four numbers `scene.Position` holds. Facing was
  dropped on the wire, so a replay could put a man on the right spot
  pointing the wrong way, which a board draws.
* `StatusChanged` is **deleted**. It was a scalar `from_status`/
  `to_status` pair standing beside `StatusEffectsChanged` with no
  producer anywhere in the engine and exactly one consumer — Prone's
  clear edge in `statuses._is_prone`, which now reads `PRONE` in a
  `StatusEffectsChanged.removed`. A combatant getting to his feet is
  still a consumer's explicit act. The event union is 29 kinds, and
  `kirby_combat/schema/events.json` is regenerated.
* `CombatSession` gains `initial_scene` and `statuses`. A session built
  with events already on it, a Scene, and no `initial_scene` raises —
  the same refusal `initial_combatants` already makes, for the same
  reason.
* `Scene` gains `snapshot()` (the board as it stands, positions copied)
  and `with_position()` (the what-if board). `move_strike` and `Images`
  both built an altered board themselves — one through
  `dataclasses.replace`, one through a hand-rolled `__slots__` proxy —
  and now ask the Scene, which is where the position map lives.
* `status_emission.apply_event_with_deltas` is **deleted** and replaced
  by `record_status_changes`. The pure diff `status_deltas` is unchanged.

## 0.18.4 — 2026-09-18

**The scene is in the published schema.** A viewer that renders a fight's
map has always hand-written its geometry types against `to_dict(scene)`'s
shape, and it drifted in five places: `Wall.segment` read as `start`/`end`
rather than two `Position` objects, a polygon read as flat coordinates
rather than `[x, y]` pairs, `elevation_range_m` missed entirely, a
hazard's `effect` read as a scalar rather than the object it is, and
`ambient.light_level` missed too. `serialization.json_schema()` now walks
`Scene` the same way it already walks `SessionStateView` — `Wall`,
`Surface`, `Hazard`, `HazardEffect`, `Furnishing`, `Construct`,
`ConstructEffect`, `AmbientConditions`, `SceneBounds` and `Position` all
get `$defs`, derived from `scene/` as authored, not retyped by hand.
`Scene.encounter` is the one field walked out on purpose — it types as
the full internal fight (`Encounter.sessions: list[CombatSession]`) that
`SessionStateView` already publishes as its own flat projection, and
walking it here would grow a second, un-flattened copy of that same
graph. Added to `FREE_FORM_PAYLOADS` for that reason, next to the four
`Any` payload bags it now sits beside.

## 0.18.3 — 2026-09-18

State view carries `spd`/`dex` (and `max_*`) as build facts. Krackle's SPD
ribbon and DEX ordering need SPD and DEX; they are bought-on-the-sheet build
facts, like `invisible`, not folds of the log — so `CombatantStateView` now
carries `spd: int` and `dex: int`, read through `combat_stats()`, the one
door every characteristic already goes through. `max_stun`/`max_body`/
`max_end` were checked and were already there, read the same way. No default:
a combatant with no SPD raises, same as every other characteristic.

## 0.18.2 — 2026-09-18

**A viewer generates its event types from the engine, and checks its fold
against the engine's.** A consumer that renders these fights has always
hand-written the event shapes, which is a copy of a contract nothing checks —
the same defect this package's own type registry had when six of twenty-eight
events could be written and never read back. `serialization.json_schema()`
walks `EVENT_CLASSES`, which is `get_args(CombatEvent)` — the union itself,
and the same derivation the registry and the round-trip gate read — and emits
a 2020-12 JSON Schema document: a top-level `oneOf` over one `$def` per event
kind, each pinning `kind` to a `const`, so a generator on the other side turns
it into a union an exhaustive switch narrows. It describes the WIRE `to_dict`
writes, not the Python behind it: `__type__` on every object, an ISO
`date-time` string for a `datetime`, an array for a tuple or a set. A field
whose type has no JSON Schema meaning RAISES rather than being skipped — a
field quietly left out is a field the consumer discovers is missing by reading
it off a real row.

**The state a viewer checks itself against.** `state_view(session)` publishes
the shape `rewind_to_sequence` exposes: the clock, the status, the last
sequence on the log, whose Phase is next, and for each fighter his vitals,
where he stands and which way he faces, what condition he is in, whether his
build carries Invisibility, and who he can perceive. NOTHING ON IT IS A NEW
RULE. Every field is read through a door this engine already had —
`classify_health`, `is_down`, `Side.of`, `position_of`, `statuses_for`,
`concealment.is_invisible`, `concealment.perceives` and `next_actor_id` — so a
viewer's fold can be compared against the engine's field by field instead of
trusted. In particular a viewer's fog is now the engine's own answer rather
than the viewer's opinion about who sees whom, which used to fail OPEN and
show everyone.

**`perceives` goes through `concealment.perceives`, which is the one door.**
That function is documented as the one place the log's hiding and the build's
Invisibility are handed to `perception.perceive` together, "so callers do not
each assemble the arguments and each forget a different one" — and it now
carries the observer's Flash and the normal-human grounding for a flat stat
block as well, which a caller reaching it still had to remember on its own.
`sense_penalties.cannot_perceive` reaches `perceive` without the concealment
arguments at all, so it does not fold Invisibility even partly: the power is
skipped entirely. A view built on it would have published an Invisible fighter
as seen by every enemy on the board while claiming to be the engine's answer.
So what `perceives` folds, exactly: a Flash on the observer's Sense Group, a
Darkness field on the ray, the target's Invisibility, a Hidden target's
opposed Stealth contest, and the walls. It is NOT always a read — `perceive`
rolls for an Invisible target's Fringe within 2 m and for a Hidden target's
Stealth contest, and those two pair kinds are a roll rather than a projection.
Invisibility is not side-aware in 6E and is not made so here: an ally is as
blind to it as an enemy.

**Being unseen is published PAIRWISE and nowhere else.** `perceives` is per
observer, which is the granularity the engine's own Hide contest resolves at —
"being unseen is not a property of the hider: one enemy may lose you while
another keeps you in view". There is deliberately no flattened `hidden` flag
beside it: a global "unseen by somebody" would answer the same question at a
second granularity and a consumer could not recover the pairwise truth. What
IS published per combatant is `invisible`, the build fact, which is true of
the character rather than of a pair.

**`state_view(session, *, roller)` — the roller is required and has no
default, because this is a playback surface.** Two reads of the same sequence
must agree, and `perceive` builds its own `RandomRoller` when handed none, so a
view that seeded itself would answer differently every call for the two rolled
pair kinds and a replay would not replay. The caller supplies the roller —
derived from the sequence it is asking about, if it wants the same board
twice — and a caller that has not thought about it gets a `TypeError` rather
than a silent reseed. `concealment.perceives` takes the roller through for the
same reason and likewise defaults nothing.

A combatant who is not on the map reads `position: None`, never the origin,
which would put an absent man adjacent to whoever stands at (0, 0, 0).

The derived document is committed and shipped: `kirby_combat/schema/events.json`
is carried in the wheel, `python -m kirby_combat.schema` prints it, and
`tests/serialization/test_json_schema.py` fails if the file and the derivation
disagree in shape. The version stamped on the document is checked against
`pyproject.toml`'s `[project] version` rather than against the environment
that generated it — an artefact derived from a stale editable install carries
the wrong version, and comparing it against that same environment would agree
whenever both were wrong. `scripts/check_release.py` repeats the check against
the built wheel, at the last door before publication. The document's `$id` is
a URN, not a URL: a standalone library does not name a deployment host it
knows nothing about. `json_schema`, `state_view`, `SessionStateView`, `CombatantStateView`
and `PositionView` are on the import surface, demonstrated by
`examples/the_schema_a_viewer_generates_from.py`.

**THIS RELEASE IS THE SCHEMA AND THE STATE VIEW, AND NOTHING ELSE.** The
harness follow-ons under discussion — a situation on `PhaseResult`, the
session-ended event's shape, a public event base class and a progress
predicate — are deliberately NOT here; they are a separate release, so nothing
downstream waits on them.

## 0.18.1 — 2026-09-17

**A round-tripped combatant can fight.** `serialization/to_dict` projects a
`HeroCombatant` to a flat snapshot and `from_dict` rebuilds it around a stub
hero with no powers, no skills, no martial arts and no equipment — and every
view on `HeroCombatant` is derived from exactly those. `attacks` walks
`hero.powers` and `hero.equipment`; `csls` walks `hero.skills`;
`defense_view`, `senses`, `movement_view`, `maneuver_view`, `framework_view`,
`is_mentalist`, `has_combat_sense`, `has_self_contained_breathing` and
`skill_roll_value` each walk one of them. So a rebuilt combatant reported
NOTHING through any of them: measured on the kirby-api harness, Drago's three
RKAs went in and none came back, and a rebuilt fight did no damage. It also
came back on no side — `side` was never written to the wire at all, so a
rebuilt roster was a free-for-all in which the two men who had been allies now
had to kill each other.

The code meant to prevent this assigned `_snapshot_override_attacks` and
`_snapshot_override_defenses`, which nothing in the engine ever read, and
monkeypatched `combat_stats` onto the instance, which `dataclasses.replace`
drops — so a rebuilt combatant also lost its resistant defenses the first time
it spent a point of END.

Replaced with ONE door: `hero_view.CombatantSnapshot` holds every derived
view, `CombatantSnapshot.of(live)` records them off a live combatant, and each
view returns the recorded value when a snapshot is present. The resolvers are
untouched and unaware — they go on reading `c.attacks`, `c.csls`, `c.senses()`
and see the same values either way. Everything hanging off `state` stays live:
STUN, BODY, END, statuses, and Drains and Aids on characteristics, which
`combat_stats` goes on applying. `skill_roll_value` now reads a new
`skill_rolls()`; `can_swim` now reads a new `swimming_m()`, so the
`cannot_swim` status stays live on a rebuilt man rather than being frozen into
the verdict.

**BREAKING (wire format).** A combatant snapshot must now carry its views.
`from_dict` raises `ValueError` naming the missing keys on a snapshot recorded
by 0.18.0 or earlier, rather than rebuilding a man who does nothing — an empty
`attacks` list is a legal combatant, which is why nothing complained. Re-record
such a combatant from the canonical character with `HeroCombatant.from_build`.

**`PresenceActionLost` can be read back off the wire.** It is a `_BaseEvent`
subclass that `pre_attacks/presence_effects.py` emits and `apply_event` folds,
and it was absent from the `CombatEvent` union — so the registry `from_dict`
derives from the union never knew the name, and a fight in which a Presence
Attack cost a man his Phase could be written and never read back
(`unknown type 'PresenceActionLost'`). Same shape as the six `VitalsChanged`
was in, one level up: `EVENT_CLASSES` guards the registry against the union
and could not guard the union against the classes. The round-trip gate now
DERIVES its set as every `_BaseEvent` subclass the events module declares, so
the union, the registry and the folder cannot disagree again.

Fixture fix, found by the new gate: `_SyntheticCombatant` shadowed the
`defenses` property while the base `defenses` *is* `defense_view()`, so a
synthetic combatant answered `[Vest]` through one door and `[]` through the
other. It overrides `defense_view` now.

Known, and left as a strict xfail rather than papered over:
`enumeration.enumerate_actions` reaches past the combatant's public surface
into `actor.hero` at 21 sites (it says so in its own comment), so a rebuilt
corpus character's menu loses the actions read straight off HEALING and AID
powers — for which no view on `HeroCombatant` exists. The combatant itself
round-trips; this is a second door in the enumerator.

## 0.18.0 — 2026-09-17

**Mental Defense applies to mental attacks.** `resolution/defense.py`'s
`_DEFENSE_MAP` had `"md"` and no `"mental"`, while `hero_view` returns
`"mental"` for any power whose build says `DEFENSE="MENTAL"` — so every mental
attack fell through to the unknown-type branch, which returned a
`DefenseProfile` of all zeroes, and a Mental Blast took full damage against any
Mental Defense at all. Both spellings now resolve to the target's MD (6E2's
Mental Combat; Mental Defense still does not apply against physical or energy
attacks, which is why it is its own row). An unrecognised `defense_type` now
RAISES instead of silently applying no defense: an all-zero profile with a line
in the audit is how this defect survived with no test failing.

`CombatSession` built with events already on it and no `initial_combatants`
raises. The combatants such a session holds are the men the fight *left*, and
`rewind_to_sequence` replays into the men it *found* — inferring one from the
other is a guess that silently makes every later rewind return a session more
hurt than the fight ever got. A session with an empty log still infers: it has
not been in a fight.

**`PhaseResult.events` is every event the call wrote.** It was assembled from
the sub-calls — the skips, the resolver's events, the spend — and the clock's
events were not among them: `ActingOrderResolved` (from `Encounter.run_segment`),
`SegmentAdvanced` (from `advance_segment`) and the free Post-Segment 12
`RecoveryTaken` all went into the log and none came back. A consumer persists
what it is handed, so its own log had holes; measured over eight Phases, four
steps lost events outright, one returned three of its nine, and replaying what
had been persisted raised `event sequence mismatch: expected 2, got 3` on the
second step. `run_phase` records the log length at entry and returns the tail at
exit — one measurement, not a second account of the Phase that can disagree with
the record.

**A Block's "acts first" is in the record.** 6E2 p.60's priority — a successful
blocker acts before that attacker in the next Segment they share, "even if [the
attacker] does not attack again" — was carried on `Encounter.acts_first`, a
field, and by no event at all. It was the last piece of fight state a consumer
could not rebuild: rehydrating the Encounter from a session's own timeline
between steps left the mapping empty, so the blocker won his Block in the live
fight and lost his priority in the replayed one. `BlockPriorityGained` now
carries it, `apply_event` folds it onto `Timeline.block_priority`, and
`Encounter.run_segment` reads it from there (`Encounter.acts_first` remains an
explicit override, merged on top; `carried_block_priority()` is the one
reading). The SPEND needs no event: an `ActingOrderResolved` containing both men
*is* the shared Segment the rule names, so `apply_event` drops the entry when it
applies that order.

**No row is edited after it is applied.** The Trip resolver (6E2 p.67) ran its
attack through `apply_event` and then `dataclasses.replace`d the payload on
`event_log[-1]` to stamp `kind="trip"`, the house-rule Acrobatics save and
`is_prone_after`. A consumer that persists rows as they are emitted stored the
row *before* that edit, `statuses._is_prone` folds exactly those keys, and the
replayed fight had a man standing whom the live fight had prone.
`resolve_attack_in_session` takes a `payload_extras` callback — called with the
finished `AttackResult`, merged into the payload *before* the `ActionResolved`
is built — so a maneuver labels its own row without ever reaching back into the
log. A test walks the engine by AST and fails on any index-assignment into an
event log or any `replace(..., event_log=...)` outside `session/apply.py` and
`session/rewind.py`; it flags the old resolver verbatim.

**Every event deserialises, because the union says so.** `from_dict`'s type
registry and `tests/serialization/test_roundtrip.py`'s coverage gate each kept a
hand-written list of event classes, and both went stale together: six of the
twenty-eight — `VitalsChanged`, `BleedingSuffered`, `PresenceApplied`,
`PresenceFaded`, `ConstructDamaged`, `ConstructSpawned` — were unregistered, so
`from_dict(to_dict(e))` raised `TypeError: unknown type` on the row that now
carries every point of STUN, BODY and END. A consumer persisting rows as JSON
could not replay one point of damage. Both now read
`kirby_combat.session.events.EVENT_CLASSES`, which is `get_args(CombatEvent)`;
the gate is parametrised over it and compares field by field, with a negative
control that a class outside the union does not round-trip.
`EVENT_KINDS` maps a `kind` string to its class. One real bug fell out of the
derived gate: a `tuple[int, ...]` field (`BleedingSuffered.dice`, 6E2 p.115)
came back as a list.

**One door steps a fight.** `run_phase` now takes the `Encounter` and owns the
clock as well as the Phase:

```python
run_phase(encounter, chooser, *, roller,
          on_unresolvable="raise", campaign=None, until=None) -> PhaseResult
```

It resolves the Segment's acting order when the fight is carrying none, and
when the order is spent it advances the Segment (and the Turn, and with it 6E2
p.131's free Post-Segment 12 Recovery, p.109's bleeding, the Adjustment fade
and `SegmentAdvanced`) until it finds a Segment somebody can act in. The
template is resolved from the Encounter and the campaign, so the `template=`
argument is gone; `roller` serves both the resolvers and 6E2 p.21's
zero-argument tie-break. `PhaseResult.encounter` carries the fight forward and
`PhaseResult.session` is a view of it.

`actor_id is None` now means ONE thing: the fight is decided by `until`
(default: last side standing), and nothing further is emitted. It used to also
mean "this Segment is spent, advance it yourself" — so a consumer stepping a
fight one Phase at a time could not finish one, and `run_encounter` held a
second copy of the advance. `run_encounter` is now a loop over `run_phase`
plus the guards a driver owns (`max_turns`, the stalemate counter, the
verdict); a test reads its body by AST to keep it that way. A whole Turn with
no actor and no verdict raises rather than returning quietly.

The stalemate counter now reads the AMOUNT on a `VitalsChanged` /
`RecoveryTaken` / `BleedingSuffered` rather than the kind alone: a man at full
STUN takes a free Recovery of nothing every Turn, and once the advance moved
inside `run_phase` that was resetting the counter every twelve Segments.

**The log rebuilds the fight.** `apply_event` is now the ONLY writer of a
combatant's STUN, BODY and END. Every resolver used to change the combatant
beside the event that described the change — an attack folded its damage onto
`session.combatants` and logged an `ActionResolved` whose payload was a
free-form dict; the END an attack, a move or a Push cost was taken off the
fighter and logged nowhere at all — so a consumer that persists the rows and
rebuilds the fight by replaying them rebuilt a fight in which nobody had been
hit. Measured: two Phases in, a fighter stood at 27 STUN in the fight that ran
and 50 in the fight replayed from its log.

`VitalsChanged(combatant_id, stun, body, end, reason)` is the new typed event
for damage and for an END spend; the deltas are signed and are deltas, not
resulting values. `RecoveryTaken` (6E2 p.130, p.131) and `BleedingSuffered`
(6E2 p.109, p.115) keep their names and their typed fields and are folded by
the same dispatcher — no fold parses a free-form dict. A change addressed to a
combatant the session does not know raises rather than passing in silence, and
an unknown event kind still raises. `vitals.record_vitals_change` is the one
emitter; `vitals.apply_vitals_delta` is now called by `apply_event` alone, and
a test walks the engine by AST to keep it that way.

`CombatSession.initial_combatants` records the men as the fight found them.
`rewind_to_sequence` replays into those rather than into the current
combatants: with a real fold there is no inverse to walk back to, and seeding
a rewind with the men as the fight LEFT them would replay its damage on top of
itself.

**The loop is in the log.** The two decisions the turn loop made in memory and
told nobody about now reach the record: `ActingOrderResolved` (who acts, in
what order, in which Segment — emitted by `Encounter.run_segment`, the one
place an order is resolved) and `PhaseSpent` (a slot consumed — emitted
wherever the loop spends one, including `next_actor_id`'s skip, which moved to
`resolve_next_actor` — asking whose Phase it is no longer changes the fight). The order carries the
declared intents that produced it (6E1 p.116(c)'s Lightning Reflexes election is
enforced off them) and a spend carries a `reason` — `"acted"`, or `"down"` /
`"left"` for a slot its owner was in no condition to use, which the loop used to
consume in silence. `apply_event` restores the acting order, the intents and the
spent flags from them, so a fight rebuilt by replaying its log alone stands where
the original stood, picks the same man to act, and refuses the same
declarations. Before this, a
consumer that persisted only the events could rehydrate a fight and find
nobody able to act.

**One door for health.** `classify_health(combatant) -> "healthy" | "wounded" |
"critical"` (exported from `kirby_combat`) is now the single statement of the
engine's own judgement about how badly hurt a fighter is — half STUN is
wounded, a quarter or any BODY at zero is critical, the same rung the Recover
offer reads. The two tactics that gated on it (`take_cover_when_hurt`,
`reposition_when_spotted`) each held a private copy of the arithmetic; both
copies and their constants are gone. Three more have followed them:
`enumerate_actions`' Recover offer (which alone was written as
`current_stun < max_stun // 2`, so at an odd STUN total it really did disagree
with the percentage the tactics read — 22 of 45 was "wounded" to one and
"healthy" to the other; it asks `health.stun_percent` now and stays on the STUN
rung specifically, because the full ladder also calls a man at 0 BODY critical
and 6E2 p.130 prices a Recovery in STUN and END),
`stand_and_take_it`'s `_STUN_HEALTHY_PCT`, and the
percentage the two hurt-tactics printed in their rationale, which is now
`health.stun_percent` — the number the ladder itself is cut from.

**`Brief.render(..., extra_doctrine=())`.** A caller's own advice for this
fight is appended after the engine's lines, under the same
"What your doctrine says, best first:" heading and at the same indent, and is
governed by exactly the same one-way suppression (`KIRBY_BRIEF_NO_DOCTRINE`, or
`doctrine=False`, removes the extras too). With extras and no doctrine of its
own, the section opens with the extras alone. Nothing else on the page changes.

`CombatTemplate.by_name(name)` resolves a stored template name
(`"6e-superheroic"`, `"6e-heroic"`) and raises `KeyError` naming the known
ones. No default argument: a fight whose rules were lost must not quietly be
run under someone else's.

## 0.17.0 — 2026-09-17

131 commits since 0.16.0 (2026-09-07 to 2026-09-13): 59 features, 62 fixes.
Highlights, from the commit subjects:

- feat: firing into melee — the held man can take the bullet
- feat: a Grab costs both men their DCV
- feat: a grabbed man can struggle — the grapple chain closes
- feat: tactics can measure reach; grappling; a Grab that led nowhere
- feat: doctrine can disarm — and a prop that cost six action kinds
- feat: doctrine stops letting men bleed to death
- feat: a scene can say what may be picked up
- feat: futility grades an attack on TERRAIN too
- feat: grade the decision, not just count it
- feat: the doctrine hint is the caller's call, not a global
- feat: a baseline records WHICH PAGE it measured
- feat: the Brief says what SHAPE the enemy is in

**Breaking:** `refactor!: the engine takes a build, never a file`.

`Brief.render(*, doctrine=...)`: the doctrine-hint section is the caller's call
(kirby-ai 0.2.x depends on this).

## 0.16.0 — 2026-09-07

**The engine can execute what it offers.** Resolvable action kinds go from
**4 to 45 of 51** — and the fights that ran before this release were wrong
in two ways nobody could see.

### Fixed

**The loop never read the Scene, so melee was never gated.** `CombatSession`
has always carried a `scene`, and `run_phase` called `enumerate_actions`
with `has_scene` defaulting to False — so `_melee_gate` returned "direct"
for every enemy and a fight offered strike, grab, disarm and trip
UNCONDITIONALLY. Combatants could punch each other from across the map.
Measured on two fighters and one map: 15 kinds in the void, melee gone at
20m, melee back at 1m.

**Nothing ever wrote a position, so a fight on a map was frozen.**
`movement_reach` decided moves completely — clamped by walls, surfaces and
capacity, with any fall — and `MovementAction.resolve` built its
`MovementResolved` with `from_pos` and `to_pos` **both hardcoded to None**.
`scene.combatant_positions` was read by the range gate, line of sight,
cover and Images placement, and written nowhere outside a test fixture.
Everyone attacked from where they started, forever.

These two hid each other: melee was ungated *and* nobody could close the
distance. Neither raised, because a stationary fight offering illegal melee
is still a valid fight — the same shape as every other defect this
carve-out has surfaced.

**`advance_segment` left a stale acting order behind**, `has_acted` flags
and all, so a Segment 3 order still described Segment 6.

### Added

`kirby_combat.scene.placement` — `commit_move`, `move_toward`,
`position_of`. Its own module on purpose: deciding where someone can go is
a rule, recording that they went there is a different one, and folding the
second into `movement_reach` would make a pure "could I get there?" query
mutate the world.

**41 newly reachable action kinds.** The rules were already written, tested
and correct; what was missing was a caller. `actions/images.py` — 480 lines
— had exactly one importer, its own test file. The engine states the mental
Attack Roll once; the parked driver wrote it out at four separate lines.
Every one of those suites was green the whole time, which is why
`registered_kinds()` is pinned by a test: only that number can tell the
difference between a rule that works and a rule that is reached.

`loop/registry.py` splits into mechanism (the decorator, the dispatch, the
raise) and `loop/resolvers.py` (the work), since the resolver list is what
grows and the dispatch should not.

`perception.images_groups` joins `flash_groups` and `darkness_groups` as
the third occupant of one shape.

### Known limits, stated

- **`AdjustmentFaded` has no emitter anywhere in the engine.** The class
  exists, `apply_event` passes it, `session/effects.py` folds it, and
  nothing constructs one — so an Aid or Drain never fades, where 6E says
  both should at 5 AP per Turn. This predates the wiring; wiring made it
  reachable, which is the first step to fixing it.
- **6 kinds remain unwired, and none is wiring.** `disarm`, `trip` and
  `spread` have no engine rule at all; `coordinate`, `reallocate` and
  `reconfigure_vpp` need machinery that does not exist yet.
- The count is **51**, not 52. `debris` is a Construct kind, not a
  LegalAction kind; an earlier regex over-counted and an AST walk settled
  it.

## 0.15.0 — 2026-09-06

**A Phase can be written down.** The third and last gap between the engine
and a fight it can run alone — damage application and the turn loop closed
the first two in 0.14.0.

### Added

`kirby_combat.Brief` and `kirby_combat.CombatantLine`, with
`PhaseSituation.brief()` as the entry point. A written description of one
Phase: who is acting, what shape they are in, who is standing where, and
what they may legally do.

The equivalent builder in the parked wrapper is 160-odd lines that —
measured 2026-09-06 — touch the database **zero** times. It was already a
pure function of engine state; only its location was wrong.

Two other homes were considered and rejected. `kirby-ai` looked obvious and
is wrong by its own charter: it owns the network hop and the policy around
it, explicitly not content, rules or rows. A module of its own would hold
one class with no second occupant. The engine, meanwhile, already renders
itself to text and always has — `LegalAction.summary` is a readable label
and `Tactic.narrative_summary` is "the one-liner shown to whatever picks
one". A Brief is those, gathered into a page.

It names nothing about what might read it, and `tests/test_vocabulary.py`
enforces that. Same seam as `Chooser`: the engine asks, and never learns
what answered.

Each offer is listed as `[action_id] summary`. The summary is for the
reader; the bracketed token is the contract, and is exactly what
`validate_choice` checks. Enemy numbers are shown as freely as the actor's,
deliberately — the anti-metagaming line in this system is drawn by
PERCEPTION, not by hiding stat blocks from whoever is choosing.

A Brief reads state and changes none.

## 0.14.0 — 2026-09-06

**The engine can run a fight.** Damage lands, the turn loop lives here, and
sides are objects.

### Added

`kirby_combat.loop` — the turn loop (sub-project D of the driver carve-out).
Whose Phase it is (6E2 p.18), who acts first (6E2 p.19-21), when the Turn
wraps and the free Post-Segment 12 Recovery fires (6E2 p.131), and when the
fight is decided (6E1 p.421) are all rules, and every one of them lived in a
web service's driver until now — 258 lines of database-bound "whose Phase is
it" and 38 more of SQL-backed "is it over".

- `Chooser` — the one thing the engine does not decide. `FirstLegalChooser`
  (deterministic, makes the loop testable) and `TacticChooser` (picks by
  `classify_role` and `tactics_for`). A pick outside the menu raises at the
  seat.
- A resolver registry. **52 action kinds are enumerable; 4 are resolvable.**
  An unregistered kind RAISES rather than skipping silently, and
  `registered_kinds()` is pinned by a test — so each resolver that migrates
  out of the parked driver moves a number rather than disappearing into a
  silence. `on_unresolvable="skip"` records the kind; a skip is never
  invisible.
- `run_phase` / `run_encounter`, with `until=` to replace last-side-standing
  and a `max_turns` guard that reports rather than loops.

`kirby_combat.Side` and `kirby_combat.Roster`. A side is an object: `Side.named`
folds case and spacing into one identity, so `"Golden"` and `"golden"` are one
army **by construction** rather than by validation — as strings they made a
fifth army in a four-army battle, changing who won, with nothing to look at.
`side=None` means a side of one, so an N-way free-for-all works under the same
rule as a team battle. `Roster` replaces four module-level helpers that all
took the same session; `Verdict` replaces a `(bool, Side | None)` tuple.

`kirby_combat.apply_vitals_delta` — one fold for every STUN/BODY/END change.

`side` on both combatant shapes.

### Fixed

**`resolve_attack_in_session` now applies its damage.** It computed
`stun_dealt`, recorded it on the event log, and left `current_stun` untouched,
so every consumer subtracted by hand — the parked driver at 15 separate call
sites, none clamping, none handling both combatant shapes. A fight could
resolve one exchange and then repeat it forever against a target that never
got hurt. Nothing is clamped: `is_ko` is `current_stun <= 0`, and 6E reads how
far below zero a character went.

**`advance_segment` left a stale acting order behind.** Each `ActingSlot`
carries the Segment it was resolved for and nothing cleared the list, so a
Segment 3 order — `has_acted` flags and all — still described Segment 6.
Nothing caught it because nothing consumed `acting_order` in a loop; the
driver tracked its cursor in the database. `apply_event` now clears it on
`SegmentAdvanced`.

**`enumerate_actions` crashed with a bare `AttributeError` on a
`StatBlockCombatant`.** It reads `actor.hero` at 21 sites, so it needs a
build-backed combatant — but a stat block is a first-class participant
everywhere else (vehicles and objects subclass it; `resolve_attack` takes
either shape). It now raises a `TypeError` naming the limitation at the
boundary. Widening enumeration to flat stat blocks is real work and is not
smuggled in behind a `getattr` default that would return a shorter menu.

### Removed

`kirby_combat.loop.sides` — replaced by `kirby_combat.roster`.

## 0.11.0 — 2026-09-05

**The Objects Table has one home, and it is not here.** Requires
`kirby-terrain>=0.1.0`.

### Changed

`kirby_combat.breakables.object_table` is DELETED. `OBJECT_DURABILITY` and
`ObjectDurability` are still importable from `kirby_combat` exactly as before —
they are now re-exported from `kirby-terrain`, the dependency-free leaf that
owns what terrain IS.

**Migration: none for supported callers.** `from kirby_combat import
OBJECT_DURABILITY` is unchanged. Only the deep path
`kirby_combat.breakables.object_table` is gone, and `tests/test_import_surface.py`
has always said anything outside `__all__` is internal.

The table was added here on 2026-09-04 and moved out a day later, which is
worth explaining rather than hiding: it belongs beside the geometry and object
model that describe terrain, not inside the engine that fights on it. A
transcribed rulebook table with two homes is exactly the drift this codebase
has a history of — "5 STR to the die" once lived in three places across two
repositories, agreeing only by luck.

`tests/breakables/test_object_table.py` no longer tests the table's contents;
kirby-terrain's suite pins all 18 rows against the book. It now tests IDENTITY —
that this package's name and kirby-terrain's name are the same object — plus a
guard that fails if a second definition ever reappears here.

## 0.10.0 — 2026-09-04

**The dice moved out.** `kirby_combat.dice` is gone; the roller now ships as
the standalone [`kirby-dice`](https://github.com/pdbethke/kirby-dice) package,
item 6 of the carve-out program. Requires `kirby-dice>=0.1.0`.

### Removed — BREAKING

`kirby_combat.dice` no longer exists, and `DiceRoller`, `RandomRoller` and
`FakeRoller` are no longer re-exported from `kirby_combat`.

**Migration:** `from kirby_combat.dice import RandomRoller` becomes
`from kirby_dice import RandomRoller`. Nothing else changes — same classes,
same behaviour.

There is deliberately **no compatibility shim**. A re-export would leave two
names for one thing, and a consumer that kept using the old one would go on
depending on this package for something it no longer owns.

The extraction is not about size — the package is under 100 lines. It is
about what a dice module is for. Bill Bame's attribution, missing entirely
until 2026-08-28, now has a module of its own and a release guard that fails
the build if it ever stops shipping. And "here is the RNG, here are its
fairness tests, here is the seed" is something a standalone package can be
and a private helper inside a combat engine cannot.

### Removed — BREAKING, and unrelated to the move

`roll_half_die()` is gone from `DiceRoller`, `RandomRoller` and `FakeRoller`,
along with `FakeRoller(half_die_results=...)`.

It had **no callers anywhere** — not in this package, not in kirby-api. Half
dice are, and always were, resolved elsewhere: the caller rolls one extra whole
d6 and `resolution/damage.py` reads the last value of the batch, converting it
to `STUN += raw // 2` and `BODY += 1 if raw >= 5`. The two definitions did not
agree — `roll_half_die` mapped 1-2 to 1, 3-4 to 2, 5-6 to 3, a different
distribution entirely — so anyone who reached for the obvious-looking API would
have silently changed damage. This is exactly the second-copy-of-the-arithmetic
problem `tests/test_dice_have_one_source.py` exists to prevent; it slipped
through because the duplicate lived inside the dice package rather than being
compared against kirby-cost.

Nothing to migrate: no caller existed. The live path is unchanged.

### Added

`RandomRoller.seed` — the seed the roller rolls from, always a real number.

An unseeded `RandomRoller()` used to draw from OS entropy, so the seed never
existed as a value and a fight could not be replayed once fought. It now
chooses its own seed with `secrets.randbits(64)` (unguessable, so recordable
does not mean predictable) and hands it back. Record `roller.seed` alongside a
fight and `RandomRoller(seed=<recorded>)` reproduces it die for die.

`tests/test_dice_fairness.py` — 20 seeded, deterministic tests the roller has
never had: chi-square uniformity over 60,000 rolls, independence of consecutive
rolls across all 36 ordered pairs, mean within five sigma of 3.5, range and
face coverage, and the seed-replay property above. Two of them guard the
guards: a loaded die must trip the uniformity assertion, and unseeded rollers
must not all share one seed.

The dice package went from 82% to **100%** coverage before moving out;
`roller.py` was the worst-covered file in the engine at 71%, and the gap was
entirely the dead method. All of that work — the fairness suite, the seed,
the 100% — travelled with the package to kirby-dice 0.1.0.

Suite here: 1404 passed (the 28 dice tests now live in kirby-dice).

## 0.9.0 — 2026-09-02

**Combat now fights the character on the sheet.** It read the CHARACTERISTICS
section alone, so every characteristic bought as a POWER was invisible to it.
Requires kirby-cost >= 0.6.0.

### Changed — this moves numbers, for 325 of 794 corpus characters

`combat_stats()` reads the TEMPORAL characteristic (base plus whatever is
currently applying) instead of the base sheet value. Measured across the whole
corpus, main vs this release:

| | characters |
|---|---|
| identical | 469 |
| changed | 325 |
| unexplained | **0** |

Of the 325: **319** buy a characteristic as a power that HD counts toward the
total (`AFFECTS_TOTAL="Yes"`) — Gorgon fought at PD 15 where his sheet says 35
— and **6** carry purchases limited to their Hero identity (6E1 p.386), which
combat had been ignoring entirely. White Wolf fought as a civilian: DEX 10
instead of 25, SPD 2 instead of 6. Ravel goes from SPD 2 to SPD 5.

Every mover was classified; none is unaccounted for. A character with no
characteristic-granting powers and no conditional purchases is byte-identical.

### Added
- **Identity is combat state.** `HeroCombatState.in_hero_id` (default True — a
  character in a fight is in costume unless someone says otherwise), on the
  wire in both directions, so a recorded fight knows which identity it was
  fought in.
- **Pushing** (6E2 p135-136), as a temporal contribution: 1 END per Character
  Point Pushed. It needed nothing beyond declaring a `Contribution`, which is
  what the design was meant to demonstrate.
- Drains and Aids are `Contribution`s weighed in the same list as a
  character's own purchases, rather than deltas subtracted afterwards.

### Fixed
- **A slot fights with the modifiers its pool carries.** `_has_modifier` /
  `_modifier_levels` were a flat scan doing neither recursion into containers
  nor inheritance from an enclosing purchase, so ARMORPIERCING, PENETRATING,
  HARDENED, IMPENETRABLE and DOESBODY were all under-reported for any power
  inside a Power Framework. Both now delegate to `kirby_cost.model.modifiers`.
- **A Drain is applied once across a snapshot round trip.** The snapshot
  recorded already-drained stats alongside the drains dict, and rehydration
  applied them again: Ravel read DEX 15 live and 11 after a round trip. Since
  replay folds forward from a captured snapshot, every recorded fight
  containing a Drain replayed with wrong numbers. Snapshots written before this
  release still replay — the pre-adjustment value is reconstructed by adding
  the recorded adjustment back.
- **rPD/rED track CURRENT PD/ED** rather than a frozen quantity of points
  (6E1 p149: an Advantage bought for a character's PD or ED applies to that PD
  or ED). An Aid on PD now raises rPD; the purchased ceiling still binds.

### Performance
- `combat_stats()` prices the stat block from ONE walk of the purchases instead
  of one per characteristic: **1.53 ms → 0.138 ms**, and 3.00 → 0.281 ms with a
  Drain active. Nothing is cached — Drains, Aids and identity flips have to
  compose live — the walk is simply paid once.

## 0.8.1 — 2026-08-31

### Fixed
- **`resolve_move_strike` no longer loses every leap-strike onto an elevated
  target to a fall.** The composite aims the close at a point one Reach short
  of the target; when the target stands on a rooftop that point hangs in the
  air beside the roof. The mid-air retry that exists precisely for this case
  — re-running the close at the target's own, supported square — was gated on
  the short-of attempt having been REFUSED or landed out of reach. A leap to
  that mid-air point is neither: it is within both the horizontal and the
  vertical capacity and it does arrive in reach, so `movement_reach` reports
  it reachable and simply attaches a fall. The retry therefore never fired,
  the phase was spent falling, and `reason="fell"` came back instead of a
  `StrikePlan`. The retry now fires whenever the short-of attempt was not
  clean — refused, short, OR fallen — since falling is what an unsupported
  destination looks like from outside `movement_reach`. This restores the
  pre-migration kirby-api behaviour, which retried when the point one metre
  short was unsupported.
- **A retry is a rescue, never a replacement.** The retried close is adopted
  only when it is itself clean (reachable, no fall, arrives in reach); a
  retry that is refused, lands short, or falls in turn leaves the original
  outcome standing. So no actor collects a strike it did not earn, and a
  genuine fall that no retry can lift is still reported as `reason="fell"`
  with `fell=True`, from the landing its own close produced.

## 0.8.0 — 2026-08-31

The reach rule as a first-class engine surface, and the close-and-strike
composite that consumes it.

### Changed
- **BEHAVIOUR CHANGE — base Hand-To-Hand Reach corrected from 2m to 1m
  (6E2 p56, 6E2 p40, 6E1 p231).** 6E2 p56 sets a character's base Reach at
  one metre, not two; 6E2 p40's Range Modifier table and 6E1 p231 corroborate
  the same boundary. Any consumer that measured HTH range against the old 2m
  figure — including anything that inferred adjacency from distance — will
  see melee reach halved after this upgrade. `hero_view._base_reach_m`
  still adds 1m per level of Stretching on top of the corrected base.

### Added
- **The reach rule as an engine surface (`kirby_combat/actions/reach.py`,
  6E2 p56).** `within_reach(distance_m, reach_m)` applies the rule to a
  measured distance and returns a `ReachVerdict` — `in_reach`, `distance_m`,
  `reach_m`, and `shortfall_m` — rather than a bare bool, so a failed close
  can say how short it fell instead of failing silently. 6E2 p36 gives the
  same boundary from the other side (combat outside Reach is Ranged Combat);
  6E2 p40's Range Modifier table gives the reach band its own row.
- **Close-and-strike composite (`kirby_combat/actions/move_strike.py`,
  6E2 p56).** `resolve_move_strike(...)` returns a `MoveStrikeOutcome` built
  from a `StrikePlan`, and settles, in order: (1) the close, resolved through
  the scene-aware `movement_reach` path so per-mode legality holds (running
  is same-elevation only, leaping has a vertical capacity, flight is free
  3D, and an illegal or over-long move clamps short rather than failing
  loudly); (2) the reach rule from this release, applied at the LANDING
  position rather than the position the action was chosen from — the check
  whose earlier absence let a martial throw resolve between combatants six
  metres apart in elevation; (3) refusal of a free strike when the close
  itself was refused (an unmodelled mode, a mode that cannot operate here, a
  Stunned combatant); (4) perception, gated at the landing position too, so
  an attacker who closed but still cannot perceive the target strikes blind
  per 6E2 p9/p127 rather than at full CV. With `scene=None` the close falls
  back to a straight line clamped to the movement budget and `mode` is
  ignored — no elevation, walls, or support are modelled in that path; only
  the reach rule still bites.

## 0.7.0 — 2026-08-28

The sense-affecting family, Presence Attack consequences, and a front door.

### Added
- **Inability to sense an opponent (6E2 p.9 / p.127)** — the CV penalty is
  now real, and it is PER-OPPONENT. `cv_modifiers` grew a second seam for
  opponent-dependent conditions plus an additive `*_delta` channel, because
  6E2 p.9's mitigated case is a flat -1 DCV that no factor can express.
  `effective_dcv/ocv/dmcv_for` take optional `against=` / `combat_type=`;
  omitting them returns exactly the previous behaviour.
- **`kirby_combat/sense_penalties.py`** — owns that rule, the
  Targeting/Nontargeting distinction, and the Nontargeting PER Roll that
  mitigates it (a Half Phase Action, expiring at the holder's next Phase via
  a driver call, following `HeldAction`'s precedent).
- **Darkness (`actions/darkness.py`, 6E1 p.188)** — an Attack Roll against
  DCV 3 places a field that is impenetrable, not merely harder to see
  through; Nightvision does not help. Converges on the same CV predicate as
  Flash rather than reimplementing it. One zone per Sense Group.
- **Images (`actions/images.py`, 6E1 p.238-239)** — placement at DCV 3,
  Line-Of-Sight perception, and disbelief tracked PER OBSERVER. A spotted
  Image does not disappear. Built by composing existing primitives against a
  point, so a Sight Image is correctly imperceptible inside a Sight Darkness
  with no special case.
- **Presence Attack consequences (6E2 p.138-139)** — a landed PA now costs
  the target something. Five tiers with `yields` / `half_phase` /
  `no_action` / DCV factor, held forward via `PresenceApplied` /
  `PresenceFaded` and folded in `session/effects.py`. `IN_COMBAT_DICE_MODIFIER`
  and `STUNNED_IMMUNE_REASON` moved in from a consumer.
- **A public API.** `__all__` went from 3 names to 80, covering the whole
  measured consumer surface, pinned by `tests/test_public_api.py`. Purely
  additive: every deep import path still works.
- **`examples/raw_orion.py`** — 6E2 p.9's worked example, asserted.
- Attribution for **Bill Bame**, whose work the dice roller is based on in
  part. It was missing entirely.

### Fixed
- `Flash.modifiers` reported a blinded character after a Flash to ANY Sense
  Group, including Hearing. 6E2 p.9 counts only TARGETING Senses. Superseded
  rather than deleted; the new predicate reads the character's real senses.
- Presence Attack durations were 12/24/36/48/60 segments, preserving only
  the book's ordering. 6E2 p.18 gives a Turn as 12 seconds and 12 Segments,
  so they convert exactly: 12/60/300/1200/3600 — up to 60x longer.
- `perception.per_roll_target` raised `AttributeError` for any
  `StatBlockCombatant`, having read `observer.hero` unconditionally.
- The inability-to-sense rule silently did nothing for `StatBlockCombatant`,
  which has no `senses()` — i.e. for every example script and much of the
  suite. Now falls back to 6E2 p.9's normal human.
- `_fold_cv_factors`'s "a 0.0 factor applies last" branch had no producer and
  was untested by construction. It now has two.

### Notes
- **0.4.0, 0.5.0 and 0.6.0 have no entries in this file.** They shipped
  without them; the gap is recorded rather than reconstructed from memory.
  0.6.0 was published by local twine rather than by tag, so the `v0.6.0` tag
  does not mark its contents.


## 0.3.0 — 2026-04-25

Phase 2 Plan 2 (engine advanced). Tier-4 parallel systems for mental
combat, vehicles, mass combat, breakables, presence attacks, GM tooling
engine layer, and full session serialization round-trip.

### Added
- Mental combat pipeline (OMCV vs DMCV, no range/LoS gating per 6E1 p105)
- Mind Control with degree ladder (ego_push / simple / contrary / violent)
  and EGO Roll breakout per 6E1 p101
- Telepathy with degree ladder (surface_thoughts / specific_memories /
  deep_thoughts / subconscious) and mental-awareness gating per 6E1 p116
- Mental Illusion with degree ladder + disbelief mechanics per 6E1 p109
- Mental Blast (STUN-only, vs Mental Defense, no BODY/KB) per 6E1 p105
- Mental Entangle (Works Against EGO + Mental Paralysis variant)
  with EGO-based escape
- Vehicles (Combatant subtype, HDC-shaped) with size, movement_inches,
  passengers, capacity-by-size table
- Passenger mechanics: cover from vehicle, firing ports, shared fate on
  vehicle destruction, rescue from crashed vehicle
- Ramming (extreme move-through): DC = round(SIZE * v / 12); +1 DC at
  >60 m/seg; attacker takes half DC self-damage per 6E Vehicles p33
- Driving rolls and maneuvers (STRAIGHT/SHARP_TURN/SWERVE/BOOTLEG_TURN/
  BARREL_ROLL); terrain and velocity modifiers
- Mass combat: Unit (pack-of-N), morale ladder
  (FRESH/STEADY/SHAKEN/ROUTING/BROKEN), aggregate damage / count loss,
  25%-casualty morale check
- Aggregate resolution: attack_vs_unit, aoe_vs_unit, attack_vs_individual,
  unit_attack_dc_bonus
- Breakables: ObjectCombatant with material defaults
  (paper/glass/wood/stone/metal/steel/concrete) and hdc_source_xml field
- Structure integrity cascade: load-bearing destruction propagates via
  StructuralGraph; combatants on collapsed surfaces flagged for falling
- Presence attacks: PRE/5 base dice + situational bonus, less PRE Defense;
  effects ladder (no_effect / hesitation / impressed / fear / cower)
  per 6E2 p139
- GM tooling engine layer:
  - Tier 1 overrides (stun adjust, status apply) — no justification
  - Tier 2 overrides (dice override, retroactive abort) — justification REQUIRED
  - Tier 3 overrides (spawn/despawn, scene mutation) — justification REQUIRED
- GM attack-on-behalf-of mechanics (NPC actions or absent-PC actions
  authored by the GM, flowing through normal pipeline)
- Combatant spawn/despawn mid-session via Tier 3 GMOverride; spawning in
  an active segment skips the immediate phase
- Serialization: to_dict (JSON-safe with __type__ discriminator) and
  from_dict (type-dispatched, subclass-preserving) with round-trip parity
  tests (representative events, every CombatEvent subclass, hypothesis
  property test on Combatant, complex Scene, Vehicle with passengers,
  Unit with morale Enum)

### HDC round-trip compatibility
- Vehicle, ObjectCombatant carry HDC-source-preserving fields for Plan 3
  import/export. Vehicle's field shape mirrors HDC vehicle XML (NAME,
  SIZE, BODY, DEF, PD, ED, STUN, SPD, DEX, STR, MOVEMENT).

### Fixed
- `from_dict` now skips `init=False` fields (events have init=False `kind`
  Literal) and resolves forward-ref string field types via the type
  registry (handles `Unit.morale -> UnitMorale` enum coercion).

### Tests
- 569 passing (up from 450 at end of Plan 1)
- 96% line coverage across `kirby_combat/`
- All new subsystems >85% (most >93%)

## 0.2.0 — 2026-04-25

Phase 2 Plan 1 (engine foundation). RAW-verified against the Codex 6E
corpus; see `feat:` and `fix:` commits for per-rule citations.

### Added
- `CombatSession` state machine with per-action event log and rewind
- `DiceRoller` protocol + `RandomRoller` (default) + `FakeRoller` (tests)
- SPD chart + Timeline with DEX/EGO-tiebroken acting order
- Reactive defenses: Dodge, Block, Abort
- Tactical modifiers: Haymaker, Set, Brace, Dive for Cover, Pulling Punch, Held Action
- Movement base + Running, Leaping, Flight, Swimming, Teleportation, Tunneling
- Move-By, Move-Through, Grab, Throw
- Multiple Attack, Sweep, Rapid Fire, Autofire, Area of Effect
- Scene data model (3D geometry, terrain, walls, hazards)
- Falling with support check, 1d6/2m formula, landing on intermediate surfaces
- Cover resolution from walls + surfaces
- Line-of-sight gating for ranged attacks (with Indirect carve-out)
- Hazard triggers and environmental events
- Recovery (Phase 12, post-12, Full Recovery)
- Adjustment powers: Aid, Drain, Transfer, Suppress, Absorption with fade
- Entangle + casual/full STR escape
- Flash + per-phase sense-group recovery
- Persistent-effect derivation in `session/effects.py` (Adjustment / Entangle / Flash)
- Martial Arts with the 6E maneuver table (16 entries from 6E2 p93)
- Trigger power activation (event predicate + charges + recharge)
- Held Action release polish (predicate-driven release, in-place resolution, next-phase expiry)
- AoE + Scene integration (wall-blocking, Indirect bypass, hazard-along-path triggers)

### Changed
- Dice rolling: engine now rolls by default via `DiceRoller` protocol;
  tests inject `FakeRoller`. Reverses Phase 1 Decision #4.

### Fixed (RAW alignment per Codex audit, 2026-04-25)
- Killing Attack STUN multiplier corrected from 1d6 to ½d6 per 6E2 p100
- Knockback formula rewritten per 6E2 p116-118 (2d6 vs BODY, KB resistance
  on meters, surface-aware impact damage)
- Move-By damage uses (STR/2) + (vel/10)d6 per 6E2 p72
- Move-By/Through attacker self-damage fractions (1/3, 1/2, full) per 6E2 p72
- Block resolves vs attacker's OCV (not opposed margin) per 6E2 p59
- Autofire: single-target one-roll-margin/2-hits + multi-target line penalty
  per 6E2 p44
- Grab requires Attack Roll at -1 OCV per 6E2 p67
- Pulling A Punch: -1 OCV per 5 DCs pulled, halves BODY only per 6E2 p89
- Throw distance via 6E1 STR/THROWING TABLE
- Dive for Cover: ½ DCV prone at destination per 6E2 p87, with -1/2m
  distance penalty
- Brace: +2 OCV that only offsets Range Modifier per 6E2 p62
- Body Shot OCV penalty -1 per 6E1 p465
- Cover OCV mapping per 6E2 p45 §BEHIND COVER MODIFIERS (6 buckets)
- Flash Ranged attacks at 0 OCV per 6E2 p127
- Move-Through OCV divisor /10 in 6E (was 5E /5)
- Entangle modifiers: 0 DCV / ½ OCV per Dorman/6E2 (not -2 each)

### Tests
- 450 passing (up from 107 at end of Phase 1)
- 96% coverage on `session/`, `scene/`, `resolution/` combined

### Unchanged
- Phase 1 attack pipeline (to-hit, damage, defense, knockback, status). The
  107 Phase-1 tests remain green throughout the Phase 2 work.

## 0.1.0 — Phase 1
Initial attack resolution engine.
