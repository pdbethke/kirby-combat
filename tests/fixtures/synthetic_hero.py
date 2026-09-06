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

import dataclasses
from typing import Any

from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import AttackPower, DefenseItem


class _SyntheticHero:
    """Minimal LoadedHero stand-in for tests.

    Implements the slice of the HD model that ``hero_view._compute_stats_from_hero``
    + the legacy-shaped read properties consume:
      - ``.name``, ``.template_name``
      - ``.characteristic_value(xmlid)`` returns from a fixed dict
      - ``.temporal_characteristic(xmlid, ctx)`` returns the same fixed
        value — synthetic heroes carry no conditional purchases, so the
        activation context never changes the result
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

    def temporal_characteristic(self, xmlid: str, ctx: Any = None) -> int:
        """No synthetic hero carries a conditional (Hero-ID-limited)
        purchase, so the temporal value is always the base value
        regardless of ``ctx``."""
        return self.characteristic_value(xmlid)


@dataclasses.dataclass
class _SyntheticCombatant(HeroCombatant):
    """HeroCombatant subclass that lets tests preserve the flat
    ``attacks`` / ``defenses`` / ``is_npc`` / ``is_mentalist`` lists that
    legacy ``Combatant`` had as fields.

    The base HeroCombatant computes ``attacks`` and ``defenses`` from
    ``hero.powers``; for synthetic tests we want the test to specify them
    directly so the resolution layer sees exactly what the test constructed.

    THESE ARE REAL DATACLASS FIELDS, AND THAT IS LOAD-BEARING. They were
    plain instance attributes (``sc._explicit_attacks = ...``, set after
    construction) plus a monkeypatched ``combat_stats`` closure until
    2026-09-06. ``dataclasses.replace`` rebuilds through ``__init__`` and
    carries FIELDS ONLY, so every one of them was silently dropped the
    moment the engine replaced a combatant --- which it does on any vitals
    change. Measured against the then-current code::

        c = synthetic_combatant(..., rpd=7, attacks=[<one AttackPower>])
        d = _decrement_end(c, 3)          # an ordinary movement END spend
        d.attacks             -> []       (was [<AttackPower>])
        d.combat_stats().rpd  ->  0       (was 7)

    So a synthetic combatant that moved, or took its free Post-Segment-12
    Recovery, came out the other side with no attacks and no resistant
    defenses. No test caught it because none asserted on those AFTER a
    vitals change --- until damage application put a replace on the attack
    path, where the target's own attacks and defenses plainly still matter.

    Overriding ``__replace__`` does NOT fix this: ``dataclasses.replace``
    calls its own ``_replace`` rather than dispatching to the class's
    ``__replace__``, so the hook never fires. Fields are the fix.

    ``knockback_resistance`` is a dataclass field on the base
    ``HeroCombatant`` (not a property), so it is set via the constructor
    directly and inherited as-is.
    """

    _explicit_attacks: list = dataclasses.field(default_factory=list)
    _explicit_defenses: list = dataclasses.field(default_factory=list)
    _explicit_csls: list = dataclasses.field(default_factory=list)
    _explicit_is_npc: bool = False
    _explicit_is_mentalist: bool = False
    #: Resistant/mental/special defenses the caller asked for. The base
    #: ``_compute_stats_from_hero`` returns 0 for all of these because a
    #: synthetic hero has no defense powers to derive them from, so
    #: ``combat_stats`` below layers the requested values back on.
    _ov_rpd: int = 0
    _ov_red: int = 0
    _ov_md: int = 0
    _ov_power_defense: int = 0
    _ov_flash_defense: int = 0

    @property
    def attacks(self) -> list[AttackPower]:
        return self._explicit_attacks

    @property
    def defenses(self) -> list[DefenseItem]:
        return self._explicit_defenses

    @property
    def is_npc(self) -> bool:
        return self._explicit_is_npc

    @property
    def is_mentalist(self) -> bool:
        return self._explicit_is_mentalist

    @property
    def csls(self) -> list:
        return self._explicit_csls

    def combat_stats(self):
        """Base stats with the caller's requested defenses layered on.

        Replaces a per-instance monkeypatch (``sc.combat_stats =
        _patched_combat_stats``) that, being an instance attribute rather
        than a field, did not survive ``dataclasses.replace`` --- see the
        class docstring.
        """
        s = super().combat_stats()
        s.rpd = self._ov_rpd
        s.red = self._ov_red
        s.md = self._ov_md
        s.power_defense = self._ov_power_defense
        s.flash_defense = self._ov_flash_defense
        return s


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

    return _SyntheticCombatant(
        id=id,
        hero=hero,  # type: ignore[arg-type]  # quacks like LoadedHero
        state=state,
        knockback_resistance=int(knockback_resistance),
        # Flat-Combatant explicit lists/flags, and the defenses the base
        # `_compute_stats_from_hero` cannot derive (a synthetic hero owns no
        # defense powers). All are real fields so they survive the
        # `dataclasses.replace` the engine performs on every vitals change --
        # see _SyntheticCombatant's docstring for the defect that caused.
        _explicit_attacks=list(attacks or []),
        _explicit_defenses=list(defenses or []),
        _explicit_csls=list(csls or []),
        _explicit_is_npc=bool(is_npc),
        _explicit_is_mentalist=bool(is_mentalist),
        _ov_rpd=rpd,
        _ov_red=red,
        _ov_md=md,
        _ov_power_defense=power_defense,
        _ov_flash_defense=flash_defense,
    )
