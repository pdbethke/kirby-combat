"""The engine has a front door, and this is its contract.

`__all__` is the supported surface. Anything in it is versioned and may not
move or vanish without a deliberate decision; anything NOT in it is internal
and may be reorganised freely.

**Why this file exists.** Measured 2026-08-28: `__all__` held THREE names
(`Campaign`, `Encounter`, `World`) while kirby-api imported **69 names from
30 modules**, nearly all two or three levels deep — plus five underscore-
prefixed privates. The published surface was 3 and the real coupling surface
was 74, none of which anyone chose. The consequence was that any internal
refactor became a cross-repo break, and every private a consumer reached had
quietly frozen.

`REQUIRED_BY_CONSUMERS` below is that measured list, minus the place and
geometry names bound for `kirby-world`. It is not a wish list: every name in
it is one a real consumer imports today. The test that it is a subset of
`__all__` is what stops the front door drifting behind the walls again.
"""

import importlib

import kirby_combat


#: Names a consumer must be able to reach from the top level. Measured from
#: kirby-api 2026-08-28 by AST, not by grep -- multi-line parenthesised
#: imports hid a third of it from the first pass.
REQUIRED_BY_CONSUMERS = {
    # Building and resolving an attack
    "AttackInput", "AttackPower", "DiceValues", "Combatant", "resolve_attack",
    "StrikeAction", "RangedAttackAction",
    # Combatants and their views
    "HeroCombatant", "HeroCombatState", "ObjectCombatant", "Vehicle",
    # Maneuvers
    "AreaOfEffect", "Block", "BlockResult", "Grab", "MoveBy", "MoveThrough",
    "MultipleAttack", "RapidFire", "Throw", "resolve_object_throw",
    "modifiers_for_maneuver_view",
    # The session and its log
    "CombatSession", "apply_event", "CombatEvent", "Timeline",
    "build_acting_order_for_segment",
    "AbortDeclared", "ActionDeclared", "ActionResolved", "SegmentAdvanced",
    "EnvironmentalTriggered", "GMOverride", "HeldActionDeclared",
    "HeldActionReleased", "MovementResolved", "StatusChanged",
    "make_author_combatant", "make_author_engine", "make_author_gm",
    # Perception and senses
    "perceive", "per_roll_target", "flash_groups", "darkness_groups",
    "darkness_personal_immunity", "disbelieve_image", "is_surprised",
    # Presence Attacks
    "base_pre_dice", "resolve_presence_attack",
    # Resolution helpers
    "compute_damage", "compute_defense", "scale_variable_slot_dice",
    "compute_impact_damage_dice", "ImpactTarget",
    "apply_attack_to_construct", "apply_autofire_to_construct",
    "has_line_of_sight", "gate_ranged_attack", "blocking_wall_for_shot",
    "range_penalty",
    # Rules configuration
    "CombatTemplate", "RAW_SUPERHEROIC",
    # The setting hierarchy
    "Campaign", "World", "Encounter",
    # Dice
    "RandomRoller", "DiceRoller", "FakeRoller",
    # Serialization
    "to_dict", "from_dict",
}


def test_all_is_declared_and_substantial():
    assert hasattr(kirby_combat, "__all__")
    assert len(kirby_combat.__all__) >= len(REQUIRED_BY_CONSUMERS)


def test_all_has_no_duplicates():
    assert len(kirby_combat.__all__) == len(set(kirby_combat.__all__))


def test_every_exported_name_actually_resolves():
    """An `__all__` entry that does not import is worse than no entry: it
    passes review and fails at `from kirby_combat import *`."""
    missing = [n for n in kirby_combat.__all__ if not hasattr(kirby_combat, n)]
    assert missing == [], f"declared but not importable: {missing}"


def test_the_measured_consumer_surface_is_covered():
    """The whole point. If this fails, a real consumer has to reach past the
    front door for the name it names."""
    missing = sorted(REQUIRED_BY_CONSUMERS - set(kirby_combat.__all__))
    assert missing == [], f"consumers need these but they are not exported: {missing}"


def test_no_private_name_is_exported():
    """A leading underscore in the public surface is a contradiction. The
    five privates kirby-api reaches for are a real gap, but the answer is a
    deliberate public function, never re-exporting the private."""
    private = [n for n in kirby_combat.__all__ if n.startswith("_")]
    assert private == [], f"private names in the public surface: {private}"


def test_star_import_gives_exactly_the_surface():
    ns: dict = {}
    exec("from kirby_combat import *", ns)  # noqa: S102 — that is the thing under test
    got = {k for k in ns if not k.startswith("__")}
    assert got == set(kirby_combat.__all__)


def test_place_and_geometry_operations_are_not_the_combat_surface():
    """Geometry belongs to the world, not the fight (see
    `2026-08-28-kirby-world-module-design.md`). The TYPES combat's own
    signatures take (Scene, Position) are exported because a caller cannot
    build an attack without them; the world OPERATIONS are not.

    This test is what stops the world's surface being absorbed into combat's
    before the split happens.
    """
    world_operations = {
        "movement_reach", "nearest_visible_point", "nearest_hidden_point",
        "compute_cover_level", "cover_ocv_modifier", "resolve_fall",
        "is_supported_at", "point_in_polygon_xy", "segments_intersect_xy",
        "segment_intersection_xy", "wall_height_blocks", "mode_requires_support",
        "resolve_construct_effect", "constructs_containing",
    }
    leaked = world_operations & set(kirby_combat.__all__)
    assert leaked == set(), f"world operations exported from combat: {sorted(leaked)}"


def test_deep_imports_still_work():
    """This change is ADDITIVE. Nothing is hidden, nothing is renamed, and no
    existing consumer breaks -- kirby-api is deliberately not being migrated.
    """
    for path in ("kirby_combat.scene.geometry",
                 "kirby_combat.session.events",
                 "kirby_combat.resolution.damage",
                 "kirby_combat.actions.reactive.block"):
        assert importlib.import_module(path) is not None


#: Exported, but never shown in `examples/` — the engine does not demonstrate
#: these as part of how it is meant to be used. Measured 2026-08-28: 19 of 80.
#:
#: Two different problems wear this label, and the set does not distinguish
#: them because the remedy is the same either way (look at it and decide):
#:
#: * **Symptoms.** `scale_variable_slot_dice`, `compute_impact_damage_dice`,
#:   `range_penalty`, `apply_attack_to_construct`, `apply_autofire_to_construct`,
#:   `gate_ranged_attack`, `has_line_of_sight`, `blocking_wall_for_shot` are
#:   resolution internals exported ONLY because kirby-api reaches for them. A
#:   well-behaved consumer calls `resolve_attack` and reads the result; it does
#:   not compute the damage itself. When the carve-out moves that rules math
#:   into this engine, ask again whether anything still needs them in public.
#: * **Gaps.** `to_dict` / `from_dict`, `make_author_gm`, `disbelieve_image`,
#:   `per_roll_target` and the sense-group readers are plausibly legitimate
#:   public API that simply has no worked example yet. The fix there is to
#:   write one.
UNDEMONSTRATED = {
    # symptoms of rules math in the wrong repo
    "scale_variable_slot_dice", "compute_impact_damage_dice", "range_penalty",
    "apply_attack_to_construct", "apply_autofire_to_construct",
    "gate_ranged_attack", "has_line_of_sight", "blocking_wall_for_shot",
    # gaps in the engine's own demonstrations
    "darkness_groups", "darkness_personal_immunity", "disbelieve_image",
    "flash_groups", "from_dict", "is_surprised", "make_author_gm",
    "modifiers_for_maneuver_view", "per_roll_target", "resolve_object_throw",
    "to_dict",
    # Added 2026-08-28 with the Presence-effects work. `effect_for_tier` is a
    # small lookup helper; the headline API is `PresenceEffects.apply`, which
    # is a class and therefore exempt from this check. A worked example for
    # the whole Presence ladder is OWED and would remove this entry.
    "effect_for_tier",
}


def _undemonstrated_now() -> set[str]:
    import pathlib as _p
    corpus = " ".join(
        f.read_text() for f in (_p.Path(__file__).parent.parent / "examples").glob("*.py")
    )
    # Types and classes are NAMED in signatures rather than called, so a
    # capitalised export needs no example to justify itself.
    callables = {n for n in kirby_combat.__all__ if n[:1].islower()}
    return {n for n in callables if n not in corpus}


def test_the_undemonstrated_set_never_grows():
    """A RATCHET, not a snapshot.

    The engine's public surface was derived from what kirby-api imports —
    the right way to find the names people need, and the wrong way to decide
    what the engine should VOUCH for, since kirby-api is a consumer we have
    already agreed is architecturally wrong. This test is the guard against
    that surface quietly becoming "whatever a mistaken consumer happened to
    import".

    Adding a NEW export with no example fails here. Writing an example for an
    existing one is rewarded by the sibling test below. The only way through
    is to demonstrate the thing or to argue it off the list deliberately.
    """
    grew = sorted(_undemonstrated_now() - UNDEMONSTRATED)
    assert grew == [], (
        "new exports with no example in examples/ — demonstrate them, or add "
        f"them to UNDEMONSTRATED with a reason: {grew}"
    )


def test_the_undemonstrated_set_is_not_stale():
    """The other half of the ratchet: once something IS demonstrated, it must
    leave the list, or the list stops meaning anything."""
    stale = sorted(UNDEMONSTRATED - _undemonstrated_now())
    assert stale == [], (
        "these are demonstrated in examples/ now — remove them from "
        f"UNDEMONSTRATED: {stale}"
    )
