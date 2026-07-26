"""Feedback round 1 (manual shakedown, 2026-07-26): journal, mutation
history, song structures via @sequence references, hammer-on/pull-off
ornaments, working titles, thumb round-trip, octave-bearing labels,
digits-in-dots rendering, ~/grip_sessions default root."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import render as RD
from grip_mcp import store as S
from grip_mcp.service import GripService

GM1 = [None, None, 8, 7, 8, None]
Q = [2, 2, 2, None, None, None]


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("song", create=True)
    return s


# --- default root -----------------------------------------------------------

def test_default_root_is_grip_sessions(monkeypatch):
    monkeypatch.delenv("MUSIC_PROJECT_ROOT", raising=False)
    assert S.project_root().name == "grip_sessions"
    monkeypatch.setenv("MUSIC_PROJECT_ROOT", "/tmp/shared_music")
    assert str(S.project_root()) == "/tmp/shared_music"


# --- journal ----------------------------------------------------------------

def test_journal_roundtrip_and_resume(svc):
    r = svc.journal("the pass grip wants to resolve down", tags=["pass"])
    assert r["stored"] is True and r["journal"]["ts"]
    svc.journal("try the bridge in open C", tags=["bridge"])
    out = svc.list_journal()
    assert out["total"] == 2
    assert out["entries"][0]["entry"] == "try the bridge in open C"  # newest first
    by_tag = svc.list_journal(tag="pass")
    assert len(by_tag["entries"]) == 1
    # Recent entries resume with the workspace:
    ws = svc.describe_workspace()
    assert len(ws["journal_recent"]) == 2


def test_journal_bootstraps_namespace(svc, tmp_path):
    svc.journal("first note before any grip")
    grip_dir = tmp_path / "song" / "grip"
    assert (grip_dir / "journal.jsonl").exists()
    assert (grip_dir / "library.json").exists()      # consistent bootstrap
    assert (grip_dir / ".gitignore").exists()


def test_journal_corrupt_line_never_blocks(svc, tmp_path):
    svc.journal("good entry")
    jp = tmp_path / "song" / "grip" / "journal.jsonl"
    jp.write_text(jp.read_text() + "{corrupt\n")
    svc.journal("after corruption")
    out = svc.list_journal()
    assert out["total"] == 2


# --- mutation history -------------------------------------------------------

def test_history_records_every_mutation(svc):
    svc.add_grip("gm-1", GM1, chosen="Gm")
    svc.set_reading("gm-1", "Bb6")
    svc.set_sequence("intro", ["gm-1"])
    svc.rename_grip("gm-1", "gm-first")
    h = svc.history()
    tools = [e["tool"] for e in h["entries"]]
    assert tools == ["rename_grip", "set_sequence", "set_reading",
                     "add_grip"]                     # newest first
    assert h["entries"][-1]["detail"]["chosen"] == "Gm/Bb"
    assert h["entries"][0]["detail"] == {"was": "gm-1", "id": "gm-first"}


def test_reads_do_not_pollute_history(svc):
    svc.add_grip("g", GM1)
    svc.get_grip("g")
    svc.describe_workspace()
    svc.list_grips()
    h = svc.history()
    assert [e["tool"] for e in h["entries"]] == ["add_grip"]


# --- song structure: @sequence references -----------------------------------

def test_song_structure_composes_without_duplication(svc):
    svc.add_grip("a", GM1)
    svc.add_grip("b", Q)
    svc.add_grip("c", [None, 2, 4, None, None, None])
    svc.set_sequence("verse", ["a", "b"])
    svc.set_sequence("chorus", ["c"])
    r = svc.set_sequence("full-song", ["@verse", "@chorus", "@verse"])
    assert r["flattened"] == ["a", "b", "c", "a", "b"]
    # Edit the section once; the structure follows:
    svc.set_sequence("verse", ["b", "a"])
    ls = svc.list_sequences()["sequences"]
    assert ls["full-song"]["flattened"] == ["b", "a", "c", "b", "a"]


def test_sequence_cycle_refused(svc):
    svc.add_grip("a", GM1)
    svc.set_sequence("x", ["a"])
    svc.set_sequence("y", ["@x"])
    r = svc.set_sequence("x", ["a", "@y"])
    assert r["error"]["code"] == "sequence_cycle"
    # And the cyclic write did not land:
    assert svc.list_sequences()["sequences"]["x"]["items"] == ["a"]


def test_remove_referenced_sequence_lifecycle(svc):
    svc.add_grip("a", GM1)
    svc.set_sequence("verse", ["a"])
    svc.set_sequence("full-song", ["@verse", "a"])
    r = svc.remove_sequence("verse")
    assert r["error"]["code"] == "sequence_referenced"
    r = svc.remove_sequence("verse", force=True)
    assert r["stored"] and r["dereferenced"] == ["full-song"]
    assert svc.list_sequences()["sequences"]["full-song"]["items"] == ["a"]


def test_render_flattens_structure(svc):
    svc.add_grip("a", GM1)
    svc.add_grip("b", Q)
    svc.set_sequence("verse", ["a", "b"])
    svc.set_sequence("full-song", ["@verse", "@verse"])
    r = svc.render(sequence="full-song")
    assert r["grips"] == ["a", "b", "a", "b"]
    assert Path(r["files"]["png"]).name.startswith("full-song__")


def test_unknown_at_reference_refused(svc):
    svc.add_grip("a", GM1)
    r = svc.set_sequence("s", ["a", "@nothere"])
    assert r["error"]["code"] == "unknown_sequence"


# --- ornaments: hammer-on / pull-off ----------------------------------------

def test_ornaments_stored_and_annotation_only(svc):
    r = svc.add_grip(
        "ham", [0, 2, 2, None, None, None],
        ornaments=[{"string": 1, "to": 2, "type": "hammer"}],
    )
    assert r["stored"] is True
    g = svc.get_grip("ham")
    assert g["grip"]["ornaments"] == [{"string": 1, "to": 2,
                                       "type": "hammer"}]
    # Annotation-only: identity comes from strings alone.
    assert g["midi"] == [40, 47, 52]   # E2 B2 E3 — no F#2 from the hammer


def test_ornament_validation(svc):
    bad = [
        ([{"string": 9, "to": 2, "type": "hammer"}], "out of range"),
        ([{"string": 4, "to": 2, "type": "hammer"}], "muted"),
        ([{"string": 2, "to": 1, "type": "hammer"}], "must land above"),
        ([{"string": 2, "to": 5, "type": "pull"}], "must land below"),
        ([{"string": 2, "to": 3, "type": "slide"}], "hammer, pull"),
    ]
    for ornaments, msg in bad:
        r = svc.add_grip("x", [0, 2, 2, None, None, None],
                         ornaments=ornaments)
        assert "error" in r and msg in r["error"]["detail"], msg


def test_ornaments_render_with_window(svc):
    g = {"frets": [0, 2, 2, None, None, None], "name": "E5",
         "capo": 0, "ornaments": [{"string": 0, "to": 4,
                                   "type": "hammer"}]}
    out = RD.render_chart([g], {"labels": "none"})
    assert 'stroke-width="1.6"' in out["svg"]        # hollow target dot
    # Window covers the ornament target:
    assert RD.fret_window([0, 2, 2, None, None, None], [4]) == (1, 4)
    assert RD.fret_window([None, None, 8, 7, 8, None], [11])[1] == 5


def test_update_grip_validates_ornaments(svc):
    svc.add_grip("g", [0, 2, 2, None, None, None])
    r = svc.update_grip("g", {"ornaments": [{"string": 1, "to": 3,
                                             "type": "hammer"}]})
    assert r["stored"] is True
    r = svc.update_grip("g", {"ornaments": [{"string": 4, "to": 3,
                                             "type": "hammer"}]})
    assert "muted" in r["error"]["detail"]


# --- working titles ---------------------------------------------------------

def test_working_title_formalized(svc):
    svc.add_grip("mystery", Q, label="the spooky one")
    lg = svc.list_grips()["grips"]["mystery"]
    assert lg["named"] is False and lg["label"] == "the spooky one"
    svc.set_reading("mystery", "Bsus4")
    assert svc.list_grips()["grips"]["mystery"]["named"] is True
    ws = svc.describe_workspace()
    assert ws["grips"]["mystery"]["named"] is True


# --- thumb round-trip -------------------------------------------------------

def test_thumb_round_trip_capture_and_render(svc):
    r = svc.add_grip("thumb-b5", [7, 9, 9, None, None, None],
                     fingers=[0, 3, 4, None, None, None], render=True)
    assert r["stored"] is True and r["warnings"] == []
    # And a voicing suggestion with a thumb feeds straight back in:
    v = svc.find_voicings("F", constraints={"allow_thumb": True})
    thumbed = [x for x in v["voicings"] if x["thumb"]]
    for x in thumbed[:1]:
        rr = svc.add_grip("f-thumb", x["strings"], fingers=x["fingers"])
        assert rr["stored"] is True


def test_thumb_renders_as_t():
    g = {"frets": [7, 9, 9, None, None, None],
         "fingers": [0, 3, 4, None, None, None], "name": "B5", "capo": 0}
    svg = RD.render_chart([g], {"labels": "none"})["svg"]
    t_path = RD._font()["paths"]["T"]
    assert t_path[:24] in svg                        # the T glyph drew


# --- octave-bearing labels + digits in dots ---------------------------------

def test_note_labels_carry_octaves(svc):
    svc.add_grip("gm-1", GM1, fingers=[None, None, 2, 1, 3, None])
    r = svc.render(ids=["gm-1"], labels="notes")
    # Rebuild the renderable to inspect labels directly:
    out = svc.get_grip("gm-1")
    assert out["candidates"][0]["pitches"] == ["Bb3", "D4", "G4"]
    # The render hash must differ from an octave-less world only via
    # content; assert the glyph for a digit-bearing label exists:
    svg_probe = RD.draw_text(0, 0, "Bb3", 10, "#000")
    assert "path" in svg_probe


def test_digits_draw_inside_dots():
    g = {"frets": GM1, "fingers": [None, None, 2, 1, 3, None],
         "string_labels": [None, None, "Bb3", "D4", "G4", None],
         "name": "Gm/Bb", "capo": 0}
    with_f = RD.render_chart([g], {"labels": "notes"})["svg"]
    without = RD.render_chart([dict(g, fingers=None)],
                              {"labels": "notes"})["svg"]
    assert len(with_f) > len(without)               # digits added paths
    assert with_f != without
