"""Storage & lifecycle tests (DESIGN §5.1, §10, §11 interaction rows):
fresh-project empty reads, first-write bootstrap, hash-guarded external
modification, atomic .bak, slug rules + reservations, tuning lifecycle
(capo chains, cycles, dangling flags, standard immutability), derived
cache regeneration, ecosystem list_projects."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grip_mcp import store as S
from grip_mcp import theory


def mkstore(tmp_path, name="gm-em-song"):
    return S.Store(tmp_path, name)


GM1 = {"strings": [None, None, 8, 7, 8, None], "tuning": "standard"}


# --- fresh-project reads = empty library, never an error (decision 53) ------

def test_fresh_read_is_empty_library(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    assert lib["grips"] == {} and lib["sequences"] == {}
    assert lib["default_tuning"] == "standard"
    assert lib["tunings"]["standard"] == S.STANDARD_TUNING
    assert not (tmp_path / "gm-em-song").exists()  # reads litter nothing


# --- first write bootstraps all four artifacts in one step ------------------

def test_first_write_bootstrap(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    grip = tmp_path / "gm-em-song" / "grip"
    assert (grip / "library.json").exists()
    assert (grip / "derived.json").exists()
    assert (grip / ".gitignore").read_text() == "derived.json\n"
    reread = st.load()
    assert reread["grips"]["gm-1"]["strings"] == GM1["strings"]


# --- pre-write hash guard ----------------------------------------------------

def test_external_modification_detected(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    lib = st.load()
    # External edit lands between our read and our write:
    external = st.library_path.read_text().replace("gm-1", "gm-x")
    st.library_path.write_text(external)
    lib["sequences"]["intro"] = ["gm-1"]
    with pytest.raises(S.StoreError, match="changed on disk"):
        st.save(lib)
    # Nothing was written; the external edit survives.
    assert "gm-x" in st.library_path.read_text()


def test_absent_is_expected_absent_not_conflict(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()          # absent
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)             # first write: no conflict


def test_atomic_write_leaves_bak(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    lib = st.load()
    lib["grips"]["gm-1"]["label"] = "Gm first inversion"
    st.save(lib)
    bak = st.library_path.with_suffix(".json.bak")
    assert bak.exists()
    assert "label" not in json.loads(bak.read_text())["grips"]["gm-1"]


# --- slugs ------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "UPPER", "a" * 41, "with space",
                                 "double__under", "strip", "adhoc"])
def test_bad_slugs_rejected(bad):
    with pytest.raises(S.StoreError):
        S.validate_slug(bad, "grip id")


@pytest.mark.parametrize("ok", ["gm-1", "b5", "intro", "open_c",
                                "a-very-long-but-legal-slug-name-here"])
def test_good_slugs(ok):
    assert S.validate_slug(ok, "grip id") == ok


# --- tuning lifecycle -------------------------------------------------------

def test_capo_chain_resolution(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["tunings"]["standard-capo3"] = {"from": "standard", "capo": 3}
    lib["tunings"]["nested"] = {"from": "standard-capo3", "capo": 2}
    r3 = S.resolve_tuning(lib, "standard-capo3")
    assert r3["pitches"][0] == "G2" and r3["capo"] == 3
    r5 = S.resolve_tuning(lib, "nested")
    assert r5["pitches"][0] == "A2" and r5["capo"] == 5
    assert r5["chain"] == ["nested", "standard-capo3", "standard"]


def test_tuning_cycle_detected(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["tunings"]["a"] = {"from": "b", "capo": 1}
    lib["tunings"]["b"] = {"from": "a", "capo": 1}
    with pytest.raises(S.StoreError, match="cycle"):
        S.resolve_tuning(lib, "a")
    flags = S.tuning_flags(lib)
    assert any(f["code"] == "tuning_cycle" for f in flags)


def test_dangling_references_flag_not_crash(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["x"] = {"strings": [0] * 6, "tuning": "nonesuch"}
    lib["default_tuning"] = "gone"
    flags = S.tuning_flags(lib)
    codes = {f["code"] for f in flags}
    assert "dangling_grip_tuning" in codes
    assert "dangling_default_tuning" in codes


def test_standard_is_immutable_on_load(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    # Hand edit tries to redefine standard:
    raw = json.loads(st.library_path.read_text())
    raw["tunings"]["standard"] = ["D2", "A2", "D3", "G3", "A3", "D4"]
    st.library_path.write_text(json.dumps(raw))
    lib = st.load()
    assert lib["tunings"]["standard"] == S.STANDARD_TUNING


def test_dadgad_definition(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["tunings"]["dadgad"] = ["D2", "A2", "D3", "G3", "A3", "D4"]
    r = S.resolve_tuning(lib, "dadgad")
    assert r["pitches"] == ["D2", "A2", "D3", "G3", "A3", "D4"]
    assert r["capo"] == 0


# --- derived cache ----------------------------------------------------------

def test_derive_grip_caches_and_invalidates(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    derived = st.load_derived()
    e1 = st.derive_grip(lib, derived, "gm-1")
    assert e1["candidates"][0]["name"] == "Bb6"      # the literal top
    assert e1["decided_at"] == "R1"
    # Cached: same object back without recompute.
    assert st.derive_grip(lib, derived, "gm-1") is e1
    # Change the grip -> input hash moves -> re-derived.
    lib["grips"]["gm-1"]["strings"] = [3, 1, None, None, None, None]
    e2 = st.derive_grip(lib, derived, "gm-1")
    assert e2["candidates"][0]["name"] == "Gdym3"


def test_derived_cache_discarded_on_engine_mismatch(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    derived = st.load_derived()
    st.derive_grip(lib, derived, "gm-1")
    st.save(lib, derived)
    # Simulate an engine upgrade on disk:
    raw = json.loads(st.derived_path.read_text())
    raw["engine_version"] = "0.0.1"
    st.derived_path.write_text(json.dumps(raw))
    fresh = st.load_derived()
    assert fresh["grips"] == {}  # regenerable cache, silently rebuilt
    assert fresh["engine_version"] == theory.ENGINE_VERSION


def test_corrupt_derived_is_absent_not_fatal(tmp_path):
    st = mkstore(tmp_path)
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    st.derived_path.write_text("{not json")
    assert st.load_derived()["grips"] == {}


# --- ecosystem scan ---------------------------------------------------------

def test_list_projects_ecosystem_wide(tmp_path):
    (tmp_path / "cdp-only" / "cdp").mkdir(parents=True)
    st = mkstore(tmp_path, "gm-em-song")
    lib = st.load()
    lib["grips"]["gm-1"] = dict(GM1)
    st.save(lib)
    (tmp_path / "broken" / "grip").mkdir(parents=True)
    (tmp_path / "broken" / "grip" / "library.json").write_text("{oops")
    r = S.list_projects(tmp_path)
    names = {p["name"]: p for p in r["projects"]}
    assert names["gm-em-song"]["grips"] == 1
    assert names["cdp-only"]["grips"] == 0          # no grip/ namespace
    assert "broken" not in names
    assert any(w["code"] == "malformed_project" for w in r["warnings"])


def test_list_projects_missing_root(tmp_path):
    r = S.list_projects(tmp_path / "nowhere")
    assert r == {"projects": [], "warnings": []}


def test_close_matches():
    assert "gm-em-song" in S.close_matches("gm-em-sog", ["gm-em-song", "other"])
