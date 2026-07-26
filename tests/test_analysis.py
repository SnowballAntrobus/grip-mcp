"""Phase 3 analysis tests (docs/PHASE3_DESIGN.md): hand-checkable
progressions, voice-matching properties, key ranking, segmentation,
the gesture-pair single-voice property, vocabulary-first display."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import analysis as AN
from grip_mcp import theory as TH
from grip_mcp.service import GripService

X = None
FOLK = {
    "c":  [X, 3, 2, 0, 1, 0],
    "am": [X, 0, 2, 2, 1, 0],
    "f":  [1, 3, 3, 2, 1, 1],
    "g":  [3, 2, 0, 0, 0, 3],
    "d":  [X, X, 0, 2, 3, 2],
    "a":  [X, 0, 2, 2, 2, 0],
}


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("song", create=True)
    for gid, strings in FOLK.items():
        s.add_grip(gid, strings)
    return s


# --- voice matching ---------------------------------------------------------

def test_voice_matching_equal_cardinality_is_sorted_pairing():
    vm = AN.voice_matching([60, 64, 67], [59, 62, 67])
    assert vm["pairs"] == [(60, 59), (64, 62), (67, 67)]
    assert vm["total"] == 3
    assert vm["left"] == [] and vm["entered"] == []


def test_voice_matching_never_crosses():
    vm = AN.voice_matching([60, 64], [65, 62])
    # sorted b = [62, 65]; monotone: 60->62, 64->65.
    assert vm["pairs"] == [(60, 62), (64, 65)]


def test_voice_matching_unequal_cardinality():
    vm = AN.voice_matching([60, 64, 67, 72], [60, 65, 69])
    assert len(vm["pairs"]) == 3
    assert len(vm["left"]) == 1 and vm["entered"] == []
    # Minimality: the DP must beat any naive prefix matching.
    assert vm["total"] <= 1 + 1 + 3


def test_voice_matching_symmetric_totals():
    a, b = [40, 47, 52], [42, 47, 52]
    assert AN.voice_matching(a, b)["total"] == \
        AN.voice_matching(b, a)["total"] == 2


# --- Roman numerals ---------------------------------------------------------

@pytest.mark.parametrize("root,qid,key,expect", [
    (0, "maj", "c-major", "I"),
    (9, "m", "c-major", "vi"),
    (5, "maj", "c-major", "IV"),
    (7, "7", "c-major", "V7"),
    (11, "dim", "c-major", "viidim"),
    (2, "m7", "c-major", "ii7"),
    (11, "maj", "e-minor", "V"),          # the admitted V in minor
    (11, "7", "e-minor", "V7"),
    (7, "maj", "e-minor", "III"),
    (4, "sus4", "e-minor", "Isus4"),      # non-tertian: uppercase + suffix
    (0, "maj7", "c-major", "Imaj7"),
])
def test_roman_numerals(root, qid, key, expect):
    assert AN.roman_numeral(root, qid, None, TH.Key.parse(key)) == expect


def test_roman_numeral_chromatic_is_none():
    # E major triad in C major: G# chromatic -> null, stated not judged.
    assert AN.roman_numeral(4, "maj", None, TH.Key.parse("c-major")) is None


def test_roman_numeral_inversion_bass():
    got = AN.roman_numeral(7, "m", 10, TH.Key.parse("bb-major"))
    assert got == "vi/Bb"


# --- analyze end to end ------------------------------------------------------

def test_folk_progression_in_c(svc):
    svc.set_sequence("prog", ["c", "am", "f", "g"])
    r = svc.analyze("prog")
    assert r["keys"][0]["key"] == "c-major"
    assert r["keys"][0]["passes"] == 4
    assert r["numerals"]["c-major"] == ["I", "vi", "IV", "V"]
    assert len(r["segments"]) == 1          # no modulation
    assert r["modulations"] == []


def test_bass_line_and_common_tones(svc):
    svc.set_sequence("prog", ["c", "am"])
    r = svc.analyze("prog")
    assert r["bass_line"][0]["pitch"] == "C3"
    assert r["bass_line"][1]["pitch"] == "A2"
    assert r["bass_motion"] == [-3]
    pair = r["pairs"][0]
    assert set(pair["common_tones"]) == {"C", "E"}
    assert pair["voice_leading"]["total"] >= 1


def test_modulation_segmentation(svc):
    # C-Am-F-G (C major) then D-A (no shared key with the first four).
    svc.set_sequence("shift", ["c", "am", "f", "g", "d", "a"])
    r = svc.analyze("shift")
    assert len(r["segments"]) == 2
    assert r["segments"][0]["steps"] == [0, 1, 2, 3]
    assert r["segments"][1]["steps"] == [4, 5]
    assert r["modulations"][0]["at_step"] == 4
    assert "c-major" in [k for k in r["segments"][0]["keys"]]


def test_gesture_pair_is_single_voice_motion(svc):
    svc.add_grip("e5", [0, 2, 2, X, X, X])
    svc.add_grip("e5-landed", [2, 2, 2, X, X, X])
    svc.set_sequence("riff", ["e5", "e5-landed"])
    r = svc.analyze("riff")
    vl = r["pairs"][0]["voice_leading"]
    moved = [m for m in vl["motions"] if m["semitones"] != 0]
    assert len(moved) == 1 and moved[0]["semitones"] == 2
    assert vl["total"] == 2


def test_chosen_drives_the_analysis(svc):
    """D2: the user's vocabulary first — renaming a step changes its
    numeral."""
    svc.add_grip("gm-1", [X, X, 8, 7, 8, X])
    svc.set_sequence("solo", ["gm-1"])
    before = svc.analyze("solo", keys=["bb-major"])
    assert before["numerals"]["bb-major"] == ["I6"]     # Bb6, the top
    svc.set_reading("gm-1", "Gm")
    after = svc.analyze("solo", keys=["bb-major"])
    assert after["numerals"]["bb-major"] == ["vi/Bb"]   # the user's Gm
    assert after["steps"][0]["name"] == "Gm/Bb"
    assert after["steps"][0]["named"] is True


def test_analyze_flattens_structure(svc):
    svc.set_sequence("verse", ["c", "am"])
    svc.set_sequence("full", ["@verse", "g"])
    r = svc.analyze("full")
    assert [s["grip"] for s in r["steps"]] == ["c", "am", "g"]


def test_analyze_is_read_only(svc):
    svc.set_sequence("prog", ["c", "am"])
    svc.analyze("prog")
    h = svc.history()
    assert all(e["tool"] != "analyze" for e in h["entries"])


def test_analyze_deterministic(svc):
    svc.set_sequence("prog", ["c", "am", "f", "g"])
    assert svc.analyze("prog") == svc.analyze("prog")


def test_explicit_keys_override(svc):
    svc.set_sequence("prog", ["c", "am"])
    r = svc.analyze("prog", keys=["a-minor"])
    assert list(r["numerals"]) == ["a-minor"]
    assert r["numerals"]["a-minor"] == ["III", "i"]


def test_bad_key_instructive(svc):
    svc.set_sequence("prog", ["c"])
    r = svc.analyze("prog", keys=["C major"])
    assert "grammar" in r["error"]["detail"]


def test_unknown_sequence_instructive(svc):
    r = svc.analyze("nope")
    assert r["error"]["code"] == "unknown_sequence"
