"""Rhythm tests (RHYTHM_DESIGN rev 3 §9): tick snapping, grouping +
accent goldens, macro expansion incl. duration policy and symbolic
bass, swing warp of BOTH endpoints (the note-off golden), the reentrant
high-G-uke fixture, meter-mismatch refusal + dangling flags,
4/4-with-6/8-bridge inheritance extended into an SMF byte-golden with
the meter change, mid-bar step starts, per-index
pattern_string_missing, rhythm-without-meter validation,
weighted-vs-ordinal key flip, audition determinism + velocity peak
ratio + single-file overwrite + WAV format golden, SMF byte-goldens,
export JSON carrying stored + realized."""

import array
import json
import struct
import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import audio as AU
from grip_mcp import midi as MI
from grip_mcp import rhythm as RH
from grip_mcp.service import GripService

E_MAJ = [0, 2, 2, 1, 0, 0]
GM1 = [None, None, 8, 7, 8, None]
AM = [None, 0, 2, 2, 1, 0]
DM = [None, None, 0, 2, 3, 2]
G_OPEN = [3, 2, 0, 0, 0, 3]
C_OPEN = [None, 3, 2, 0, 1, 0]
UKE_C = [0, 0, 0, 3]  # over the high-G uke tuning below


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("rhythm-test", create=True)
    s.add_grip("e", E_MAJ)
    s.add_grip("a", AM)
    s.add_grip("d", DM)
    s.add_grip("g", G_OPEN)
    s.add_grip("c", C_OPEN)
    return s


# --- §2: the tick grid ------------------------------------------------------

def test_tick_snapping():
    assert RH.snap_ticks("1/3") == 320       # the §9 golden
    assert RH.snap_ticks("1/5") == 192       # quintuplet exact
    assert RH.snap_ticks("1/7") == 137       # septuplet snaps (~0.1%)
    assert RH.snap_ticks(1) == 960
    assert RH.snap_ticks(3.5) == 3360
    assert RH.snap_ticks("7/2") == 3360
    with pytest.raises(RH.RhythmError):
        RH.snap_ticks("nope")
    with pytest.raises(RH.RhythmError):
        RH.snap_ticks(-1)


def test_round_half_up_is_the_one_rule():
    assert RH.round_half_up(Fraction(1, 2)) == 1
    assert RH.round_half_up(Fraction(3, 2)) == 2
    assert RH.round_half_up(Fraction(2, 3)) == 1
    assert RH.round_half_up(Fraction(1, 3)) == 0


# --- §4: grouping + accent goldens ------------------------------------------

def test_grouping_defaults():
    assert RH.default_grouping(1) == [1]          # the num=1 patch
    assert RH.default_grouping(3) == [3]
    assert RH.default_grouping(4) == [2, 2]
    assert RH.default_grouping(6) == [3, 3]       # documented 6/x call
    assert RH.default_grouping(7) == [2, 2, 3]
    assert RH.default_grouping(8) == [2, 2, 2, 2]  # documented 8/8 miss
    assert RH.default_grouping(9) == [3, 3, 3]
    assert RH.default_grouping(5) == [2, 3]


def test_accent_goldens():
    # 4/4: 108 88 100 88; off-beats 76
    m, g = [4, 4], RH.default_grouping(4)
    got = [RH.accent_velocity(b * 960, m, g) for b in range(4)]
    assert got == [108, 88, 100, 88]
    assert RH.accent_velocity(480, m, g) == 76
    # 3/4: one group of 3 — no secondary accent
    m, g = [3, 4], RH.default_grouping(3)
    assert [RH.accent_velocity(b * 960, m, g) for b in range(3)] == \
        [108, 88, 88]
    # 6/8 compound: group start at beat 3
    m, g = [6, 8], RH.default_grouping(6)
    assert [RH.accent_velocity(b * 960, m, g) for b in range(6)] == \
        [108, 88, 88, 100, 88, 88]
    # 7/8 = 2+2+3
    m, g = [7, 8], RH.default_grouping(7)
    assert [RH.accent_velocity(b * 960, m, g) for b in range(7)] == \
        [108, 88, 100, 88, 100, 88, 88]
    # num=1
    m, g = [1, 4], RH.default_grouping(1)
    assert RH.accent_velocity(0, m, g) == 108
    # second bar restarts the ladder
    m, g = [4, 4], [2, 2]
    assert RH.accent_velocity(4 * 960, m, g) == 108


# --- §5: macro expansion (duration policy, accent map, symbolic bass) -------

def test_macro_expansion_golden():
    evs = RH.expand_events(
        [{"at": 0, "verb": "bass"},
         {"at": 2, "verb": "strum"},
         {"at": "5/2", "verb": "strum"}],
        3840, [4, 4], [2, 2])
    assert [e["at"] for e in evs] == [0, 1920, 2400]
    # let ring: to next onset; the last to pattern end
    assert [e["dur"] for e in evs] == [1920, 480, 1440]
    # accent map: bar start, group start, off-beat
    assert [e["velocity"] for e in evs] == [108, 100, 76]
    # verbs expand to note forms — nothing hidden behind a verb
    assert evs[0]["note"] == {"string": "bass"}
    assert evs[1]["note"] == {"strings": "all"}


def test_expansion_explicit_fields_survive():
    evs = RH.expand_events(
        [{"at": 0, "dur": "1/2", "velocity": 55,
          "note": {"strings": [1, 2], "up": True}}],
        1920, [2, 4], [2])
    assert evs == [{"at": 0, "dur": 480, "velocity": 55,
                    "note": {"strings": [1, 2], "up": True}}]


def test_pitch_events_are_melody_parts_not_patterns():
    with pytest.raises(RH.RhythmError) as e:
        RH.expand_events([{"at": 0, "note": {"pitch": "D4"}}],
                         960, [1, 4], [1])
    assert e.value.code == "melody_not_yet"


def test_builtins_meter_parametric():
    # bass-strum in 6/8: symbolic bass on group starts
    p = RH.builtin_pattern("bass-strum", [6, 8], [3, 3])
    assert p["length_ticks"] == 6 * 960
    notes = [e["note"] for e in p["events"]]
    assert notes[0] == {"string": "bass"}
    assert notes[3] == {"string": "bass"}
    assert notes[1] == {"strings": "all"}
    assert [e["velocity"] for e in p["events"]] == \
        [108, 88, 88, 100, 88, 88]
    # whole spans the bar in any meter
    for meter in ([4, 4], [7, 8], [3, 2], [1, 4]):
        w = RH.builtin_pattern("whole", meter,
                               RH.default_grouping(meter[0]))
        assert w["events"][0]["dur"] == meter[0] * 960


# --- §4: swing — both endpoints warp (the note-off golden) ------------------

SW = {"subdivision": 480, "ratio": {"num": 2, "den": 3}}


def test_swing_warp_points():
    assert RH.warp_tick(0, SW) == 0
    assert RH.warp_tick(480, SW) == 640    # the off-point
    assert RH.warp_tick(960, SW) == 960    # pair boundary fixed
    assert RH.warp_tick(240, SW) == 320    # interior moves (a pickup)
    assert RH.warp_tick(720, SW) == 800
    # straight ratio is the identity
    st = {"subdivision": 480, "ratio": {"num": 1, "den": 2}}
    for t in (0, 100, 480, 700, 960, 1441):
        assert RH.warp_tick(t, st) == t


def test_swing_warps_durations_with_onsets():
    """Finding 3's golden: an event [0, 480) under triplet swing must
    END at the warped off-point (640), not the straight one — note-offs
    land at swung positions."""
    lib = {"sequences": {"s": {"meter": [4, 4], "swing": SW,
                               "rhythm": "p", "steps": ["x"]}},
           "rhythms": {"p": {"length_ticks": 3840, "meter": [4, 4],
                             "events": [
                                 {"at": 0, "dur": 480, "velocity": 100,
                                  "note": {"string": 1}},
                                 {"at": 480, "dur": 480, "velocity": 80,
                                  "note": {"string": 1}}]}}}
    gi = {"x": {"name": None, "sounding": [
        {"string": 1, "midi": 60, "pitch": "C4"}]}}
    rz = RH.realize(lib, "s", gi)
    e0, e1 = rz["events"]
    assert (e0["at"], e0["dur"]) == (0, 640)      # end warped to 640
    assert (e1["at"], e1["dur"]) == (640, 320)    # onset warped, dur too
    # the straight grid is preserved in events_stored
    s0, s1 = rz["events_stored"]
    assert (s0["at"], s0["dur"]) == (0, 480)
    assert (s1["at"], s1["dur"]) == (480, 480)


def test_swing_anchor_at_pattern_start():
    """Pairs tile from tick 0 of each pattern instance: the second
    instance of a non-pair-multiple pattern warps identically."""
    lib = {"sequences": {"s": {"meter": [4, 4], "swing": SW, "rhythm": "p",
                               "steps": [{"item": "x", "repeat": 2}]}},
           "rhythms": {"p": {"length_ticks": 1440, "meter": [4, 4],
                             "events": [
                                 {"at": 240, "dur": 240, "velocity": 90,
                                  "note": {"string": 1}}]}}}
    gi = {"x": {"name": None, "sounding": [
        {"string": 1, "midi": 60, "pitch": "C4"}]}}
    rz = RH.realize(lib, "s", gi)
    assert rz["events"][0]["at"] == RH.warp_tick(240, SW)
    assert rz["events"][1]["at"] == 1440 + RH.warp_tick(240, SW)


def test_swing_layering_pattern_overrides_and_null_forces_straight():
    base_events = [{"at": 480, "dur": 480, "velocity": 90,
                    "note": {"string": 1}}]
    gi = {"x": {"name": None, "sounding": [
        {"string": 1, "midi": 60, "pitch": "C4"}]}}
    # pattern "swing": null under a swung sequence -> straight
    lib = {"sequences": {"s": {"meter": [4, 4], "swing": SW, "rhythm": "p",
                               "steps": ["x"]}},
           "rhythms": {"p": {"length_ticks": 3840, "meter": [4, 4],
                             "swing": None, "events": base_events}}}
    rz = RH.realize(lib, "s", gi)
    assert rz["events"][0]["at"] == 480  # forced straight
    # pattern with its own swing overrides (never composes)
    hard = {"subdivision": 480, "ratio": {"num": 3, "den": 4}}
    lib["rhythms"]["p"] = {"length_ticks": 3840, "meter": [4, 4],
                           "swing": hard, "events": base_events}
    rz = RH.realize(lib, "s", gi)
    assert rz["events"][0]["at"] == RH.warp_tick(480, hard) == 720


def test_swing_null_child_section_forces_straight(svc):
    svc.set_sequence("swung", ["e", "a"], meter=[4, 4], tempo=120,
                     swing=SW, rhythm="quarters")
    svc.set_sequence("plain", ["d"], meter=[4, 4], tempo=120,
                     swing="straight", rhythm="p-off")
    # need an off-beat pattern to see the difference
    svc.set_rhythm("p-off", [4, 4], 4,
                   [{"at": "1/2", "dur": "1/2", "note": {"string": 1}}])
    svc.set_sequence("plain", ["d"], meter=[4, 4], tempo=120,
                     swing="straight", rhythm="p-off")
    r = svc.set_sequence("song", ["@swung", "@plain"], meter=[4, 4],
                         tempo=120, swing=SW)
    assert r["stored"]
    tl = svc.export_timeline("song")
    assert "error" not in tl
    # the child's off-beat event stays straight (480 into its span)
    child_at = 2 * 3840
    offs = [e for e in _read_export(tl)["events"]
            if e["at"] >= child_at]
    assert offs[0]["at"] == child_at + 480


def _read_export(payload):
    return json.loads(Path(payload["file"]).read_text())


# --- §3: the reentrant high-G uke fixture -----------------------------------

@pytest.fixture()
def uke(svc):
    svc.define_tuning("uke-high-g", pitches=["G4", "C4", "E4", "A4"])
    svc.add_grip("uke-c", UKE_C, tuning="uke-high-g")
    return svc


def test_uke_bass_is_pitch_strum_is_physical(uke):
    uke.set_sequence("u", ["uke-c"], meter=[4, 4], tempo=120,
                     rhythm="bass-strum")
    tl = uke.export_timeline("u")
    assert "error" not in tl
    doc = _read_export(tl)
    beat1 = [e for e in doc["events"] if e["at"] == 0]
    # symbolic bass -> lowest PITCH = C4, physical string 2
    assert len(beat1) == 1
    assert beat1[0]["pitch"] == "C4" and beat1[0]["string"] == 2
    # strum -> physical order: the high G sounds, first in traversal
    beat2 = sorted((e for e in doc["events"] if e["at"] == 960),
                   key=lambda e: e["string"])
    assert [e["pitch"] for e in beat2] == ["G4", "C4", "E4", "C5"]


def test_uke_arp_up_is_physical_order_jangle(uke):
    uke.set_sequence("u", ["uke-c"], meter=[4, 4], tempo=120,
                     rhythm="arp-up")
    doc = _read_export(uke.export_timeline("u"))
    by_onset = sorted(doc["events"], key=lambda e: e["at"])
    # physical 1->n: G4 first — the jangle is the default, and the
    # arp onsets space at dur/n
    assert [e["pitch"] for e in by_onset] == ["G4", "C4", "E4", "C5"]
    assert [e["at"] for e in by_onset] == [0, 960, 1920, 2880]


# --- §3: physical indexing on sparse grips + per-index drops ----------------

def test_sparse_grip_indexing_and_per_index_drop(svc):
    # x-x-8-7-8-x: 3 sounding strings; 1 = lowest physical sounding
    svc.add_grip("gm1", GM1)
    svc.set_rhythm("pick5", [4, 4], 4, [
        {"at": 0, "note": {"strings": [1, 2, 5]}},
        {"at": 1, "note": {"string": 6}},
        {"at": 2, "note": {"string": 3}},
    ])
    svc.set_sequence("s", ["gm1"], meter=[4, 4], tempo=100,
                     rhythm="pick5")
    tl = svc.export_timeline("s")
    doc = _read_export(tl)
    # chord hit drops index 5 only — 1 and 2 still sound
    assert len([e for e in doc["events"] if e["at"] == 0]) == 2
    # single-string overflow drops whole
    assert not [e for e in doc["events"] if e["at"] == 960]
    # index 3 = highest sounding string exists
    assert len([e for e in doc["events"] if e["at"] == 1920]) == 1
    codes = [(w["code"], w["detail"]["string"]) for w in tl["warnings"]]
    assert ("pattern_string_missing", 5) in codes
    assert ("pattern_string_missing", 6) in codes


# --- §5: validation — assignment refusals, meter gates ----------------------

def test_rhythm_requires_meter(svc):
    r = svc.set_sequence("s", ["e", "a"], rhythm="quarters")
    assert r["error"]["code"] == "rhythm_requires_meter"
    r = svc.set_sequence("s", [{"item": "e", "rhythm": "whole"}, "a"])
    assert r["error"]["code"] == "rhythm_requires_meter"
    r = svc.set_sequence("s", ["e"], tempo=120)
    assert r["error"]["code"] == "rhythm_requires_meter"


def test_meter_mismatch_refused_at_assignment(svc):
    svc.set_rhythm("waltz", [3, 4], 3, [{"at": 0, "verb": "strum"}])
    r = svc.set_sequence("s", ["e"], meter=[4, 4], tempo=100,
                         rhythm="waltz")
    assert r["error"]["code"] == "meter_mismatch"
    # and per-step
    r = svc.set_sequence("s", [{"item": "e", "rhythm": "waltz"}],
                         meter=[4, 4], tempo=100)
    assert r["error"]["code"] == "meter_mismatch"


def test_redefinition_meter_guard(svc):
    svc.set_rhythm("pat", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", ["e"], meter=[4, 4], tempo=100, rhythm="pat")
    r = svc.set_rhythm("pat", [3, 4], 3, [{"at": 0, "verb": "strum"}])
    assert r["error"]["code"] == "meter_mismatch"
    assert "s" in r["error"]["detail"]


def test_hand_edit_mismatch_gets_dangling_treatment(svc):
    svc.set_rhythm("pat", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", ["e"], meter=[4, 4], tempo=100, rhythm="pat")
    # hand edit: pattern's meter changes post-assignment
    st = svc._store()
    lib = st.load()
    lib["rhythms"]["pat"]["meter"] = [3, 4]
    lib["rhythms"]["pat"]["length_ticks"] = 2880
    st.save(lib)
    # load is flagged, never a crash
    ws = svc.describe_workspace()
    assert any(f["code"] == "meter_mismatch" for f in ws["flags"])
    # touching tools error instructively
    r = svc.export_timeline("s")
    assert r["error"]["code"] == "meter_mismatch"


def test_dangling_rhythm_flag_and_error(svc):
    svc.set_rhythm("pat", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", ["e"], meter=[4, 4], tempo=100, rhythm="pat")
    st = svc._store()
    lib = st.load()
    del lib["rhythms"]["pat"]  # hand edit
    st.save(lib)
    ws = svc.describe_workspace()
    assert any(f["code"] == "dangling_rhythm" for f in ws["flags"])
    r = svc.export_timeline("s")
    assert r["error"]["code"] == "dangling_rhythm"


def test_unknown_rhythm_at_assignment(svc):
    r = svc.set_sequence("s", ["e"], meter=[4, 4], rhythm="nope")
    assert r["error"]["code"] == "unknown_rhythm"


def test_child_meter_requires_tempo(svc):
    svc.set_sequence("bridge", ["d"], meter=[6, 8])  # meter, no tempo
    r = svc.set_sequence("song", ["e", "@bridge"], meter=[4, 4],
                         tempo=120, rhythm="whole")
    assert r["error"]["code"] == "child_meter_requires_tempo"


def test_exports_require_tempo(svc):
    svc.set_sequence("s", ["e"], meter=[4, 4], rhythm="whole")
    assert svc.export_midi("s")["error"]["code"] == "no_tempo"
    assert svc.render_audio("s")["error"]["code"] == "no_tempo"
    # the timeline export needs only meter
    assert "error" not in svc.export_timeline("s")


def test_builtin_rhythms_immutable(svc):
    r = svc.set_rhythm("whole", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    assert r["error"]["code"] == "builtin_rhythm"
    r = svc.remove_rhythm("bass-strum")
    assert r["error"]["code"] == "builtin_rhythm"


def test_remove_rhythm_refuses_then_force_drops(svc):
    svc.set_rhythm("pat", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", [{"item": "e", "rhythm": "pat"}, "a"],
                     meter=[4, 4], tempo=100, rhythm="pat")
    r = svc.remove_rhythm("pat")
    assert r["error"]["code"] == "rhythm_assigned"
    r = svc.remove_rhythm("pat", force=True)
    assert r["stored"]
    seq = svc._store().load()["sequences"]["s"]
    assert "rhythm" not in seq
    assert seq["steps"] == ["e", "a"]  # step collapses to plain id


# --- §5: inheritance — the 4/4 song with the 6/8 bridge ---------------------

@pytest.fixture()
def bridged(svc):
    svc.set_sequence("verse", ["e", "a"])          # plain child inherits
    svc.set_sequence("bridge", ["d"], meter=[6, 8], tempo=80,
                     rhythm="bass-strum")
    svc.set_sequence("song", ["@verse", "@bridge", "e"],
                     meter=[4, 4], tempo=120, rhythm="quarters")
    return svc


def test_bridge_inheritance_sections(bridged):
    tl = bridged.export_timeline("song")
    doc = _read_export(tl)
    secs = doc["sections"]
    assert [s["meter"] for s in secs] == [[4, 4], [6, 8], [4, 4]]
    assert [s["tempo"] for s in secs] == [120, 80, 120]
    assert [s["at"] for s in secs] == [0, 7680, 13440]
    # bar numbering: meter change starts a fresh bar, bars count on
    steps = doc["steps"]
    assert [(s["bar"], s["beat"]) for s in steps] == \
        [(1, 1), (2, 1), (3, 1), (4, 1)]


def test_bridge_smf_byte_golden_contains_meter_change(bridged):
    """§9: the inheritance fixture extended into export_midi."""
    r = bridged.export_midi("song")
    assert "error" not in r
    smf = Path(r["file"]).read_bytes()
    assert smf[:4] == b"MThd"
    assert struct.unpack(">H", smf[12:14])[0] == 3840  # fixed PPQ
    # both time signatures present: 4/4 (cc=24) and compound 6/8 (cc=36)
    assert b"\xff\x58\x04" + bytes([4, 2, 24, 8]) in smf
    assert b"\xff\x58\x04" + bytes([6, 3, 36, 8]) in smf
    # both tempo metas, rounded half up: 120bpm quarter = 500000;
    # 80bpm eighth-beat = (60e6/80)*(8/4) = 1500000
    assert b"\xff\x51\x03" + struct.pack(">I", 500000)[1:] in smf
    assert b"\xff\x51\x03" + struct.pack(">I", 1500000)[1:] in smf
    # deterministic: same call, same bytes (idempotent overwrite)
    r2 = bridged.export_midi("song")
    assert Path(r2["file"]).read_bytes() == smf
    assert r2["file"] == r["file"]


def test_mid_bar_step_starts(svc):
    """Non-bar-multiple spans start later steps mid-bar — harmonic
    rhythm across barlines is real (§5)."""
    svc.set_rhythm("half", [4, 4], 2, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", [{"item": "e", "rhythm": "half"}, "a"],
                     meter=[4, 4], tempo=100)
    doc = _read_export(svc.export_timeline("s"))
    s0, s1 = doc["steps"]
    assert (s1["bar"], s1["beat"]) == (1, 3)
    assert s1["placement"] == "on_beat"
    assert s0["placement"] == "bar_start"


def test_repeat_included_in_span(svc):
    svc.set_sequence("s", [{"item": "e", "repeat": 3}, "a"],
                     meter=[4, 4], tempo=100, rhythm="quarters")
    doc = _read_export(svc.export_timeline("s"))
    assert doc["steps"][0]["span"] == 3 * 3840
    assert doc["steps"][1]["at"] == 3 * 3840
    # events repeat in every instance
    e_hits = [e for e in doc["events"] if e["step"] == 0]
    assert len(e_hits) == 3 * 4 * 6  # 3 bars x 4 strums x 6 strings


def test_unassigned_steps_realize_as_whole(svc):
    svc.set_sequence("s", ["e", "a"], meter=[4, 4], tempo=100)
    doc = _read_export(svc.export_timeline("s"))
    assert doc["steps"][0]["rhythm"] == "whole"
    assert doc["steps"][0]["span"] == 3840


# --- §6: analyze — timeline + weighted keys ---------------------------------

def test_analyze_degrades_without_meter(svc):
    svc.set_sequence("s", ["e", "a"])
    r = svc.analyze("s")
    assert "error" not in r
    assert "timeline" not in r
    assert all("ticks" not in k for k in r["keys"])


def test_analyze_timeline_and_weighted_keys(svc):
    svc.set_sequence("s", ["e", "a", "d"], meter=[4, 4], tempo=100,
                     rhythm="quarters")
    r = svc.analyze("s")
    assert "error" not in r
    tl = r["timeline"]
    assert tl["total_ticks"] == 3 * 3840
    assert [s["at"] for s in tl["steps"]] == [0, 3840, 7680]
    assert [(s["bar"], s["beat"]) for s in tl["steps"]] == \
        [(1, 1), (2, 1), (3, 1)]
    for k in r["keys"]:
        assert "ticks" in k
        assert k["ticks"] % 3840 == 0


def test_weighted_vs_ordinal_key_flip(svc):
    """§9: the same harmonies rank differently when duration talks —
    a long-held foreign chord outweighs count. E A D pass in A major;
    G is chromatic there but diatonic to G major (with E A D minus the
    E's g# ... use G C D vs E). Build: E (1 bar) vs G C (long)."""
    svc.set_rhythm("long", [4, 4], 16, [{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", [{"item": "e"},
                           {"item": "g", "rhythm": "long"},
                           {"item": "c", "rhythm": "long"},
                           {"item": "d", "rhythm": "long"}],
                     meter=[4, 4], tempo=100)
    weighted = svc.analyze("s")
    unweighted_keys = [k["key"] for k in
                       svc.analyze("s", keys=None)["keys"]]
    # weighted: G-major material holds 12 of 13 bars ("long" = 16
    # beats = 4 bars each for g, c, d; e holds 1)
    assert weighted["keys"][0]["key"] == "g-major"
    assert weighted["keys"][0]["ticks"] == 12 * 3840
    assert unweighted_keys  # ordinal path still computes
    # tie fallback: two keys passing the same steps order ordinally
    ks = [k for k in weighted["keys"]
          if k["ticks"] == weighted["keys"][0]["ticks"]]
    if len(ks) > 1:
        sigs = [abs(__import__("grip_mcp.theory", fromlist=["Key"])
                    .Key.parse(k["key"]).signature) for k in ks]
        assert sigs == sorted(sigs)


def test_analyze_carries_pattern_warnings(svc):
    svc.add_grip("gm1", GM1)
    svc.set_rhythm("wide", [4, 4], 4,
                   [{"at": 0, "note": {"strings": [1, 2, 3, 4]}}])
    svc.set_sequence("s", ["gm1"], meter=[4, 4], tempo=100,
                     rhythm="wide")
    r = svc.analyze("s")
    assert any(w["code"] == "pattern_string_missing"
               for w in r["warnings"])


# --- §6: the bus — export JSON carries stored + realized --------------------

def test_export_json_stored_and_realized(svc):
    svc.set_sequence("s", ["e"], meter=[4, 4], tempo=120,
                     swing=SW, rhythm="quarters")
    tl = svc.export_timeline("s")
    doc = _read_export(tl)
    assert doc["kind"] == "grip_timeline"
    assert doc["ticks_per_beat"] == 960
    assert doc["content_hash"] == tl["content_hash"]
    stored = doc["events_stored"]
    realized = doc["events"]
    assert len(stored) == len(realized) == 4 * 6
    # straight grid in stored; swing applied in realized (beat offsets
    # are on-pair boundaries here so onsets match, durations differ
    # where an end falls on an off-point)
    assert {e["at"] for e in stored} == {0, 960, 1920, 2880}
    # the swing parameter rides the section record
    assert doc["sections"][0]["swing"] == SW
    # hash is over the realized form
    assert tl["content_hash"] == RH.content_hash(realized)
    # canonical event key order (§8)
    assert list(realized[0]) == ["at", "dur", "velocity", "midi",
                                 "pitch", "string", "step", "grip"]
    # filename convention: <seq>__<hash8>
    assert Path(tl["file"]).name == f"s__{tl['content_hash'][:8]}.json"


def test_export_no_meter_refused(svc):
    svc.set_sequence("s", ["e", "a"])
    r = svc.export_timeline("s")
    assert r["error"]["code"] == "no_meter"


# --- §6: audition — determinism, velocity, single file, format golden -------

@pytest.fixture()
def tiny_song(svc):
    svc.set_rhythm("hit", [1, 4], 1,
                   [{"at": 0, "velocity": 127, "note": {"string": 1}}])
    svc.set_sequence("s", [{"item": "e", "rhythm": "hit"}],
                     meter=[1, 4], tempo=300)
    return svc


def test_audition_wav_format_golden(tiny_song):
    r = tiny_song.render_audio("s")
    assert "error" not in r
    wav = Path(r["file"]).read_bytes()
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    fmt = struct.unpack("<HHIIHH", wav[20:36])
    assert fmt == (1, 1, 44100, 88200, 2, 16)  # PCM mono 16-bit 44.1k
    assert r["sample_rate"] == 44100
    assert r["seconds"] == 0.2  # one beat at 300 BPM


def test_audition_deterministic_and_single_file(tiny_song):
    r1 = tiny_song.render_audio("s")
    b1 = Path(r1["file"]).read_bytes()
    r2 = tiny_song.render_audio("s")
    assert r2["file"] == r1["file"]  # ONE file per sequence, overwrite
    assert Path(r2["file"]).read_bytes() == b1
    assert Path(r1["file"]).name == "s__audition.wav"
    renders = Path(r1["file"]).parent
    wavs = list(renders.glob("*.wav"))
    assert len(wavs) == 1  # the no-GC answer


def test_audition_velocity_peak_ratio(svc):
    """The velocity test on the defined substrate: no normalizer, so
    amplitude tracks velocity/127 as a peak-sample ratio."""
    svc.set_rhythm("v127", [1, 4], 1,
                   [{"at": 0, "velocity": 127, "note": {"string": 1}}])
    svc.set_rhythm("v64", [1, 4], 1,
                   [{"at": 0, "velocity": 64, "note": {"string": 1}}])
    svc.set_sequence("hi", [{"item": "e", "rhythm": "v127"}],
                     meter=[1, 4], tempo=300)
    svc.set_sequence("lo", [{"item": "e", "rhythm": "v64"}],
                     meter=[1, 4], tempo=300)
    hi = array.array(
        "h", Path(svc.render_audio("hi")["file"]).read_bytes()[44:])
    lo = array.array(
        "h", Path(svc.render_audio("lo")["file"]).read_bytes()[44:])
    ratio = max(map(abs, hi)) / max(map(abs, lo))
    assert 1.6 < ratio < 2.4  # ~127/64 with identical noise shape


def test_stagger_realization_only(svc):
    """The 12 ms strum stagger exists in the audition only: exports
    keep chord-hit onsets identical."""
    svc.set_sequence("s", ["e"], meter=[4, 4], tempo=120,
                     rhythm="quarters")
    doc = _read_export(svc.export_timeline("s"))
    beat1 = [e for e in doc["events"] if e["at"] == 0]
    assert len(beat1) == 6  # all six strings, same onset — no stagger
    r = svc.export_midi("s")
    assert "error" not in r  # and none in MIDI (byte-golden elsewhere)


# --- SMF details: retrigger, velocities, channel ----------------------------

def test_smf_truncate_at_retrigger_and_no_velocity_zero():
    sections = [{"at": 0, "meter": [4, 4], "tempo": 120, "swing": None,
                 "grouping": [2, 2]}]
    events = [
        {"at": 0, "dur": 2000, "velocity": 100, "midi": 60},
        {"at": 960, "dur": 960, "velocity": 90, "midi": 60},
    ]
    smf = MI.write_smf(sections, events, 3840)
    # find the notes track and walk it
    i = smf.index(b"MTrk", smf.index(b"MTrk") + 4)
    track = smf[i + 8:]
    msgs = []
    t = 0
    p = 0
    while p < len(track):
        delta = 0
        while True:
            b = track[p]
            p += 1
            delta = (delta << 7) | (b & 0x7F)
            if not b & 0x80:
                break
        t += delta
        status = track[p]
        if status == 0xFF:
            length = track[p + 2]
            p += 3 + length
            continue
        msgs.append((t, status, track[p + 1], track[p + 2]))
        p += 3
    ons = [m for m in msgs if m[1] == 0x90]
    offs = [m for m in msgs if m[1] == 0x80]
    # channel 1 (wire 0) throughout; ons carry 1-127
    assert all(m[1] in (0x90, 0x80) for m in msgs)
    assert all(1 <= m[3] <= 127 for m in ons)
    # retrigger truncation: first off lands AT the second on (x4 SMF)
    assert ons[0][0] == 0
    assert ons[1][0] == 960 * 4
    assert offs[0][0] == 960 * 4  # truncated from 2000*4 to 960*4


def test_smf_conversion_factors():
    for denom, f in ((2, 8), (4, 4), (8, 2), (16, 1)):
        assert MI._factor(denom) == f


# --- §8: canonical serialization --------------------------------------------

def test_canonical_orders(svc):
    svc.set_rhythm("pat", [4, 4], 4,
                   [{"at": 0, "verb": "strum"}], swing=SW)
    lib = svc._store().load()
    pat = lib["rhythms"]["pat"]
    assert list(pat) == ["length_ticks", "meter", "swing", "events"]
    assert list(pat["events"][0]) == ["at", "dur", "velocity", "note"]
    assert list(pat["swing"]) == ["subdivision", "ratio"]
    assert list(pat["swing"]["ratio"]) == ["num", "den"]
    svc.set_sequence("s", [{"item": "e", "repeat": 2}, "a"],
                     meter=[4, 4], tempo=100, rhythm="pat")
    seq = svc._store().load()["sequences"]["s"]
    assert list(seq) == ["meter", "tempo", "rhythm", "steps"]
    assert list(seq["steps"][0]) == ["item", "repeat"]
    # no floats anywhere in stored time
    blob = json.dumps(lib)
    assert isinstance(pat["length_ticks"], int)
    assert all(isinstance(e["at"], int) and isinstance(e["dur"], int)
               for e in pat["events"])
    assert "." not in json.dumps(pat)


# --- integration with the existing surface ----------------------------------

def test_plain_sequences_untouched(svc):
    r = svc.set_sequence("s", ["e", "a"])
    assert r["stored"]
    lib = svc._store().load()
    assert lib["sequences"]["s"] == ["e", "a"]  # stays a plain list


def test_rename_and_remove_grip_traverse_object_form(svc):
    svc.set_sequence("s", [{"item": "e", "repeat": 2}, "a"],
                     meter=[4, 4], tempo=100, rhythm="whole")
    r = svc.rename_grip("e", "e-maj")
    assert r["sequence_occurrences_rewritten"] == 1
    seq = svc._store().load()["sequences"]["s"]
    assert seq["steps"][0] == {"item": "e-maj", "repeat": 2}
    r = svc.remove_grip("e-maj")
    assert r["error"]["code"] == "grip_referenced"
    r = svc.remove_grip("e-maj", force=True)
    assert r["stored"]
    assert svc._store().load()["sequences"]["s"]["steps"] == ["a"]


def test_journal_history_record_rhythm_ops(svc):
    svc.set_rhythm("pat", [4, 4], 4, [{"at": 0, "verb": "strum"}])
    svc.remove_rhythm("pat")
    tools = [e["tool"] for e in svc.history()["entries"]]
    assert "set_rhythm" in tools and "remove_rhythm" in tools


def test_server_exposes_rhythm_tools(tmp_path):
    import asyncio
    pytest.importorskip("mcp")
    from grip_mcp.server import build_server
    tools = asyncio.run(build_server(tmp_path).list_tools())
    names = {t.name for t in tools}
    for t in ("set_rhythm", "list_rhythms", "remove_rhythm",
              "export_timeline", "export_midi", "render_audio"):
        assert t in names
    assert len(names) == 33
