"""Shared test fixtures for kirby-combat."""
import pytest

from kirby_combat.models import AttackPower, DefenseItem
from fixtures.synthetic_hero import synthetic_combatant
from dataclasses import replace
from tests.templates import PLAIN


@pytest.fixture
def superhero_template():
    return replace(PLAIN, name="Test Superheroic")


@pytest.fixture
def blaster():
    return synthetic_combatant(
        id="blaster", name="Blaster",
        ocv=8, dcv=7, omcv=5, dmcv=5,
        spd=6, dex=26, ego=15, str_=20, con=25, pre=20, rec=10,
        pd=10, ed=15, rpd=5, red=10, md=5,
        power_defense=0, flash_defense=0,
        max_stun=50, max_body=15, max_end=50,
        current_stun=50, current_body=15, current_end=50,
        attacks=[
            AttackPower(
                xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
            AttackPower(
                xmlid="RKA", name="Killing Blast", damage_dice=3,
                half_die=False, plus_one=True,
                damage_type="killing", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
        defenses=[DefenseItem(name="Force Field", pd=5, ed=5, rpd=5, red=5)],
    )


@pytest.fixture
def brick():
    return synthetic_combatant(
        id="brick", name="Brick",
        ocv=6, dcv=4, omcv=0, dmcv=0,
        spd=4, dex=18, ego=10, str_=60, con=30, pre=20, rec=15,
        pd=25, ed=15, rpd=15, red=5, md=0,
        power_defense=0, flash_defense=0,
        max_stun=60, max_body=20, max_end=60,
        current_stun=60, current_body=20, current_end=60,
        knockback_resistance=10,
    )


# ---------------------------------------------------------------------------
# REPLAY PARITY SWEEP (two-databases spec §6 R1). `--replay-parity=<file>`
# checks, after EVERY `run_phase` any test makes, that the fight rebuilt from
# its own log is the fight that ran (`kirby_combat.session.parity`), and
# writes each divergence to <file> as JSON lines. Off unless asked for: it
# rebuilds the whole fight every Phase.
# ---------------------------------------------------------------------------

_PARITY: dict = {"path": None, "test": None, "exempt": False, "found": 0}


def pytest_addoption(parser):
    parser.addoption("--replay-parity", default=None, metavar="FILE",
                     help="record replay-parity divergences after every run_phase")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "state_set_by_hand(reason): the test changes the fight's state outside "
        "its log (setting STUN, adding a wall mid-fight), so the replay-parity "
        "sweep cannot hold it to parity. The reason says what it sets.")
    path = config.getoption("--replay-parity")
    if not path:
        return
    import json

    import kirby_combat
    import kirby_combat.loop
    import kirby_combat.loop.run as run_mod
    from kirby_combat.session.parity import divergence

    _PARITY["path"] = path
    open(path, "w").close()
    original = run_mod.run_phase

    import functools

    @functools.wraps(original)  # so `inspect.getsource(run_phase)` still reads the engine's
    def checked(encounter, chooser, **kw):
        result = original(encounter, chooser, **kw)
        if _PARITY["exempt"]:
            return result
        try:
            diffs = divergence(result.session)
        except Exception as exc:  # a rebuild that cannot even run is a finding
            diffs = [f"REBUILD RAISED {type(exc).__name__}: {exc}"]
        if diffs:
            last = result.session.event_log[-1].kind if result.session.event_log else None
            _PARITY["found"] += 1
            with open(_PARITY["path"], "a") as fh:
                fh.write(json.dumps({
                    "test": _PARITY["test"], "last_event": last,
                    "phase_kind": result.kind,
                    "diffs": [str(d) for d in diffs[:25]],
                    "n": len(diffs),
                }, default=str) + "\n")
        return result

    run_mod.run_phase = checked
    kirby_combat.loop.run_phase = checked
    kirby_combat.run_phase = checked


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _PARITY["test"] = item.nodeid
    _PARITY["exempt"] = item.get_closest_marker("state_set_by_hand") is not None


def pytest_sessionfinish(session, exitstatus):
    """The sweep is a GATE: any divergence fails the run."""
    if _PARITY["path"] and _PARITY["found"]:
        session.exitstatus = 1
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            tr.write_line(f"REPLAY PARITY: {_PARITY['found']} divergence(s), "
                          f"see {_PARITY['path']}", red=True)
