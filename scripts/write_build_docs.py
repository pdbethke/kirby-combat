#!/usr/bin/env python3
"""Write the suite's real-character corpus: one canonical build doc per cleared .hdc.

    KIRBY_COST_HDT=<your Main6E.hdt> python scripts/write_build_docs.py <hdc dir> <out dir>
    KIRBY_COMBAT_BUILDS=<out dir> pytest

kirby-combat reads no .hdc (tests/corpus.py), so the cleared characters reach
it as build docs written ONCE, here, by kirby-cost's own loader and writer —
`HDCLoader` then `to_build_json` — never copied from the oracle-dump .json that
sits beside each .hdc in kirby-cost's fixtures (Warp review 2026-10-20, F2).

Writes exactly the characters tests/corpus.py's AUTHORED names, and refuses
(exit 1, writing nothing) if any of their .hdc is missing: a corpus with a
character short is the run that goes green on less than it claims.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.corpus import AUTHORED  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    hdc_dir, out_dir = Path(argv[0]).expanduser(), Path(argv[1]).expanduser()
    sources = {name: hdc_dir / f"{name}.hdc" for name in sorted(AUTHORED)}
    missing = [str(p) for p in sources.values() if not p.is_file()]
    if missing:
        print(f"refused: no {', '.join(missing)}", file=sys.stderr)
        return 1

    from kirby_cost.io.build_json import to_build_json
    from kirby_cost.io.hdc_loader import HDCLoader

    loader = HDCLoader()
    docs = {name: to_build_json(loader.load_file(str(path))) for name, path in sources.items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        target = out_dir / f"{name}.json"
        target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
