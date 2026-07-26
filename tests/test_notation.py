"""Notation tests (NOTATION_DESIGN ratified rev 2 §6): render goldens,
the round-trip property with its true precondition and direction,
every named fallback reason, the accent micro-grammar, [12]-vs-12,
refusals with their messages, and the service surfacing (echo-verify
at definition, exact-meter echo at attachment, labeled built-in
previews)."""

import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import notation as NT
from grip_mcp import rhythm as RH
from grip_mcp.service import GripService

E_MAJ = [0, 2, 2, 1, 0, 0]
AM = [None, 0, 2, 2, 1, 0]
SW = {"subdivision": 480, "ratio": {"num": 2, "den": 3}}


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("notation-test", create=True)
    s.add_grip("e", E_MAJ)
    s.add_grip("a", AM)
    return s


def _pat(length, meter, events, **extra):
    return {"length_ticks": length, "meter": meter, **extra,
            "events": events}


def _expand(auth, length, meter, grouping=None):
    return RH.expand_events(auth, length, meter,
                            grouping or RH.default_grouping(meter[0]))


def _roundtrip(pat):
    p = NT.parse_notation(NT.render_notation(pat))
    g = (p.get("grouping") or pat.get("grouping")
         or RH.default_grouping(p["meter"][0]))
    assert p["meter"] == pat["meter"]
    assert p["length_ticks"] == pat["length_ticks"]
    if "swing" in pat:
        assert p.get("swing") == pat["swing"]
    re = RH.expand_events(p["events"], p["length_ticks"], p["meter"], g)
    assert re == pat["events"]


# --- canonical fractions ----------------------------------------------------

def test_frac_str_canonical():
    assert NT.frac_str(Fraction(7, 2)) == "7/2" or True  # see below
    # proper mixed form, lowest terms:
    assert NT.frac_str(Fraction(7, 2)) == "3+1/2"
    assert NT.frac_str(Fraction(1, 3)) == "1/3"
    assert NT.frac_str(Fraction(4)) == "4"
    assert NT.frac_str(Fraction(640, 960)) == "2/3"
    assert NT.parse_frac("2+1/3", "x") == Fraction(7, 3)
    assert NT.parse_frac("1/2", "x") == Fraction(1, 2)
    assert NT.parse_frac("4", "x") == Fraction(4)


# --- render goldens ---------------------------------------------------------

def test_swung_bass_demo_golden():
    pat = _pat(3840, [4, 4], _expand(
        [{"at": 0, "verb": "bass"}, {"at": "1/2", "verb": "strum"},
         {"at": 1, "verb": "strum"}, {"at": 2, "verb": "bass"},
         {"at": "5/2", "verb": "strum"}, {"at": 3, "verb": "strum"}],
        3840, [4, 4]), swing=SW)
    assert NT.render_notation(pat) == (
        "4/4 swing 2:3 @ 1/2\n"
        "# 1 & 2 & 3 & 4 &\n"
        "B D D . B D D ."
    )


def test_builtin_goldens_accent_plain():
    """Built-ins expand with map velocities, so their grids carry no
    accent ink at all — the design paying for itself."""
    for meter, counting in (([4, 4], "# 1 2 3 4"),
                            ([3, 4], "# 1 2 3"),
                            ([6, 8], "# 1 2 3 4 5 6"),
                            ([7, 8], "# 1 2 3 4 5 6 7")):
        g = RH.default_grouping(meter[0])
        pat = RH.builtin_pattern("quarters", meter, g)
        text = NT.render_notation(pat)
        header, count_row, bar = text.split("\n")
        assert header == f"{meter[0]}/{meter[1]}"
        assert count_row == counting
        assert bar == " ".join(["D"] * meter[0])
        assert ">" not in text and "(" not in text and "@" not in text
    bs = NT.render_notation(RH.builtin_pattern("bass-strum", [6, 8],
                                               [3, 3]))
    assert bs.split("\n")[2] == "B D D B D D"


def test_arp_and_whole_goldens():
    w = NT.render_notation(RH.builtin_pattern("whole", [4, 4], [2, 2]))
    assert w == "4/4\n# 1 2 3 4\nD . . ."
    a = NT.render_notation(RH.builtin_pattern("arp-up", [3, 4], [3]))
    assert a == "3/4\n# 1 2 3\nA . ."


def test_swing_straight_header_round_trip():
    pat = _pat(3840, [4, 4],
               _expand([{"at": 0, "verb": "strum"}], 3840, [4, 4]),
               swing=None)
    text = NT.render_notation(pat)
    assert "swing straight" in text.split("\n")[0]
    p = NT.parse_notation(text)
    assert "swing" in p and p["swing"] is None
    _roundtrip(pat)


def test_grouping_header_round_trip():
    pat = _pat(8 * 960, [8, 8],
               _expand([{"at": 0, "verb": "strum"},
                        {"at": 3, "verb": "strum"},
                        {"at": 6, "verb": "strum"}],
                       8 * 960, [8, 8], [3, 3, 2]),
               grouping=[3, 3, 2])
    text = NT.render_notation(pat)
    assert "grouping 3+3+2" in text.split("\n")[0]
    _roundtrip(pat)


def test_multibar_and_rest_bars():
    pat = _pat(2 * 3840, [4, 4], _expand(
        [{"at": 0, "verb": "strum"}], 2 * 3840, [4, 4]))
    text = NT.render_notation(pat)
    lines = text.split("\n")
    assert lines[2] == "D . . ."
    assert lines[3] == ". . . ."  # an all-'.' rest bar is legal
    _roundtrip(pat)
    p = NT.parse_notation("4/4\n. . . .\nD . . .")
    assert p["length_ticks"] == 2 * 3840
    assert p["events"][0]["at"] == "4"  # bar 2 beat 1 = beat 4 0-based


def test_counting_rows():
    pat = _pat(3840, [4, 4], _expand(
        [{"at": "1/4", "verb": "strum"}], 3840, [4, 4]))
    assert "# 1 e & a 2 e & a 3 e & a 4 e & a" in NT.render_notation(pat)
    pat = _pat(3840, [4, 4], _expand(
        [{"at": "1/3", "verb": "strum"}], 3840, [4, 4]))
    assert "# 1 t l 2 t l 3 t l 4 t l" in NT.render_notation(pat)
    pat = _pat(960, [1, 4], _expand(
        [{"at": "1/8", "verb": "strum"}], 960, [1, 4]))
    assert "# 1 . e . & . a ." in NT.render_notation(pat)


def test_accent_ink_and_escapes():
    ev = _expand([{"at": 0, "velocity": 76, "note": {"string": 1}},
                  {"at": 1, "velocity": 108, "note": {"string": 2}},
                  {"at": 2, "velocity": 93, "note": {"string": 3}},
                  {"at": 3, "note": {"string": 4}}],
                 3840, [4, 4])
    text = NT.render_notation(_pat(3840, [4, 4], ev))
    assert text.split("\n")[2] == "(1) >2 3@93 4"
    _roundtrip(_pat(3840, [4, 4], ev))


def test_redundant_ink_normalizes():
    """render-after-parse normalizes; the echo shows canonical form."""
    p = NT.parse_notation("4/4\n>D . (D) .")  # > at bar start = map
    ev = _expand(p["events"], 3840, [4, 4])
    assert ev[0]["velocity"] == 108
    text = NT.render_notation(_pat(3840, [4, 4], ev))
    assert text.split("\n")[2] == "D . (D) ."  # >D plain; ghost stays


def test_bracket_vocabulary_and_12_vs_bare_12():
    assert NT._parse_token("[12]")[0] == {"strings": [1, 2]}
    assert NT._parse_token("12")[0] == {"string": 12}
    assert NT._parse_token("[1,10,12]")[0] == {"strings": [1, 10, 12]}
    assert NT._parse_token("[135]^")[0] == {"strings": [1, 3, 5],
                                            "up": True}
    n, v = NT._parse_token(">[1,3,5]^")
    assert n == {"strings": [1, 3, 5], "up": True} and v == 108
    # render normalization: compact <= 9, comma beyond
    ev = _expand([{"at": 0, "note": {"strings": [1, 3, 5]}},
                  {"at": 1, "note": {"strings": [1, 10, 12]}},
                  {"at": 2, "note": {"string": 12}}], 3840, [4, 4])
    row = NT.render_notation(_pat(3840, [4, 4], ev)).split("\n")[2]
    assert row.split() == ["[135]", "[1,10,12]", "12", "."]
    _roundtrip(_pat(3840, [4, 4], ev))


# --- fallback reasons (all four, and in order) ------------------------------

def test_each_reason_exactly():
    base = {"at": 0, "dur": 960, "velocity": 108,
            "note": {"strings": "all"}}
    # off-grid onsets (sextuplet 160) — durations kept let-ring
    t = NT.render_notation(_pat(3840, [4, 4], [
        {**base, "dur": 160},
        {**base, "at": 160, "dur": 3680, "velocity": 76}]))
    assert "# off-grid onsets" in t and t.count("#") == 1
    # explicit durations only
    t = NT.render_notation(_pat(3840, [4, 4], [
        {**base, "dur": 480}]))
    assert "# explicit durations" in t and t.count("#") == 1
    # partial bar only
    t = NT.render_notation(_pat(3360, [4, 4], [
        {**base, "dur": 3360}]))
    assert "# partial bar" in t and t.count("#") == 1
    # simultaneous only
    t = NT.render_notation(_pat(3840, [4, 4], [
        {**base, "dur": 3840},
        {"at": 0, "dur": 3840, "velocity": 90,
         "note": {"string": "bass"}}]))
    assert "# simultaneous events" in t and t.count("#") == 1


def test_multi_reason_in_order():
    pat = _pat(3360, [4, 4], [
        {"at": 0, "dur": 1920, "velocity": 108,
         "note": {"string": "bass"}},
        {"at": 0, "dur": 960, "velocity": 88,
         "note": {"strings": [3, 4, 5]}},
        {"at": 1280, "dur": 320, "velocity": 76,
         "note": {"strings": "all"}}])
    t = NT.render_notation(pat)
    lines = t.split("\n")
    assert lines[1] == "# explicit durations"
    assert lines[2] == "# partial bar"
    assert lines[3] == "# simultaneous events"
    _roundtrip(pat)


def test_list_form_golden_and_length_fraction():
    pat = _pat(3360, [4, 4], [
        {"at": 0, "dur": 1920, "velocity": 108,
         "note": {"string": "bass"}},
        {"at": 1280, "dur": 320, "velocity": 76,
         "note": {"strings": "all"}}])
    t = NT.render_notation(pat)
    assert t.split("\n")[0] == "4/4 length 3+1/2"
    assert "@ 2+1/3 D dur 1/3" in t
    _roundtrip(pat)


# --- parse refusals ---------------------------------------------------------

def test_dotless_idiom_refused():
    with pytest.raises(RH.RhythmError) as e:
        NT.parse_notation("4/4\nD D U U D U")
    assert "ambiguous until dotted" in e.value.detail
    assert "[4, 8, 12, 16, 32]" in e.value.detail


def test_velocity_escape_range():
    for bad in ("D@0", "D@128"):
        with pytest.raises(RH.RhythmError) as e:
            NT._parse_token(bad)
        assert e.value.code == "bad_velocity"
        assert "note-off" in NT._parse_token.__doc__ or \
            "note-off" in e.value.detail


def test_mixed_accent_marks_refused():
    for bad in (">D@93", "(D@93)", ">(D)"):
        with pytest.raises(RH.RhythmError) as e:
            NT._parse_token(bad)
        assert "accent marks" in e.value.detail or \
            "ghost" in e.value.detail


def test_inconsistent_slot_counts():
    with pytest.raises(RH.RhythmError) as e:
        NT.parse_notation("4/4\nD . . .\nD . .")
    assert "slot counts" in e.value.detail


def test_unknown_tokens_and_headers():
    with pytest.raises(RH.RhythmError) as e:
        NT.parse_notation("4/4\nD X . .")
    assert "vocabulary" in e.value.detail
    with pytest.raises(RH.RhythmError) as e:
        NT.parse_notation("4/4 tempo 120\nD . . .")
    assert "unknown header token" in e.value.detail
    with pytest.raises(RH.RhythmError):
        NT.parse_notation("4/4 swing 2:3\nD . . .")  # missing @ sub


def test_comments_anywhere_and_pipes():
    p = NT.parse_notation(
        "# a note\n4/4\n# another\n| D . D . |\n# trailing")
    assert p["length_ticks"] == 3840
    assert len(p["events"]) == 2


def test_grid_length_header_agreement():
    p = NT.parse_notation("4/4 length 4\nD . . .")
    assert p["length_ticks"] == 3840
    with pytest.raises(RH.RhythmError) as e:
        NT.parse_notation("4/4 length 8\nD . . .")
    assert e.value.code == "notation_conflict"


# --- the round-trip fuzzer --------------------------------------------------

def test_round_trip_fuzz():
    """parse(render(p)) re-expands to exactly p for every
    grid-representable pattern — deterministic pseudo-random cases."""
    import random
    rng = random.Random(0xC0FFEE)
    notes = ([{"strings": "all"}, {"strings": "all", "up": True},
              {"string": "bass"}, {"arp": "up"}, {"arp": "down"}]
             + [{"string": n} for n in (1, 2, 5, 11)]
             + [{"strings": [1, 3]}, {"strings": [2, 10], "up": True}])
    for meter in ([4, 4], [3, 4], [6, 8], [7, 8], [1, 4], [5, 4]):
        for step in (960, 480, 320, 240, 120):
            for _ in range(4):
                bar = meter[0] * 960
                bars = rng.choice((1, 2))
                slots = bar // step * bars
                onsets = sorted(rng.sample(range(slots),
                                           min(rng.randrange(1, 6),
                                               slots)))
                auth = []
                for o in onsets:
                    ev = {"at": NT.frac_str(Fraction(o * step, 960)),
                          "note": rng.choice(notes)}
                    r = rng.random()
                    if r < 0.2:
                        ev["velocity"] = 108
                    elif r < 0.4:
                        ev["velocity"] = 76
                    elif r < 0.5:
                        ev["velocity"] = rng.randrange(1, 128)
                    auth.append(ev)
                length = bars * bar
                expanded = _expand(auth, length, meter)
                _roundtrip(_pat(length, meter, expanded))


# --- service surfacing ------------------------------------------------------

def test_set_rhythm_notation_input_and_echo(svc):
    r = svc.set_rhythm("swung", notation=(
        "4/4 swing 2:3 @ 1/2\n"
        "B D D . B D D ."))
    assert r["stored"], r
    assert r["notation"] == ("4/4 swing 2:3 @ 1/2\n"
                             "# 1 & 2 & 3 & 4 &\n"
                             "B D D . B D D .")
    pat = r["rhythm"]
    assert pat["length_ticks"] == 3840 and pat["swing"] == SW
    # events path still carries the echo
    r2 = svc.set_rhythm("plain", meter=[4, 4], length=4,
                        events=[{"at": 0, "verb": "strum"}])
    assert r2["notation"] == "4/4\n# 1 2 3 4\nD . . ."


def test_set_rhythm_notation_xor_events(svc):
    r = svc.set_rhythm("x", meter=[4, 4], length=4)
    assert r["error"]["code"] == "exactly_one_of"
    r = svc.set_rhythm("x", meter=[4, 4], length=4,
                       events=[{"at": 0, "verb": "strum"}],
                       notation="4/4\nD . . .")
    assert r["error"]["code"] == "exactly_one_of"


def test_notation_conflicts_per_field(svc):
    base = "4/4 swing 2:3 @ 1/2 grouping 2+2\nB D D . B D D ."
    ok = svc.set_rhythm("ok", notation=base, meter=[4, 4], length=4,
                        swing=SW, grouping=[2, 2])
    assert ok["stored"], ok  # agreement is fine
    for kwargs in ({"meter": [3, 4]}, {"length": 8},
                   {"swing": "straight"},
                   {"swing": {"subdivision": 240,
                              "ratio": {"num": 2, "den": 3}}},
                   {"grouping": [1, 3]}):
        r = svc.set_rhythm("bad", notation=base, **kwargs)
        assert r["error"]["code"] == "notation_conflict", (kwargs, r)


def test_list_rhythms_notation_and_builtin_previews(svc):
    svc.set_rhythm("pat", meter=[4, 4], length=4,
                   events=[{"at": 0, "verb": "strum"}])
    r = svc.list_rhythms()
    assert r["notation"]["pat"] == "4/4\n# 1 2 3 4\nD . . ."
    b = r["builtins"]
    assert "# in 4/4; adapts to the governing meter" in \
        b["whole"]["notation"]
    assert "notation_6_8" in b["bass-strum"]
    assert "# in 6/8" in b["bass-strum"]["notation_6_8"]
    assert b["bass-strum"]["notation_6_8"].split("\n")[-1] == \
        "B D D B D D"
    assert "notation_6_8" not in b["whole"]


def test_set_sequence_attachment_echo_exact_meter(svc):
    svc.set_rhythm("pat", meter=[4, 4], length=4,
                   events=[{"at": 0, "verb": "strum"}])
    r = svc.set_sequence("s", [{"item": "e", "rhythm": "bass-strum"},
                               "a"],
                         meter=[4, 4], tempo=100, rhythm="pat")
    assert set(r["notation"]) == {"pat", "bass-strum"}
    # built-in previews in the ACTUAL governing meter, no example label
    assert r["notation"]["bass-strum"] == \
        "4/4\n# 1 2 3 4\nB D B D"
    assert "# in 4/4" not in r["notation"]["bass-strum"]


def test_mixed_meter_echo_per_pattern_meter_pair(svc):
    """The same built-in previews per (pattern, governing meter): the
    6/8 child call echoes 6/8; the 4/4 parent call echoes 4/4."""
    svc.add_grip("d", [None, None, 0, 2, 3, 2])
    child = svc.set_sequence("bridge", ["d"], meter=[6, 8], tempo=80,
                             rhythm="bass-strum")
    assert child["notation"]["bass-strum"].split("\n")[-1] == \
        "B D D B D D"
    parent = svc.set_sequence("song", ["e", "@bridge"], meter=[4, 4],
                              tempo=120, rhythm="bass-strum")
    assert parent["notation"]["bass-strum"].split("\n")[-1] == \
        "B D B D"


def test_echo_scoped_to_this_call(svc):
    svc.set_rhythm("pat", meter=[4, 4], length=4,
                   events=[{"at": 0, "verb": "strum"}])
    svc.set_sequence("s", [{"item": "e", "rhythm": "pat"}],
                     meter=[4, 4], tempo=100)
    # a later call assigning only the default echoes only it
    r = svc.set_sequence("s2", ["a"], meter=[4, 4], tempo=100,
                         rhythm="whole")
    assert set(r["notation"]) == {"whole"}
    # no rhythm context -> no echo key
    r = svc.set_sequence("plain", ["e", "a"])
    assert "notation" not in r


def test_notation_round_trip_through_service(svc):
    """User writes notation; the stored pattern realizes identically
    to the events path."""
    svc.set_rhythm("by-notation", notation="4/4\nB . D . B . D .")
    svc.set_rhythm("by-events", meter=[4, 4], length=4, events=[
        {"at": 0, "verb": "bass"}, {"at": 1, "verb": "strum"},
        {"at": 2, "verb": "bass"}, {"at": 3, "verb": "strum"}])
    lib = svc._store().load()
    assert lib["rhythms"]["by-notation"]["events"] == \
        lib["rhythms"]["by-events"]["events"]
