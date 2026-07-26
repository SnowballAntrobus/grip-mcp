"""Property tests over the reference engine (DESIGN §11): transposition
covariance (PCs mod 12, never spellings), tuning covariance, ranking
stability, totality over random sets incl. doubled-PC and single-PC
inputs, shadow presence, dedup — plus the fixture-coverage meta-check
(the Milestone-0 membership criterion)."""

import json
import random
from pathlib import Path

import pytest

import refengine as R

TBL = R.table()
FIXTURE_DIR = Path(__file__).parent / "fixtures"
ALL_FIXTURES = {
    **json.loads((FIXTURE_DIR / "set_a.json").read_text()),
    **json.loads((FIXTURE_DIR / "set_b.json").read_text()),
}

rng = random.Random(1207)  # fixed seed, deterministic


def midis_to_input(midis):
    """One string per note, all frets 0: identify() over arbitrary notes."""
    tuning = []
    for m in sorted(midis):
        pc = m % 12
        sp = R.spell_canonical(pc)
        tuning.append(R.pitch_name(sp, m))
    return [0] * len(midis), tuning


def cand_shape(c):
    """Spelling-free candidate identity: PCs mod 12 (DESIGN §5.2.6)."""
    return (
        R.Spelling.parse(c["root"]).pc,
        c["quality"],
        R.Spelling.parse(c["bass"]).pc,
    )


def random_midi_set():
    n = rng.randint(1, 6)
    return [rng.randint(40, 76) for _ in range(n)]


CASES = [random_midi_set() for _ in range(300)]


# --- totality ----------------------------------------------------------------

@pytest.mark.parametrize("midis", CASES)
def test_totality_random_inputs(midis):
    strings, tuning = midis_to_input(midis)
    r = R.identify(strings, tuning)
    pcs = {m % 12 for m in midis}
    if len(pcs) < 2:
        assert r["candidates"] == [] and "pitch_report" in r
    else:
        assert len(r["candidates"]) >= 1
        assert r["decided_at"] in {"R0", "R1", "R2", "R3", "tiebreak", "unique"}
        # coll appears iff nothing else covers, and then alone at the bottom.
        colls = [c for c in r["candidates"] if c["quality"] == "coll"]
        if colls:
            assert len(r["candidates"]) == 1


# --- dedup: no same-root same-set duplicates (meta-test clause, §7.1) -------

@pytest.mark.parametrize("midis", CASES[:150])
def test_dedup_holds(midis):
    strings, tuning = midis_to_input(midis)
    r = R.identify(strings, tuning)
    seen = set()
    for c in r["candidates"]:
        root_pc = R.Spelling.parse(c["root"]).pc
        tones = frozenset(
            (root_pc + t) % 12
            for t in TBL["qualities"][c["quality"]]["tones"]
        ) if c["quality"] != "coll" else frozenset(
            R.Spelling.parse(p[:-1] if p[-1].isdigit() else p).pc
            for p in c["pitches"]
        )
        key = (root_pc, tones)
        assert key not in seen, f"duplicate {key} in {[x['name'] for x in r['candidates']]}"
        seen.add(key)


# --- transposition covariance (candidate SETS; PCs mod 12) ------------------

@pytest.mark.parametrize("midis", CASES[:60])
def test_transposition_covariance(midis):
    if len({m % 12 for m in midis}) < 2:
        pytest.skip("needs >= 2 distinct PCs")
    strings, tuning = midis_to_input(midis)
    base = {cand_shape(c) for c in R.identify(strings, tuning)["candidates"]}
    for k in (1, 5, 11):
        s2, t2 = midis_to_input([m + k for m in midis])
        moved = {
            cand_shape(c) for c in R.identify(s2, t2)["candidates"]
        }
        expected = {
            ((r + k) % 12, q, (b + k) % 12) for (r, q, b) in base
        }
        assert moved == expected


# --- tuning covariance: same MIDI notes, different route --------------------

def test_tuning_covariance_same_notes():
    # Q as fretted in standard vs the same notes as "open strings" of a
    # bespoke tuning: identical candidates and ranking.
    a = R.identify([2, 2, 2, None, None, None], "standard")
    b = R.identify([0, 0, 0], ["F#2", "B2", "E3"])
    assert a["candidates"] == b["candidates"]
    assert a["decided_at"] == b["decided_at"]


def test_tuning_covariance_fret_offset():
    a = R.identify([5, 5, None, None, None, None], "standard")
    b = R.identify([3, 3, None, None, None, None], ["F#2", "B2", "D3", "G3", "B3", "E4"])
    assert a["candidates"] == b["candidates"]


# --- ranking stability -------------------------------------------------------

def test_ranking_stability_repeat_calls():
    one = R.identify([2, 2, 2, None, None, None])
    two = R.identify([2, 2, 2, None, None, None])
    assert one == two


# --- shadow presence (the mechanical shadow rule, §7.3) ---------------------

@pytest.mark.parametrize("bass_pc", range(12))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6, 8, 9, 10, 11])
def test_shadow_presence_all_dyads(bass_pc, k):
    """Every table row rooted at the bass whose tones contain k appears."""
    midis = [48 + bass_pc, 48 + bass_pc + k]
    strings, tuning = midis_to_input(midis)
    r = R.identify(strings, tuning)
    got = {
        c["quality"]
        for c in r["candidates"]
        if R.Spelling.parse(c["root"]).pc == bass_pc
    }
    expected = {
        qid for qid, row in TBL["qualities"].items()
        if row["gen"] == "table" and k in row["tones"]
    }
    assert expected <= got
    # And the dyad itself, rooted at the bass.
    dyads = {q for q in got if q.startswith("dy")}
    assert len(dyads) == 1


def test_distance_7_generates_only_x5():
    r = R.identify([None, 2, 4, None, None, None])  # {B, F#}
    dyads = [c for c in r["candidates"] if c["quality"].startswith("dy")]
    assert dyads == []
    assert r["candidates"][0]["quality"] == "5"


def test_distance_5_generates_inverted_fifth():
    r = R.identify([2, 2, None, None, None, None])  # {F#, B} bass F#
    assert "B5/F#" in [c["name"] for c in r["candidates"]]


def test_doubled_pc_input_equivalent_to_simple():
    simple = R.identify([None, 2, 4, None, None, None])       # B2, F#3
    doubled = R.identify([7, 9, 9, None, None, None])         # B2, F#3, B3
    assert [c["name"] for c in simple["candidates"]] == [
        c["name"] for c in doubled["candidates"]
    ]


# --- decided_at sanity over fixtures ----------------------------------------

@pytest.mark.parametrize("fname", sorted(ALL_FIXTURES))
def test_decided_at_domain(fname):
    r = ALL_FIXTURES[fname]["result"]
    if r["candidates"]:
        assert r["decided_at"] in {"R0", "R1", "R2", "R3", "tiebreak", "unique"}
    else:
        assert r["decided_at"] is None


# --- fixture coverage: the Milestone-0 membership criterion -----------------

def test_every_quality_required_by_a_fixture():
    """A quality enters the freeze only if a Set A or B fixture requires it
    as top or root-at-bass shadow (DESIGN §13)."""
    covered = set()
    for fx in ALL_FIXTURES.values():
        cands = fx["result"]["candidates"]
        if not cands:
            continue
        covered.add(cands[0]["quality"])
        for c in cands:
            if c["root_is_bass"] and c["root_sounds"]:
                covered.add(c["quality"])
    missing = set(TBL["qualities"]) - covered
    assert not missing, f"table rows without a requiring fixture: {sorted(missing)}"
