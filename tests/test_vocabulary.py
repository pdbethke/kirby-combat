"""A library does not name its consumers' internals.

kirby-combat, kirby-cost, kirby-dice and kirby-terrain are standalone
packages. A comment here that names a module in a consuming application --
or worse, cites line numbers inside it -- is a leaky abstraction and a
guaranteed source of rot: those offsets were pinned against a file in
another repository that no CI here can check, and they were wrong within
weeks. Describe the ROLE ("the consumer's driver", "the chooser") and the
comment stays true for as long as the role does.

The same rule covers vendor and product names. This package models
CHOOSING -- a `chooser`, an `option`, a `situation`, a `decide()` -- and
that vocabulary is deliberately neutral about what implements the choice.
The neutrality is the better design as well as the tidier one: a scripted
chooser and any other kind are then indistinguishable to the engine, which
is exactly what lets a fight run with no dependencies at all.

A comment convention does not survive contact with a year of commits. This
does, because it fails the build. It follows the same shape as
kirby-terrain's leaf test: assert the property, then assert the assertion
could actually fail.

To permit a genuine exception, add it to ALLOW with a reason. Deliberate
and reviewable beats a silently widened pattern.
"""
import pathlib
import re
import subprocess

#: Unambiguous vendor, product and technique names. Deliberately NOT "ai":
#: `ai = AttackInput(...)` is an ordinary local in several tests, so banning
#: it would train everyone to ignore this test -- the failure mode that ends
#: with the guard deleted.
TERMS = [
    "llm", "ollama", "anthropic", "openai", "gpt", "chatgpt", "claude",
    "gemini", "mistral", "llama", "huggingface", "copilot", "bedrock",
    "medialib", "prompt",
]

#: Underscore is a word character, so `\bllm\b` does NOT match `llm_driver` --
#: the exact string this test exists to catch. These lookarounds treat any
#: non-alphanumeric as a boundary, so `llm_driver`, `LLM-driver` and `(llm)`
#: all match.
PATTERN = re.compile(
    "|".join(rf"(?<![a-z0-9]){t}(?![a-z0-9])" for t in TERMS), re.IGNORECASE
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: (path, matched term) -> why it is allowed to stay.
ALLOW: dict[tuple[str, str], str] = {
    (".gitignore", "claude"): "editor tooling directory, not a project reference",
}


def _tracked_files() -> list[str]:
    """Every file git tracks -- source, README, pyproject, CI workflows.

    Uses git rather than rglob so the scan covers exactly what is published
    and nothing that is not: no .venv, no build artefacts, no local scratch.
    """
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.split()


def _offenders() -> list[str]:
    found: list[str] = []
    here = pathlib.Path(__file__).name
    for rel in _tracked_files():
        # This file necessarily contains every banned term.
        if pathlib.Path(rel).name == here:
            continue
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable; nothing to read anyway
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in PATTERN.finditer(line):
                term = match.group(0).lower()
                if (rel, term) in ALLOW:
                    continue
                found.append(f"{rel}:{lineno}: {term!r} in {line.strip()[:80]!r}")
    return found


def test_the_published_source_names_no_inference_vocabulary() -> None:
    offenders = _offenders()
    assert offenders == [], (
        "A library must not name its consumers' internals. These "
        "references do:\n  "
        + "\n  ".join(offenders)
        + "\n\nRephrase to describe the ROLE ('the consumer's driver', 'the "
          "chooser') rather than the implementation. If a reference is "
          "genuinely necessary, add it to ALLOW with a reason."
    )


def test_the_guard_would_notice_a_leak() -> None:
    """Guards the guard.

    A word-boundary bug would make the test above pass on every input while
    appearing to work -- so assert against the specific string that motivated
    it, underscore and all.
    """
    assert PATTERN.search("see llm_driver.py for details")
    assert PATTERN.search("calls the Anthropic API")
    assert PATTERN.search("OLLAMA_BASE_URL")
    # ...and does not fire on ordinary prose or an `ai` local.
    assert not PATTERN.search("ai = AttackInput(attacker=a, target=b)")
    assert not PATTERN.search("the domain contains available terrain")


def test_the_scan_actually_reads_files() -> None:
    """A `git ls-files` that returned nothing would make the guard vacuous."""
    tracked = _tracked_files()
    assert len(tracked) > 5, tracked
    assert any(f.endswith(".py") for f in tracked)
