"""Phase R tests (docs/RHYTHM_DESIGN.md): rhythm vocabulary lifecycle,
sequence assignment with @ref inheritance, timeline realization,
duration-weighted analysis, deterministic audition, the bus document."""

import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import rhythm as RH
from grip_mcp.service import GripService

X = None
GALLOP = {
    "length_beats": 4,
    "events": [
        {"at": 0, "dur": 1, "play": "bass"},
        {"at": 1, "dur": 0.5, "play": "strum"},
        {"at": 1.5, "dur": 0.5, "play": "strum-up"},
        {"at": 2, "dur": 2, "play": "arp-up"},
    ],
}


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("song", create=True)
    for gid, st in [("c", [X, 3, 2, 0, 1, 0]), ("am", [X, 0, 2, 2, 1, 0]),
                    ("g", [3, 2, 0, 0, 0, 3]), ("d", [X, X, 0, 2, 3, 2]),
                    ("a", [X, 0, 2, 2, 2, 0])]:
        s.add_grip(gid, st)
    return s


# --- vocabulary lifecycle ---------------------------------------------------

def test_define_and_list(svc):
    r = svc.define_rhythm("gallop", 4, GALLOP["events"])
    assert r["stored"] is True
    lr = svc.list_rhythms()
    assert "gallop" in lr["rhythms"] and "whole" in lr["builtin"]


def test_builtins_immutable(svc):
    r = svc.define_rhythm("whole", 4, GALLOP["events"])
    assert r["error"]["code"] == "immutable_rhythm"
    assert svc.remove_rhythm("quarters")["error"]["code"] == \
        "immutable_rhythm"


def test_remove_refused_while_assigned(svc):
    svc.define_rhythm("gallop", 4, GALLOP["events"])
    svc.set_sequence("prog", ["c", "am"])
    svc.set_rhythm("prog", rhythm="gallop")
    r = svc.remove_rhythm("gallop")
    assert r["error"]["code"] == "rhythm_referenced"


def test_validation_instructive(svc):
    bad = svc.define_rhythm("x", 4, [{"at": 5, "dur": 1, "play": "strum"}])
    assert "outside" in bad["error"]["detail"]
    bad = svc.define_rhythm("x", 4, [{"at": 0, "dur": 1, "play": "chug"}])
    assert "strum" in bad["error"]["detail"]


# --- assignment + normalization ---------------------------------------------

def test_plain_list_sequences_untouched(svc):
    svc.set_sequence("prog", ["c", "am"])
    lib = json.loads(
        (svc.root / "song" / "grip" / "library.json").read_text()
    )
    assert lib["sequences"]["prog"] == ["c", "am"]   # legacy form intact
    # And analysis of an unrhythmed sequence has no timeline:
    a = svc.analyze("prog")
    assert "onset_beats" not in a["steps"][0]
    assert "beats" not in a["keys"][0]


def test_set_rhythm_assignment(svc):
    svc.define_rhythm("gallop", 4, GALLOP["events"])
    svc.set_sequence("prog", ["c", "am", "g"])
    r = svc.set_rhythm("prog", rhythm="gallop", tempo=120,
                       steps={"2": {"rhythm": "whole", "repeat": 2}})
    assert r["stored"] is True
    assert r["resolved_steps"] == [
        {"grip": "c", "rhythm": "gallop", "repeat": 1},
        {"grip": "am", "rhythm": "gallop", "repeat": 1},
        {"grip": "g", "rhythm": "whole", "repeat": 2},
    ]


def test_at_ref_inheritance(svc):
    """Sections keep their own feels; unassigned sections inherit the
    parent default (R2)."""
    svc.define_rhythm("gallop", 4, GALLOP["events"])
    svc.set_sequence("verse", ["c", "am"])
    svc.set_sequence("chorus", ["g", "d"])
    svc.set_rhythm("chorus", rhythm="arp-up")
    svc.set_sequence("full", ["@verse", "@chorus"])
    svc.set_rhythm("full", rhythm="gallop")
    lib = GripService.__new__(GripService)  # raw store access
    st = svc._store()
    steps = RH.flatten_with_rhythm(st.load(), "full")
    assert [s["rhythm"] for s in steps] == \
        ["gallop", "gallop", "arp-up", "arp-up"]


# --- realization ------------------------------------------------------------

def test_timeline_offsets_and_repeats(svc):
    svc.set_sequence("prog", ["c", "am"])
    svc.set_rhythm("prog", rhythm="quarters",
                   steps={"1": {"rhythm": "whole", "repeat": 2}})
    a = svc.analyze("prog")
    s0, s1 = a["steps"]
    assert s0["onset_beats"] == 0 and s0["duration_beats"] == 4
    assert s1["onset_beats"] == 4 and s1["duration_beats"] == 8
    assert s0["bar"] == 1 and s1["bar"] == 2


def test_arp_divides_evenly(svc):
    st = svc._store()
    lib = st.load()
    steps = [{"grip": "c", "rhythm": "arp-up", "repeat": 1,
              "assigned": True}]
    gd = {"c": {"midis_by_string": [None, 48, 52, 55, 60, 64]}}
    tl = RH.realize(lib, steps, gd)
    ev = tl[0]["events"]
    assert len(ev) == 5                       # five sounding strings
    assert ev[0]["midis"] == [48] and ev[-1]["midis"] == [64]
    assert ev[1]["at"] - ev[0]["at"] == pytest.approx(0.8)  # 4/5 beats


def test_string_list_skips_muted(svc):
    st = svc._store()
    lib = st.load()
    lib.setdefault("rhythms", {})["pick"] = {
        "length_beats": 1, "meter": [4, 4],
        "events": [{"at": 0, "dur": 1, "play": [1, 5]}],
    }
    steps = [{"grip": "c", "rhythm": "pick", "repeat": 1,
              "assigned": True}]
    gd = {"c": {"midis_by_string": [None, 48, 52, 55, 60, 64]}}
    tl = RH.realize(lib, steps, gd)
    # String 1 is muted on this grip -> skipped; string 5 sounds.
    assert tl[0]["events"][0]["midis"] == [60]


# --- duration-weighted analysis (R3) ----------------------------------------

def test_duration_weight_flips_a_tie(svc):
    """c, am, g pass in C major AND fit around D/A differently; hold the
    D-major side longer and the weighting must move the ranking in a way
    step counts cannot."""
    svc.set_sequence("shift", ["c", "g", "d", "a"])
    plain = svc.analyze("shift")
    # steps: c passes c-major/g-major-side; d+a pass d/a-side; counts
    # tie at 3/4 for g-major and d-major.
    assert plain["keys"][0]["key"] == "g-major"   # step-count winner
    svc.set_rhythm("shift", rhythm="whole",
                   steps={"2": {"repeat": 4}, "3": {"repeat": 4}})
    weighted = svc.analyze("shift")
    assert weighted["keys"][0]["key"] == "d-major"  # duration winner
    assert weighted["keys"][0]["beats"] == 36
    assert weighted["keys"][0]["of_beats"] == 40
    # g-major (the unweighted #1) no longer even places top-3:
    assert "g-major" not in [k["key"] for k in weighted["keys"]]


def test_unrhythmed_analysis_unchanged(svc):
    svc.set_sequence("prog", ["c", "am", "g"])
    a = svc.analyze("prog")
    assert a["keys"][0]["key"] == "c-major"
    assert "beats" not in a["keys"][0]


# --- audition (R4) ----------------------------------------------------------

def test_render_audio_deterministic_wav(svc):
    svc.set_sequence("prog", ["c", "am"])
    svc.set_rhythm("prog", rhythm="quarters", tempo=140)
    r1 = svc.render_audio("prog")
    r2 = svc.render_audio("prog")
    assert r1["files"] == r2["files"]         # same request, same file
    p = Path(r1["files"]["wav"])
    assert p.exists() and p.name.startswith("prog__")
    with wave.open(str(p), "rb") as w:
        assert w.getframerate() == RH.SR and w.getnchannels() == 1
        assert w.getnframes() > RH.SR         # more than a second
    assert r1["seconds"] > 3


def test_render_audio_unassigned_uses_whole_default(svc):
    svc.set_sequence("prog", ["c", "am"])
    r = svc.render_audio("prog", tempo=160)
    assert Path(r["files"]["wav"]).exists()
    assert r["tempo"] == 160


# --- the bus document (R5) --------------------------------------------------

def test_export_timeline_document(svc):
    svc.add_grip("gm-1", [X, X, 8, 7, 8, X], chosen="Gm")
    svc.set_sequence("intro", ["gm-1", "c"])
    svc.set_rhythm("intro", rhythm="bass-strum", tempo=90)
    r = svc.export_timeline("intro")
    p = Path(r["files"]["json"])
    assert p.exists()
    assert p.parent.name == "exports"          # the §3 bus
    assert p.name.startswith("grip__intro__")  # §3 naming
    doc = json.loads(p.read_text())
    assert doc["format"] == "grip-timeline" and doc["version"] == 1
    assert doc["tempo"] == 90
    s0 = doc["steps"][0]
    assert s0["name"] == "Gm/Bb"               # the user's vocabulary first
    assert s0["named"] is True
    assert s0["events"] and "midis" in s0["events"][0]
    assert doc["keys"] and doc["numerals"]


def test_export_timeline_idempotent_and_scoped(svc, tmp_path):
    svc.set_sequence("prog", ["c", "am"])
    r1 = svc.export_timeline("prog")
    r2 = svc.export_timeline("prog")
    assert r1["files"] == r2["files"]
    assert str(tmp_path) in r1["files"]["json"]
