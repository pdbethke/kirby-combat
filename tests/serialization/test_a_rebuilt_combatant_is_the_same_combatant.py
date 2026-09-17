"""A combatant rebuilt from its own snapshot is the same combatant.

THE DEFECT THIS PINS. kirby-api is a harness: it persists the engine's
events and rebuilds a session by replay, and it stores each STARTING
combatant as the engine's own serialized form -- ``to_dict`` out,
``from_dict`` back. ``from_dict`` rebuilds a ``HeroCombatant`` around a stub
hero with no powers, no skills, no martial arts and no equipment, and EVERY
view on that class is derived from exactly those. So a round-tripped
combatant reported nothing through any of them. Measured on the harness:
Drago's three RKAs went in and none came back, and the rebuilt fight did no
damage.

The code that was supposed to prevent that assigned two instance
attributes, ``_snapshot_override_attacks`` and
``_snapshot_override_defenses``, which nothing in the engine ever read --
and which named two of the nine views that were empty.

So this file asks the question a per-field round-trip test cannot:

1. Does the fight come out the same? Run a seeded fight to
   ``last_side_standing``; rebuild every starting combatant through
   ``from_dict(to_dict(c))``; run the same seeded fight from the rebuilt
   men; compare the event logs row for row.

2. Does the combatant come out the same? For every public view on
   ``HeroCombatant`` -- the list DERIVED from the class's own surface, not
   written out here -- the rebuilt value equals the live one, for every
   character the suite has.

Both have a negative control that runs first.
"""
from __future__ import annotations

import dataclasses
import inspect
import json

import pytest

from kirby_combat.encounter import Encounter
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import FirstLegalChooser
from kirby_combat.loop.run import run_encounter
from kirby_combat.models import AttackPower, CombatSkillLevel, DefenseItem
from kirby_combat.serialization import from_dict, to_dict
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from fixtures.synthetic_hero import synthetic_combatant

FIGHT_SEED = 5
SESSION_SEED = 7
MAX_TURNS = 8


# ---------------------------------------------------------------------------
# The cast
# ---------------------------------------------------------------------------

def _rifleman(id_: str, side: str, dex: int) -> HeroCombatant:
    """A man with a gun, some armour, a Combat Skill Level and a skill.

    Everything on him is something the rebuilt combatant has to answer for
    through a DIFFERENT property, so a fight between two of them exercises
    the attack list, the defense list, the CSLs the to-hit roll sums and
    the stat block all at once.
    """
    rifle = AttackPower(
        xmlid="RKA", name="Rifle", damage_dice=2, half_die=True,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=150.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, source_id=f"{id_}-rka",
        is_ranged=True,
    )
    vest = DefenseItem(name="Vest", rpd=3, red=3, is_resistant=True)
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=6, spd=4, dex=dex, rec=6,
        str_=15, con=18, pd=5, ed=5, rpd=3, red=3,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
        side=Side.named(side), attacks=[rifle], defenses=[vest],
        csls=[CombatSkillLevel(levels=2, applies_to="ocv", breadth="ranged")],
        skills={"STEALTH": 12},
    )


def _cast() -> list[HeroCombatant]:
    return [_rifleman("a", "blue", 23), _rifleman("b", "red", 11)]


def _rebuilt(combatants: list[HeroCombatant]) -> list[HeroCombatant]:
    """Through the wire the harness actually uses: JSON, not Python objects.

    A dict round trip alone would let a value survive as an object the
    engine handed back to itself; the harness writes `payload_jsonb`.
    """
    return [from_dict(json.loads(json.dumps(to_dict(c)))) for c in combatants]


def _fight(combatants: list[HeroCombatant]):
    session = CombatSession.create(
        id="s", combatants=combatants, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=SESSION_SEED),
    ).start()
    result = run_encounter(
        Encounter(id="e", turn=1, segment=12, sessions=[session]),
        FirstLegalChooser(), roller=RandomRoller(seed=FIGHT_SEED),
        on_unresolvable="skip", max_turns=MAX_TURNS,
    )
    return result


#: An event's identity is fresh on every run and says nothing about whether
#: two fights agree -- nor does a reference to another row's identity
#: (`declaration_event_id`). Everything else on the row does, including the
#: whole `result_payload`: that is where what was rolled, what got through
#: and who was Stunned by it live.
_IDENTITY_FIELDS = frozenset({"id", "timestamp", "author"})


def _is_identity(name: str) -> bool:
    return name in _IDENTITY_FIELDS or name.endswith("_event_id")


def _shape(event) -> tuple:
    return (event.kind, tuple(
        (f.name, repr(getattr(event, f.name)))
        for f in dataclasses.fields(event)
        if not _is_identity(f.name)
    ))


# ---------------------------------------------------------------------------
# (1) The fight
# ---------------------------------------------------------------------------

def test_the_fight_is_worth_comparing():
    """THE NEGATIVE CONTROL, first. Two logs of a fight in which nobody
    could attack are trivially identical, which is exactly the state this
    file exists to catch -- so the fight must land blows and end."""
    result = _fight(_cast())
    kinds = [e.kind for e in result.encounter.sessions[0].event_log]

    assert result.complete, f"the fight did not finish: {result.notes}"
    assert "ActionResolved" in kinds
    assert "VitalsChanged" in kinds, "nobody was hurt, so the fight proves nothing"


def test_a_rebuilt_combatant_still_has_something_to_fight_with():
    """The second negative control: the men the comparison below rebuilds
    must not come back empty. This is the assertion that fails on the
    shape this fixes -- `attacks` returned `[]`, and a combatant with no
    attacks is a legal combatant, so the fight ran and did nothing."""
    for live, rebuilt in zip(_cast(), _rebuilt(_cast())):
        assert rebuilt.attacks, f"{live.id} came back with no attacks"
        assert rebuilt.defenses, f"{live.id} came back with no defenses"
        assert rebuilt.csls, f"{live.id} came back with no Combat Skill Levels"
        assert rebuilt.side == live.side, f"{live.id} came back on no side"
        assert rebuilt.combat_stats().rpd == live.combat_stats().rpd


def test_the_same_seeded_fight_from_rebuilt_combatants_writes_the_same_log():
    """THE PROPERTY. Same seeds, same cast, one of them rebuilt from
    nothing but its snapshot -- row for row, the same fight."""
    live = _fight(_cast())
    replayed = _fight(_rebuilt(_cast()))

    assert replayed.winner == live.winner
    assert ([_shape(e) for e in replayed.encounter.sessions[0].event_log]
            == [_shape(e) for e in live.encounter.sessions[0].event_log])


def _corpus_cast() -> list[HeroCombatant]:
    """Two real authored characters, whose frameworks, martial maneuvers,
    movement modes and duplicate xmlids the synthetic cast cannot stand in
    for."""
    from tests.corpus import require_authored

    ravel = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    bokor = HeroCombatant.from_build(require_authored("Bokor"), id="bokor")
    ravel.side = Side.named("blue")
    bokor.side = Side.named("red")
    return [ravel, bokor]


def test_a_rebuilt_corpus_cast_fights():
    """The reported defect, on real characters: a rebuilt fight did no
    damage, because every man came out of the wire unarmed."""
    rebuilt = _rebuilt(_corpus_cast())
    assert all(c.attacks for c in rebuilt), "the corpus cast came back unarmed"

    result = _fight(rebuilt)
    kinds = [e.kind for e in result.encounter.sessions[0].event_log]

    assert "ActionResolved" in kinds
    assert "VitalsChanged" in kinds, "the rebuilt corpus fight did no damage"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`enumeration.enumerate_actions` reaches PAST the combatant's public "
        "surface into `actor.hero` at 21 sites -- it says so in its own "
        "comment -- and a rebuilt combatant's hero is a stub. Measured on "
        "the corpus with no scene and no enemies: Ravel's menu loses both "
        "`heal` actions and Bokor's loses a `heal` and an `aid`, because "
        "those are read straight off HEALING and AID powers rather than "
        "through a view, and no view on HeroCombatant reports them. The "
        "combatant itself round-trips -- every public view is compared "
        "below and every one of them agrees -- so this is a SECOND DOOR in "
        "the enumerator, not a gap in the snapshot, and closing it means "
        "giving the class views for the power kinds enumeration reads and "
        "moving those 21 sites onto them. Left as a strict xfail so it "
        "reports the day that lands."
    ),
)
def test_a_corpus_fight_from_rebuilt_combatants_writes_the_same_log():
    live = _fight(_corpus_cast())
    replayed = _fight(_rebuilt(_corpus_cast()))

    assert replayed.winner == live.winner
    assert ([_shape(e) for e in replayed.encounter.sessions[0].event_log]
            == [_shape(e) for e in live.encounter.sessions[0].event_log])


# ---------------------------------------------------------------------------
# (2) The combatant, view by view -- over a DERIVED list
# ---------------------------------------------------------------------------

def _public_views() -> list[str]:
    """Every public property and no-argument method on ``HeroCombatant``.

    DERIVED, NOT WRITTEN DOWN. A hand-written list of what a resolver reads
    is a list of where the property holds, and this repo has been bitten by
    that six times: the list goes stale the moment a view is added, and the
    view a snapshot forgets is precisely the one nobody thought to list.
    Reading the class's own surface means a view added tomorrow is compared
    tomorrow, and ``CombatantSnapshot.of`` has to grow with it or this
    fails.

    No-argument methods count: ``senses()``, ``movement_view()``,
    ``maneuver_view()``, ``framework_view()``, ``combat_stats()`` and
    ``skill_rolls()`` are all read by resolvers or by enumeration, and are
    methods rather than properties only by convention.
    """
    views: list[str] = []
    for name in dir(HeroCombatant):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(HeroCombatant, name)
        if isinstance(attr, property):
            views.append(name)
            continue
        if isinstance(attr, (classmethod, staticmethod)):
            continue
        if not callable(attr):
            continue
        params = list(inspect.signature(attr).parameters)
        if params == ["self"]:
            views.append(name)
    return sorted(views)


def test_the_derived_view_list_is_not_empty_or_thin():
    """The floor. A derivation that quietly found nothing would make every
    comparison below vacuous -- the failure mode of every gate that walks
    something instead of listing it."""
    views = _public_views()

    assert len(views) >= 35, views
    # The nine that were empty on a rebuilt combatant, plus the two the
    # dead `_snapshot_override_*` plumbing was aimed at. If the derivation
    # stops finding these it has broken, not improved.
    for name in ("attacks", "defenses", "csls", "senses", "movement_view",
                 "maneuver_view", "framework_view", "combat_stats",
                 "str_strike_view", "is_mentalist", "skill_rolls",
                 "has_combat_sense", "has_self_contained_breathing",
                 "can_swim", "swimming_m"):
        assert name in views, f"{name} is no longer in the derived surface"


def _read(combatant: HeroCombatant, view: str):
    value = inspect.getattr_static(type(combatant), view)
    return (getattr(combatant, view) if isinstance(value, property)
            else getattr(combatant, view)())


def _a_rich_synthetic() -> HeroCombatant:
    return _rifleman("rich", "blue", 18)


def _subjects():
    """Every combatant the suite has, live. Corpus characters skip when the
    builds are not configured; the synthetic one always runs."""
    from tests.corpus import AUTHORED, require_authored

    yield "synthetic", _a_rich_synthetic()
    for name in sorted(AUTHORED):
        yield name, HeroCombatant.from_build(require_authored(name), id=name.lower())


@pytest.mark.parametrize("name", ["synthetic", "Bokor", "PowerLad", "Ravel"])
def test_every_public_view_survives_the_round_trip(name):
    """THE PROPERTY, over the derived list and over every character the
    suite has: what the rebuilt combatant reports IS what the live one
    reported, through the same property, with no second path anywhere in
    the resolvers."""
    subjects = dict(_subjects())
    live = subjects[name]
    rebuilt = _rebuilt([live])[0]

    differ = []
    for view in _public_views():
        want = _read(live, view)
        got = _read(rebuilt, view)
        if got != want:
            differ.append(f"{view}: rebuilt {got!r} != live {want!r}")

    assert not differ, "\n".join(differ)


def test_the_view_comparison_could_actually_fail():
    """The negative control for the comparison itself: a combatant whose
    snapshot has been emptied must be REPORTED as differing. Without this,
    the test above passes if `_read` silently returns the same thing for
    everybody."""
    live = _a_rich_synthetic()
    rebuilt = _rebuilt([live])[0]
    hollowed = dataclasses.replace(
        rebuilt, snapshot=dataclasses.replace(rebuilt.snapshot, attacks=[]))

    differ = [v for v in _public_views() if _read(hollowed, v) != _read(live, v)]

    assert "attacks" in differ


def test_a_snapshot_recorded_before_the_views_existed_says_so():
    """A recording written by 0.18.0 cannot answer what a combatant fights
    with, and refuses loudly instead of rebuilding a man who does nothing.

    That is the whole shape of the defect: an empty `attacks` list is a
    legal combatant, so nothing complained."""
    payload = to_dict(_a_rich_synthetic())
    payload.pop("attacks")
    payload.pop("frameworks")

    with pytest.raises(ValueError, match="attacks"):
        from_dict(payload)
