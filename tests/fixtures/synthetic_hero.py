"""``synthetic_combatant()`` — drop-in replacement for tests that
construct a flat ``Combatant`` directly.

The combatant-redesign migration deletes ``LegacyCombatant`` in step 6.
Existing tests that build a Combatant with hand-picked stats need to
migrate to a HeroCombatant. This helper keeps the same flat-keyword
constructor signature the old class had so the migration becomes a
one-line search-and-replace per file:

    Combatant(id="x", name="X", ocv=8, dcv=8, ...)
    →
    synthetic_combatant(id="x", name="X", ocv=8, dcv=8, ...)

Internally it builds a minimal LoadedHero-shaped stub whose
``characteristic_value(xmlid)`` returns the requested int values.
combat_stats() / state / the legacy-shaped read properties on
HeroCombatant all flow through correctly.

Default values mirror Combatant's defaults so partial-arg tests
(e.g. only specifying STR + STUN) work the same way.

Limitations vs. real HeroCombatant.from_hdc():
  - ``hero.powers`` is empty by default. If the test wants attack
    powers, pass ``attacks=[...]`` (forwarded to the synthetic
    state where the legacy Combatant.attacks list lived).
  - ``hero.skills``, ``perks``, etc. are empty. Tests that read
    these probably need a real HDC fixture.
  - ``defense_view()`` returns the legacy ``defenses=[...]`` list
    verbatim (no power-walking). Plenty for unit tests.
"""
from __future__ import annotations

from typing import Any

from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import AttackPower, DefenseItem


class _SyntheticHero:
    """Minimal LoadedHero stand-in for tests.

    Implements the slice of the HD model that ``hero_view._compute_stats_from_hero``
    + the legacy-shaped read properties consume:
      - ``.name``, ``.template_name``
      - ``.characteristic_value(xmlid)`` returns from a fixed dict
      - ``.powers`` is an empty list (or a list of pre-built attack
        records the test wants surfaced via the ``attacks`` legacy field)
      - ``.skills`` / ``.perks`` / ``.talents`` / ``.complications``
        empty lists (tests that need richer data should use a real HDC fixture)
    """

    def __init__(
        self,
        *,
        name: str,
        char_values: dict[str, int],
    ) -> None:
        self.name = name
        self.template_name = "synthetic.Test.hdt"
        self._char_values = char_values
        self.powers: list = []
        self.skills: list = []
        self.perks: list = []
        self.talents: list = []
        self.complications: list = []
        self.equipment: list = []

    def characteristic_value(self, xmlid: str) -> int:
        return self._char_values.get(xmlid.upper(), 0)


class _SyntheticCombatant(HeroCombatant):
    """HeroCombatant subclass that lets tests preserve the flat
    ``attacks`` / ``defenses`` / ``is_npc`` / ``is_mentalist`` lists
    that legacy ``Combatant`` had as fields.

    The base HeroCombatant computes ``attacks`` and ``defenses`` from
    ``hero.powers``; for synthetic tests we want the test to specify
    them directly so the resolution layer sees exactly what the test
    constructed.

    ``knockback_resistance`` is a dataclass field on the base
    ``HeroCombatant`` (not a property), so it's set via the
    constructor directly and inherited as-is.
    """

    @property
    def attacks(self) -> list[AttackPower]:
        return getattr(self, "_explicit_attacks", [])

    @property
    def defenses(self) -> list[DefenseItem]:
        return getattr(self, "_explicit_defenses", [])

    @property
    def is_npc(self) -> bool:
        return getattr(self, "_explicit_is_npc", False)

    @property
    def is_mentalist(self) -> bool:
        return getattr(self, "_explicit_is_mentalist", False)

    @property
    def csls(self) -> list:
        return getattr(self, "_explicit_csls", [])


def synthetic_combatant(
    *,
    id: str,
    name: str,
    ocv: int = 3,
    dcv: int = 3,
    omcv: int = 3,
    dmcv: int = 3,
    spd: int = 2,
    dex: int = 10,
    ego: int = 10,
    int_: int = 10,
    str_: int = 10,
    con: int = 10,
    pre: int = 10,
    rec: int = 4,
    pd: int = 2,
    ed: int = 2,
    rpd: int = 0,
    red: int = 0,
    md: int = 0,
    power_defense: int = 0,
    flash_defense: int = 0,
    max_stun: int = 20,
    max_body: int = 10,
    max_end: int = 20,
    current_stun: int | None = None,
    current_body: int | None = None,
    current_end: int | None = None,
    attacks: list[AttackPower] | None = None,
    defenses: list[DefenseItem] | None = None,
    csls: list[Any] | None = None,
    is_mentalist: bool = False,
    is_npc: bool = False,
    knockback_resistance: int = 0,
) -> _SyntheticCombatant:
    """Construct a HeroCombatant with the same flat kwargs that the
    pre-migration Combatant dataclass accepted.

    Tests that did:
        c = Combatant(id="x", name="X", ocv=8, ...)

    migrate one-line to:
        c = synthetic_combatant(id="x", name="X", ocv=8, ...)
    """
    char_values = {
        "OCV": ocv, "DCV": dcv, "OMCV": omcv, "DMCV": dmcv,
        "SPD": spd, "DEX": dex, "EGO": ego, "INT": int_, "STR": str_,
        "CON": con, "PRE": pre, "REC": rec,
        "PD": pd, "ED": ed,
        "STUN": max_stun, "BODY": max_body, "END": max_end,
        # rPD / rED / MD / POWD / FLASHD aren't characteristics in 6E
        # — they come from powers. _compute_stats_from_hero walks
        # hero.powers to total them. Since synthetic has no powers,
        # we override below by constructing the state directly with
        # the wanted defenses already in the explicit list.
    }
    hero = _SyntheticHero(name=name, char_values=char_values)

    state = HeroCombatState(
        current_stun=current_stun if current_stun is not None else max_stun,
        current_body=current_body if current_body is not None else max_body,
        current_end=current_end if current_end is not None else max_end,
    )

    sc = _SyntheticCombatant(
        id=id,
        hero=hero,  # type: ignore[arg-type]  # quacks like LoadedHero
        state=state,
        knockback_resistance=int(knockback_resistance),
    )

    # Preserve the flat-Combatant explicit lists/flags
    sc._explicit_attacks = list(attacks or [])
    sc._explicit_defenses = list(defenses or [])
    sc._explicit_is_npc = bool(is_npc)
    sc._explicit_is_mentalist = bool(is_mentalist)

    # Patch combat_stats() to return rPD/rED/MD/POWD/FLASHD that the
    # caller specified (overriding the default-0 from _compute_stats_from_hero
    # since synthetic has no defense powers).
    base_compute = sc.combat_stats

    def _patched_combat_stats():
        s = base_compute()
        s.rpd = rpd
        s.red = red
        s.md = md
        s.power_defense = power_defense
        s.flash_defense = flash_defense
        return s

    sc.combat_stats = _patched_combat_stats  # type: ignore[method-assign]

    if csls is not None:
        sc._explicit_csls = list(csls)

    return sc
