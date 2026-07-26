"""Table-totality meta-test (DESIGN §11, §13).

Runs against the quality table alone (tomllib; no other imports), so a table
edit that breaks a structural invariant fails here even if every other test
module is skipped or stale. The dedup-over-random-inputs property lives with
the reference-script property tests (it needs the generator).
"""

import re
import tomllib
from pathlib import Path

import pytest

TABLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "grip_mcp" / "data" / "qualities.toml"
)

LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACC_VALUE = {"": 0, "b": -1, "bb": -2, "#": 1, "##": 2}
# Degree -> (letter steps from root, natural semitones from root)
DEGREE_SEMIS = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11, "9": 14}
DEGREE_RE = re.compile(r"^(bb|##|b|#)?([12345679])$")
SPELLING_RE = re.compile(r"^([A-G])(bb|##|b|#)?$")

REQUIRED_COLUMNS = {
    "name", "tones", "degrees", "spell", "tier", "order",
    "inversion", "discount", "family", "gen", "doc",
}


@pytest.fixture(scope="module")
def table():
    with open(TABLE_PATH, "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def qualities(table):
    return table["qualities"]


def spelling_pc(s: str) -> int:
    m = SPELLING_RE.match(s)
    assert m, f"bad spelling {s!r}"
    return (LETTER_PC[m.group(1)] + ACC_VALUE[m.group(2) or ""]) % 12


# --- file-level structure ---------------------------------------------------

def test_versions_present(table):
    assert table["table"]["schema_version"] == 1
    assert re.match(r"^\d+\.\d+\.\d+$", table["table"]["table_version"])


def test_canonical_root_table(table):
    roots = table["roots"]["canonical"]
    assert len(roots) == 12
    assert [spelling_pc(r) for r in roots] == list(range(12))
    # Flat-side table with the single sharp exception F# (decision ledger).
    sharps = [r for r in roots if "#" in r]
    assert sharps == ["F#"]


def test_tiers_table(table):
    assert sorted(int(k) for k in table["tiers"]) == [1, 2, 3, 4, 5, 6]


# --- per-row totality (every row, including dyads, `5`, `coll`) -------------

def test_every_row_has_every_column(qualities):
    for qid, row in qualities.items():
        missing = REQUIRED_COLUMNS - set(row)
        assert not missing, f"{qid}: missing columns {sorted(missing)}"


def test_ids_equal_names_except_maj(qualities):
    for qid, row in qualities.items():
        if qid == "maj":
            assert row["name"] == ""
        else:
            assert row["name"] == qid, f"{qid}: id/name drift"


def test_tones_wellformed(qualities):
    for qid, row in qualities.items():
        tones = row["tones"]
        assert tones == sorted(set(tones)), f"{qid}: tones not sorted/distinct"
        assert tones[0] == 0, f"{qid}: tones must contain 0 first"
        assert all(0 <= t <= 11 for t in tones), f"{qid}: tone out of range"


def test_tier_membership_and_no_memberless_tiers(table, qualities):
    declared = {int(k) for k in table["tiers"]}
    used = {row["tier"] for row in qualities.values()}
    assert used == declared, "memberless or undeclared tier"


def test_quality_order_globally_unique_and_tier_consistent(qualities):
    orders = [row["order"] for row in qualities.values()]
    assert len(orders) == len(set(orders)), "quality-order collision"
    # Tie-break order never contradicts R3: a lower tier sorts wholly before
    # a higher tier in the order column too (keeps the column reviewable).
    by_order = sorted(qualities.values(), key=lambda r: r["order"])
    tiers_in_order = [r["tier"] for r in by_order]
    assert tiers_in_order == sorted(tiers_in_order)


def test_inversion_semantics_domain(qualities):
    for qid, row in qualities.items():
        assert row["inversion"] in ("member-index", "none"), qid
        if qid in ("q4", "coll") or row["gen"] == "dyad":
            assert row["inversion"] == "none", f"{qid}: DESIGN §7.4 null set"


def test_discount_sets(qualities):
    for qid, row in qualities.items():
        assert set(row["discount"]) <= set(row["tones"]), f"{qid}: discount not a tone"
    # dim and aug discount nothing — altered fifths are defining (§7.2),
    # and the same principle extends to every altered-fifth row.
    for qid in ("dim", "aug", "m7b5", "dim7"):
        assert qualities[qid]["discount"] == [], qid
    # Default policy: rows containing an unaltered P5 discount exactly {7}.
    for qid, row in qualities.items():
        if 7 in row["tones"] and qid not in ("5",):
            assert row["discount"] == [7], f"{qid}: default-discount drift"


def test_families_declared(table, qualities):
    declared = set(table["grammar"]["families"])
    used = {row["family"] for row in qualities.values()}
    assert used == declared, "family column vs grammar.families drift"


def test_spelling_degrees_realize_tones(qualities):
    """The mechanical content check: degrees (on a C root) == tones."""
    for qid, row in qualities.items():
        if row["spell"] == "canonical":
            assert row["degrees"] == [], qid
            continue
        pcs = []
        for token in row["degrees"]:
            m = DEGREE_RE.match(token)
            assert m, f"{qid}: bad degree token {token!r}"
            acc, deg = m.group(1) or "", m.group(2)
            pcs.append((DEGREE_SEMIS[deg] + ACC_VALUE[acc]) % 12)
        assert len(pcs) == len(set(pcs)), f"{qid}: degree PC collision"
        assert sorted(pcs) == row["tones"], f"{qid}: degrees do not spell tones"


# --- special-case generators ------------------------------------------------

def test_dyad_rows_match_fixed_token_set(table, qualities):
    tokens = table["grammar"]["dyad_tokens"]
    assert tokens == ["m2", "M2", "m3", "M3", "P4", "A4", "m6", "M6", "m7", "M7"]
    dyads = {qid: row for qid, row in qualities.items() if row["gen"] == "dyad"}
    assert sorted(dyads) == sorted("dy" + t for t in tokens)
    # PC distance per token; distance 7 must have no dyad (X5 exclusivity).
    distances = {row["tones"][1] for row in dyads.values()}
    assert distances == {1, 2, 3, 4, 5, 6, 8, 9, 10, 11}
    for row in dyads.values():
        assert len(row["tones"]) == 2 and row["tier"] == 1


def test_five_and_coll_rows(qualities):
    assert qualities["5"]["tones"] == [0, 7]
    assert qualities["5"]["gen"] == "table"
    coll = qualities["coll"]
    assert coll["gen"] == "coll" and coll["tier"] == 6
    assert coll["spell"] == "canonical"
    # coll must be the very bottom of the tie-break column too.
    assert coll["order"] == max(r["order"] for r in qualities.values())


# --- grammar: parse-unambiguity ---------------------------------------------

def _decompositions(s: str, suffixes: set[str]) -> list[tuple[str, str]]:
    """All (root, suffix) splits of a bass-less name string."""
    out = []
    m = re.match(r"^[A-G]", s)
    if not m:
        return out
    for acc in ("bb", "##", "b", "#", ""):
        root = s[0] + acc
        if s.startswith(root) and s[len(root):] in suffixes:
            out.append((root, s[len(root):]))
    return out


@pytest.fixture(scope="module")
def suffixes(table, qualities):
    names = {row["name"] for row in qualities.values()}
    fams = set(table["grammar"]["families"])
    return names, fams


def test_suffix_sets_wellformed(suffixes):
    names, fams = suffixes
    assert len(names) == len(set(names))
    for s in names | fams:
        assert re.match(r"^[A-Za-z0-9]*$", s), f"suffix {s!r} escapes grammar"
        assert not s.startswith(("b", "#")), f"suffix {s!r} collides with accidentals"


def test_name_grammar_parse_unambiguous(qualities, suffixes):
    """Every root spelling x quality name parses back to exactly one split."""
    names, fams = suffixes
    accepted = names | fams  # the wider chosen-grammar set (A2)
    roots = [
        letter + acc
        for letter in "ABCDEFG"
        for acc in ("", "b", "#", "bb", "##")
    ]
    for root in roots:
        for suffix in accepted:
            s = root + suffix
            found = _decompositions(s, accepted)
            assert (root, suffix) in found, f"{s}: parse lost its own split"
            assert len(found) == 1, f"{s}: ambiguous parse {found}"


def test_rejected_encodings_stay_rejected(suffixes):
    """DESIGN §5.2.4: `Gm3`, `AA4` must not be parseable names."""
    names, fams = suffixes
    accepted = names | fams
    assert _decompositions("Gm3", accepted) == []
    assert _decompositions("AA4", accepted) == []
