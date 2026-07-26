"""Interaction tests (DESIGN §11): create-gate, first-write bootstrap,
fresh-project reads, default_tuning resolution + envelope echo +
lifecycle refusals, envelope warning codes each observable, transpose
fields, resume completeness, reservations, exactly-one-of, structured
errors."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp.service import GripService

GM1 = [None, None, 8, 7, 8, None]
Q = [2, 2, 2, None, None, None]


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("gm-em-song", create=True)
    return s


# --- envelope: every response carries the project ---------------------------

def test_every_response_carries_project(svc):
    for r in (svc.describe_workspace(), svc.list_grips(),
              svc.identify(Q), svc.list_projects()):
        assert r["project"] == "gm-em-song"


def test_no_project_is_instructive(tmp_path):
    s = GripService(tmp_path)
    r = s.identify(Q)
    assert r["error"]["code"] == "no_project"
    assert "set_project" in r["error"]["detail"]


# --- the create gate (§6.2): typo slug -> refusal, nothing on disk ----------

def test_create_gate_refuses_with_close_matches(tmp_path):
    s = GripService(tmp_path)
    s.set_project("gm-em-song", create=True)
    s.add_grip("gm-1", GM1, render=False)  # first write materializes it
    s2 = GripService(tmp_path)
    r = s2.set_project("gm-em-sog")  # typo
    assert r["error"]["code"] == "unknown_project"
    assert "gm-em-song" in r["error"]["detail"]
    assert s2.project is None
    assert not (tmp_path / "gm-em-sog").exists()


def test_confirmed_create_defers_to_first_write(tmp_path):
    s = GripService(tmp_path)
    r = s.set_project("new-idea", create=True)
    assert r["created"] is True
    assert not (tmp_path / "new-idea").exists()  # litters nothing
    s.add_grip("x", [0, None, None, None, None, None], render=False)
    assert (tmp_path / "new-idea" / "grip" / "library.json").exists()


def test_open_existing_project(tmp_path):
    a = GripService(tmp_path)
    a.set_project("song", create=True)
    a.add_grip("g", GM1, render=False)
    b = GripService(tmp_path)
    r = b.set_project("song")
    assert r["opened"] is True and r["created"] is False


# --- one-call capture (§6.1) ------------------------------------------------

def test_add_grip_one_call_common_case(svc):
    r = svc.add_grip("gm-1", GM1, chosen="Gm", label="Gm first inversion",
                     render=False)
    assert r["stored"] is True
    assert r["chosen"] == "Gm/Bb"          # three-tier resolution
    assert r["resolved_pitches"] == ["E2", "A2", "D3", "G3", "B3", "E4"]
    assert r["top"] == "Bb6"               # the literal reading; echo-check
    assert r["tuning"] == "standard"       # resolved, concrete
    assert r["warnings"] == []


def test_add_grip_chosen_miss_is_partial_success(svc):
    r = svc.add_grip("q", Q, chosen="Gm", render=False)
    assert r["stored"] is True             # the grip stored anyway
    codes = [w["code"] for w in r["warnings"]]
    assert codes == ["chosen_miss"]
    detail = r["warnings"][0]["detail"]
    assert detail["suggestions"][0] == "F#q4"
    assert "set_reading" in detail["repair"]
    assert svc.get_grip("q")["chosen"] is None


def test_add_grip_render_is_opt_in(svc):
    quiet = svc.add_grip("gm-0", [3, 1, None, None, None, None])
    assert quiet["stored"] is True and "render" not in quiet
    r = svc.add_grip("gm-1", GM1, fingers=[None, None, 2, 1, 3, None],
                     render=True)
    assert r["stored"] is True and r["warnings"] == []
    files = r["render"]["files"]
    assert set(files) == {"png"}  # PNG only (feedback)
    assert Path(files["png"]).exists()
    assert Path(files["png"]).name.startswith("gm-1__")


def test_add_grip_duplicate_refused(svc):
    svc.add_grip("gm-1", GM1, render=False)
    r = svc.add_grip("gm-1", GM1, render=False)
    assert r["error"]["code"] == "grip_exists" and r["stored"] is False


def test_add_grip_reserved_slug(svc):
    r = svc.add_grip("adhoc", GM1, render=False)
    assert r["error"]["code"] == "reserved_slug"


def test_add_grip_length_mismatch_names_both_lengths(svc):
    r = svc.add_grip("x", [0, 0, 0], render=False)
    assert "3" in r["error"]["detail"] and "6" in r["error"]["detail"]


def test_fingers_validation(svc):
    r = svc.add_grip("x", GM1, fingers=[1, None, 2, 1, 3, None],
                     render=False)  # finger on muted string
    assert "muted/open" in r["error"]["detail"]


# --- default_tuning resolution + envelope echo (decisions 50/52) ------------

def test_default_tuning_resolves_at_call_time(svc):
    svc.define_tuning("dadgad",
                      pitches=["D2", "A2", "D3", "G3", "A3", "D4"])
    svc.update_project_defaults("dadgad")
    r = svc.add_grip("open", [0, 0, 0, 0, 0, 0], render=False)
    assert r["tuning"] == "dadgad"          # stored concrete, echoed
    assert r["top"] == "Dsus4"
    assert svc.get_grip("open")["grip"]["tuning"] == "dadgad"


def test_default_tuning_lifecycle_refusals(svc):
    svc.define_tuning("dadgad",
                      pitches=["D2", "A2", "D3", "G3", "A3", "D4"])
    svc.update_project_defaults("dadgad")
    r = svc.remove_tuning("dadgad")
    assert r["error"]["code"] == "tuning_referenced"
    r = svc.update_project_defaults("nonesuch")
    assert r["error"]["code"] == "unknown_tuning" and r["stored"] is False


def test_capo_tuning_and_badge_fields(svc):
    svc.define_tuning("std-capo3", from_="standard", capo=3)
    r = svc.identify([0, 0, 0, None, None, None], tuning="std-capo3")
    assert r["capo"] == 3
    assert r["resolved_pitches"][:3] == ["G2", "C3", "F3"]


# --- identify (§6.1) --------------------------------------------------------

def test_identify_previews_without_storing(svc):
    r = svc.identify(Q, context_key="e-minor")
    assert r["mode"] == "context"
    assert r["candidates"][1]["name"] == "Bsus4/F#"
    assert svc.list_grips()["grips"] == {}  # nothing stored


def test_identify_truncates_to_top_8(svc):
    r = svc.identify([None, 2, 4, None, None, None])  # B5: 26 candidates
    assert len(r["candidates"]) == 8
    assert r["truncated"] == 18


def test_identify_single_pc_pitch_report(svc):
    r = svc.identify([0, None, None, None, None, 0])
    assert r["candidates"] == [] and r["pitch_report"]["doubling"] == 2


# --- set_reading (§6.1): valid, ambiguous, miss -----------------------------

def test_set_reading_valid_ambiguous_miss(svc):
    svc.add_grip("q", Q, render=False)
    ok = svc.set_reading("q", "Bsus4")
    assert ok["stored"] is True and ok["chosen"] == "Bsus4/F#"
    amb = svc.set_reading("q", "Bsus")
    assert amb["error"]["code"] == "chosen_ambiguous"
    assert "B7sus4/F#" in amb["error"]["detail"]
    miss = svc.set_reading("q", "Gm")
    assert miss["error"]["code"] == "chosen_miss"
    assert "F#q4" in miss["error"]["detail"]
    # The valid reading survived the failed attempts.
    assert svc.get_grip("q")["chosen"] == "Bsus4/F#"


# --- update_grip ------------------------------------------------------------

def test_update_grip_stales_chosen_with_new_top(svc):
    svc.add_grip("g", GM1, chosen="Gm", render=False)
    r = svc.update_grip("g", {"strings": [3, 1, None, None, None, None]})
    codes = [w["code"] for w in r["warnings"]]
    assert "chosen_staled" in codes
    w = next(w for w in r["warnings"] if w["code"] == "chosen_staled")
    assert w["detail"]["new_top"] == "Gdym3"


def test_update_grip_rejects_immutables_and_required_deletes(svc):
    svc.add_grip("g", GM1, render=False)
    assert svc.update_grip("g", {"id": "x"})["error"]["code"] == \
        "immutable_field"
    assert svc.update_grip("g", {"created": "now"})["error"]["code"] == \
        "immutable_field"
    assert svc.update_grip("g", {"strings": None})["error"]["code"] == \
        "required_field"


def test_update_grip_null_deletes_optional(svc):
    svc.add_grip("g", GM1, label="x", render=False)
    r = svc.update_grip("g", {"label": None})
    assert r["stored"] and "label" not in r["grip"]


# --- rename / remove with sequence references -------------------------------

def test_remove_grip_refuses_while_referenced(svc):
    svc.add_grip("a", GM1, render=False)
    svc.add_grip("b", Q, render=False)
    svc.set_sequence("intro", ["a", "b", "a"])
    r = svc.remove_grip("a")
    assert r["error"]["code"] == "grip_referenced"
    assert "'intro': 2" in r["error"]["detail"]      # every occurrence counts
    r = svc.remove_grip("a", force=True)
    assert r["stored"] is True
    assert svc.list_sequences()["sequences"]["intro"]["items"] == ["b"]


def test_rename_grip_rewrites_sequences_atomically(svc):
    svc.add_grip("a", GM1, render=False)
    svc.set_sequence("intro", ["a", "a"])
    r = svc.rename_grip("a", "gm-first")
    assert r["sequence_occurrences_rewritten"] == 2
    assert svc.list_sequences()["sequences"]["intro"]["items"] == \
        ["gm-first", "gm-first"]
    assert svc.get_grip("gm-first")["id"] == "gm-first"


# --- transpose (§6.1) -------------------------------------------------------

def test_transpose_exactly_one_of(svc):
    r = svc.transpose(2)
    assert r["error"]["code"] == "exactly_one_of"
    r = svc.transpose(2, id="x", strings=GM1)
    assert r["error"]["code"] == "exactly_one_of"


def test_transpose_fingers_carry_for_closed_shapes(svc):
    svc.add_grip("g", GM1, fingers=[None, None, 2, 1, 3, None],
                 render=False)
    r = svc.transpose(2, id="g")
    assert r["strings"] == [None, None, 10, 9, 10, None]
    assert r["fingers"] == [None, None, 2, 1, 3, None]  # verbatim
    assert r["warnings"] == []


def test_transpose_opens_fretted_warning_with_count(svc):
    svc.add_grip("e", [0, 2, 2, 1, 0, 0],
                 fingers=[None, 2, 3, 1, None, None], render=False)
    r = svc.transpose(2, id="e")
    w = next(w for w in r["warnings"] if w["code"] == "opens_fretted")
    assert w["detail"]["count"] == 3
    assert r["fingers"] == [None, 2, 3, 1, None, None]


def test_transpose_below_fret_0_capo_relative_error(svc):
    svc.define_tuning("std-capo3", from_="standard", capo=3)
    svc.add_grip("g", [None, None, 2, 1, 2, None], tuning="std-capo3",
                 render=False)
    r = svc.transpose(-3, id="g")
    assert r["error"]["code"] == "below_fret_0"
    assert "capo" in r["error"]["detail"]


def test_transpose_raw_strings_uses_default_tuning(svc):
    r = svc.transpose(2, strings=[3, 1, None, None, None, None])
    assert r["tuning"] == "standard"       # decision 50; envelope echo
    assert r["top"] == "Adym3"             # {A, C}: the dyad tops


def test_transpose_save_as_covariant_chosen_and_provenance(svc):
    svc.add_grip("gm-1", GM1, chosen="Gm", render=False)
    r = svc.transpose(2, id="gm-1", save_as="am-1")
    assert r["stored"] is True
    assert r["chosen"] == "Am/C"           # re-derivation, never respelling
    g = svc.get_grip("am-1")
    assert g["grip"]["derived_from"] == {"id": "gm-1", "semitones": 2}


# --- sequences --------------------------------------------------------------

def test_sequence_unknown_grip_instructive(svc):
    r = svc.set_sequence("intro", ["nope"])
    assert r["error"]["code"] == "unknown_grip"


def test_sequence_reserved_name(svc):
    svc.add_grip("a", GM1, render=False)
    r = svc.set_sequence("strip", ["a"])
    assert r["error"]["code"] == "reserved_slug"


# --- render (§6.4) ----------------------------------------------------------

def test_render_exactly_one_of(svc):
    r = svc.render()
    assert r["error"]["code"] == "exactly_one_of"


def test_render_sequence_strip_prefix_and_idempotent(svc):
    svc.add_grip("a", GM1, render=False)
    svc.add_grip("b", Q, render=False)
    svc.set_sequence("intro", ["a", "b"])
    r1 = svc.render(sequence="intro")
    assert Path(r1["files"]["png"]).name.startswith("intro__")
    assert set(r1["files"]) == {"png"}     # PNG only (feedback)
    r2 = svc.render(sequence="intro")
    assert r1["files"] == r2["files"]      # identical request, same files
    r3 = svc.render(ids=["a", "b"])
    assert Path(r3["files"]["png"]).name.startswith("strip__")


def test_render_labels_modes(svc):
    svc.add_grip("gm-1", GM1, chosen="Gm", render=False)
    notes = svc.render(ids=["gm-1"], labels="notes")
    intervals = svc.render(ids=["gm-1"], labels="intervals")
    assert notes["render_hash"] != intervals["render_hash"]


def test_render_display_spelling_follows_chosen(svc):
    """§5.2.3: display spelling follows chosen if set, else top."""
    svc.add_grip("g", GM1, render=False)
    top = svc.render(ids=["g"])
    svc.set_reading("g", "Gm")
    named = svc.render(ids=["g"])
    assert top["render_hash"] != named["render_hash"]  # name band changed


# --- resume completeness (§6.2) ---------------------------------------------

def test_describe_workspace_resume_completeness(svc):
    svc.define_tuning("dadgad",
                      pitches=["D2", "A2", "D3", "G3", "A3", "D4"])
    svc.add_grip("gm-1", GM1, chosen="Gm", tags=["intro"], render=False)
    svc.add_grip("q", Q, render=False)
    svc.set_sequence("intro", ["gm-1", "q"])
    r = svc.describe_workspace()
    assert r["grips"]["gm-1"]["chosen"] == "Gm/Bb"
    assert r["grips"]["gm-1"]["stale"] is False
    assert r["grips"]["gm-1"]["tags"] == ["intro"]
    assert r["sequences"] == {"intro": ["gm-1", "q"]}
    assert "dadgad" in r["tunings"] and r["default_tuning"] == "standard"
    assert r["flags"] == []
    assert r["counts"] == {"grips": 2, "sequences": 1}


def test_describe_workspace_flags_dangling(svc, tmp_path):
    svc.add_grip("g", GM1, render=False)
    # Hand edit dangles the grip's tuning:
    import json
    libp = tmp_path / "gm-em-song" / "grip" / "library.json"
    lib = json.loads(libp.read_text())
    lib["grips"]["g"]["tuning"] = "gone"
    libp.write_text(json.dumps(lib))
    r = svc.describe_workspace()
    assert any(f["code"] == "dangling_grip_tuning" for f in r["flags"])
    # Tools touching the affected grip error instructively:
    g = svc.get_grip("g")
    assert g["error"]["code"] == "unknown_tuning"


# --- tuning lifecycle through the service -----------------------------------

def test_define_tuning_exactly_one_of_and_immutability(svc):
    assert svc.define_tuning("x")["error"]["code"] == "exactly_one_of"
    assert svc.define_tuning(
        "x", pitches=["E2"], from_="standard"
    )["error"]["code"] == "exactly_one_of"
    assert svc.define_tuning(
        "standard", pitches=["E2"]
    )["error"]["code"] == "immutable_tuning"
    assert svc.remove_tuning("standard")["error"]["code"] == \
        "immutable_tuning"


def test_remove_tuning_refuses_chained_base(svc):
    svc.define_tuning("open-c",
                      pitches=["C2", "G2", "C3", "G3", "C4", "E4"])
    svc.define_tuning("open-c-capo2", from_="open-c", capo=2)
    r = svc.remove_tuning("open-c")
    assert r["error"]["code"] == "tuning_referenced"
    assert "open-c-capo2" in r["error"]["detail"]


def test_redefine_unreferenced_tuning_allowed(svc):
    svc.define_tuning("exp", pitches=["E2", "A2", "D3", "G3", "B3", "E4"])
    r = svc.define_tuning("exp",
                          pitches=["D2", "A2", "D3", "G3", "B3", "E4"])
    assert r["stored"] is True and r["resolved_pitches"][0] == "D2"


# --- bulk-capture idiom (§6.3) ----------------------------------------------

def test_bulk_capture_then_one_strip(svc):
    for gid, s in [("a", GM1), ("b", Q),
                   ("c", [None, 2, 4, None, None, None])]:
        r = svc.add_grip(gid, s, render=False)
        assert r["stored"] and "render" not in r
    svc.set_sequence("song", ["a", "b", "c"])
    r = svc.render(sequence="song")
    assert "files" in r
