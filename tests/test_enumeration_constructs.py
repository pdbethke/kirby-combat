"""enumerate_actions offers attack:construct for tactically-relevant destructible cover (spec §3)."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from kirby_combat.scene import Construct, Position
from kirby_combat.hero_view import HeroCombatant, HeroCombatState

from kirby_combat.enumeration import enumerate_actions


# Synthetic powers still need identities: kirby indexes on ids, so a stub
# without one is not modelling a real power. Mirrors the engine, which
# assigns from a counter when the source supplies no ID.
_STUB_IDS = itertools.count(9_000_001)



# ── stub helpers (same pattern as test_action_enumeration.py) ───────────────

@dataclass
class _StubPower:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    input_value: str | None = None
    option_id: str | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)
    id: int = field(default_factory=lambda: next(_STUB_IDS))


@dataclass
class _StubChar:
    """A characteristic object. The bare STR Strike takes its identity from
    the STR characteristic's id, so a stub hero needs real objects here."""
    xmlid: str
    id: int = field(default_factory=lambda: next(_STUB_IDS))


@dataclass
class _StubHero:
    name: str = "Test"
    template_name: str = "synthetic.Test.hdt"
    powers: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    perks: list = field(default_factory=list)
    talents: list = field(default_factory=list)
    complications: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    _char_values: dict = field(default_factory=dict)
    characteristics: list = field(default_factory=lambda: [
        _StubChar("STR"), _StubChar("DEX"), _StubChar("CON"),
    ])

    def characteristic_value(self, xmlid: str) -> int:
        return self._char_values.get(xmlid.upper(), 0)

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        """No stub hero carries a conditional (Only-In-Hero-ID) purchase,
        so the temporal value is the base value whatever ``ctx`` says.
        combat_stats() reads this instead of characteristic_value()."""
        return self.characteristic_value(xmlid)


def _combatant(
    *, id: str, name: str = "", str_: int = 20, ocv: int = 8,
    dcv: int = 8, spd: int = 4, pre: int = 15, stun: int = 40,
    body: int = 12, end_: int = 40, pd: int = 10, ed: int = 10,
    powers: list | None = None,
) -> HeroCombatant:
    chars = {
        "STR": str_, "DEX": 15, "CON": 15, "INT": 15, "EGO": 12, "PRE": pre,
        "OCV": ocv, "DCV": dcv, "OMCV": 3, "DMCV": 3, "SPD": spd,
        "PD": pd, "ED": ed, "REC": 5, "END": end_, "BODY": body, "STUN": stun,
        "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
    }
    hero = _StubHero(name=name or id, _char_values=chars, powers=powers or [])
    return HeroCombatant(
        id=id, hero=hero,  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=stun, current_body=body, current_end=end_),
        knockback_resistance=0,
    )


# ── construct fixtures ───────────────────────────────────────────────────────

def _destructible_wall() -> Construct:
    return Construct(
        obj_id="w1",
        kind="wall",
        segment=(Position(0, -5, 0), Position(0, 5, 0)),
        blocks_los=True,
        def_value=2,
        body=8,
    )


def _indestructible_zone() -> Construct:
    return Construct(obj_id="z", kind="hazard_zone")


# ── tests ────────────────────────────────────────────────────────────────────

class TestConstructEnumeration:

    def test_offers_attack_on_destructible_wall(self):
        # _StubPower drives real HeroCombatant.attacks derivation.
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        action_ids = [a.action_id for a in actions]
        assert any(aid.startswith("attack:construct:w1:") for aid in action_ids), (
            f"Expected attack:construct:w1:... in {action_ids}"
        )

    def test_construct_action_has_correct_kind_and_target(self):
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert construct_actions, "Expected at least one attack_construct action"
        ca = construct_actions[0]
        assert ca.target_id == "w1"
        assert ca.power_xmlid == "ENERGYBLAST"
        assert "DEF 2" in ca.summary
        assert "BODY 8" in ca.summary

    def test_indestructible_construct_not_offered(self):
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        zone = _indestructible_zone()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[zone],
        )
        action_ids = [a.action_id for a in actions]
        assert not any(":construct:z:" in aid for aid in action_ids), (
            f"Indestructible zone should not be offered; got {action_ids}"
        )

    def test_no_constructs_arg_behaves_as_before(self):
        """Omitting constructs= keeps existing behaviour unchanged."""
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")

        actions = enumerate_actions(actor, [enemy], has_scene=True)
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert not construct_actions, "No construct actions when constructs not passed"

    def test_no_scene_no_construct_actions(self):
        """has_scene=False suppresses construct actions even with a destructible wall."""
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=False, constructs=[wall],
        )
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert not construct_actions

    def test_only_one_offer_per_construct_and_highest_dice_chosen(self):
        """Actor has two ranged attack powers; only ONE action per construct,
        and the higher-dice power (ENERGYBLAST 8d6 > BLASTER 6d6) is chosen."""
        actor = _combatant(
            id="a", name="Shooter",
            powers=[
                _StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8),
                _StubPower(xmlid="BLASTER", name="Blaster", levels=6),
            ],
        )
        wall = _destructible_wall()
        enemy = _combatant(id="e", name="Enemy")

        actions = enumerate_actions(actor, [enemy], has_scene=True, constructs=[wall])
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert len(construct_actions) == 1, (
            f"Expected exactly 1 offer per construct, got {len(construct_actions)}"
        )
        # The higher-dice power must be the one selected.
        assert construct_actions[0].power_xmlid == "ENERGYBLAST", (
            f"Expected ENERGYBLAST (8d6) to be chosen over BLASTER (6d6), "
            f"got {construct_actions[0].power_xmlid}"
        )

    def test_mental_attack_only_actor_gets_no_construct_offer(self):
        """A mentalist whose only attack power is MENTALBLAST must NOT get an
        attack:construct offer — constructs have no Mental Defense."""
        actor = _combatant(
            id="m", name="Mentalist",
            powers=[_StubPower(xmlid="MENTALBLAST", name="Mental Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert not construct_actions, (
            f"Mentalist with only MENTALBLAST should get no attack:construct offer; "
            f"got {[a.action_id for a in construct_actions]}"
        )

    def test_mental_and_physical_actor_chooses_physical_for_construct(self):
        """When an actor has BOTH a mental attack and a physical blast, the
        physical power is chosen for the construct offer (not the mental one)."""
        actor = _combatant(
            id="m", name="Hybrid",
            powers=[
                _StubPower(xmlid="MENTALBLAST", name="Mental Blast", levels=10),
                _StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=6),
            ],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert len(construct_actions) == 1, (
            f"Expected exactly 1 construct offer, got {len(construct_actions)}"
        )
        assert construct_actions[0].power_xmlid == "ENERGYBLAST", (
            f"Expected physical ENERGYBLAST for construct, "
            f"got {construct_actions[0].power_xmlid}"
        )

    # ── Task 4: rapid-fire vs constructs ─────────────────────────────────

    def test_ranged_actor_gets_rapid_fire_construct_offer(self):
        """An actor with a ranged attack (the PR-61 rapid-fire capability
        test) gets ONE rapid_fire offer per destructible construct, with
        the same action_id format as the combatant offer."""
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        rf = [
            a for a in actions
            if a.kind == "rapid_fire" and a.target_id == "w1"
        ]
        assert len(rf) == 1, (
            f"Expected exactly one rapid_fire offer vs the wall; "
            f"got {[a.action_id for a in rf]}"
        )
        # <kind>:<construct id>:<power id>:<shots> — no xmlid in the token.
        assert rf[0].action_id.startswith("rapid_fire:w1:")
        assert rf[0].action_id.endswith(":3")
        assert "ENERGYBLAST" not in rf[0].action_id
        assert rf[0].power_xmlid == "ENERGYBLAST"
        assert rf[0]._attack_view is not None

    def test_melee_only_actor_gets_no_rapid_fire_construct_offer(self):
        """Rapid fire requires a ranged power (range_m > 0) — a melee-only
        actor still gets attack_construct (fallback) but NO rapid_fire offer."""
        actor = _combatant(
            id="b", name="Brawler",
            powers=[_StubPower(xmlid="HKA", name="Claws", levels=2)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        rf = [
            a for a in actions
            if a.kind == "rapid_fire" and a.target_id == "w1"
        ]
        assert not rf, (
            f"Melee-only actor must not get rapid_fire vs the wall; "
            f"got {[a.action_id for a in rf]}"
        )

    def test_indestructible_construct_gets_no_rapid_fire_offer(self):
        actor = _combatant(
            id="a", name="Shooter",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="e", name="Enemy")
        zone = _indestructible_zone()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[zone],
        )
        rf = [
            a for a in actions
            if a.kind == "rapid_fire" and a.target_id == "z"
        ]
        assert not rf

    def test_melee_only_actor_gets_construct_offer(self):
        """An actor with only a melee damaging power (no ranged) still gets an
        attack:construct offer — melee is the fallback when no ranged exists."""
        actor = _combatant(
            id="b", name="Brawler",
            powers=[_StubPower(xmlid="HKA", name="Claws", levels=2)],
        )
        enemy = _combatant(id="e", name="Enemy")
        wall = _destructible_wall()

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        construct_actions = [a for a in actions if a.kind == "attack_construct"]
        assert construct_actions, (
            f"Melee-only actor (HKA) should still get an attack:construct offer; "
            f"got no such action"
        )
        assert construct_actions[0].power_xmlid == "HKA"


# ── force_wall stacking guard ─────────────────────────────────────────────────

def _live_force_wall(owner_id: str) -> Construct:
    """A spawned force_wall with body > 0, owned by owner_id."""
    return Construct(
        obj_id="fw1",
        kind="force_wall",
        segment=(Position(-8, -3, 0), Position(-8, 3, 0)),
        blocks_los=True,
        blocks_movement=True,
        def_value=8,
        body=10,
        source_combatant_id=owner_id,
    )


def _destroyed_force_wall(owner_id: str) -> Construct:
    """A spawned force_wall that has been destroyed (body=0)."""
    return Construct(
        obj_id="fw2",
        kind="force_wall",
        segment=(Position(-8, -3, 0), Position(-8, 3, 0)),
        blocks_los=True,
        blocks_movement=True,
        def_value=8,
        body=0,
        source_combatant_id=owner_id,
    )


class TestForceWallStackingGuard:

    def test_offer_suppressed_while_own_wall_alive(self):
        """The actor already has a live force_wall (body > 0); must NOT get a
        second offer."""
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="FORCEWALL", name="Arcane Shield")],
        )
        enemy = _combatant(id="enemy")
        live_wall = _live_force_wall(owner_id="caster")

        offers = [
            a for a in enumerate_actions(
                actor, [enemy], has_scene=True, constructs=[live_wall],
            )
            if a.kind == "force_wall"
        ]
        assert not offers, (
            "force_wall offer must be suppressed while the actor's own wall stands; "
            f"got {[a.action_id for a in offers]}"
        )

    def test_offer_returns_when_own_wall_destroyed(self):
        """After the actor's wall is destroyed (body=0), the offer reappears."""
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="FORCEWALL", name="Arcane Shield")],
        )
        enemy = _combatant(id="enemy")
        destroyed_wall = _destroyed_force_wall(owner_id="caster")

        offers = [
            a for a in enumerate_actions(
                actor, [enemy], has_scene=True, constructs=[destroyed_wall],
            )
            if a.kind == "force_wall"
        ]
        assert len(offers) == 1, (
            "force_wall offer must reappear once the actor's wall is destroyed; "
            f"got {[a.action_id for a in offers]}"
        )

    def test_another_casters_wall_does_not_suppress_offer(self):
        """A live force_wall owned by a DIFFERENT combatant must NOT suppress
        this actor's offer."""
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="FORCEWALL", name="Arcane Shield")],
        )
        enemy = _combatant(id="enemy")
        # wall owned by 'ally', not 'caster'
        ally_wall = _live_force_wall(owner_id="ally")

        offers = [
            a for a in enumerate_actions(
                actor, [enemy], has_scene=True, constructs=[ally_wall],
            )
            if a.kind == "force_wall"
        ]
        assert len(offers) == 1, (
            "Another combatant's live force_wall must not suppress this actor's offer; "
            f"got {[a.action_id for a in offers]}"
        )


# ── own wall is not a target ──────────────────────────────────────────────────

class TestOwnWallNotATarget:
    """A combatant must never be offered attack_construct / rapid_fire
    against a wall they themselves spawned — shooting down your own Force
    Wall is self-sabotage. Authored walls (source_combatant_id None) keep
    both offers."""

    def test_own_force_wall_gets_no_attack_or_rapid_fire_offer(self):
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="enemy")
        own_wall = _live_force_wall(owner_id="caster")

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[own_wall],
        )
        offending = [
            a for a in actions
            if a.kind in ("attack_construct", "rapid_fire")
            and a.target_id == own_wall.obj_id
        ]
        assert not offending, (
            "actor must not be offered attacks on their OWN force wall; "
            f"got {[a.action_id for a in offending]}"
        )

    def test_another_casters_wall_keeps_both_offers(self):
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="enemy")
        enemy_wall = _live_force_wall(owner_id="enemy")

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[enemy_wall],
        )
        kinds = {
            a.kind for a in actions
            if a.kind in ("attack_construct", "rapid_fire")
            and a.target_id == enemy_wall.obj_id
        }
        assert kinds == {"attack_construct", "rapid_fire"}, (
            "another caster's wall must keep both construct offers; "
            f"got {[a.action_id for a in actions]}"
        )

    def test_authored_wall_unaffected_by_ownership_filter(self):
        """Authored walls carry source_combatant_id None — offers remain."""
        actor = _combatant(
            id="caster",
            powers=[_StubPower(xmlid="ENERGYBLAST", name="Energy Blast", levels=8)],
        )
        enemy = _combatant(id="enemy")
        wall = _destructible_wall()  # source_combatant_id defaults to None

        actions = enumerate_actions(
            actor, [enemy], has_scene=True, constructs=[wall],
        )
        kinds = {
            a.kind for a in actions
            if a.kind in ("attack_construct", "rapid_fire")
            and a.target_id == wall.obj_id
        }
        assert kinds == {"attack_construct", "rapid_fire"}
