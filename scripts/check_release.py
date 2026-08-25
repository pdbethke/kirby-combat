#!/usr/bin/env python3
"""Guards a release artifact against the four ways a kirby package has shipped wrong.

Run it on `dist/` before uploading, locally or in CI:

    python scripts/check_release.py dist/

Each check exists because the failure it catches actually happened, and each
one shipped or nearly shipped a package that pip installs happily and that
breaks, or lies, on use. Exit code 1 on any failure; nothing here is advisory.

1. LICENSED CONTENT. These packages ship no Hero Games data -- no `.hdt`, no
   `.hdc`, no `.hde`. That is a licensing boundary, not a preference, and the
   only place it can be enforced is the built artifact: a stray fixture path
   in MANIFEST.in or package_data would carry one in silently.

2. DEPENDENCY FLOORS THAT DO NOT EXIST. On 2026-08-25 both kirby-combat and
   kirby-sheet declared `kirby-cost>=0.3.0` while importing modules that 0.3.0
   does not contain. pip resolves that constraint to 0.3.0 without complaint
   and hands the user a package that dies at import. So: install the built
   wheel into a clean venv with no local packages visible, and import EVERY
   submodule.

   WHAT THIS DOES NOT CATCH, stated plainly: drift at the ATTRIBUTE level. If
   a floor is too low because the code needs `TemplateData.defense` — a field
   added in a later version — every module still imports and this check passes.
   Only running the package's own suite against the installed distribution
   would catch that, and the suite needs a Hero Designer template that CI does
   not have. Treat a green run here as "the modules resolve", not "the floor
   is right".

3. VERSION DISAGREEMENT. kirby-sheet 0.2.0 shipped with
   `kirby_sheet.__version__ == "0.1.0"` while its metadata said 0.2.0 --
   pip reporting one number and the code another. kirby-combat had the same
   drift at 0.3.28. Three instances make it a pattern.

4. TAG/VERSION MISMATCH (CI only). A tag that disagrees with pyproject means
   the published version and the git history point at different code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

LICENSED_SUFFIXES = (".hdt", ".hdc", ".hde")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"ok    {msg}")


def artifact_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        return zipfile.ZipFile(path).namelist()
    return tarfile.open(path).getnames()


def check_licensed(dist: Path) -> bool:
    clean = True
    for art in sorted(dist.iterdir()):
        if art.suffix not in (".whl", ".gz"):
            continue
        bad = [n for n in artifact_names(art) if n.lower().endswith(LICENSED_SUFFIXES)]
        if bad:
            fail(f"{art.name} carries licensed content: {bad[:5]}")
            clean = False
        else:
            ok(f"{art.name}: no .hdt/.hdc/.hde")
    return clean


def wheel_metadata(wheel: Path) -> dict[str, list[str]]:
    z = zipfile.ZipFile(wheel)
    name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    meta: dict[str, list[str]] = {}
    for line in z.read(name).decode().splitlines():
        if not line or line[0].isspace():
            continue
        if ": " in line:
            k, v = line.split(": ", 1)
            meta.setdefault(k, []).append(v)
    return meta


def check_install_and_version(wheel: Path) -> bool:
    """Install into a clean venv and confirm it imports and agrees about its version.

    The venv is built WITHOUT system site packages and installed with
    --no-cache-dir, so a dependency that only resolves because it happens to
    be on this machine cannot mask a floor that is too low.
    """
    meta = wheel_metadata(wheel)
    dist_name = meta["Name"][0]
    version = meta["Version"][0]
    module = dist_name.replace("-", "_")

    with tempfile.TemporaryDirectory() as tmp:
        env_dir = Path(tmp) / "v"
        venv.create(env_dir, with_pip=True, system_site_packages=False)
        py = env_dir / "bin" / "python"
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "-q", "--no-cache-dir", str(wheel)],
            capture_output=True, text=True, cwd=tmp,
        )
        if proc.returncode != 0:
            fail(f"{dist_name} {version} does not install cleanly:\n{proc.stderr[-600:]}")
            return False

        # EVERY submodule, not just the top-level package.
        #
        # A bare `import kirby_sheet` was the first version of this check and
        # it was worthless: it passed a wheel pinned to a kirby-cost that did
        # not contain the modules the package imports, because nothing at top
        # level reached them. Walking the package forces every module-level
        # `from kirby_cost.engine.damage import ...` to actually resolve,
        # which is how a floor that is too low announces itself.
        probe = (
            "import json,importlib,pkgutil;"
            f"m=importlib.import_module({module!r});"
            "bad=[];"
            "\n"
            "for _mi in pkgutil.walk_packages(m.__path__, m.__name__ + '.'):\n"
            "    try:\n"
            "        importlib.import_module(_mi.name)\n"
            "    except Exception as e:\n"
            "        bad.append(f'{_mi.name}: {type(e).__name__}: {e}')\n"
            "from importlib.metadata import version as v\n"
            f"print(json.dumps({{'module':getattr(m,'__version__',None),'meta':v({dist_name!r}),'bad':bad}}))"
        )
        # Deliberately clear the template variable: a package must import with
        # no Hero Designer installation configured.
        env = {k: val for k, val in os.environ.items() if k != "KIRBY_COST_HDT"}
        # cwd=tmp and -P are both load-bearing, and this check was WORTHLESS
        # without them. Python puts the current directory on sys.path, so
        # running this from a package's own repo -- the normal way -- imported
        # the local source tree instead of the installed wheel. Measured
        # 2026-08-25: a wheel pinned to kirby-cost==0.3.0 passed, because the
        # probe was resolving kirby_cost from
        # /home/.../kirby-cost/kirby_cost and reporting version 0.4.0. The
        # guard was validating the working tree and calling it an artifact.
        # -P (3.11+) drops cwd from sys.path; cwd=tmp puts it somewhere with
        # nothing importable in it. Belt and braces, deliberately.
        proc = subprocess.run(
            [str(py), "-P", "-c", probe],
            capture_output=True, text=True, env=env, cwd=tmp,
        )
        if proc.returncode != 0:
            fail(f"{dist_name} {version} installs but does not import:\n{proc.stderr[-800:]}")
            return False

        got = json.loads(proc.stdout.strip().splitlines()[-1])
        if got["bad"]:
            fail(
                f"{dist_name} {version} installs but {len(got['bad'])} submodule(s) "
                f"do not import -- usually a dependency floor lower than what the "
                f"code actually needs:"
            )
            for line in got["bad"][:6]:
                print(f"        {line}")
            return False
        ok(f"{dist_name} {version}: every submodule imports, with no template configured")
        if got["module"] is None:
            fail(f"{module}.__version__ is not defined")
            return False
        if got["module"] != got["meta"]:
            fail(
                f"{module}.__version__ is {got['module']!r} but the distribution "
                f"says {got['meta']!r} -- pip and the code would report different numbers"
            )
            return False
        ok(f"{module}.__version__ agrees with the distribution metadata ({got['meta']})")
    return True


def check_tag(wheel: Path) -> bool:
    """Only meaningful in CI, where the tag is what triggered the release."""
    ref = os.environ.get("GITHUB_REF_NAME")
    if not ref:
        return True
    version = wheel_metadata(wheel)["Version"][0]
    if ref.lstrip("v") != version:
        fail(f"tag {ref!r} does not match the built version {version!r}")
        return False
    ok(f"tag {ref} matches the built version")
    return True


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not dist.is_dir():
        fail(f"{dist} is not a directory")
        return 1
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        fail(f"expected exactly one wheel in {dist}, found {len(wheels)}")
        return 1

    results = [
        check_licensed(dist),
        check_install_and_version(wheels[0]),
        check_tag(wheels[0]),
    ]
    if all(results):
        print("\nall release guards passed")
        return 0
    print("\nrelease guards FAILED -- do not upload")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
