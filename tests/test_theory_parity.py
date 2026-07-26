"""Implementation-vs-reference parity (DESIGN §11).

The V1 engine (grip_mcp.theory, line-of-fifths formulation) and the
reference script (tools/reference/refengine.py, letter-table formulation)
share only the frozen quality table. These tests pin their agreement on
every fixture and across randomized inputs — full §7.4 field equality
except `reading` (presentation prose is each engine's own).
"""

import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import refengine as REF
from grip_mcp import theory as T

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ALL_FIXTURES = {
    **json.loads((FIXTURE_DIR / "set_a.json").read_text()),
    **json.loads((FIXTURE_DIR / "set_b.json").read_text()),
}

PARITY_FIELDS = (
    "name", "root", "quality", "bass", "inversion",
    "intervals_from_root", "missing", "pitches",
)


def strip(c):
    out = {k: c[k] for k in PARITY_FIELDS}
    if "r0_pass" in c:
        out["r0_pass"] = c["r0_pass"]
    return out


@pytest.mark.parametrize("fname", sorted(ALL_FIXTURES))
def test_fixture_parity(fname):
    fx = ALL_FIXTURES[fname]["result"]
    inp = fx["input"]
    tuning = inp["tuning"]  # fixtures store resolved pitch lists
    got = T.identify(inp["strings"], tuning, inp["context_key"])
    assert [strip(c) for c in got["candidates"]] == [
        strip(c) for c in fx["candidates"]
    ]
    assert got["decided_at"] == fx["decided_at"]
    assert got["midi"] == fx["midi"]
    assert got["mode"] == fx["mode"]
    if not fx["candidates"]:
        assert got["pitch_report"]["pitches"] == fx["pitch_report"]["pitches"]
    for c in got["candidates"]:
        assert c["reading"]  # non-empty; prose is the engine's own


# --- randomized cross-engine equivalence ------------------------------------

rng = random.Random(4611)
CASES = [
    [rng.randint(40, 76) for _ in range(rng.randint(2, 6))]
    for _ in range(200)
]
KEYS = [None, "e-minor", "c#-major", "db-major", "g-major", "f-minor",
        "b-minor", "eb-major"]


def midis_to_input(midis):
    tuning = []
    for m in sorted(midis):
        sp = REF.spell_canonical(m % 12)
        tuning.append(REF.pitch_name(sp, m))
    return [0] * len(midis), tuning


@pytest.mark.parametrize("i", range(len(CASES)))
def test_random_parity(i):
    midis = CASES[i]
    context = KEYS[i % len(KEYS)]
    strings, tuning = midis_to_input(midis)
    ref = REF.identify(strings, tuning, context)
    got = T.identify(strings, tuning, context)
    if len({m % 12 for m in midis}) < 2:
        assert got["candidates"] == [] == ref["candidates"]
        assert got["pitch_report"]["pitches"] == ref["pitch_report"]["pitches"]
        return
    assert [strip(c) for c in got["candidates"]] == [
        strip(c) for c in ref["candidates"]
    ]
    assert got["decided_at"] == ref["decided_at"]


# --- chosen resolution parity ------------------------------------------------

PROBES = [
    ("q", "Bsus4"), ("q", "Bsus"), ("q", "Gm"), ("q", "F#q4"),
    ("q", "F♯q4"), ("q", "Gbq4"), ("q", "Esus2/F#"), ("q", "B7"),
    ("gm-1", "Gm"), ("gm-1", "Gm/A#"), ("gm-1", "Bb6"),
    ("b5", "B5"), ("b5", "Bsus"), ("b5", "Bm"), ("b5", "B"),
    ("cdim-gb", "Cdim/Gb"), ("cdim-gb", "Cdim"), ("cdim-gb", "Cdim/F#"),
    ("dadgad-open", "Dsus"), ("dadgad-open", "Aq4"),
]


@pytest.mark.parametrize("fname,probe", PROBES)
def test_resolution_parity(fname, probe):
    cands = ALL_FIXTURES[fname]["result"]["candidates"]
    ref = REF.resolve_chosen(probe, cands)
    got = T.resolve_chosen(probe, cands)
    assert got == ref


def test_covariant_parity_cdim():
    old = ALL_FIXTURES["ddim-ab"]["result"]
    new = ALL_FIXTURES["cdim-gb"]["result"]
    got = T.covariant_chosen(old["candidates"], "Ddim/Ab",
                             new["candidates"], 10)
    assert got == "Cdim/Gb"
    assert got == REF.covariant_chosen(old, "Ddim/Ab", new, 10)


# --- engine constants ---------------------------------------------------------

def test_engine_version_and_table():
    assert T.ENGINE_VERSION == "1.0.0"
    assert T.table_version() == "1.0.0"


def test_input_contract():
    with pytest.raises(T.TheoryError):
        T.identify([None] * 6, ["E2", "A2", "D3", "G3", "B3", "E4"])
    with pytest.raises(T.TheoryError, match="5"):
        T.identify([0] * 5, ["E2", "A2", "D3", "G3", "B3", "E4"])
    with pytest.raises(T.TheoryError):
        T.identify([-1, 0], ["E2", "A2"])


# --- the A5.1 overflow corner (regression for the parity-found gap) ---------

def test_overflow_fallback_dim7_on_fb_respelling():
    """In db-major, PC 4 respells Fb; dim7 rooted there would need Ebbb.
    The candidate's root must fall back to canonical E — in both engines,
    identically, ranking included."""
    midis = [64, 67, 70, 73]  # {E, G, Bb, C#(Db)} = dim7 rotations
    strings, tuning = midis_to_input(midis)
    ref = REF.identify(strings, tuning, "db-major")
    got = T.identify(strings, tuning, "db-major")
    assert [strip(c) for c in got["candidates"]] == [
        strip(c) for c in ref["candidates"]
    ]
    e_rooted = [c for c in got["candidates"] if c["quality"] == "dim7"
                and c["root"] in ("E", "Fb")]
    assert e_rooted and all(c["root"] == "E" for c in e_rooted)


def test_overflow_fallback_aug_on_bs_respelling():
    """In c#-major, PC 0 respells B#; aug rooted there would need F####.
    Root falls back to canonical C."""
    midis = [60, 64, 68]  # {C, E, G#}
    strings, tuning = midis_to_input(midis)
    ref = REF.identify(strings, tuning, "c#-major")
    got = T.identify(strings, tuning, "c#-major")
    assert [strip(c) for c in got["candidates"]] == [
        strip(c) for c in ref["candidates"]
    ]
    pc0_aug = [c for c in got["candidates"]
               if c["quality"] == "aug" and c["root"] in ("C", "B#")]
    assert pc0_aug and all(c["root"] == "C" for c in pc0_aug)  # not B#
