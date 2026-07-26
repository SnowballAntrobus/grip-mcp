"""The V1 acceptance test (DESIGN §11, final row): the full workflow, in
order, against the real service — no optional deps, unconditional CI.

set_project(create=true) -> empty-read -> add_grip x Set A (one with
chosen, one bulk with render:false) -> set_sequence -> render(sequence)
-> identify(Q, context_key='e-minor', render=true) -> set_reading
(valid, ambiguous, miss) -> transpose(save_as) with covariant chosen ->
external-edit simulation.

The library it builds is the Gm/Em song the fixtures came from — the
doc's shipping note made executable.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp.service import GripService

X = None
SET_A_GRIPS = {
    "gm-o":  ([3, 1, X, X, X, X], None),
    "pass":  ([5, X, X, 3, X, X], None),
    "gm-1":  ([X, X, 8, 7, 8, X], "Gm"),      # the one with chosen
    "b5":    ([X, 2, 4, X, X, X], None),
}


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """One service instance carried through the whole acceptance flow."""
    root = tmp_path_factory.mktemp("acceptance")
    svc = GripService(root)
    return {"svc": svc, "root": root}


def test_01_create_gate_then_confirmed_create(flow):
    svc = flow["svc"]
    refused = svc.set_project("gm-em-song")
    assert refused["error"]["code"] == "unknown_project"
    r = svc.set_project("gm-em-song", create=True)
    assert r["created"] is True
    assert not (flow["root"] / "gm-em-song").exists()


def test_02_empty_read(flow):
    r = flow["svc"].describe_workspace()
    assert r["counts"] == {"grips": 0, "sequences": 0}
    assert r["default_tuning"] == "standard"
    assert "standard" in r["tunings"]
    assert not (flow["root"] / "gm-em-song").exists()  # reads litter nothing


def test_03_capture_set_a(flow):
    svc = flow["svc"]
    # One full-fat capture with chosen and the default-on render:
    strings, chosen = SET_A_GRIPS["gm-1"]
    r = svc.add_grip("gm-1", strings, fingers=[X, X, 2, 1, 3, X],
                     label="Gm first inversion", tags=["intro"],
                     chosen=chosen, render=True)
    assert r["stored"] is True
    assert r["chosen"] == "Gm/Bb"
    assert r["top"] == "Bb6"
    assert r["resolved_pitches"] == ["E2", "A2", "D3", "G3", "B3", "E4"]
    assert Path(r["render"]["files"]["png"]).exists()
    assert set(r["render"]["files"]) == {"png"}  # PNG only
    # Bulk capture: render=false per grip (§6.3 idiom):
    for gid, (strings, chosen) in SET_A_GRIPS.items():
        if gid == "gm-1":
            continue
        r = svc.add_grip(gid, strings, chosen=chosen, render=False)
        assert r["stored"] is True and "render" not in r
    # First write bootstrapped everything in one step:
    grip_dir = flow["root"] / "gm-em-song" / "grip"
    assert (grip_dir / "library.json").exists()
    assert (grip_dir / "derived.json").exists()
    assert (grip_dir / ".gitignore").read_text() == "derived.json\n"


def test_04_sequence_and_strip_render(flow):
    svc = flow["svc"]
    r = svc.set_sequence("intro", ["gm-o", "pass", "gm-1", "b5"])
    assert r["stored"] is True
    rr = svc.render(sequence="intro", title="intro")
    assert Path(rr["files"]["png"]).name.startswith("intro__")
    assert Path(rr["files"]["png"]).exists()
    again = svc.render(sequence="intro", title="intro")
    assert again["files"] == rr["files"]   # idempotent overwrite


def test_05_identify_q_in_e_minor_with_render(flow):
    svc = flow["svc"]
    r = svc.identify([2, 2, 2, X, X, X], context_key="e-minor",
                     render=True)
    assert r["mode"] == "context"
    assert r["top"] == "F#q4"
    assert r["candidates"][1]["name"] == "Bsus4/F#"
    assert r["decided_at"] == "R1"
    assert Path(r["render"]["files"]["png"]).name.startswith("adhoc__")
    # Preview stores nothing:
    assert set(flow["svc"].list_grips()["grips"]) == set(SET_A_GRIPS)


def test_06_set_reading_valid_ambiguous_miss(flow):
    svc = flow["svc"]
    svc.add_grip("q", [2, 2, 2, X, X, X], render=False)
    valid = svc.set_reading("q", "Bsus4")
    assert valid["stored"] is True and valid["chosen"] == "Bsus4/F#"
    ambiguous = svc.set_reading("q", "Bsus")
    assert ambiguous["error"]["code"] == "chosen_ambiguous"
    miss = svc.set_reading("q", "Cmaj7")
    assert miss["error"]["code"] == "chosen_miss"
    assert svc.get_grip("q")["chosen"] == "Bsus4/F#"  # valid one survives


def test_07_transpose_save_as_covariant(flow):
    svc = flow["svc"]
    r = svc.transpose(2, id="gm-1", save_as="am-1")
    assert r["stored"] is True
    assert r["chosen"] == "Am/C"           # covariant re-derivation
    g = svc.get_grip("am-1")
    assert g["grip"]["derived_from"] == {"id": "gm-1", "semitones": 2}
    assert g["grip"]["tuning"] == "standard"


def test_08_external_edit_simulation(flow):
    svc = flow["svc"]
    libp = flow["root"] / "gm-em-song" / "grip" / "library.json"
    # A hand edit between calls is seen immediately (reads always fresh):
    lib = json.loads(libp.read_text())
    lib["grips"]["gm-1"]["tags"] = ["intro", "hand-edited"]
    libp.write_text(json.dumps(lib))
    r = svc.get_grip("gm-1")
    assert r["grip"]["tags"] == ["intro", "hand-edited"]
    # A corrupt hand edit errors instructively, crashes nothing, loses
    # nothing (the corrupt file stays for the user to fix):
    good = libp.read_text()
    libp.write_text("{broken json")
    r = svc.list_grips()
    assert r["error"]["code"] == "bad_json"
    libp.write_text(good)
    assert svc.get_grip("gm-1")["chosen"] == "Gm/Bb"


def test_09_resume_speaks_the_vocabulary(flow):
    """Session resume is one call and the LLM speaks the user's names."""
    svc2 = GripService(flow["root"])
    svc2.set_project("gm-em-song")
    r = svc2.describe_workspace()
    assert r["grips"]["gm-1"]["chosen"] == "Gm/Bb"
    assert r["grips"]["gm-1"]["stale"] is False
    assert r["grips"]["gm-1"]["named"] is True
    assert r["grips"]["q"]["chosen"] == "Bsus4/F#"
    assert r["sequences"]["intro"] == ["gm-o", "pass", "gm-1", "b5"]
    assert r["flags"] == []
