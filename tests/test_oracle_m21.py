"""music21 oracle (DESIGN §11): validates table rows' tone sets — and, as
a bonus, their degree-stacked member spellings — against an independent
implementation. Optional dependency group `grip-mcp[m21]`; skipped cleanly
when absent (unconditional CI never needs it).

Coverage: the 14 tertian rows the doc requires, plus the three sus rows
music21 can also express. The remaining rows (10 dyads, `5`, `q4`, `coll`)
have no music21 chord-symbol equivalent and get the human pass at freeze
(REVIEW.md) — dyads and `5` are bare interval definitions, so the
degrees-realize-tones meta-test already covers their content mechanically.
"""

import pytest

m21harmony = pytest.importorskip("music21.harmony")

import refengine as R

TBL = R.table()

# quality id -> music21 chord-symbol figure on C
M21_FIGURES = {
    "maj": "C", "m": "Cm", "dim": "Cdim", "aug": "C+",
    "6": "C6", "m6": "Cm6",
    "7": "C7", "maj7": "Cmaj7", "m7": "Cm7",
    "m7b5": "Cm7b5", "dim7": "Cdim7", "mMaj7": "CmM7",
    "add9": "Cadd9", "madd9": "Cmadd9",
    "sus2": "Csus2", "sus4": "Csus4", "7sus4": "C7sus4",
}

TERTIAN = [
    "maj", "m", "dim", "aug", "6", "m6",
    "7", "maj7", "m7", "m7b5", "dim7", "mMaj7", "add9", "madd9",
]


def m21_name_to_ascii(name: str) -> str:
    return name.replace("-", "b")


@pytest.mark.parametrize("qid", sorted(M21_FIGURES))
def test_tone_sets_match_oracle(qid):
    cs = m21harmony.ChordSymbol(M21_FIGURES[qid])
    oracle = sorted({p.pitchClass for p in cs.pitches})
    assert oracle == TBL["qualities"][qid]["tones"], qid


@pytest.mark.parametrize("qid", sorted(M21_FIGURES))
def test_member_spellings_match_oracle(qid):
    cs = m21harmony.ChordSymbol(M21_FIGURES[qid])
    oracle = {m21_name_to_ascii(p.name) for p in cs.pitches}
    root = R.Spelling.parse("C")
    ours = {
        str(R.spell_member(root, token))
        for token in TBL["qualities"][qid]["degrees"]
    }
    assert ours == oracle, qid


def test_oracle_covers_all_tertian_rows():
    """The doc's mechanical-oracle obligation is the tertian rows; make the
    coverage claim itself checkable."""
    assert set(TERTIAN) <= set(M21_FIGURES)
    non_tertian_unoracled = set(TBL["qualities"]) - set(M21_FIGURES)
    # Exactly the rows REVIEW.md sends to the human pass:
    assert non_tertian_unoracled == (
        {"5", "q4", "coll"} | {q for q in TBL["qualities"] if q.startswith("dy")}
    )


# --- Phase 3: Roman numeral oracle (PHASE3 §4) ------------------------------

def test_roman_degree_and_case_match_oracle():
    """Our numerals vs music21.roman.romanNumeralFromChord: degree and
    case must agree for tertian rows in root position across all 24
    keys. Suffix conventions differ by design (m21: viio, I7; ours:
    viidim, Imaj7) — degree+case is the mechanically shared core."""
    import sys
    from pathlib import Path
    sys.path.insert(
        0, str(Path(__file__).resolve().parent.parent / "src")
    )
    from music21 import chord as m21chord
    from music21 import key as m21key
    from music21 import roman as m21roman

    from grip_mcp import analysis as AN
    from grip_mcp import theory as GT

    ROMAN_SET = {"I", "II", "III", "IV", "V", "VI", "VII"}

    def split_ours(s):
        i = 0
        while i < len(s) and s[i] in "b#":
            i += 1
        j = i
        while j < len(s) and s[j].upper() in "IV X".replace(" ", ""):
            j += 1
        return s[i:j]  # the numeral body, case intact

    checked = 0
    for mode in ("major", "minor"):
        for tonic_pc, tonic in enumerate(
            ["c", "db", "d", "eb", "e", "f", "f#", "g", "ab", "a",
             "bb", "b"]
        ):
            gkey = GT.Key.parse(f"{tonic}-{mode}")
            m21k = m21key.Key(
                GT.lof_str(gkey.tonic_lof)
                if mode == "major"
                else GT.lof_str(gkey.tonic_lof).lower()
            )
            for qid in ("maj", "m", "dim", "7", "m7", "maj7"):
                for degree_pc in sorted(gkey.scale_pcs):
                    ours = AN.roman_numeral(degree_pc, qid, None, gkey)
                    if ours is None:
                        continue  # chromatic in this key; oracle n/a
                    row = GT.load_table()["qualities"][qid]
                    # Key-spelled members — the oracle must hear the
                    # chord as the key spells it (Gb, not F#, in db).
                    members = GT.member_spellings(
                        degree_pc, qid, f"{tonic}-{mode}"
                    )
                    base = 60 + degree_pc  # root position, stacked above

                    def to_m21(p):  # our ASCII flats -> m21's '-'
                        return p[0] + p[1:].replace("b", "-")

                    pitches = [
                        to_m21(GT.pitch_str(members[(degree_pc + t) % 12],
                                            base + t))
                        for t in row["tones"]
                    ]
                    rn = m21roman.romanNumeralFromChord(
                        m21chord.Chord(pitches), m21k
                    )
                    body = split_ours(ours)
                    assert body, ours
                    theirs = "".join(
                        ch for ch in rn.figure if ch.upper() in "IVX"
                    )
                    assert body == theirs, (
                        f"{tonic}-{mode} {qid} pc{degree_pc}: "
                        f"ours {ours} vs m21 {rn.figure}"
                    )
                    checked += 1
    assert checked > 300
