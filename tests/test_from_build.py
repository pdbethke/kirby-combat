"""A combatant is built from a LOADED BUILD, and from nothing else.

PeterB, 2026-09-08: *"remove ANY raw hdc loading from kirby combat"* /
*"it needs to take LoadedHero object -- always"*. The rule itself is
older (2026-07-30): characters come from the costed corpus, and HDC's
only remaining role is one-time import.

`HeroCombatant.from_hdc(path)` was the ONLY constructor this class had,
so every consumer that wanted a character had no choice but to hand the
engine a file path and re-parse HDC at runtime. The benchmark did it for
nine men every run; a demo script did it; twenty-odd tests did it. That
is not a downstream habit, it is the only door there was.

`from_hdc` was two lines of parsing followed by wrapping that already
worked on a `LoadedHero` -- which is exactly what
`kirby_cost.io.build_json.build_from_json` returns. So the door now
takes the build, and the parse belongs to whoever did the import.
"""
from __future__ import annotations

import pytest

from tests.corpus import require_template
from kirby_cost.io.build_json import build_from_json
from kirby_combat.hero_view import HeroCombatant

#: The smallest thing that is a character: a name, a template to cost
#: against, and one characteristic. Hand-written rather than exported
#: from anybody's .hdc, so this file carries no licensed content and no
#: person's creative work.
MINIMAL = {
    "name": "Probe",
    "template": "builtIn.Superheroic6E.hdt",
    "base_points": 400,
    "disad_points": 0,
    "experience": 0,
    "characteristics": [
        {"id": "1", "xmlid": "STR", "levels": 20, "base_cost": 0.0,
         "level_cost": 1.0, "level_value": 1.0, "alias": "STR"},
    ],
    "powers": [], "skills": [], "perks": [], "talents": [],
    "martial_arts": [], "disadvantages": [],
}


def test_a_combatant_is_built_from_a_loaded_build():
    require_template()
    combatant = HeroCombatant.from_build(build_from_json(MINIMAL), id="probe")
    assert combatant.id == "probe"
    assert combatant.hero.name == "Probe"


def test_the_id_defaults_to_the_name():
    require_template()
    assert HeroCombatant.from_build(build_from_json(MINIMAL)).id == "probe"


def test_vitals_are_seeded_from_the_build():
    require_template()
    """What `from_hdc` did after the parse, and the only part worth keeping."""
    c = HeroCombatant.from_build(build_from_json(MINIMAL))
    assert c.state.current_stun == c.combat_stats().max_stun
    assert c.state.current_body == c.combat_stats().max_body


def test_the_engine_cannot_be_handed_a_file_path():
    """The door is gone, not merely unused. A constructor that takes a
    path is an invitation to re-parse HDC at runtime, and this package
    must not offer one."""
    assert not hasattr(HeroCombatant, "from_hdc")


def test_no_module_in_the_package_imports_the_hdc_loader():
    """The stronger guard: nothing in kirby_combat may reach for
    `HDCLoader` at all. `LoadedHero` is fine -- that is the TYPE of the
    thing we are handed; `HDCLoader` is the act of parsing a file.

    Walked with `ast`, not grep: grep undercounts Python imports (a
    parenthesised multi-line import hides names) and OVERCOUNTS prose --
    two docstrings in this package discuss the loader by name, and a
    text match calls those defects. Only real bindings and real uses
    count.
    """
    import ast
    import pathlib

    offenders = []
    root = pathlib.Path(__file__).resolve().parent.parent / "kirby_combat"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if any(a.name == "HDCLoader" for a in node.names):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}: from {node.module} import HDCLoader")
            elif isinstance(node, ast.Import):
                if any(a.name.endswith("hdc_loader") for a in node.names):
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}: import {a.name}")
            elif isinstance(node, ast.Name) and node.id == "HDCLoader":
                offenders.append(f"{path.relative_to(root)}:{node.lineno}: uses HDCLoader")
    assert not offenders, "kirby_combat must not parse HDC:\n" + "\n".join(offenders)
