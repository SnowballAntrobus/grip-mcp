"""Set B theory fixtures (DESIGN §11): folk chords, the Freddie Green
shell, drop-2 voicings, DADGAD, the Xm-vs-Xdim discount ordering, the B5
same-root tie-break, the dyad-token sweep, the coll exemplar, and the
Cdim/Gb spelling input."""

import json
from pathlib import Path

import pytest

import refengine as R

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "set_b.json").read_text()
)


def result(name):
    return FIXTURES[name]["result"]


def names(name):
    return [c["name"] for c in result(name)["candidates"]]


def cand(name, cname):
    return next(c for c in result(name)["candidates"] if c["name"] == cname)


@pytest.mark.parametrize("fname", sorted(FIXTURES))
def test_regenerates_clean(fname):
    fx = FIXTURES[fname]["result"]
    inp = fx["input"]
    fresh = R.identify(inp["strings"], inp["tuning"], inp["context_key"])
    assert fresh == fx


# --- open-position folk chords ----------------------------------------------

@pytest.mark.parametrize("fname,top", [
    ("folk-c", "C"), ("folk-g", "G"), ("folk-d", "D"),
    ("folk-em", "Em"), ("folk-am", "Am"),
])
def test_folk_chords_top_exactly(fname, top):
    r = result(fname)
    first = r["candidates"][0]
    assert first["name"] == top
    assert first["missing"] == []
    assert first["inversion"] == 0
    assert first["root_is_bass"] and first["root_sounds"]


# --- the {G, B, F} shell: G7 tops, coll suppressed, rung script-asserted ----

def test_freddie_green_shell():
    r = result("freddie-g7")
    assert names("freddie-g7")[0] == "G7"
    assert cand("freddie-g7", "G7")["missing"] == ["D"]
    assert all(c["quality"] != "coll" for c in r["candidates"])
    # "The rung floats with the frozen table version ... asserted by the
    # script, not prose" (§7.3) — and float it did: engine 1.1.0's
    # foreign-bass class ended the cover's uniqueness (Bdim/G et al.),
    # moving the rung from "unique" to R1. Every non-top reading is
    # foreign.
    assert all(c["foreign_bass"] for c in r["candidates"][1:])
    assert r["decided_at"] == "R1"


# --- drop-2 voicings --------------------------------------------------------

def test_drop2_cmaj7():
    r = result("drop2-cmaj7")
    assert names("drop2-cmaj7")[0] == "Cmaj7"
    assert r["candidates"][0]["pitches"] == ["C3", "G3", "B3", "E4"]
    # Another rung float (engine 1.1.0): Em/C et al. end the uniqueness.
    assert all(c["foreign_bass"] for c in r["candidates"][1:])
    assert r["decided_at"] == "R1"


def test_drop2_dm7():
    r = result("drop2-dm7")
    # The C6/Am7-class coincidence, R1-sorted: Dm7 (root-is-bass) above
    # the exact F6/D inversion. Kept deliberately; do not "fix" (§7.1).
    assert names("drop2-dm7")[:2] == ["Dm7", "F6/D"]
    assert all(c["foreign_bass"] for c in r["candidates"][2:])
    assert r["decided_at"] == "R1"


# --- DADGAD -----------------------------------------------------------------

def test_dadgad_open():
    r = result("dadgad-open")
    assert names("dadgad-open")[:7] == [
        "Dsus4", "D7sus4", "Gsus2/D", "Aq4/D",
        "A7sus4/D", "Gadd9/D", "Gmadd9/D",
    ]
    assert all(c["foreign_bass"] for c in r["candidates"][7:])
    assert r["decided_at"] == "R2"
    # A7sus4/D: the discounted fifth (E) is the one missing tone.
    assert cand("dadgad-open", "A7sus4/D")["missing"] == ["E"]


# --- Xm-vs-Xdim discount ordering (R2.2) ------------------------------------

def test_am_beats_adim_at_r2_2():
    ns = names("am-vs-adim")
    assert ns[0] == "Adym3"
    assert ns.index("Am") < ns.index("Adim")
    assert cand("am-vs-adim", "Am")["missing"] == ["E"]
    assert cand("am-vs-adim", "Adim")["missing"] == ["Eb"]


# --- the B5 same-root tie-break (quality-order column) ----------------------

def test_b5_same_root_tiebreak():
    ns = names("b5-tiebreak")
    assert ns[0] == "B5"
    # Bsus2 and Bsus4 tie through R2 (one non-discounted miss each) and R3
    # (same tier, same root letter): the quality-order column decides.
    assert ns.index("Bsus4") == ns.index("Bsus2") + 1
    s2, s4 = cand("b5-tiebreak", "Bsus2"), cand("b5-tiebreak", "Bsus4")
    assert len(s2["missing"]) == len(s4["missing"]) == 1


# --- dyad-token sweep: every token arrives with its fixture -----------------

@pytest.mark.parametrize("fname,top", [
    ("dy-M2", "CdyM2"), ("dy-A4", "CdyA4"), ("dy-m6", "Cdym6"),
    ("dy-M6", "CdyM6"), ("dy-m7", "Cdym7"), ("dy-M7", "CdyM7"),
])
def test_dyad_sweep_tops(fname, top):
    assert names(fname)[0] == top


def test_dyad_a4_is_sharp_leaning():
    # PC distance 6 = A4, sharp-leaning: the member spells F# over C (§7.1).
    c = cand("dy-A4", "CdyA4")
    assert c["pitches"] == ["C3", "F#3"]


def test_dy_m2_shadows_carry_add9_family():
    # sus2/add9/madd9 arrive as root-at-bass shadows of {X, X+2} (§7.3).
    for shadow in ("Csus2", "Cadd9", "Cmadd9"):
        c = cand("dy-M2", shadow)
        assert c["root_is_bass"] and c["root_sounds"]


# --- totality catch-all + foreign bass (PHASE3 §3) --------------------------

def test_cluster3_now_reads_as_foreign_fragments():
    """Engine 1.1.0: the 3-note cluster's uppers {Db, D} are coverable
    over the foreign C bass (Dmaj7 contains both), so readings exist and
    coll stays suppressed — its catch-all role is strictly empty-set."""
    r = result("coll-cluster")
    assert names("coll-cluster")[0] == "Dmaj7/C"
    assert all(c["foreign_bass"] for c in r["candidates"])
    assert all(c["quality"] != "coll" for c in r["candidates"])
    assert r["decided_at"] == "tiebreak"


def test_coll_cluster4():
    """The 4-note chromatic cluster: nothing covers it, uppers included
    — coll, alone, at the bass (its fixture per the membership
    criterion)."""
    r = result("coll-cluster4")
    assert names("coll-cluster4") == ["Ccoll"]
    c = r["candidates"][0]
    assert c["quality"] == "coll"
    assert c["missing"] == []
    assert c["inversion"] is None
    assert c["pitches"] == ["C3", "Db3", "D3", "Eb4"]
    assert r["decided_at"] == "unique"


def test_c_over_d_foreign_bass():
    """The classic C/D: the literal top is Cadd9/D (that PC set IS
    Cadd9); C/D is the first foreign reading — present, flagged, bass
    never in missing, inversion null."""
    r = result("c-over-d")
    assert names("c-over-d")[0] == "Cadd9/D"
    cd = cand("c-over-d", "C/D")
    assert cd["foreign_bass"] is True
    assert cd["bass"] == "D"
    assert cd["inversion"] is None
    assert cd["missing"] == []          # the bass is never a missing tone
    assert r["decided_at"] == "R1"
    # Class ordering: every foreign reading ranks below every
    # chord-tone reading.
    flags = [c["foreign_bass"] for c in r["candidates"]]
    assert flags == sorted(flags)


def test_pedal_point():
    """{D, C, G}: the literal top is Dq4 (it IS a fourths stack); the
    power chord over the pedal (C5/D) arrives in the foreign class."""
    r = result("pedal-d")
    assert names("pedal-d")[0] == "Dq4"
    c5 = cand("pedal-d", "C5/D")
    assert c5["foreign_bass"] is True and c5["missing"] == []
    flags = [c["foreign_bass"] for c in r["candidates"]]
    assert flags == sorted(flags)


# --- member-stacking bass spelling (Cdim/Gb) --------------------------------

def test_cdim_gb_spelling():
    ns = names("cdim-gb")
    # Member stacking spells Cdim's diminished fifth Gb; the canonical root
    # table would say F#. The name must carry the stacked spelling (§11).
    assert "Cdim/Gb" in ns
    assert "Cdim/F#" not in ns
    # The literal top is the dim7 rotation rooted at the bass — kept
    # deliberately (dedup decision, §7.1).
    assert ns[0] == "F#dim7"


def test_ddim_ab_source():
    assert "Ddim/Ab" in names("ddim-ab")


# --- single-distinct-PC contract --------------------------------------------

def test_unison_pitch_report():
    r = result("unison-e")
    assert r["candidates"] == []
    assert r["pitch_report"]["pitches"] == ["E2", "E4"]
    assert r["pitch_report"]["doubling"] == 2
