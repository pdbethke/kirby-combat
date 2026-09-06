"""Every tactic declares where it comes from, and no two collide."""
import re

from kirby_combat.tactics.base import Basis, Tactic
from kirby_combat.tactics.library import all_tactics


def test_the_catalogue_is_populated():
    assert len(all_tactics()) == 20


def test_every_tactic_is_a_tactic_with_a_name():
    for t in all_tactics():
        assert isinstance(t, Tactic)
        assert t.name, f"{type(t).__name__} has no name"


def test_names_are_unique():
    """The name is the registry key; a collision silently drops one."""
    names = [t.name for t in all_tactics()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert dupes == [], dupes


def test_every_tactic_declares_a_basis():
    """The price of a catalogue in the engine: twenty entries arrived with
    three citations. An entry with neither a citation nor a stated judgement
    is an unsourced rule wearing the engine's credibility."""
    missing = [t.name for t in all_tactics()
               if not isinstance(getattr(t, "basis", None), Basis)]
    assert missing == [], missing


def test_a_basis_says_something():
    bare = [t.name for t in all_tactics()
            if not (t.basis.mechanism or t.basis.doctrine or t.basis.judgement)]
    assert bare == [], bare


def test_citations_are_shaped_like_citations():
    """Catches a half-written citation. It CANNOT catch a wrong one, which is
    why every page here was verified against the codex rather than derived:
    6E2's printed page is its PDF page minus two, and 6E1 is not calibrated."""
    pat = re.compile(r"^6E[12] p\d{1,3}$")
    bad = []
    for t in all_tactics():
        for field in ("mechanism", "doctrine"):
            v = getattr(t.basis, field)
            if v is not None and not pat.match(v):
                bad.append(f"{t.name}.{field}={v!r}")
    assert bad == [], bad


def test_the_two_raw_tactics_are_the_ones_the_book_advises():
    """6E2 p39, "Evening The Odds", names five ways to affect a foe you
    cannot hurt. Two of them exist as tactics: Pushing (way 1) and using the
    environment (way 4). The other three -- surprise, try something
    different, use your skills -- are NOT implemented, and that gap is the
    point of recording doctrine separately from mechanism."""
    raw = {t.name for t in all_tactics() if t.basis.is_raw}
    assert raw == {"push_when_winning", "exploit_hazards"}
    for t in all_tactics():
        if t.basis.is_raw:
            assert t.basis.doctrine == "6E2 p39"
