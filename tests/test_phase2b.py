"""Phase 2b tests (DESIGN §9): the instrument-tuning workflow —
declaration with history superseding default_tuning, retune plans with
direction+magnitude-only warnings, lifecycle references, tuning cards."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp.service import GripService

DADGAD = ["D2", "A2", "D3", "G3", "A3", "D4"]
OPEN_C = ["C2", "G2", "C3", "G3", "C4", "E4"]


@pytest.fixture()
def svc(tmp_path):
    s = GripService(tmp_path)
    s.set_project("songs", create=True)
    s.define_tuning("dadgad", pitches=DADGAD)
    s.define_tuning("open-c", pitches=OPEN_C)
    return s


# --- declaration with history (question 5's lean) ---------------------------

def test_declaration_supersedes_default_tuning(svc):
    r = svc.set_instrument_tuning("dadgad")
    assert r["stored"] is True
    assert r["declared"]["tuning"] == "dadgad" and r["declared"]["since"]
    assert r["default_tuning"] == "dadgad"
    # Capture defaults now follow the declaration:
    g = svc.add_grip("open", [0] * 6, render=False)
    assert g["tuning"] == "dadgad" and g["top"] == "Dsus4"


def test_declaration_history_appends(svc):
    svc.set_instrument_tuning("dadgad")
    r = svc.set_instrument_tuning("open-c")
    assert r["declarations"] == 2
    ws = svc.describe_workspace()
    assert ws["instrument"]["tuning"] == "open-c"


def test_redeclaration_includes_retune_plan(svc):
    svc.set_instrument_tuning("dadgad")
    r = svc.set_instrument_tuning("open-c")
    plan = r["retune"]
    assert plan["from"] == "dadgad" and plan["to"] == "open-c"
    # dadgad -> open-c: D2->C2, A2->G2, D3->C3, G3->G3, A3->C4, D4->E4
    deltas = [s["semitones"] for s in plan["strings"]]
    assert deltas == [-2, -2, -2, 0, 3, 2]


def test_unknown_tuning_refused(svc):
    r = svc.set_instrument_tuning("nonesuch")
    assert r["error"]["code"] == "unknown_tuning" and r["stored"] is False


def test_declared_tuning_is_a_lifecycle_reference(svc):
    svc.set_instrument_tuning("dadgad")
    r = svc.remove_tuning("dadgad")
    assert r["error"]["code"] == "tuning_referenced"
    assert "set_instrument_tuning" in r["error"]["detail"]


def test_dangling_declaration_flags(svc, tmp_path):
    import json
    svc.set_instrument_tuning("dadgad")
    svc.add_grip("g", [0] * 6, render=False)
    libp = tmp_path / "songs" / "grip" / "library.json"
    lib = json.loads(libp.read_text())
    del lib["tunings"]["dadgad"]
    lib["default_tuning"] = "standard"
    for g in lib["grips"].values():
        g["tuning"] = "standard"
    libp.write_text(json.dumps(lib))
    ws = svc.describe_workspace()
    assert any(f["code"] == "dangling_instrument_tuning"
               for f in ws["flags"])


# --- retune_plan ------------------------------------------------------------

def test_retune_plan_deltas_directions_order(svc):
    r = svc.retune_plan(to="dadgad", from_="standard")
    # standard -> dadgad: E2->D2, A2->A2, D3->D3, G3->G3, B3->A3, E4->D4
    assert [s["semitones"] for s in r["strings"]] == [-2, 0, 0, 0, -2, -2]
    assert [s["direction"] for s in r["strings"]] == \
        ["down", "hold", "hold", "hold", "down", "down"]
    # Downs first low->high; no ups; holds omitted:
    assert r["suggested_order"] == [1, 5, 6]
    assert r["warnings"] == []


def test_retune_plan_defaults_from_declaration(svc):
    svc.set_instrument_tuning("dadgad")
    r = svc.retune_plan(to="standard")
    assert r["from"] == "dadgad"
    assert [s["direction"] for s in r["strings"]] == \
        ["up", "hold", "hold", "hold", "up", "up"]
    assert r["suggested_order"] == [1, 5, 6]


def test_retune_plan_large_delta_warnings_heuristic_only(svc):
    svc.define_tuning("weird", pitches=["A2", "A2", "D3", "G3", "B3", "E4"])
    r = svc.retune_plan(to="weird", from_="standard")  # low E up a fourth
    w = [x for x in r["warnings"] if x["code"] == "large_delta"]
    assert len(w) == 1
    assert w[0]["detail"]["string"] == 1
    assert w[0]["detail"]["semitones"] == 5
    assert "aggressive" in w[0]["detail"]["note"]


def test_retune_plan_downtune_slack_warning(svc):
    svc.define_tuning("drop-low", pitches=["A1", "A2", "D3", "G3", "B3", "E4"])
    r = svc.retune_plan(to="drop-low", from_="standard")
    w = [x for x in r["warnings"] if x["code"] == "large_delta"]
    assert len(w) == 1 and w[0]["detail"]["direction"] == "down"
    assert "slack" in w[0]["detail"]["note"]


def test_retune_plan_string_count_mismatch(svc):
    svc.define_tuning("uke", pitches=["G4", "C4", "E4", "A4"])
    r = svc.retune_plan(to="uke", from_="standard")
    assert r["error"]["code"] == "length_mismatch"
    assert "6" in r["error"]["detail"] and "4" in r["error"]["detail"]


def test_retune_plan_capo_note(svc):
    svc.define_tuning("std-capo3", from_="standard", capo=3)
    r = svc.retune_plan(to="std-capo3", from_="standard")
    assert [s["semitones"] for s in r["strings"]] == [3] * 6
    assert "not a peg turn" in r["capo_note"]


# --- rendered tuning cards via the strip machinery --------------------------

def test_tuning_cards_render(svc):
    r = svc.retune_plan(to="dadgad", from_="standard", render=True)
    files = r["render"]["files"]
    assert set(files) == {"png"}
    assert Path(files["png"]).name.startswith("retune__")
    assert Path(files["png"]).exists()


def test_declaration_card_render(svc):
    r = svc.set_instrument_tuning("dadgad", render=True)
    assert Path(r["render"]["files"]["png"]).name.startswith("dadgad__")
