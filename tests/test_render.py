"""Render tests (DESIGN §11): normalized-SVG goldens, rasterization smoke,
render-hash distinctness across options, window/barre/truncation rules."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import render as R

GOLDEN_DIR = Path(__file__).parent / "goldens"

GM1 = {
    "frets": [None, None, 8, 7, 8, None],
    "fingers": [None, None, 2, 1, 3, None],
    "string_labels": [None, None, "Bb", "D", "G", None],
    "name": "Gm/Bb", "capo": 0,
}
DADGAD_OPEN = {
    "frets": [0, 0, 0, 0, 0, 0], "name": "Dsus4", "capo": 0,
    "string_labels": ["D", "A", "D", "G", "A", "D"],
}
G7_CAPO = {
    "frets": [3, None, 3, 4, None, None],
    "fingers": [1, None, 2, 3, None, None],
    "name": "G7", "capo": 3,
}


# --- goldens (deterministic output: exact match, regeneratable) -------------

@pytest.mark.parametrize("name,grips,options", [
    ("gm1_chart", [GM1], {"labels": "notes"}),
    ("strip_mixed", [GM1, DADGAD_OPEN, G7_CAPO],
     {"labels": "notes", "title": "intro strip", "columns": 3}),
    ("gm1_neck_dark", [GM1],
     {"labels": "fingers", "orientation": "neck", "theme": "dark"}),
])
def test_golden(name, grips, options):
    got = R.render_chart(grips, options)["svg"]
    path = GOLDEN_DIR / f"{name}.svg"
    if not path.exists():  # first run writes; review + commit the golden
        path.parent.mkdir(exist_ok=True)
        path.write_text(got, encoding="utf-8")
        pytest.skip(f"golden {name} written; review and re-run")
    assert got == path.read_text(encoding="utf-8")


def test_deterministic_repeat():
    a = R.render_chart([GM1], {"labels": "notes"})
    b = R.render_chart([GM1], {"labels": "notes"})
    assert a["svg"] == b["svg"] and a["hash"] == b["hash"]


# --- rasterization smoke ----------------------------------------------------

def test_png_smoke():
    resvg = pytest.importorskip("resvg_py")  # core dep; guard for bare envs
    out = R.render_chart([GM1], {"labels": "notes"})
    png = R.to_png(out["svg"], out["width"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


# --- render hash: covers grips incl. fingers, every option, version ---------

def test_hash_distinct_across_options():
    base = R.render_chart([GM1], {"labels": "notes"})["hash"]
    variants = [
        R.render_chart([GM1], {"labels": "intervals"})["hash"],
        R.render_chart([GM1], {"labels": "notes", "theme": "dark"})["hash"],
        R.render_chart([GM1], {"labels": "notes", "orientation": "neck"})["hash"],
        R.render_chart([GM1], {"labels": "notes", "title": "x"})["hash"],
    ]
    assert len({base, *variants}) == 5


def test_hash_covers_fingers():
    """The identity hash excludes fingers — correct for identification,
    disqualifying for renders (§6.4). The render hash must NOT."""
    without = dict(GM1, fingers=None)
    a = R.render_hash([GM1], {"labels": "none"})
    b = R.render_hash([without], {"labels": "none"})
    assert a != b


# --- window rules (§8) ------------------------------------------------------

def test_window_from_fretted_only():
    assert R.fret_window([None, None, 8, 7, 8, None]) == (7, 4)


def test_window_min_four_with_nut():
    assert R.fret_window([None, 3, 2, 0, 1, 0]) == (1, 4)


def test_window_all_open_fallback():
    assert R.fret_window([0, 0, 0, 0, 0, 0]) == (1, 4)


def test_window_wide_shape():
    start, rows = R.fret_window([5, None, None, None, None, 10])
    assert start == 5 and rows == 6


def test_open_strings_marked_outside_window():
    """Open strings always draw as O markers regardless of window."""
    svg = R.render_chart(
        [{"frets": [0, None, 7, 7, 8, 0], "name": "", "capo": 0}],
        {"labels": "none"},
    )["svg"]
    assert svg.count('stroke-width="1.8"') >= 3  # 2 O rings + 1 X


# --- barres (all label modes) -----------------------------------------------

def test_barre_runs_contiguous_same_finger_same_fret():
    frets = [1, 3, 3, 2, 1, 1]
    fingers = [1, 3, 4, 2, 1, 1]
    assert R.barre_runs(frets, fingers) == [(1, 4, 5)]


def test_barre_full():
    assert R.barre_runs([5] * 6, [1] * 6) == [(5, 0, 5)]


def test_barre_broken_by_muted_string():
    assert R.barre_runs([5, None, 5], [1, None, 1]) == []


def test_barres_drawn_in_all_label_modes():
    g = {"frets": [5] * 6, "fingers": [1] * 6, "name": "A", "capo": 0}
    for mode in ("notes", "intervals", "fingers", "none"):
        svg = R.render_chart([g], {"labels": mode})["svg"]
        assert 'rx="8.50"' in svg  # the barre rounded rect


# --- text -------------------------------------------------------------------

def test_truncation_with_ellipsis():
    long = "Gm7b5add9oversomethingverylong"
    t = R.truncate(long, 13, 100)
    assert t.endswith("…") and R.text_width(t, 13) <= 100


def test_text_as_glyph_paths_never_text_elements():
    svg = R.render_chart([GM1], {"labels": "notes", "title": "t"})["svg"]
    assert "<text" not in svg
    assert "<path" in svg


# --- errors are instructive -------------------------------------------------

def test_unknown_options_instructive():
    with pytest.raises(R.RenderError, match="dark"):
        R.render_chart([GM1], {"theme": "sepia"})
    with pytest.raises(R.RenderError, match="fingers"):
        R.render_chart([GM1], {"labels": "nope"})
    with pytest.raises(R.RenderError, match="neck"):
        R.render_chart([GM1], {"orientation": "sideways"})
