"""grip-mcp reference derivation engine (Milestone 0).

Standalone by design (DESIGN §11): shares ONLY the quality table
(src/grip_mcp/data/qualities.toml) with the eventual implementation. All
fixture expectations in tests/fixtures/ are this module's reviewed output,
never hand derivations — hand-application of the ranking rules went 0-for-4
across the design reviews.

Implements, mechanically, the whole of DESIGN §7 plus the spelling chain of
§5.2 and the three-tier `chosen` resolution of §5.1 / APPENDIX A2:

* candidate generation: 12 root PCs x table rows under exact PC cover;
  bass-rooted interval dyads for 2-distinct-PC inputs (distance 7 -> only
  X5; distance 5 gains the inverted X5/<bass> through ordinary generation
  of the `5` row); conditional `coll` catch-all;
* strict lexicographic ranking R0..R3 + tie-break (alphabetical root
  letter, quality-order column, root-PC determinism backstop) and
  `decided_at` (the rung at which #1 separated from #2);
* spelling: canonical root table context-free; key respelling (scale
  spelling for diatonic roots, |LoF - signature| with sharp-side ties for
  chromatic roots); strict member stacking from the (re)spelled root;
  `coll` members per the canonical table applied to each PC (§5.2.2 —
  literal, including under context, where only coll's *root* respells).

Engine versioning: REF_ENGINE_VERSION bumps whenever output could change.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REF_ENGINE_VERSION = "0.1.0"

_TABLE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "grip_mcp" / "data" / "qualities.toml"
)

LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Line-of-fifths base index per letter (F=-1 .. B=5); LoF = base + 7*acc.
LETTER_LOF = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
ACC_VALUE = {"": 0, "b": -1, "bb": -2, "#": 1, "##": 2}
ACC_STR = {0: "", -1: "b", -2: "bb", 1: "#", 2: "##"}
DEGREE_SEMIS = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11, "9": 14}
_DEGREE_RE = re.compile(r"^(bb|##|b|#)?([12345679])$")
_PITCH_RE = re.compile(r"^([A-G])(bb|##|b|#)?(-?\d+)$")
_KEY_RE = re.compile(r"^([a-g])(b|#)?-(major|minor)$")

INTERVAL_WORDS = {
    "m2": "minor-second", "M2": "major-second", "m3": "minor-third",
    "M3": "major-third", "P4": "perfect-fourth", "A4": "tritone",
    "m6": "minor-sixth", "M6": "major-sixth", "m7": "minor-seventh",
    "M7": "major-seventh",
}

BUILTIN_TUNINGS = {
    "standard": ["E2", "A2", "D3", "G3", "B3", "E4"],
    "dadgad": ["D2", "A2", "D3", "G3", "A3", "D4"],
}


class InputError(ValueError):
    """Structured, instructive input rejection (DESIGN §6.4 posture)."""


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------

def load_table(path: Path = _TABLE_PATH) -> dict:
    with open(path, "rb") as f:
        table = tomllib.load(f)
    # Precompute realized degree PCs per row (root-relative).
    for qid, row in table["qualities"].items():
        row["id"] = qid
        row["degree_pcs"] = [
            (DEGREE_SEMIS[m.group(2)] + ACC_VALUE[m.group(1) or ""]) % 12
            for m in (_DEGREE_RE.match(t) for t in row["degrees"])
            if m
        ]
    return table


_TABLE = None


def table() -> dict:
    global _TABLE
    if _TABLE is None:
        _TABLE = load_table()
    return _TABLE


# --------------------------------------------------------------------------
# Spelling
# --------------------------------------------------------------------------

class Spelling:
    """A letter + accidental; octave-free."""

    __slots__ = ("letter", "acc")

    def __init__(self, letter: str, acc: int):
        self.letter = letter
        self.acc = acc

    @classmethod
    def parse(cls, s: str) -> "Spelling":
        m = re.match(r"^([A-G])(bb|##|b|#)?$", s)
        if not m:
            raise InputError(f"bad spelling {s!r}")
        return cls(m.group(1), ACC_VALUE[m.group(2) or ""])

    @property
    def pc(self) -> int:
        return (LETTER_PC[self.letter] + self.acc) % 12

    @property
    def lof(self) -> int:
        return LETTER_LOF[self.letter] + 7 * self.acc

    def __str__(self) -> str:
        return self.letter + ACC_STR[self.acc]

    def __repr__(self) -> str:  # pragma: no cover
        return f"Spelling({self})"


def spell_canonical(pc: int) -> Spelling:
    return Spelling.parse(table()["roots"]["canonical"][pc % 12])


def spell_member(root: Spelling, degree_token: str) -> Spelling:
    """Strict interval stacking from a (re)spelled root (§5.2.2)."""
    m = _DEGREE_RE.match(degree_token)
    if not m:
        raise InputError(f"bad degree token {degree_token!r}")
    acc, deg = ACC_VALUE[m.group(1) or ""], m.group(2)
    steps = (int(deg) - 1) % 7
    letter = LETTERS[(LETTERS.index(root.letter) + steps) % 7]
    target_pc = (root.pc + DEGREE_SEMIS[deg] + acc) % 12
    needed = ((target_pc - LETTER_PC[letter] + 6) % 12) - 6
    if not -2 <= needed <= 2:
        # Beyond double accidentals — reachable only from extreme context
        # respellings; callers fall back per APPENDIX A5.1.
        raise InputError(f"unspellable member {degree_token} on {root}")
    return Spelling(letter, needed)


def pitch_name(sp: Spelling, midi: int) -> str:
    """Scientific pitch, octave follows the LETTER (APPENDIX A6)."""
    octave = (midi - sp.acc) // 12 - 1
    return f"{sp}{octave}"


def parse_pitch(s: str) -> int:
    m = _PITCH_RE.match(s)
    if not m:
        raise InputError(f"bad pitch {s!r} (expected e.g. 'E2', 'F#3')")
    letter, acc, octave = m.group(1), ACC_VALUE[m.group(2) or ""], int(m.group(3))
    return (octave + 1) * 12 + LETTER_PC[letter] + acc


# --------------------------------------------------------------------------
# Keys (context_key)
# --------------------------------------------------------------------------

MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]  # natural minor (R0 basis)


class Key:
    def __init__(self, tonic: Spelling, mode: str):
        self.tonic = tonic
        self.mode = mode
        steps = MAJOR_STEPS if mode == "major" else MINOR_STEPS
        self.scale_pcs = [(tonic.pc + s) % 12 for s in steps]
        # Signature anchor: LoF of the tonic for major; relative major for
        # minor (natural-minor basis) — APPENDIX A5.
        self.signature = tonic.lof if mode == "major" else tonic.lof - 3
        # Scale spellings: sequential letters from the tonic, accidentals
        # forced by the PCs.
        self._degree_spelling = {}
        start = LETTERS.index(tonic.letter)
        for i, pc in enumerate(self.scale_pcs):
            letter = LETTERS[(start + i) % 7]
            needed = ((pc - LETTER_PC[letter] + 6) % 12) - 6
            self._degree_spelling[pc] = Spelling(letter, needed)

    @classmethod
    def parse(cls, s: str) -> "Key":
        m = _KEY_RE.match(s)
        if not m:
            raise InputError(
                f"bad context_key {s!r} (grammar: <tonic>-<mode>, lowercase, "
                "e.g. 'e-minor', 'c#-major', 'db-major')"
            )
        tonic = Spelling(m.group(1).upper(), ACC_VALUE[m.group(2) or ""])
        return cls(tonic, m.group(3))

    def spell_root(self, pc: int) -> Spelling:
        """Key respelling: diatonic = as the scale spells it; chromatic =
        |LoF - signature| minimum over {flat, natural, sharp} spellings,
        ties sharp-side (APPENDIX A5)."""
        pc %= 12
        if pc in self._degree_spelling:
            return self._degree_spelling[pc]
        candidates = []
        for letter in LETTERS:
            acc = ((pc - LETTER_PC[letter] + 6) % 12) - 6
            if -1 <= acc <= 1:
                sp = Spelling(letter, acc)
                candidates.append(sp)
        # min |LoF - s|; tie -> larger LoF (sharp side).
        best = min(candidates, key=lambda sp: (abs(sp.lof - self.signature), -sp.lof))
        return best


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------

class Candidate:
    def __init__(self, root_pc: int, row: dict, sounding_rel: frozenset,
                 bass_pc: int, tones: tuple):
        self.root_pc = root_pc
        self.row = row
        self.qid = row["id"]
        self.tones = tones                      # absolute-interval tone set
        self.sounding_rel = sounding_rel        # sounding PCs relative to root
        self.bass_pc = bass_pc
        self.missing_rel = tuple(sorted(set(tones) - set(sounding_rel)))
        self.r0_pass = None                     # set in context mode

    # -- ranking ------------------------------------------------------------

    def rank_key(self, root_spelling: Spelling) -> tuple:
        r0 = 0 if self.r0_pass in (True, None) else 1
        r1 = 0 if self.root_pc == self.bass_pc else 1
        root_sounds = 0 in self.sounding_rel
        r2a = 0 if root_sounds else 1
        discounted = set(self.row["discount"])
        r2b = len(set(self.missing_rel) - discounted)
        r2c = len(self.missing_rel)
        r3 = self.row["tier"]
        letter = "ABCDEFG".index(root_spelling.letter)
        return (r0, r1, r2a, r2b, r2c, r3, letter, self.row["order"], self.root_pc)


RANK_LABELS = ["R0", "R1", "R2", "R2", "R2", "R3", "tiebreak", "tiebreak", "tiebreak"]


def candidate_root_spelling(cand: Candidate, key: Key | None) -> Spelling:
    """The candidate's root spelling, with the double-accidental overflow
    fallback (APPENDIX A5.1): if member stacking from the key-respelled
    root would need a triple accidental (e.g. dim7 on an Fb respelling),
    the root falls back to the canonical table, which never overflows.
    Found by randomized parity testing; deterministic and per-candidate."""
    if key is None:
        return spell_canonical(cand.root_pc)
    root_sp = key.spell_root(cand.root_pc)
    if cand.row["spell"] == "stack":
        try:
            for token in cand.row["degrees"]:
                spell_member(root_sp, token)
        except InputError:
            return spell_canonical(cand.root_pc)
    return root_sp


def _spell_candidate(cand: Candidate, key: Key | None) -> dict:
    """Root, member and bass spellings for one candidate."""
    row = cand.row
    root_sp = candidate_root_spelling(cand, key)

    member_sp: dict[int, Spelling] = {}
    if row["spell"] == "canonical":  # coll — §5.2.2, literal: members stay
        for t in cand.tones:         # canonical even when the root respells
            pc = (cand.root_pc + t) % 12
            member_sp[pc] = spell_canonical(pc)
    else:
        for token in row["degrees"]:
            sp = spell_member(root_sp, token)
            member_sp[sp.pc] = sp
    return {"root": root_sp, "members": member_sp}


def _reading(cand: Candidate, spelled: dict, midis: list[int],
             name: str, tier_labels: dict) -> str:
    row = cand.row
    root_sp = spelled["root"]
    if row["gen"] == "dyad":
        token = row["name"][2:]
        word = INTERVAL_WORDS[token]
        spread = None
        by_pc = {}
        for m in sorted(midis):
            by_pc.setdefault(m % 12, m)
        other_pc = (cand.root_pc + cand.tones[1]) % 12
        if cand.root_pc in by_pc and other_pc in by_pc:
            spread = by_pc[other_pc] - by_pc[cand.root_pc]
        txt = f"Bare {word} dyad above {root_sp}"
        if spread is not None and spread > 12:
            txt += f" (sounds compound: {spread} semitones)"
        return txt
    if row["gen"] == "coll":
        return f"Unclassified collection over {root_sp}; no floor quality covers it"
    parts = [f"{name}: {tier_labels[str(row['tier'])]} reading"]
    if 0 not in cand.sounding_rel:
        parts.append(f"root {root_sp} assumed")
    if cand.missing_rel and not (len(cand.missing_rel) == 1 and 0 in cand.missing_rel):
        missing = [t for t in cand.missing_rel if t != 0]
        names = [str(spelled["members"][(cand.root_pc + t) % 12]) for t in missing]
        if names:
            parts.append(f"{', '.join(names)} assumed")
    if cand.root_pc != cand.bass_pc:
        bass_sp = spelled["members"].get(cand.bass_pc)
        parts.append(f"{bass_sp} in the bass")
    return "; ".join(parts)


# --------------------------------------------------------------------------
# identify
# --------------------------------------------------------------------------

def resolve_tuning(tuning) -> list[str]:
    if isinstance(tuning, str):
        try:
            return BUILTIN_TUNINGS[tuning]
        except KeyError:
            raise InputError(
                f"unknown tuning {tuning!r}; reference tunings: "
                f"{sorted(BUILTIN_TUNINGS)}"
            ) from None
    return list(tuning)


def identify(strings, tuning="standard", context_key: str | None = None) -> dict:
    tuning_pitches = resolve_tuning(tuning)
    if len(strings) != len(tuning_pitches):
        raise InputError(
            f"strings length {len(strings)} != tuning length "
            f"{len(tuning_pitches)}"
        )
    open_midis = [parse_pitch(p) for p in tuning_pitches]
    midis = [
        om + fret
        for om, fret in zip(open_midis, strings)
        if fret is not None
    ]
    if any(f is not None and f < 0 for f in strings):
        raise InputError("negative fret")
    if not midis:
        raise InputError("no sounding strings (all muted)")

    sounding = sorted(midis)
    bass_midi = sounding[0]
    bass_pc = bass_midi % 12
    pcs = frozenset(m % 12 for m in midis)
    key = Key.parse(context_key) if context_key else None
    tbl = table()

    result = {
        "engine_version": REF_ENGINE_VERSION,
        "table_version": tbl["table"]["table_version"],
        "input": {
            "strings": list(strings),
            "tuning": tuning_pitches,
            "context_key": context_key,
        },
        "midi": sounding,
        "mode": "context" if key else "context-free",
    }

    if len(pcs) == 1:
        sp = spell_canonical(bass_pc)
        result["pitch_report"] = {
            "pitch_class": str(sp),
            "pitches": [pitch_name(sp, m) for m in sounding],
            "doubling": len(sounding),
            "note": "single distinct pitch class; no candidates (DESIGN §7.1)",
        }
        result["candidates"] = []
        result["decided_at"] = None
        return result

    candidates = _generate(pcs, bass_pc, tbl)
    if key:
        for c in candidates:
            c.r0_pass = _r0(c, key)

    ranked = sorted(
        candidates,
        key=lambda c: c.rank_key(candidate_root_spelling(c, key)),
    )

    tier_labels = {str(k): v for k, v in tbl["tiers"].items()}
    out = []
    for c in ranked:
        spelled = _spell_candidate(c, key)
        root_sp = spelled["root"]
        suffix = c.row["name"]
        if c.bass_pc != c.root_pc:
            bass_sp = spelled["members"][c.bass_pc]
            name = f"{root_sp}{suffix}/{bass_sp}"
        else:
            name = f"{root_sp}{suffix}"
        inversion = None
        if c.row["inversion"] == "member-index":
            inversion = c.row["degree_pcs"].index((c.bass_pc - c.root_pc) % 12)
        entry = {
            "name": name,
            "root": str(root_sp),
            "quality": c.qid,
            "bass": str(spelled["members"].get(c.bass_pc, root_sp)),
            "inversion": inversion,
            "intervals_from_root": sorted(c.sounding_rel),
            "missing": [
                str(spelled["members"][(c.root_pc + t) % 12])
                for t in c.missing_rel
            ],
            "pitches": [
                pitch_name(
                    spelled["members"].get(m % 12, spell_canonical(m % 12)), m
                )
                for m in sounding
            ],
            "reading": _reading(c, spelled, sounding, name, tier_labels),
            "root_is_bass": c.root_pc == c.bass_pc,
            "root_sounds": 0 in c.sounding_rel,
        }
        if key:
            entry["r0_pass"] = bool(c.r0_pass)
        out.append(entry)

    result["candidates"] = out
    result["decided_at"] = _decided_at(ranked, key)
    return result


def _generate(pcs: frozenset, bass_pc: int, tbl: dict) -> list[Candidate]:
    rows = tbl["qualities"]
    found: dict[tuple, Candidate] = {}

    # Table rows: 12 roots x rows, exact PC cover (sounding ⊆ tones).
    for row in rows.values():
        if row["gen"] != "table":
            continue
        tone_set = frozenset(row["tones"])
        for root in range(12):
            rel = frozenset((p - root) % 12 for p in pcs)
            if rel <= tone_set:
                dk = (root, frozenset((root + t) % 12 for t in row["tones"]))
                if dk not in found:  # table rows beat special-case generators
                    found[dk] = Candidate(
                        root, row, rel, bass_pc, tuple(row["tones"])
                    )

    # Dyads: one candidate, rooted at the bass, 2-distinct-PC inputs only;
    # PC distance 7 generates only X5 (already covered by the `5` row above).
    if len(pcs) == 2:
        (other,) = [p for p in pcs if p != bass_pc]
        distance = (other - bass_pc) % 12
        if distance != 7:
            row = rows["dy" + _token_for(distance, tbl)]
            dk = (bass_pc, frozenset(pcs))
            if dk not in found:
                found[dk] = Candidate(
                    bass_pc, row, frozenset([0, distance]), bass_pc,
                    (0, distance),
                )

    # Totality catch-all: iff nothing covers, coll at the bass, zero missing.
    if not found:
        row = rows["coll"]
        rel = tuple(sorted((p - bass_pc) % 12 for p in pcs))
        found[(bass_pc, pcs)] = Candidate(
            bass_pc, row, frozenset(rel), bass_pc, rel
        )

    return list(found.values())


def _token_for(distance: int, tbl: dict) -> str:
    for token in tbl["grammar"]["dyad_tokens"]:
        if tbl["qualities"]["dy" + token]["tones"][1] == distance:
            return token
    raise AssertionError(f"no dyad token for distance {distance}")  # pragma: no cover


def _r0(cand: Candidate, key: Key) -> bool:
    """Binary diatonic membership over the complete chord-tone set, root on
    a scale degree; minor admits the V major triad and V7 purely by
    quality + degree (DESIGN §7.2)."""
    scale = set(key.scale_pcs)
    if cand.root_pc not in scale:
        return False
    abs_tones = {(cand.root_pc + t) % 12 for t in cand.tones}
    if abs_tones <= scale:
        return True
    if (
        key.mode == "minor"
        and cand.root_pc == (key.tonic.pc + 7) % 12
        and cand.qid in ("maj", "7")
    ):
        return True
    return False


def _decided_at(ranked: list[Candidate], key: Key | None) -> str | None:
    if not ranked:
        return None
    if len(ranked) == 1:
        return "unique"
    def kf(c):
        return c.rank_key(candidate_root_spelling(c, key))
    k1, k2 = kf(ranked[0]), kf(ranked[1])
    for i, (a, b) in enumerate(zip(k1, k2)):
        if a != b:
            return RANK_LABELS[i]
    return "tiebreak"  # pragma: no cover — full keys cannot tie post-dedup


# --------------------------------------------------------------------------
# chosen resolution (three tiers; APPENDIX A2)
# --------------------------------------------------------------------------

_UNICODE_ACCIDENTALS = {"♯": "#", "♭": "b", "\U0001d12a": "##",
                        "\U0001d12b": "bb"}


def normalize_chosen(s: str) -> str:
    for u, a in _UNICODE_ACCIDENTALS.items():
        s = s.replace(u, a)
    return s


def parse_chosen(s: str, tbl: dict) -> tuple[int, str, int | None]:
    """-> (root_pc, suffix, bass_pc|None). Raises InputError on no-parse."""
    s = normalize_chosen(s)
    bass_pc = None
    if "/" in s:
        s, bass_str = s.split("/", 1)
        m = re.match(r"^([A-G])(bb|##|b|#)?$", bass_str)
        if not m:
            raise InputError(f"bad bass {bass_str!r}")
        bass_pc = Spelling(m.group(1), ACC_VALUE[m.group(2) or ""]).pc
    m = re.match(r"^([A-G])(bb|##|b|#)?(.*)$", s)
    if not m:
        raise InputError(f"bad chosen {s!r}: no root")
    root_pc = Spelling(m.group(1), ACC_VALUE[m.group(2) or ""]).pc
    suffix = m.group(3)
    names = {row["name"] for row in tbl["qualities"].values()}
    fams = set(tbl["grammar"]["families"])
    if suffix not in names | fams:
        raise InputError(f"bad chosen {s!r}: unknown suffix {suffix!r}")
    return root_pc, suffix, bass_pc


def resolve_chosen(chosen: str, candidates: list[dict]) -> dict:
    """Resolve a chosen string against a FULL candidate set (§5.1).

    Returns {"status": "resolved", "name": ...} | {"status": "ambiguous",
    "matches": [...]} | {"status": "miss", "suggestions": [...]}.
    """
    tbl = table()
    try:
        root_pc, suffix, bass_pc = parse_chosen(chosen, tbl)
    except InputError:
        return {
            "status": "miss",
            "suggestions": [c["name"] for c in candidates[:8]],
        }

    def cpc(spelled: str) -> int:
        return Spelling.parse(spelled).pc

    norm = normalize_chosen(chosen)
    # Tier 1: exact canonical match.
    exact = [c for c in candidates if c["name"] == norm]
    if len(exact) == 1:
        return {"status": "resolved", "name": exact[0]["name"], "tier": 1}

    def bass_ok(c):
        return bass_pc is None or cpc(c["bass"]) == bass_pc

    # Tier 2: root-PC + exact quality row.
    qid_by_name = {row["name"]: qid for qid, row in tbl["qualities"].items()}
    if suffix in qid_by_name:
        hits = [
            c for c in candidates
            if cpc(c["root"]) == root_pc and c["quality"] == qid_by_name[suffix]
            and bass_ok(c)
        ]
        if len(hits) == 1:
            return {"status": "resolved", "name": hits[0]["name"], "tier": 2}
        if len(hits) > 1:
            return {"status": "ambiguous", "matches": [c["name"] for c in hits]}

    # Tier 3: root-PC + family.
    if suffix in set(tbl["grammar"]["families"]):
        fam_rows = {
            qid for qid, row in tbl["qualities"].items()
            if row["family"] == suffix
        }
        hits = [
            c for c in candidates
            if cpc(c["root"]) == root_pc and c["quality"] in fam_rows
            and bass_ok(c)
        ]
        if len(hits) == 1:
            return {"status": "resolved", "name": hits[0]["name"], "tier": 3}
        if len(hits) > 1:
            return {"status": "ambiguous", "matches": [c["name"] for c in hits]}

    return {
        "status": "miss",
        "suggestions": [c["name"] for c in candidates[:8]],
    }


# --------------------------------------------------------------------------
# Covariant chosen re-derivation (DESIGN §6.1 / §11)
# --------------------------------------------------------------------------

def covariant_chosen(old_result: dict, old_chosen_name: str,
                     new_result: dict, semitones: int) -> str | None:
    """Transpose a chosen by re-derivation, never by string transform.

    Finds the old chosen among old candidates, maps (root, quality, bass)
    by +semitones mod 12, and returns the matching new candidate's
    canonical name (the covariance property guarantees it exists).
    """
    old = next(
        (c for c in old_result["candidates"] if c["name"] == old_chosen_name),
        None,
    )
    if old is None:
        return None
    want_root = (Spelling.parse(old["root"]).pc + semitones) % 12
    want_bass = (Spelling.parse(old["bass"]).pc + semitones) % 12
    for c in new_result["candidates"]:
        if (
            Spelling.parse(c["root"]).pc == want_root
            and c["quality"] == old["quality"]
            and Spelling.parse(c["bass"]).pc == want_bass
        ):
            return c["name"]
    return None
