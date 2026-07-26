"""Three-tier `chosen` resolution tests (DESIGN §5.1, §11, APPENDIX A2),
including the named Cdim/Gb covariant-re-derivation divergence case."""

import json
from pathlib import Path

import refengine as R

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SET_A = json.loads((FIXTURE_DIR / "set_a.json").read_text())
SET_B = json.loads((FIXTURE_DIR / "set_b.json").read_text())

Q = SET_A["q"]["result"]["candidates"]
GM1 = SET_A["gm-1"]["result"]["candidates"]


# --- tier 1: exact canonical ------------------------------------------------

def test_exact_canonical_match():
    r = R.resolve_chosen("F#q4", Q)
    assert r == {"status": "resolved", "name": "F#q4", "tier": 1}


def test_exact_with_slash_bass():
    r = R.resolve_chosen("Esus2/F#", Q)
    assert r["status"] == "resolved" and r["tier"] == 1


# --- tier 2: root-PC + exact quality row ------------------------------------

def test_bsus4_on_q_resolves_tier2():
    """'Bsus4' on Q -> the one B-rooted sus4 candidate -> Bsus4/F# (§5.1)."""
    r = R.resolve_chosen("Bsus4", Q)
    assert r == {"status": "resolved", "name": "Bsus4/F#", "tier": 2}


def test_gm_on_gm1_resolves():
    r = R.resolve_chosen("Gm", GM1)
    assert r["status"] == "resolved" and r["name"] == "Gm/Bb"


def test_supplied_bass_filters():
    # Both an exact name and a tier-2 selection agree with a bass filter.
    r = R.resolve_chosen("Bsus4/F#", Q)
    assert r["status"] == "resolved" and r["name"] == "Bsus4/F#"


# --- tier 3: root-PC + family -----------------------------------------------

def test_bsus_on_q_is_ambiguous_tier3():
    """'Bsus' on Q -> Bsus4/F# and B7sus4/F# both carry family sus (§5.1)."""
    r = R.resolve_chosen("Bsus", Q)
    assert r["status"] == "ambiguous"
    assert sorted(r["matches"]) == ["B7sus4/F#", "Bsus4/F#"]


def test_family_fallthrough_unique():
    # {F#, A}: no exact F#m7 input string needed — 'F#m' hits the m row at
    # tier 2 (F#m is a shadow); use family to reach a unique non-name row.
    fa = R.identify([2, 0, None, None, None, None])["candidates"]
    r = R.resolve_chosen("F#dy", fa)
    assert r["status"] == "resolved" and r["name"] == "F#dym3" and r["tier"] == 3


# --- enharmonic inputs resolve by PC (spelling never survives) --------------

def test_enharmonic_inputs():
    fa = R.identify([2, 0, None, None, None, None])["candidates"]  # {F#, A}
    for probe in ("F#m", "Gbm"):
        r = R.resolve_chosen(probe, fa)
        assert r["status"] == "resolved" and r["name"] == "F#m", probe
    r = R.resolve_chosen("Gm/A#", GM1)
    assert r["status"] == "resolved" and r["name"] == "Gm/Bb"


def test_unicode_accidentals_normalize():
    r = R.resolve_chosen("F♯q4", Q)  # F♯q4
    assert r["status"] == "resolved" and r["name"] == "F#q4"


# --- miss -> partial success (suggestions, never a re-send) -----------------

def test_miss_returns_suggestions():
    r = R.resolve_chosen("Gm", Q)
    assert r["status"] == "miss"
    assert r["suggestions"][0] == "F#q4"
    assert len(r["suggestions"]) <= 8


def test_unparseable_is_a_miss_not_an_exception():
    r = R.resolve_chosen("totally-not-a-chord", Q)
    assert r["status"] == "miss"


# --- covariant re-derivation incl. the Cdim/Gb divergence (§11) -------------

def test_covariant_chosen_cdim_gb():
    """Transposing Ddim/Ab by +10 must yield Cdim/Gb (member stacking), not
    Cdim/F# (naive respelling via the canonical root table for PC 6)."""
    old = SET_B["ddim-ab"]["result"]
    new = SET_B["cdim-gb"]["result"]
    got = R.covariant_chosen(old, "Ddim/Ab", new, 10)
    assert got == "Cdim/Gb"
    assert got != "Cdim/F#"


def test_covariant_chosen_simple():
    old = R.identify([3, 1, None, None, None, None])       # {G, Bb}
    new = R.identify([5, 3, None, None, None, None])       # {A, C}
    assert R.covariant_chosen(old, "Gm", new, 2) == "Am"


def test_covariance_property_guarantees_existence():
    """§6.1: the covariance property guarantees the transposed candidate
    exists — spot-check over every Set A fixture with a candidate list."""
    for name, fx in SET_A.items():
        r = fx["result"]
        if not r["candidates"] or r["input"]["context_key"]:
            continue
        strings = r["input"]["strings"]
        up = [None if s is None else s + 2 for s in strings]
        moved = R.identify(up, r["input"]["tuning"])
        for c in r["candidates"]:
            assert R.covariant_chosen(r, c["name"], moved, 2) is not None, (
                name, c["name"],
            )
