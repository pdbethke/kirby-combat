"""Recovery resolution tests — Phase 12, post-12, Full Recovery."""
import pytest

from kirby_combat.models import Combatant
from kirby_combat.template import RAW_SUPERHEROIC
from kirby_combat.resolution.recovery import compute_recovery


def _c(
    stun: int = 30,
    body: int = 15,
    end: int = 30,
    rec: int = 5,
    max_stun: int = 30,
    max_body: int = 15,
    max_end: int = 30,
) -> Combatant:
    return Combatant(
        id="c", name="c", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=rec,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=max_stun, max_body=max_body, max_end=max_end,
        current_stun=stun, current_body=body, current_end=end,
    )


def test_phase_12_recovery_returns_rec_when_not_ko():
    c = _c(stun=20, end=10, rec=5)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "phase_12")
    assert stun_d == 5
    assert end_d == 5


def test_post_12_recovery_returns_rec_when_not_ko():
    c = _c(stun=20, end=10, rec=5)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
    assert stun_d == 5
    assert end_d == 5


def test_recovery_clamped_to_max_stun_and_end():
    c = _c(stun=28, end=29, rec=5, max_stun=30, max_end=30)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
    assert stun_d == 2         # capped at 30 - 28
    assert end_d == 1          # capped at 30 - 29


def test_ko_cannot_take_phase_12_recovery():
    c = _c(stun=-5, end=5, rec=5)     # KO'd
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "phase_12")
    assert stun_d == 0
    assert end_d == 0


def test_ko_still_gets_post_12_recovery():
    c = _c(stun=-5, end=5, rec=5)     # KO'd
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
    assert stun_d == 5                 # full REC to STUN even while KO'd
    assert end_d == 5


def test_full_recovery_restores_to_max():
    c = _c(stun=3, end=7, rec=5, max_stun=30, max_end=30)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "full_recovery")
    assert stun_d == 27        # 30 - 3
    assert end_d == 23         # 30 - 7


def test_full_recovery_from_ko_restores_to_max():
    c = _c(stun=-10, end=0, rec=5, max_stun=30, max_end=30)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "full_recovery")
    assert stun_d == 40        # 30 - (-10)
    assert end_d == 30


def test_unknown_recovery_type_raises():
    c = _c()
    with pytest.raises(ValueError, match="unknown recovery_type"):
        compute_recovery(c, RAW_SUPERHEROIC, "bogus")


def test_zero_rec_character_gets_no_recovery():
    c = _c(stun=20, end=10, rec=0)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
    assert stun_d == 0
    assert end_d == 0


# ─────────────────────────────────────────────────────────────────────────────
# HeroCombatant dual-dispatch (combatant-redesign step 2)
# ─────────────────────────────────────────────────────────────────────────────


def _hero_combatant(*, stun: int, end: int, rec: int):
    """Build a minimal HeroCombatant whose combat_stats() returns the
    given rec/max_stun/max_end, and whose state carries current values.
    Uses a stub `hero` that just exposes `characteristic_value()` returning
    fixed values keyed by xmlid — no need for a real LoadedHero.
    """
    from kirby_combat.hero_view import HeroCombatant, HeroCombatState

    char_values = {
        "STR": 10, "DEX": 10, "CON": 10, "INT": 10, "EGO": 10, "PRE": 10,
        "OCV": 3, "DCV": 3, "OMCV": 3, "DMCV": 3,
        "SPD": 4, "PD": 5, "ED": 5,
        "REC": rec,
        "END": 60,  # max_end mostly irrelevant for these tests
        "BODY": 10, "STUN": 60,
    }

    class _StubHero:
        name = "test"
        powers: list = []  # noqa: RUF012

        def characteristic_value(self, xmlid: str) -> int:
            return char_values.get(xmlid.upper(), 0)

    return HeroCombatant(
        id="test",
        hero=_StubHero(),  # type: ignore[arg-type]  # quacks like LoadedHero
        state=HeroCombatState(
            current_stun=stun,
            current_body=10,
            current_end=end,
        ),
    )


def test_hero_combatant_phase_12_normal():
    """HeroCombatant: phase_12 recovery applies REC, capped at max."""
    c = _hero_combatant(stun=10, end=20, rec=8)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "phase_12")
    assert stun_d == 8
    assert end_d == 8


def test_hero_combatant_phase_12_ko_blocked():
    """HeroCombatant: KO'd characters cannot phase_12 recover."""
    c = _hero_combatant(stun=-5, end=10, rec=5)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "phase_12")
    assert stun_d == 0
    assert end_d == 0


def test_hero_combatant_post_12_works_when_ko():
    """HeroCombatant: post_12 still applies even when KO'd."""
    c = _hero_combatant(stun=-5, end=10, rec=5)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "post_12")
    assert stun_d == 5
    assert end_d == 5


def test_hero_combatant_full_recovery_to_max():
    """HeroCombatant: full_recovery brings vitals back to max_*."""
    c = _hero_combatant(stun=10, end=15, rec=4)
    stun_d, end_d = compute_recovery(c, RAW_SUPERHEROIC, "full_recovery")
    # max_stun was 60, max_end was 60 in our stub
    assert stun_d == 50  # 60 - 10
    assert end_d == 45   # 60 - 15
