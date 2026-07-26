"""CLI for the reference derivation engine.

Usage:
    python tools/reference/derive.py --strings "x,x,8,7,8,x" \
        [--tuning standard | --tuning "E2,A2,D3,G3,B3,E4"] \
        [--context-key e-minor] [--top N]

Prints the full identify() result as JSON. `x` (or `-`) = muted string.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import refengine


def parse_strings(s: str):
    out = []
    for tok in s.split(","):
        tok = tok.strip().lower()
        out.append(None if tok in ("x", "-", "") else int(tok))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strings", required=True)
    ap.add_argument("--tuning", default="standard")
    ap.add_argument("--context-key", default=None)
    ap.add_argument("--top", type=int, default=None,
                    help="truncate candidate list in the printout")
    args = ap.parse_args(argv)

    tuning = (
        [p.strip() for p in args.tuning.split(",")]
        if "," in args.tuning
        else args.tuning
    )
    try:
        result = refengine.identify(
            parse_strings(args.strings), tuning, args.context_key
        )
    except refengine.InputError as e:
        json.dump({"error": str(e)}, sys.stdout, indent=2)
        print()
        return 1
    if args.top is not None:
        result["truncated"] = max(0, len(result["candidates"]) - args.top)
        result["candidates"] = result["candidates"][: args.top]
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
