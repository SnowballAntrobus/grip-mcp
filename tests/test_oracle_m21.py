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
