"""V1 theory core (DESIGN §4, §5.2, §7): dependency-free interval-table
code over MIDI numbers, driven by the frozen Milestone-0 quality table.

Independent of tools/reference/refengine.py by design — the two share
ONLY data/qualities.toml (DESIGN §11). Where the reference engine spells
with letter/step tables, this implementation runs entirely on
line-of-fifths integers (a spelling IS an LoF index; pc = 7·lof mod 12;
intervals are LoF deltas), so agreement between the two on every fixture
is a real check, not an echo.

Output schema per candidate is exactly §7.4: name, root, quality, bass,
inversion, intervals_from_root, missing, pitches, reading. Responses:
midi, mode, candidates (FULL set — truncation is response shaping, done
by the server layer), decided_at, pitch_report for single-PC inputs.
"""

from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from importlib import resources

ENGINE_VERSION = "1.1.0"

# --- line-of-fifths machinery ----------------------------------------------
# LoF index l: ... Fb=-8 Cb=-7 Gb=-6 Db=-5 Ab=-4 Eb=-3 Bb=-2 F=-1 C=0 G=1
# D=2 A=3 E=4 B=5 F#=6 C#=7 ... B#=12 ... ; letter = LSEQ[l % 7],
# accidental = (l - base(letter)) // 7, pitch class = 7·l mod 12.

_LSEQ = ["C", "G", "D", "A", "E", "B", "F"]
_BASE = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F": -1}
_ACC_TXT = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
_TXT_ACC = {v: k for k, v in _ACC_TXT.items()}

# Degree token -> LoF delta of the natural degree; accidentals shift by ±7.
_DEG_LOF = {"1": 0, "2": 2, "3": 4, "4": -1, "5": 1, "6": 3, "7": 5, "9": 2}
_DEG_RE = re.compile(r"^(bb|##|b|#)?([12345679])$")
_PITCH_RE = re.compile(r"^([A-G])(bb|##|b|#)?(-?\d+)$")
_KEY_RE = re.compile(r"^([a-g])(b|#)?-(major|minor)$")
_NOTE_RE = re.compile(r"^([A-G])(bb|##|b|#)?$")


class TheoryError(ValueError):
    """Instructive input rejection."""


def lof_letter(l: int) -> str:
    return _LSEQ[l % 7]


def lof_acc(l: int) -> int:
    return (l - _BASE[lof_letter(l)]) // 7


def lof_pc(l: int) -> int:
    return (7 * l) % 12


def lof_str(l: int) -> str:
    acc = lof_acc(l)
    if not -2 <= acc <= 2:
        raise TheoryError(f"unspellable (lof={l})")
    return lof_letter(l) + _ACC_TXT[acc]


def parse_note(s: str) -> int:
    """Note name -> LoF index."""
    m = _NOTE_RE.match(s)
    if not m:
        raise TheoryError(f"bad note {s!r}")
    return _BASE[m.group(1)] + 7 * _TXT_ACC[m.group(2) or ""]


def degree_lof_delta(token: str) -> int:
    m = _DEG_RE.match(token)
    if not m:
        raise TheoryError(f"bad degree token {token!r}")
    return _DEG_LOF[m.group(2)] + 7 * _TXT_ACC[m.group(1) or ""]


def parse_pitch(s: str) -> int:
    """'F#3' -> MIDI. Octave follows the letter (APPENDIX A6)."""
    m = _PITCH_RE.match(s)
    if not m:
        raise TheoryError(f"bad pitch {s!r} (expected e.g. 'E2', 'F#3')")
    letter, acc, octave = m.group(1), _TXT_ACC[m.group(2) or ""], int(m.group(3))
    natural_pc = lof_pc(_BASE[letter])
    return (octave + 1) * 12 + natural_pc + acc


def pitch_str(l: int, midi: int) -> str:
    octave = (midi - lof_acc(l)) // 12 - 1
    return f"{lof_str(l)}{octave}"


# --- the frozen table -------------------------------------------------------

@lru_cache(maxsize=1)
def load_table() -> dict:
    data = (resources.files("grip_mcp") / "data" / "qualities.toml").read_bytes()
    tbl = tomllib.loads(data.decode("utf-8"))
    canon = tbl["roots"]["canonical"]
    tbl["_canonical_lof"] = {pc: parse_note(name) for pc, name in enumerate(canon)}
    for qid, row in tbl["qualities"].items():
        row["_id"] = qid
        row["_deg_deltas"] = [degree_lof_delta(t) for t in row["degrees"]]
        row["_tone_by_pcrel"] = {
            (7 * d) % 12: d for d in row["_deg_deltas"]
        }  # rel pc -> LoF delta from root
        row["_tones"] = frozenset(row["tones"])
    tbl["_names"] = {row["name"]: qid for qid, row in tbl["qualities"].items()}
    tbl["_families"] = {}
    for qid, row in tbl["qualities"].items():
        tbl["_families"].setdefault(row["family"], set()).add(qid)
    tbl["_dyad_by_distance"] = {
        row["tones"][1]: qid
        for qid, row in tbl["qualities"].items()
        if row["gen"] == "dyad"
    }
    return tbl


def table_version() -> str:
    return load_table()["table"]["table_version"]


# --- keys -------------------------------------------------------------------

_MAJOR_DELTAS = [0, 2, 4, -1, 1, 3, 5]          # LoF deltas of the degrees
_MINOR_DELTAS = [0, 2, -3, -1, 1, -4, -2]        # natural minor


class Key:
    def __init__(self, tonic_lof: int, mode: str):
        self.tonic_lof = tonic_lof
        self.mode = mode
        deltas = _MAJOR_DELTAS if mode == "major" else _MINOR_DELTAS
        self.signature = tonic_lof if mode == "major" else tonic_lof - 3
        self._diatonic = {lof_pc(tonic_lof + d): tonic_lof + d for d in deltas}
        self.scale_pcs = frozenset(self._diatonic)
        self.tonic_pc = lof_pc(tonic_lof)

    @classmethod
    def parse(cls, s: str) -> "Key":
        m = _KEY_RE.match(s)
        if not m:
            raise TheoryError(
                f"bad context_key {s!r} (grammar: <tonic>-<mode>, lowercase, "
                "e.g. 'e-minor', 'c#-major', 'db-major')"
            )
        tonic = _BASE[m.group(1).upper()] + 7 * _TXT_ACC[m.group(2) or ""]
        return cls(tonic, m.group(3))

    def spell(self, pc: int) -> int:
        """pc -> LoF: diatonic as the scale spells it; chromatic by
        |LoF - signature| over single-accidental spellings, ties sharp."""
        pc %= 12
        if pc in self._diatonic:
            return self._diatonic[pc]
        best = None
        for l in range(-8, 13):  # the single-accidental band
            if lof_pc(l) == pc:
                k = (abs(l - self.signature), -l)
                if best is None or k < best[0]:
                    best = (k, l)
        return best[1]


# --- candidates -------------------------------------------------------------

class _Cand:
    __slots__ = ("root_pc", "row", "abs_tones", "sounding_rel", "bass_pc",
                 "missing_rel", "r0", "foreign")

    def __init__(self, root_pc, row, abs_tones, pcs, bass_pc,
                 foreign=False):
        self.root_pc = root_pc
        self.row = row
        self.abs_tones = abs_tones
        self.sounding_rel = frozenset((p - root_pc) % 12 for p in pcs)
        self.bass_pc = bass_pc
        self.foreign = foreign
        tone_rel = (
            frozenset(row["_tones"]) if row["gen"] != "coll"
            else frozenset((p - root_pc) % 12 for p in abs_tones)
        )
        self.missing_rel = tuple(sorted(tone_rel - self.sounding_rel))
        self.r0 = None
        assert not (foreign and (bass_pc - root_pc) % 12 in tone_rel)


def _rank(c: _Cand, root_lof: int) -> tuple:
    # R1 three classes (PHASE3 §3): root-is-bass < inversion < foreign.
    if c.root_pc == c.bass_pc:
        r1 = 0
    elif c.foreign:
        r1 = 2
    else:
        r1 = 1
    return (
        0 if c.r0 in (True, None) else 1,
        r1,
        0 if 0 in c.sounding_rel else 1,
        len(set(c.missing_rel) - set(c.row["discount"])),
        len(c.missing_rel),
        c.row["tier"],
        "ABCDEFG".index(lof_letter(root_lof)),
        c.row["order"],
        c.root_pc,
    )


_RANK_LABELS = ("R0", "R1", "R2", "R2", "R2", "R3", "tiebreak", "tiebreak",
                "tiebreak")


def _r0_pass(c: _Cand, key: Key) -> bool:
    if c.root_pc not in key.scale_pcs:
        return False
    if c.abs_tones <= key.scale_pcs:
        return True
    return (
        key.mode == "minor"
        and c.root_pc == (key.tonic_pc + 7) % 12
        and c.row["_id"] in ("maj", "7")
    )


def _generate(pcs: frozenset, upper_pcs: frozenset, bass_pc: int,
              tbl: dict) -> list[_Cand]:
    out: dict[tuple, _Cand] = {}
    for row in tbl["qualities"].values():
        if row["gen"] != "table":
            continue
        for root in range(12):
            abs_tones = frozenset((root + t) % 12 for t in row["tones"])
            if pcs <= abs_tones:
                key = (root, abs_tones)
                if key not in out:
                    out[key] = _Cand(root, row, abs_tones, pcs, bass_pc)
            elif (
                len(upper_pcs) >= 2
                and bass_pc not in abs_tones
                and upper_pcs <= abs_tones
            ):
                # Foreign-bass slash candidate (PHASE3 §3).
                key = (root, abs_tones)
                if key not in out:
                    out[key] = _Cand(root, row, abs_tones, pcs, bass_pc,
                                     foreign=True)
    if len(pcs) == 2:
        (other,) = pcs - {bass_pc}
        dist = (other - bass_pc) % 12
        if dist != 7:  # distance 7 generates only X5 (already above)
            row = tbl["qualities"][tbl["_dyad_by_distance"][dist]]
            key = (bass_pc, pcs)
            if key not in out:
                out[key] = _Cand(bass_pc, row, frozenset(pcs), pcs, bass_pc)
    if not out:  # totality catch-all
        row = tbl["qualities"]["coll"]
        out[(bass_pc, pcs)] = _Cand(bass_pc, row, frozenset(pcs), pcs, bass_pc)
    return list(out.values())


def _root_lof(c: _Cand, key: Key | None, tbl: dict) -> int:
    """Root spelling with the double-accidental overflow fallback
    (APPENDIX A5.1): if any member's LoF from the key-respelled root
    leaves the double-accidental band, the root falls back to the
    canonical table spelling, which never overflows."""
    if key is None:
        return tbl["_canonical_lof"][c.root_pc]
    l = key.spell(c.root_pc)
    if c.row["spell"] == "stack" and any(
        abs(lof_acc(l + d)) > 2 for d in c.row["_deg_deltas"]
    ):
        return tbl["_canonical_lof"][c.root_pc]
    return l


def _member_lofs(c: _Cand, root_lof: int, tbl: dict) -> dict[int, int]:
    """abs pc -> LoF for every chord member of this candidate."""
    if c.row["spell"] == "canonical":  # coll: canonical per PC, always
        return {p: tbl["_canonical_lof"][p] for p in c.abs_tones}
    return {
        lof_pc(root_lof + d): root_lof + d
        for d in c.row["_deg_deltas"]
    }


def _tier_label(tbl: dict, tier: int) -> str:
    return tbl["tiers"][str(tier)]


def _reading(c: _Cand, name: str, root_lof: int, members: dict[int, int],
             midis: list[int], tbl: dict) -> str:
    row = c.row
    if row["gen"] == "dyad":
        words = {
            "m2": "minor-second", "M2": "major-second", "m3": "minor-third",
            "M3": "major-third", "P4": "perfect-fourth", "A4": "tritone",
            "m6": "minor-sixth", "M6": "major-sixth", "m7": "minor-seventh",
            "M7": "major-seventh",
        }
        word = words[row["name"][2:]]
        lowest = {}
        for m in sorted(midis):
            lowest.setdefault(m % 12, m)
        other_pc = (c.root_pc + row["tones"][1]) % 12
        txt = f"Bare {word} dyad above {lof_str(root_lof)}"
        if other_pc in lowest and c.root_pc in lowest:
            spread = lowest[other_pc] - lowest[c.root_pc]
            if spread > 12:
                txt += f" (sounds compound: {spread} semitones)"
        return txt
    if row["gen"] == "coll":
        return (
            f"Unclassified collection over {lof_str(root_lof)}; "
            "no floor quality covers it"
        )
    parts = [f"{name}: {_tier_label(tbl, row['tier'])} reading"]
    if 0 not in c.sounding_rel:
        parts.append(f"root {lof_str(root_lof)} assumed")
    assumed = [
        lof_str(members[(c.root_pc + t) % 12])
        for t in c.missing_rel if t != 0
    ]
    if assumed:
        parts.append(f"{', '.join(assumed)} assumed")
    if c.root_pc != c.bass_pc:
        if c.foreign:
            parts.append(f"foreign bass {lof_str(members[c.bass_pc])}")
        else:
            parts.append(f"{lof_str(members[c.bass_pc])} in the bass")
    return "; ".join(parts)


def identify_midis(midis: list[int], context_key: str | None = None) -> dict:
    """Core entry: sounded MIDI numbers -> full ranked reading set."""
    if not midis:
        raise TheoryError("no sounding strings (all muted)")
    tbl = load_table()
    sounding = sorted(midis)
    bass_pc = sounding[0] % 12
    pcs = frozenset(m % 12 for m in midis)
    key = Key.parse(context_key) if context_key else None

    result = {
        "engine_version": ENGINE_VERSION,
        "table_version": table_version(),
        "midi": sounding,
        "mode": "context" if key else "context-free",
    }

    if len(pcs) == 1:
        l = tbl["_canonical_lof"][bass_pc]
        result["pitch_report"] = {
            "pitch_class": lof_str(l),
            "pitches": [pitch_str(l, m) for m in sounding],
            "doubling": len(sounding),
            "note": "single distinct pitch class; no candidates (DESIGN §7.1)",
        }
        result["candidates"] = []
        result["decided_at"] = None
        return result

    upper_pcs = frozenset(m % 12 for m in sounding[1:])
    cands = _generate(pcs, upper_pcs, bass_pc, tbl)
    if key:
        for c in cands:
            c.r0 = _r0_pass(c, key)
    ranked = sorted(cands, key=lambda c: _rank(c, _root_lof(c, key, tbl)))

    out = []
    for c in ranked:
        root_lof = _root_lof(c, key, tbl)
        members = _member_lofs(c, root_lof, tbl)
        if c.foreign:
            # Foreign bass: not a member — canonical, or key-respelled.
            members[c.bass_pc] = (
                key.spell(c.bass_pc) if key
                else tbl["_canonical_lof"][c.bass_pc]
            )
        suffix = c.row["name"]
        if c.bass_pc != c.root_pc:
            name = f"{lof_str(root_lof)}{suffix}/{lof_str(members[c.bass_pc])}"
        else:
            name = f"{lof_str(root_lof)}{suffix}"
        if c.foreign or c.row["inversion"] != "member-index":
            inversion = None
        else:
            # Index of the bass member in degree order (0 = root position).
            rel = (c.bass_pc - c.root_pc) % 12
            inversion = c.row["_deg_deltas"].index(c.row["_tone_by_pcrel"][rel])
        entry = {
            "name": name,
            "root": lof_str(root_lof),
            "quality": c.row["_id"],
            "bass": lof_str(members[c.bass_pc]),
            "inversion": inversion,
            "intervals_from_root": sorted(c.sounding_rel),
            "missing": [
                lof_str(members[(c.root_pc + t) % 12]) for t in c.missing_rel
            ],
            "pitches": [pitch_str(members[m % 12], m) for m in sounding],
            "reading": _reading(c, name, root_lof, members, sounding, tbl),
            "foreign_bass": c.foreign,
        }
        if key:
            entry["r0_pass"] = bool(c.r0)
        out.append(entry)

    result["candidates"] = out
    if len(ranked) == 1:
        result["decided_at"] = "unique"
    else:
        k1 = _rank(ranked[0], _root_lof(ranked[0], key, tbl))
        k2 = _rank(ranked[1], _root_lof(ranked[1], key, tbl))
        result["decided_at"] = next(
            _RANK_LABELS[i] for i, (a, b) in enumerate(zip(k1, k2)) if a != b
        )
    return result


def identify(strings, tuning_pitches: list[str],
             context_key: str | None = None) -> dict:
    """Frets + tuning pitch strings -> identify. The storage layer resolves
    tuning names/capo chains to pitch strings before calling this."""
    if len(strings) != len(tuning_pitches):
        raise TheoryError(
            f"strings length {len(strings)} does not match tuning length "
            f"{len(tuning_pitches)}"
        )
    for f in strings:
        if f is not None and (not isinstance(f, int) or f < 0):
            raise TheoryError(f"bad fret {f!r} (null = muted, 0 = open, n >= 0)")
    opens = [parse_pitch(p) for p in tuning_pitches]
    midis = [o + f for o, f in zip(opens, strings) if f is not None]
    r = identify_midis(midis, context_key)
    r["tuning"] = list(tuning_pitches)
    r["strings"] = list(strings)
    return r


# --- chord-name helpers (Phase 2a: find_voicings input/output) --------------

def parse_chord_name(s: str) -> tuple[int, str, int | None]:
    """Canonical chord name -> (root_pc, quality_id, bass_pc|None).

    The suffix must name a specific table quality (families are ambiguous
    for search — instructive error names the members). `coll` has no
    interval structure and is rejected. Bass must be a chord tone
    (foreign-bass slash chords are Phase 3). Enharmonic and Unicode
    accidental inputs resolve by PC as everywhere else.
    """
    tbl = load_table()
    src = _norm(s)
    body, bass_pc = src, None
    if "/" in src:
        body, bass = src.split("/", 1)
        try:
            bass_pc = _pc_of_name(bass)
        except TheoryError:
            raise TheoryError(f"bad bass {bass!r} in {s!r}") from None
    m = re.match(r"^([A-G])(bb|##|b|#)?(.*)$", body)
    if not m:
        raise TheoryError(f"bad chord name {s!r}: no root")
    root_pc = lof_pc(_BASE[m.group(1)] + 7 * _TXT_ACC[m.group(2) or ""])
    suffix = m.group(3)
    if suffix in tbl["_names"]:
        qid = tbl["_names"][suffix]
    elif suffix in tbl["_families"]:
        members = sorted(
            tbl["qualities"][q]["name"] or "(major)"
            for q in tbl["_families"][suffix]
        )
        raise TheoryError(
            f"{suffix!r} is a family, not a quality; voicing search needs "
            f"one of: {members}"
        )
    else:
        raise TheoryError(
            f"unknown quality suffix {suffix!r} in {s!r}"
        )
    if qid == "coll":
        raise TheoryError(
            "coll has no interval structure; use render_neck with a pitch "
            "set, or pick a table quality"
        )
    tones = {(root_pc + t) % 12 for t in tbl["qualities"][qid]["tones"]}
    if bass_pc is not None and bass_pc not in tones:
        raise TheoryError(
            f"bass {lof_str(load_table()['_canonical_lof'][bass_pc])} is "
            f"not a chord tone of {body}; foreign-bass slash chords are "
            "Phase 3"
        )
    return root_pc, qid, bass_pc


def chord_root_lof(root_pc: int, qid: str,
                   context_key: str | None = None) -> int:
    """Root spelling for a (root, quality) with the A5.1 overflow
    fallback, matching identify's behavior exactly."""
    tbl = load_table()
    if context_key is None:
        return tbl["_canonical_lof"][root_pc]
    key = Key.parse(context_key)
    l = key.spell(root_pc)
    row = tbl["qualities"][qid]
    if row["spell"] == "stack" and any(
        abs(lof_acc(l + d)) > 2 for d in row["_deg_deltas"]
    ):
        return tbl["_canonical_lof"][root_pc]
    return l


def member_spellings(root_pc: int, qid: str,
                     context_key: str | None = None) -> dict[int, int]:
    """abs pc -> LoF for the chord's members (strict stacking, §5.2.2)."""
    tbl = load_table()
    row = tbl["qualities"][qid]
    root_lof = chord_root_lof(root_pc, qid, context_key)
    return {lof_pc(root_lof + d): root_lof + d for d in row["_deg_deltas"]}


def chord_name(root_pc: int, qid: str, bass_pc: int | None = None,
               context_key: str | None = None) -> str:
    tbl = load_table()
    root_lof = chord_root_lof(root_pc, qid, context_key)
    name = lof_str(root_lof) + tbl["qualities"][qid]["name"]
    if bass_pc is not None and bass_pc != root_pc:
        members = member_spellings(root_pc, qid, context_key)
        name += "/" + lof_str(members[bass_pc])
    return name


# --- chosen resolution (three tiers; §5.1 / APPENDIX A2) --------------------

_UNI = {"♯": "#", "♭": "b", "\U0001d12a": "##", "\U0001d12b": "bb"}


def _norm(s: str) -> str:
    for u, a in _UNI.items():
        s = s.replace(u, a)
    return s


def _pc_of_name(s: str) -> int:
    m = _NOTE_RE.match(s)
    if not m:
        raise TheoryError(f"bad note {s!r}")
    return lof_pc(parse_note(s))


def resolve_chosen(chosen: str, candidates: list[dict]) -> dict:
    tbl = load_table()
    s = _norm(chosen)
    bass_pc = None
    body = s
    if "/" in s:
        body, bass = s.split("/", 1)
        try:
            bass_pc = _pc_of_name(bass)
        except TheoryError:
            return {"status": "miss",
                    "suggestions": [c["name"] for c in candidates[:8]]}
    m = re.match(r"^([A-G])(bb|##|b|#)?(.*)$", body)
    suffixes = set(tbl["_names"]) | set(tbl["_families"])
    if not m or m.group(3) not in suffixes:
        return {"status": "miss",
                "suggestions": [c["name"] for c in candidates[:8]]}
    root_pc = lof_pc(_BASE[m.group(1)] + 7 * _TXT_ACC[m.group(2) or ""])
    suffix = m.group(3)

    exact = [c for c in candidates if c["name"] == s]
    if len(exact) == 1:
        return {"status": "resolved", "name": exact[0]["name"], "tier": 1}

    def matches(qids):
        # Foreign-bass candidates are reachable at tiers 2-3 only via an
        # explicit /bass (A2 amendment): shorthand must never silently
        # land on a foreign-bass fragment; the exact name always works.
        return [
            c for c in candidates
            if _pc_of_name(c["root"]) == root_pc and c["quality"] in qids
            and not (c.get("foreign_bass") and bass_pc is None)
            and (bass_pc is None or _pc_of_name(c["bass"]) == bass_pc)
        ]

    if suffix in tbl["_names"]:
        hits = matches({tbl["_names"][suffix]})
        if len(hits) == 1:
            return {"status": "resolved", "name": hits[0]["name"], "tier": 2}
        if hits:
            return {"status": "ambiguous", "matches": [c["name"] for c in hits]}
    if suffix in tbl["_families"]:
        hits = matches(tbl["_families"][suffix])
        if len(hits) == 1:
            return {"status": "resolved", "name": hits[0]["name"], "tier": 3}
        if hits:
            return {"status": "ambiguous", "matches": [c["name"] for c in hits]}
    return {"status": "miss", "suggestions": [c["name"] for c in candidates[:8]]}


def covariant_chosen(old_candidates: list[dict], old_name: str,
                     new_candidates: list[dict], semitones: int) -> str | None:
    """Chosen transposes by re-derivation, never string transform (§6.1)."""
    old = next((c for c in old_candidates if c["name"] == old_name), None)
    if old is None:
        return None
    want = (
        (_pc_of_name(old["root"]) + semitones) % 12,
        old["quality"],
        (_pc_of_name(old["bass"]) + semitones) % 12,
    )
    for c in new_candidates:
        if (_pc_of_name(c["root"]), c["quality"], _pc_of_name(c["bass"])) == want:
            return c["name"]
    return None
