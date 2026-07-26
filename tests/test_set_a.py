"""Set A theory fixtures (DESIGN §11): script-generated expectations plus
the doc's named claims as explicit asserts.

Where §7.3's prose enumerations diverge from strict rule application, the
assertions here pin the SCRIPT's output (the doc's own authority rule:
hand-application is 0-for-4; fixture expectations are the script's reviewed
output). Every such divergence is catalogued in REVIEW.md for the
freeze-gate review.
"""

import json
from pathlib import Path

import pytest

import refengine as R

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "set_a.json").read_text()
)


def result(name):
    return FIXTURES[name]["result"]


def names(name):
    return [c["name"] for c in result(name)["candidates"]]


def cand(name, cname):
    return next(c for c in result(name)["candidates"] if c["name"] == cname)


def rank(name, cname):
    return names(name).index(cname)


# --- regeneration: fixtures are exactly what the engine derives today -------

@pytest.mark.parametrize("fname", sorted(FIXTURES))
def test_regenerates_clean(fname):
    fx = FIXTURES[fname]["result"]
    inp = fx["input"]
    fresh = R.identify(inp["strings"], inp["tuning"], inp["context_key"])
    assert fresh == fx


# --- Gm-O: m3 dyad -> Gm (-D) -> fragments · decided_at R2 ------------------

def test_gm_o():
    r = result("gm-o")
    assert names("gm-o")[0] == "Gdym3"
    assert names("gm-o")[1] == "Gm"
    assert cand("gm-o", "Gm")["missing"] == ["D"]
    assert r["decided_at"] == "R2"
    # Xm (-P5) beats Xdim (-d5) at R2.2 — the discount consequence, §7.2.
    assert rank("gm-o", "Gm") < rank("gm-o", "Gdim")


# --- PASS: dyad tops; rivals inversion-class or rootless · decided_at R1 ----

def test_pass():
    r = result("pass")
    assert names("pass")[0] == "Adym2"
    assert r["decided_at"] == "R1"
    for c in r["candidates"][1:]:
        assert not (c["root_is_bass"] and c["root_sounds"])
    # The grip sounds a compound minor ninth; the reading says so, the
    # name stays m2 (§7.3).
    assert "compound" in r["candidates"][0]["reading"]
    assert "13 semitones" in r["candidates"][0]["reading"]


# --- Gm-1: the canonical chosen argument ------------------------------------

def test_gm_1():
    r = result("gm-1")
    # The most literal complete reading tops: Bb6 (root-position, one
    # discounted miss) above the exact inversion Gm/Bb — separated at R1.
    assert names("gm-1")[0] == "Bb6"
    assert names("gm-1")[1] == "Gm/Bb"
    assert r["decided_at"] == "R1"
    gm = cand("gm-1", "Gm/Bb")
    assert gm["inversion"] == 1
    assert gm["missing"] == []
    assert gm["pitches"] == ["Bb3", "D4", "G4"]


# --- B5 root position: shadows + the same-root tie-break --------------------

def test_b5():
    r = result("b5")
    assert names("b5")[0] == "B5"
    assert r["decided_at"] == "R2"
    for cname, miss in [("Bsus2", ["C#"]), ("Bsus4", ["E"]),
                        ("Bm", ["D"]), ("B", ["D#"])]:
        assert cand("b5", cname)["missing"] == miss
    # R3: triads above add/sus (doc prose enumerated sus first — REVIEW.md).
    assert rank("b5", "B") < rank("b5", "Bsus2")
    assert rank("b5", "Bm") < rank("b5", "Bsus2")
    # The first fixture exercising the quality-order column directly:
    # Bsus2 vs Bsus4 tie through R2 and R3 with the same root.
    assert rank("b5", "Bsus4") == rank("b5", "Bsus2") + 1


# --- G-dy: major-third dyad with its shadow ---------------------------------

def test_g_dy():
    assert names("g-dy")[0] == "GdyM3"
    assert cand("g-dy", "G")["missing"] == ["D"]


# --- B5/F#: the canonical argument for chosen -------------------------------

def test_b5_over_fs():
    r = result("b5-over-fs")
    # Strict rule application (script-derived; enumeration differs from the
    # doc's prose — REVIEW.md): the full root-at-bass class precedes ALL
    # inversions (R1), so B5/F# sits fifth, after F#q4 and F#7sus4, which
    # the prose list omitted. The F#sus4 shadow (v0.5's miss) is #2.
    assert names("b5-over-fs")[:9] == [
        "F#dyP4", "F#sus4", "F#q4", "F#7sus4",
        "B5/F#", "B/F#", "Bm/F#", "Bsus2/F#", "Bsus4/F#",
    ]
    assert cand("b5-over-fs", "F#sus4")["missing"] == ["C#"]
    assert r["decided_at"] == "R2"
    # The conversation's own name is well below the top — the chosen
    # argument stands (stronger than the doc stated: fifth, not third).
    assert rank("b5-over-fs", "B5/F#") == 4


# --- Q: the three-way sus2/sus4/q4 rotation ---------------------------------

def test_q_context_free():
    r = result("q")
    assert names("q") == [
        "F#q4", "F#7sus4", "Bsus4/F#", "Esus2/F#",
        "B7sus4/F#", "Eadd9/F#", "Emadd9/F#",
    ]
    assert cand("q", "F#7sus4")["missing"] == ["C#"]
    assert r["decided_at"] == "R2"


def test_q_in_e_minor():
    r = result("q-e-minor")
    assert r["mode"] == "context"
    passers = [c["name"] for c in r["candidates"] if c["r0_pass"]]
    # Exactly the documented passer set (§7.3).
    assert set(passers) == {
        "F#q4", "Bsus4/F#", "Esus2/F#", "Emadd9/F#", "B7sus4/F#",
    }
    # Top unchanged; context #2 is Bsus4/F#; decided_at R1 (§7.3, verbatim).
    assert names("q-e-minor")[0] == "F#q4"
    assert names("q-e-minor")[1] == "Bsus4/F#"
    assert r["decided_at"] == "R1"
    # Failers rank below every passer.
    flags = [c["r0_pass"] for c in r["candidates"]]
    assert flags == sorted(flags, reverse=True)


# --- thumb-B5: doubling and octaves do not change the candidate set ---------

def test_thumb_b5():
    assert names("thumb-b5") == names("b5")
    assert result("thumb-b5")["midi"] != result("b5")["midi"]


# --- {B, D#}: context-free vs e-minor (first R0-failure fixture) ------------

def test_b_ds_context_free():
    r = result("b-ds")
    assert names("b-ds")[0] == "BdyM3"
    assert names("b-ds")[1] == "B"
    assert cand("b-ds", "B")["missing"] == ["F#"]
    assert r["decided_at"] == "R2"
    # Member stacking admits doubles (§5.2.2): Baug's missing fifth spells
    # F## — grammar ##, never G.
    assert cand("b-ds", "Baug")["missing"] == ["F##"]


def test_b_ds_in_e_minor():
    r = result("b-ds-e-minor")
    # The dyad fails R0 (D# chromatic, non-tertian); B (-F#) passes as the
    # admitted V triad and tops (§7.3).
    assert names("b-ds-e-minor")[0] == "B"
    assert cand("b-ds-e-minor", "BdyM3")["r0_pass"] is False
    assert cand("b-ds-e-minor", "B")["r0_pass"] is True
    # V7 is admitted purely by quality + degree (§7.2), so B7 passes too
    # and becomes #2 — which makes decided_at R2, not the doc's claimed
    # R0 (#1 vs #2 separate inside R2). Doc divergence — REVIEW.md.
    assert cand("b-ds-e-minor", "B7")["r0_pass"] is True
    assert names("b-ds-e-minor")[1] == "B7"
    assert r["decided_at"] == "R2"
    # The R0-failure part of the fixture stands: every candidate below the
    # two admitted V readings fails R0.
    assert [c["r0_pass"] for c in r["candidates"]].count(True) == 2
