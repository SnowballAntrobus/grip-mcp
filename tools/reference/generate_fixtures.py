"""Regenerate tests/fixtures/set_a.json and set_b.json.

All fixture expectations are the reference script's reviewed output, never
hand derivations (DESIGN §11). Deterministic: same table + same engine ->
byte-identical files (asserted by the regeneration test).

Usage: python tools/reference/generate_fixtures.py [--check]
    --check: exit 1 if the on-disk fixtures differ from regeneration.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import refengine

X = None  # muted

# name -> (strings, tuning, context_key)
SET_A = {
    # The Gm/Em song the fixtures came from (DESIGN §7.3, §11).
    "gm-o":       ([3, 1, X, X, X, X], "standard", None),
    "pass":       ([5, X, X, 3, X, X], "standard", None),
    "gm-1":       ([X, X, 8, 7, 8, X], "standard", None),
    "b5":         ([X, 2, 4, X, X, X], "standard", None),
    "g-dy":       ([3, 2, X, X, X, X], "standard", None),
    "b5-over-fs": ([2, 2, X, X, X, X], "standard", None),
    "q":          ([2, 2, 2, X, X, X], "standard", None),
    "q-e-minor":  ([2, 2, 2, X, X, X], "standard", "e-minor"),
    "thumb-b5":   ([7, 9, 9, X, X, X], "standard", None),
    "b-ds":       ([X, 2, 1, X, X, X], "standard", None),
    "b-ds-e-minor": ([X, 2, 1, X, X, X], "standard", "e-minor"),
}

SET_B = {
    # Open-position folk chords.
    "folk-c":     ([X, 3, 2, 0, 1, 0], "standard", None),
    "folk-g":     ([3, 2, 0, 0, 0, 3], "standard", None),
    "folk-d":     ([X, X, 0, 2, 3, 2], "standard", None),
    "folk-em":    ([0, 2, 2, 0, 0, 0], "standard", None),
    "folk-am":    ([X, 0, 2, 2, 1, 0], "standard", None),
    # The Freddie Green shell: G7 tops, coll suppressed, rung script-asserted.
    "freddie-g7": ([3, X, 3, 4, X, X], "standard", None),
    # Drop-2 voicings.
    "drop2-cmaj7": ([X, 3, 5, 4, 5, X], "standard", None),
    "drop2-dm7":   ([X, 5, 7, 5, 6, X], "standard", None),
    # DADGAD.
    "dadgad-open": ([0, 0, 0, 0, 0, 0], "dadgad", None),
    # Xm-vs-Xdim discount ordering (R2.2).
    "am-vs-adim": ([X, 0, X, X, 1, X], "standard", None),
    # The B5 same-root tie-break (quality-order column, exercised directly).
    "b5-tiebreak": ([X, 2, 4, X, X, X], "standard", None),
    # Dyad-token sweep: every remaining token arrives with its fixture
    # (membership criterion, DESIGN §13).
    "dy-M2": ([X, 3, 0, X, X, X], "standard", None),
    "dy-A4": ([X, 3, 4, X, X, X], "standard", None),
    "dy-m6": ([X, 3, 6, X, X, X], "standard", None),
    "dy-M6": ([X, 3, 7, X, X, X], "standard", None),
    "dy-m7": ([X, 3, 8, X, X, X], "standard", None),
    "dy-M7": ([X, 3, 9, X, X, X], "standard", None),
    # Totality catch-all: the chromatic cluster nothing covers.
    "coll-cluster": ([8, 4, 0, X, X, X], "standard", None),
    # Member-stacking bass spelling (the Cdim/Gb divergence input) and its
    # transposition source (Ddim/Ab).
    "cdim-gb": ([2, 6, X, 5, X, X], "standard", None),
    "ddim-ab": ([4, X, 0, X, X, 1], "standard", None),
    # Single-distinct-PC contract: pitch report, no candidates.
    "unison-e": ([0, X, X, X, X, 0], "standard", None),
}

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def build(specs: dict) -> dict:
    out = {}
    for name, (strings, tuning, context_key) in specs.items():
        out[name] = {
            "result": refengine.identify(strings, tuning, context_key),
        }
    return out


def render(specs: dict) -> str:
    return json.dumps(build(specs), indent=2, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    ok = True
    for fname, specs in (("set_a.json", SET_A), ("set_b.json", SET_B)):
        path = FIXTURE_DIR / fname
        text = render(specs)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"STALE: {path}", file=sys.stderr)
                ok = False
            else:
                print(f"clean: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
