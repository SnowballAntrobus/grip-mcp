"""Phase 2a tests (DESIGN §9): voicing search with the playability model,
deterministic documented ranking, tuning parameterization from day one,
and neck overlays. The name→shape bridge retires here: results are exact
by construction, cross-checked against identify anyway as belt."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import theory as TH
from grip_mcp import voicings as V
from grip_mcp.service import GripService

STANDARD = ["E2", "A2", "D3", "G3", "B3", "E4"]
DADGAD = ["D2", "A2", "D3", "G3", "A3", "D4"]


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("demo", create=True)
    return s


# --- the canon: classic shapes surface --------------------------------------

def test_open_e_is_the_top_e_voicing():
    r = V.find_voicings(STANDARD, "E")
    assert r["voicings"][0]["strings"] == [0, 2, 2, 1, 0, 0]


def test_open_c_shape_found():
    r = V.find_voicings(STANDARD, "C")
    assert [None, 3, 2, 0, 1, 0] in [v["strings"] for v in r["voicings"]]


def test_gm_barre_found_with_barre_detected():
    r = V.find_voicings(STANDARD, "Gm")
    shapes = {tuple(v["strings"]): v for v in r["voicings"]}
    barre = shapes.get((3, 5, 5, 3, 3, 3))
    assert barre is not None
    assert barre["barre"] == {"fret": 3, "from_string": 1}
    # Deterministic suggestion rule: barre = 1, remaining by (fret,
    # string) get sequential digits — 2 and 3 here (a player may prefer
    # 3 and 4; these are suggestions, the rule is the spec).
    assert barre["fingers"] == [1, 2, 3, 1, 1, 1]


def test_f_barre_needs_barre_and_gets_it():
    r = V.find_voicings(STANDARD, "F")
    shapes = {tuple(v["strings"]): v for v in r["voicings"]}
    f = shapes.get((1, 3, 3, 2, 1, 1))
    assert f is not None and f["barre"] == {"fret": 1, "from_string": 1}


def test_exactness_cross_checked_against_identify():
    """Belt over exact-by-construction: the top result of every quality
    re-identifies with the requested chord among its candidates."""
    for chord in ("Gm", "Cmaj7", "D7", "Am7b5", "Esus4", "B5"):
        r = V.find_voicings(STANDARD, chord)
        top = r["voicings"][0]
        idr = TH.identify(top["strings"], STANDARD)
        root_pc, qid, _ = TH.parse_chord_name(chord)
        assert any(
            c["quality"] == qid
            and TH._pc_of_name(c["root"]) == root_pc
            and c["missing"] == []
            for c in idr["candidates"]
        ), chord


# --- coverage rules ---------------------------------------------------------

def test_full_coverage_required_by_default():
    r = V.find_voicings(STANDARD, "Cmaj7")
    for v in r["voicings"]:
        pcs = {m % 12 for m in v["midi"]}
        assert pcs == {0, 4, 7, 11}


def test_allow_omissions_uses_the_tables_discount_column():
    r = V.find_voicings(STANDARD, "Cmaj7",
                        constraints={"allow_omissions": True})
    pcs_sets = [{m % 12 for m in v["midi"]} for v in r["voicings"]]
    assert {0, 4, 11} in pcs_sets          # fifth omitted (discount {7})
    assert all({0, 4, 11} <= s for s in pcs_sets)  # never the third


def test_slash_bass_is_a_hard_constraint():
    r = V.find_voicings(STANDARD, "Gm/Bb")
    assert r["chord"] == "Gm/Bb"
    for v in r["voicings"]:
        assert v["midi"][0] % 12 == 10
        assert v["bass"] == "Bb"


def test_no_slash_root_in_bass_ranks_first_but_inversions_listed():
    r = V.find_voicings(STANDARD, "Gm")
    assert r["voicings"][0]["root_in_bass"] is True
    assert any(not v["root_in_bass"] for v in r["voicings"])


def test_foreign_bass_refused_as_phase_3():
    with pytest.raises(TH.TheoryError, match="Phase 3"):
        V.find_voicings(STANDARD, "C/D")


def test_family_suffix_refused_instructively():
    with pytest.raises(TH.TheoryError, match="sus2"):
        V.find_voicings(STANDARD, "Gsus")


def test_coll_refused():
    with pytest.raises(TH.TheoryError, match="render_neck"):
        V.find_voicings(STANDARD, "Ccoll")


# --- playability model ------------------------------------------------------

def test_span_and_finger_limits_hold():
    r = V.find_voicings(STANDARD, "G")
    for v in r["voicings"]:
        assert v["span"] <= 4
        fingers = [d for d in v["fingers"] if d not in (None, 0)]
        assert len(set(fingers)) <= 4
        assert v["fretted"] <= 4 or v["barre"]


def test_span_cap_is_five():
    with pytest.raises(V.VoicingError, match="caps at 5"):
        V.find_voicings(STANDARD, "C", constraints={"max_span": 6})


def test_unknown_constraint_instructive():
    with pytest.raises(V.VoicingError, match="allow_thumb"):
        V.find_voicings(STANDARD, "C", constraints={"nope": 1})


def test_thumb_over_frees_a_finger():
    """A 5-fretted shape without barre feasibility needs the thumb."""
    base = V.find_voicings(STANDARD, "G7")
    shapes = {tuple(v["strings"]) for v in base["voicings"]}
    thumb = V.find_voicings(STANDARD, "G7",
                            constraints={"allow_thumb": True})
    tshapes = {tuple(v["strings"]) for v in thumb["voicings"]}
    assert shapes <= tshapes               # thumb only adds
    added = tshapes - shapes
    assert added                            # and does add something
    tv = {tuple(v["strings"]): v for v in thumb["voicings"]}
    assert any(tv[s]["thumb"] and tv[s]["fingers"][0] == 0 for s in added
               if tv[s]["strings"][0])


def test_barre_infeasible_with_open_inside():
    # [1, 3, 3, 2, 1, 0]: open top string inside a would-be barre at 1.
    assert V._playability([1, 3, 3, 2, 1, 0],
                          V.DEFAULT_CONSTRAINTS) is None


def test_all_open_voicing_playability():
    p = V._playability([0, 0, 0, 0, 0, 0], V.DEFAULT_CONSTRAINTS)
    assert p["fretted"] == 0 and p["fingers"] == [None] * 6


# --- ranking: deterministic, documented -------------------------------------

def test_near_fret_pulls_the_window():
    far = V.find_voicings(STANDARD, "Gm", near_fret=10)
    assert far["voicings"][0]["position"] >= 8


def test_determinism():
    a = V.find_voicings(STANDARD, "Cmaj7")
    b = V.find_voicings(STANDARD, "Cmaj7")
    assert a == b


def test_lower_position_preferred_by_default():
    r = V.find_voicings(STANDARD, "E")
    positions = [v["position"] for v in r["voicings"][:3]]
    assert positions == sorted(positions)


# --- tuning-parameterized from day one --------------------------------------

def test_dadgad_dsus4_all_open_tops():
    r = V.find_voicings(DADGAD, "Dsus4")
    assert r["voicings"][0]["strings"] == [0, 0, 0, 0, 0, 0]


def test_capo_tuning_capo_relative_frets(svc):
    svc.define_tuning("std-capo3", from_="standard", capo=3)
    r = svc.find_voicings("Bb", tuning="std-capo3")
    # Bb with capo 3 = G-shape territory: capo-relative frets, and the
    # response carries the capo for the badge.
    assert r["capo"] == 3
    tops = [v["strings"] for v in r["voicings"][:8]]
    assert any(s[:4] == [None, 0, 0, 0] or s == [3, 2, 0, 0, 0, 3]
               for s in tops)


def test_four_string_instrument():
    uke = ["G4", "C4", "E4", "A4"]
    r = V.find_voicings(uke, "C")
    assert r["voicings"][0]["strings"] == [0, 0, 0, 3]


# --- spelling ---------------------------------------------------------------

def test_key_respelling_in_output():
    r = V.find_voicings(STANDARD, "F#m", key="f#-minor")
    assert r["chord"] == "F#m"
    v = r["voicings"][0]
    assert any(p.startswith("C#") for p in v["pitches"])
    r2 = V.find_voicings(STANDARD, "Gbm", key="gb-minor")
    assert r2["chord"] == "Gbm"
    assert any(p.startswith("Db") for p in r2["voicings"][0]["pitches"])


# --- service layer + renders ------------------------------------------------

def test_service_envelope_and_truncation(svc):
    r = svc.find_voicings("Gm")
    assert r["project"] == "demo"
    assert len(r["voicings"]) <= 8 and r["truncated"] > 0
    assert r["tuning"] == "standard"


def test_service_render_strip(svc):
    r = svc.find_voicings("Gm", render=True)
    files = r["render"]["files"]
    assert Path(files["svg"]).exists() and Path(files["png"]).exists()
    assert Path(files["svg"]).name.startswith("adhoc__")


def test_render_neck_key_overlay(svc):
    r = svc.render_neck(overlay_key="e-minor")
    assert Path(r["files"]["png"]).exists()
    svg = Path(r["files"]["svg"]).read_text()
    assert "<text" not in svg
    assert Path(r["files"]["svg"]).name.startswith("neck__")


def test_render_neck_pitch_set_and_exactly_one_of(svc):
    r = svc.render_neck(overlay_pitches=["G", "Bb", "D"])
    assert r["overlay"] == "G Bb D"
    both = svc.render_neck(overlay_key="e-minor",
                           overlay_pitches=["E"])
    assert both["error"]["code"] == "exactly_one_of"
    neither = svc.render_neck()
    assert neither["error"]["code"] == "exactly_one_of"


def test_render_neck_hash_distinct_across_overlays(svc):
    a = svc.render_neck(overlay_key="e-minor")
    b = svc.render_neck(overlay_key="g-major")
    assert a["render_hash"] != b["render_hash"]
