"""kirby-combat: HERO System 6E combat engine."""
from importlib.metadata import PackageNotFoundError, version as _version

try:
    #: Read from the installed distribution rather than restated here.
    #: A hardcoded literal drifts: this said "0.3.0" while pyproject said
    #: 0.3.28 and the built wheel carried 0.3.28, so anything introspecting
    #: the version got a wrong answer -- and 0.3.28 shipped to PyPI that way.
    __version__ = _version("kirby-combat")
except PackageNotFoundError:  # not installed (e.g. a source checkout on sys.path)
    __version__ = "0.0.0+unknown"

# kirby-cost is NOT optional, and this import is what makes that true at load
# time rather than in principle.
#
# Every `from kirby_cost...` in this package is function-local -- a leftover
# from when the dependency WAS optional and was imported behind try/except.
# That left a real hole: `dependencies = ["kirby-cost>=0.4.0"]` could be wrong,
# or satisfied by a version missing the modules this package calls, and nothing
# would notice until a specific combat function ran. Measured 2026-08-25: a
# wheel pinned to kirby-cost==0.3.0, which contains no `kirby_cost.engine`
# at all, installed and imported without complaint.
#
# So resolve the load-bearing modules here, eagerly. A floor that is too low
# now fails at `import kirby_combat` with a clear ImportError, which is a
# problem someone can act on, instead of surfacing mid-fight.
from kirby_cost.engine import damage as _damage  # noqa: F401,E402
from kirby_cost.engine import rolls as _rolls  # noqa: F401,E402

# ---------------------------------------------------------------------------
# THE IMPORT SURFACE
# ---------------------------------------------------------------------------
#
# `__all__` below is the CONTRACT. A name in it is supported: it will not move,
# rename or vanish without a deliberate decision. A name NOT in it is internal,
# and the package reorganises it freely -- including moving whole sub-packages
# to other distributions, which is exactly what
# `2026-08-28-kirby-world-module-design.md` is about to do to `scene/`.
#
# Why this exists (measured 2026-08-28): this list held THREE names while
# kirby-api imported 69 from 30 modules, nearly all two or three levels deep,
# plus five underscore-prefixed privates. A published surface of 3 against a
# real coupling surface of 74 meant every internal refactor was a cross-repo
# break, and every private a consumer reached had quietly frozen. `tests/
# test_import_surface.py` holds the measured consumer list and fails if the door
# stops covering it.
#
# ADDITIVE BY DESIGN. Nothing here hides or renames anything: every deep path
# that worked before still works. kirby-api is deliberately not being migrated
# (PeterB: "dont delete it - just stop worrying about it"), so this breaks
# nothing and asks nothing of it. What it changes is which path is OBVIOUS --
# when the front door is this visible, "call the engine" stops competing with
# "reimplement the rule over here", which is the failure this platform has
# already paid for once.
#
# PROVISIONAL SUBSET -- read this before treating all 80 names as equal.
#
# This surface was DERIVED from what kirby-api imports. That is the right way
# to find the names people actually need, and the wrong way to decide what the
# engine should VOUCH for -- because kirby-api is a consumer we have already
# agreed is architecturally wrong (it holds ~5,100 lines of rules math it
# should not; see kirby/docs/superpowers/notes/2026-08-28-rules-math-stranded-
# in-api.md). Deriving a contract from a mistaken consumer risks canonising the
# mistake.
#
# Measured 2026-08-28: eight exported names have NO usage anywhere in
# `examples/` -- the engine never demonstrates them as things a caller uses:
#
#     scale_variable_slot_dice, compute_impact_damage_dice, range_penalty,
#     apply_attack_to_construct, apply_autofire_to_construct,
#     gate_ranged_attack, has_line_of_sight, blocking_wall_for_shot
#
# They are exported because kirby-api reaches for them, and several are
# resolution internals a well-behaved consumer would never touch: you call
# `resolve_attack` and read the result, you do not compute the damage yourself.
#
# They are NOT removed today -- removing them would be churn that helps nobody
# while kirby-api is set aside. They are recorded here so that when the
# carve-out moves rules math into this engine, the question gets asked again:
# does anything still need this in public, or was it only ever a symptom?
# `tests/test_import_surface.py::test_the_undemonstrated_set_never_grows` keeps the
# list honest.

# NOT exported, deliberately: the world OPERATIONS (movement_reach,
# nearest_visible_point, cover, falling, the geometry primitives). Those are
# `kirby-world`'s surface. The place TYPES (Scene, Position, Wall, ...) ARE
# exported, because this package's own signatures take them and a caller
# cannot build an attack without them; after the split they re-export from
# kirby_world, which is ordinary for a library that exposes its dependency's
# types in its own API.

from kirby_combat.campaign import Campaign  # noqa: E402
from kirby_combat.encounter import Encounter  # noqa: E402
from kirby_combat.world import World  # noqa: E402

from kirby_combat.models import (  # noqa: E402
    AttackInput, AttackPower, Combatant, DiceValues,
)
from kirby_combat.actions import (  # noqa: E402
    RangedAttackAction, StrikeAction, resolve_attack,
)
from kirby_combat.actions.area_of_effect import AreaOfEffect  # noqa: E402
from kirby_combat.actions.grab import Grab  # noqa: E402
from kirby_combat.actions.martial_arts import modifiers_for_maneuver_view  # noqa: E402
from kirby_combat.actions.move_by import MoveBy  # noqa: E402
from kirby_combat.actions.move_through import MoveThrough  # noqa: E402
from kirby_combat.actions.multiple_attack import MultipleAttack  # noqa: E402
from kirby_combat.actions.rapid_fire import RapidFire  # noqa: E402
from kirby_combat.actions.reactive.block import Block, BlockResult  # noqa: E402
from kirby_combat.actions.throw import Throw, resolve_object_throw  # noqa: E402
from kirby_combat.breakables.object_combatant import ObjectCombatant  # noqa: E402
from kirby_combat.vehicles.vehicle import Vehicle  # noqa: E402
from kirby_combat.hero_view import HeroCombatState, HeroCombatant  # noqa: E402

from kirby_combat.session import apply_event  # noqa: E402
from kirby_combat.session.combat_session import CombatSession  # noqa: E402
from kirby_combat.session.timeline import (  # noqa: E402
    Timeline, build_acting_order_for_segment,
)
from kirby_combat.session.events import (  # noqa: E402
    AbortDeclared, ActionDeclared, ActionResolved, CombatEvent,
    EnvironmentalTriggered, GMOverride, HeldActionDeclared, HeldActionReleased,
    MovementResolved, SegmentAdvanced, StatusChanged,
    make_author_combatant, make_author_engine, make_author_gm,
)

from kirby_combat.perception import (  # noqa: E402
    darkness_groups, darkness_personal_immunity, disbelieve_image,
    flash_groups, is_surprised, per_roll_target, perceive,
)
from kirby_combat.pre_attacks.presence import (  # noqa: E402
    IN_COMBAT_DICE_MODIFIER, STUNNED_IMMUNE_REASON,
    base_pre_dice, resolve_presence_attack,
)
from kirby_combat.pre_attacks.presence_effects import (  # noqa: E402
    PRESENCE_TIERS, PresenceEffects, PresenceTier, effect_for_tier,
)
from kirby_combat.resolution.damage import (  # noqa: E402
    compute_damage, scale_variable_slot_dice,
)
from kirby_combat.resolution.defense import compute_defense  # noqa: E402
from kirby_combat.resolution.knockback import (  # noqa: E402
    ImpactTarget, compute_impact_damage_dice,
)
from kirby_combat.resolution.line_of_sight import (  # noqa: E402
    blocking_wall_for_shot, gate_ranged_attack, has_line_of_sight,
)
from kirby_combat.resolution.object_damage import (  # noqa: E402
    apply_attack_to_construct, apply_autofire_to_construct,
)
from kirby_combat.tables import range_penalty  # noqa: E402
from kirby_combat.template import CombatTemplate, RAW_SUPERHEROIC  # noqa: E402
from kirby_combat.serialization import from_dict, to_dict  # noqa: E402
from kirby_combat.dice import DiceRoller, FakeRoller, RandomRoller  # noqa: E402

# Place TYPES only -- see the note above on why the operations are absent.
from kirby_combat.scene.scene import (  # noqa: E402
    AmbientConditions, Hazard, HazardEffect, Position, Scene, SceneBounds,
    Surface, Wall,
)
from kirby_combat.scene.construct import Construct, ConstructEffect  # noqa: E402

__all__ = [
    # The setting hierarchy
    "Campaign", "World", "Encounter",
    # Building and resolving an attack
    "AttackInput", "AttackPower", "Combatant", "DiceValues",
    "RangedAttackAction", "StrikeAction", "resolve_attack",
    # Combatants
    "HeroCombatant", "HeroCombatState", "ObjectCombatant", "Vehicle",
    # Maneuvers
    "AreaOfEffect", "Block", "BlockResult", "Grab", "MoveBy", "MoveThrough",
    "MultipleAttack", "RapidFire", "Throw", "modifiers_for_maneuver_view",
    "resolve_object_throw",
    # The session and its log
    "CombatSession", "Timeline", "apply_event", "build_acting_order_for_segment",
    "AbortDeclared", "ActionDeclared", "ActionResolved", "CombatEvent",
    "EnvironmentalTriggered", "GMOverride", "HeldActionDeclared",
    "HeldActionReleased", "MovementResolved", "SegmentAdvanced",
    "StatusChanged",
    "make_author_combatant", "make_author_engine", "make_author_gm",
    # Perception and senses
    "darkness_groups", "darkness_personal_immunity", "disbelieve_image",
    "flash_groups", "is_surprised", "per_roll_target", "perceive",
    # Presence Attacks
    "base_pre_dice", "resolve_presence_attack",
    "IN_COMBAT_DICE_MODIFIER", "STUNNED_IMMUNE_REASON",
    "PRESENCE_TIERS", "PresenceEffects", "PresenceTier", "effect_for_tier",
    # Resolution helpers
    "ImpactTarget", "apply_attack_to_construct", "apply_autofire_to_construct",
    "blocking_wall_for_shot", "compute_damage", "compute_defense",
    "compute_impact_damage_dice", "gate_ranged_attack", "has_line_of_sight",
    "range_penalty", "scale_variable_slot_dice",
    # Rules configuration
    "CombatTemplate", "RAW_SUPERHEROIC",
    # Dice
    "DiceRoller", "FakeRoller", "RandomRoller",
    # Serialization
    "from_dict", "to_dict",
    # Place TYPES (operations live in kirby-world)
    "AmbientConditions", "Construct", "ConstructEffect", "Hazard",
    "HazardEffect", "Position", "Scene", "SceneBounds", "Surface", "Wall",
]
