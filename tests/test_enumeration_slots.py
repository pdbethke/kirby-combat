"""Task 7: per-slot distinct attack actions + AVAD bypass labels.

Two Multipower slots with the SAME xmlid (ENERGYBLAST) but distinct
slot_ids must produce TWO distinct action_ids — one must carry an NND
(AVAD) label in its summary.

No DB, no Ollama — pure function, self-contained stub actors.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from unittest.mock import PropertyMock, patch

from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import AttackPower

from kirby_combat.enumeration import enumerate_actions


# Synthetic powers still need identities: kirby indexes on ids, so a stub
# without one is not modelling a real power. Mirrors the engine, which
# assigns from a counter when the source supplies no ID.
_STUB_IDS = itertools.count(9_000_001)



# ── shared stub helpers (same pattern as test_action_enumeration.py) ─────────


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


def _bare_combatant(*, id: str, name: str = "") -> HeroCombatant:
    """Minimal combatant with no attack powers and no skills."""
    chars = {
        "STR": 20, "DEX": 15, "CON": 15, "INT": 15, "EGO": 12, "PRE": 15,
        "OCV": 8, "DCV": 8, "OMCV": 3, "DMCV": 3, "SPD": 4,
        "PD": 10, "ED": 10, "REC": 5, "END": 40, "BODY": 12, "STUN": 40,
        "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
    }
    hero = _StubHero(name=name or id, _char_values=chars)
    return HeroCombatant(
        id=id, hero=hero,  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=40, current_body=12, current_end=40),
        knockback_resistance=0,
    )


def _mp_energy_blast(
    slot_id: str,
    dice: int = 8,
    avad: bool = False,
    avad_defense: str = "",
) -> AttackPower:
    """One ENERGYBLAST slot in a Multipower (same xmlid, distinct slot_id)."""
    return AttackPower(
        xmlid="ENERGYBLAST",
        name="Energy Blast",  # intentionally the same name for both slots
        damage_dice=dice,
        half_die=False,
        plus_one=False,
        damage_type="normal",
        defense_type="ed",
        range_m=60.0,
        uses_str=False,
        str_min=0,
        armor_piercing=0,
        penetrating=0,
        increased_stun_mult=0,
        framework_xmlid="MULTIPOWER",
        slot_id=slot_id,
        avad=avad,
        avad_defense=avad_defense,
    )


def _actor_with_mp_slots(slots: list[AttackPower]) -> HeroCombatant:
    """Return a HeroCombatant whose `.attacks` property yields `slots`.

    We override `.attacks` via PropertyMock so the test controls the
    exact AttackPower instances — including framework_xmlid / slot_id /
    avad — without needing to replicate the engine's _build_attack_power
    logic for framework powers.
    """
    actor = _bare_combatant(id="helios", name="Helios")
    with patch.object(
        type(actor), "attacks", new_callable=PropertyMock, return_value=slots
    ):
        # Patch must be active when enumerate_actions reads actor.attacks.
        # We capture it via a closure by returning a wrapped version.
        pass  # can't return here; build the wrapper below
    # Subclass approach: simpler, keeps the patch alive for the test's lifetime.
    # We build an ephemeral subclass that overrides the property.
    _slots = slots

    class _PatchedCombatant(type(actor)):
        @property  # type: ignore[override]
        def attacks(self) -> list[AttackPower]:  # type: ignore[override]
            return _slots

    # Re-create actor as an instance of the patched subclass.
    patched = _PatchedCombatant(
        id=actor.id,
        hero=actor.hero,  # type: ignore[arg-type]
        state=actor.state,
        knockback_resistance=actor.knockback_resistance,
    )
    return patched


# ── fixtures ──────────────────────────────────────────────────────────────────

SLOT_NORMAL = _mp_energy_blast(slot_id="SLOT_NORMAL_8d6", dice=8)
SLOT_AVAD = _mp_energy_blast(
    slot_id="SLOT_AVAD_6d6",
    dice=6,
    avad=True,
    avad_defense="Power Defense",
)


def _make_scene() -> tuple[HeroCombatant, HeroCombatant]:
    actor = _actor_with_mp_slots([SLOT_NORMAL, SLOT_AVAD])
    enemy = _bare_combatant(id="gorgon", name="Gorgon")
    return actor, enemy


# ── tests ─────────────────────────────────────────────────────────────────────


def test_two_same_xmlid_slots_yield_two_distinct_actions() -> None:
    """Two MP slots with the same xmlid (ENERGYBLAST) but distinct slot_ids
    must produce two distinct action_ids — no collision."""
    actor, enemy = _make_scene()
    actions = enumerate_actions(actor, [enemy])
    atk_ids = [a.action_id for a in actions if a.kind == "attack"]

    assert len(set(atk_ids)) == len(atk_ids), (
        f"action_id collision detected: {atk_ids}"
    )
    # Both slots must produce an offer (one per slot). Identified by the
    # slot's own id — the shared xmlid is a type and names neither of them.
    assert len(atk_ids) >= 2, f"Expected ≥2 attack actions, got: {atk_ids}"
    assert not any("ENERGYBLAST" in i.upper() for i in atk_ids), (
        f"the shared xmlid must not appear in a token: {atk_ids}"
    )


def test_avad_slot_summary_flags_bypass() -> None:
    """The AVAD slot's summary must carry 'NND' and 'bypass' so the LLM
    knows it ignores normal PD/ED."""
    actor, enemy = _make_scene()
    actions = enumerate_actions(actor, [enemy])
    avad_actions = [
        a for a in actions
        if a.kind == "attack" and "NND" in (a.summary or "")
    ]
    assert avad_actions, "No attack action carries 'NND' in its summary"
    assert "bypass" in avad_actions[0].summary.lower(), (
        f"Expected 'bypass' in NND summary, got: {avad_actions[0].summary!r}"
    )


def test_a_plain_power_without_an_identity_is_refused() -> None:
    """There is no "old format" left to fall back to.

    A plain top-level power used to be keyed ``attack:{enemy}:{xmlid}:{pname}``.
    That is the keying that made 630 corpus objects share a token while
    reporting success, so a view arriving without an id is now refused rather
    than silently given an ambiguous name. Every real view carries one.
    """
    import pytest

    # Build an actor with a plain top-level power (no framework_xmlid).
    plain_ap = AttackPower(
        xmlid="ENERGYBLAST", name="Fire Bolt",
        damage_dice=8, half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed",
        range_m=60.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        # framework_xmlid="" (default), slot_id="" (default)
    )
    actor = _actor_with_mp_slots([plain_ap])
    enemy = _bare_combatant(id="bob", name="Bob")
    with pytest.raises(ValueError, match="carries no id"):
        enumerate_actions(actor, [enemy])
