"""Phase 3 analysis (docs/PHASE3_DESIGN.md): Roman numerals in candidate
keys, bass line, common tones, voice-leading distance, modulation
segmentation. Deterministic, documented rules throughout — never tuned
weights. Read-only and derived: nothing here writes state.
"""

from __future__ import annotations

from . import theory as TH

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]
_LETTERS = ["C", "D", "E", "F", "G", "A", "B"]


# ---------------------------------------------------------------------------
# Voice leading: minimal-total-|semitone| monotone matching (PHASE3 §2.4)
# ---------------------------------------------------------------------------

def voice_matching(a: list[int], b: list[int]) -> dict:
    """Match sorted MIDI lists a -> b minimizing total |motion| over a
    monotone (non-crossing by construction) matching; DP chooses which
    notes of the longer list go unmatched. Ties break toward matching
    lower notes first."""
    a, b = sorted(a), sorted(b)
    n, m = len(a), len(b)
    k = min(n, m)
    INF = float("inf")
    # dp[i][j] = min cost matching first i of a with first j of b,
    # using exactly min(i, j) matches... we need: total matches = k and
    # monotone. dp over (i, j, matched) is heavy; standard trick: cost
    # of leaving a note unmatched is 0 but the count of matches must be
    # k = min(n, m) — equivalently, every note of the SHORTER list is
    # matched. WLOG ensure a is the shorter (flip at the end).
    flipped = n > m
    if flipped:
        a, b = b, a
        n, m = m, n
    # dp[i][j]: first i notes of a (all matched) using first j notes of b.
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    choice = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0] = [0.0] * (m + 1)
    for i in range(1, n + 1):
        for j in range(i, m + 1):
            skip = dp[i][j - 1]           # b[j-1] unmatched
            take = dp[i - 1][j - 1] + abs(a[i - 1] - b[j - 1])
            # Tie -> prefer matching (lower notes matched first).
            if take <= skip:
                dp[i][j] = take
                choice[i][j] = "take"
            else:
                dp[i][j] = skip
                choice[i][j] = "skip"
    # Recover pairs.
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        if choice[i][j] == "take":
            pairs.append((a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        else:
            j -= 1
    pairs.reverse()
    matched_a = [p[0] for p in pairs]
    matched_b = [p[1] for p in pairs]
    if flipped:
        pairs = [(y, x) for (x, y) in pairs]
        matched_a, matched_b = matched_b, matched_a
        a, b = b, a
    left = _multiset_minus(a, matched_a)
    entered = _multiset_minus(b, matched_b)
    return {
        "pairs": pairs,
        "total": int(sum(abs(y - x) for x, y in pairs)),
        "left": left,
        "entered": entered,
    }


def _multiset_minus(whole: list[int], part: list[int]) -> list[int]:
    out = list(whole)
    for x in part:
        out.remove(x)
    return sorted(out)


# ---------------------------------------------------------------------------
# Roman numerals (PHASE3 §2.5)
# ---------------------------------------------------------------------------

_MINOR_THIRD_STRIP = {
    "m": "", "m7": "7", "m6": "6", "madd9": "add9", "mMaj7": "Maj7",
    "m7b5": "7b5",
}


def roman_numeral(root_pc: int, qid: str, bass_pc: int | None,
                  key: TH.Key) -> str | None:
    """Mechanical numeral per the design note; None when the candidate
    fails R0 in the key (chromatic to that key, stated not judged)."""
    tbl = TH.load_table()
    row = tbl["qualities"][qid]
    if not _r0(root_pc, qid, key):
        return None
    root_lof = TH.chord_root_lof(root_pc, qid, None)
    # Respell in key (with overflow fallback, matching identify):
    l = key.spell(root_pc)
    if row["spell"] == "stack" and any(
        abs(TH.lof_acc(l + d)) > 2 for d in row["_deg_deltas"]
    ):
        l = root_lof
    tonic_letter = TH.lof_letter(key.tonic_lof)
    root_letter = TH.lof_letter(l)
    degree = (_LETTERS.index(root_letter) - _LETTERS.index(tonic_letter)) % 7
    deltas = (TH._MAJOR_DELTAS if key.mode == "major" else TH._MINOR_DELTAS)
    diatonic_lof = key.tonic_lof + deltas[degree]
    acc = (l - diatonic_lof) // 7
    prefix = ("b" * -acc) if acc < 0 else ("#" * acc)
    numeral = _ROMAN[degree]
    tones = set(row["tones"])
    if 3 in tones and 4 not in tones:
        numeral = numeral.lower()
    suffix = row["name"]
    if 3 in tones and suffix in _MINOR_THIRD_STRIP:
        suffix = _MINOR_THIRD_STRIP[suffix]
    out = f"{prefix}{numeral}{suffix}"
    if bass_pc is not None and bass_pc != root_pc:
        members = TH.member_spellings(root_pc, qid, None)
        # Bass in the key's spelling where it is a member; the member
        # spelling relative to the key-respelled root:
        key_members = {
            TH.lof_pc(l + d): l + d for d in row["_deg_deltas"]
        }
        bass_lof = key_members.get(bass_pc, members.get(bass_pc))
        if bass_lof is not None:
            out += "/" + TH.lof_str(bass_lof)
    return out


def _r0(root_pc: int, qid: str, key: TH.Key) -> bool:
    tbl = TH.load_table()
    row = tbl["qualities"][qid]
    if root_pc not in key.scale_pcs:
        return False
    abs_tones = frozenset((root_pc + t) % 12 for t in row["tones"])
    if abs_tones <= key.scale_pcs:
        return True
    return (
        key.mode == "minor"
        and root_pc == (key.tonic_pc + 7) % 12
        and qid in ("maj", "7")
    )


# ---------------------------------------------------------------------------
# Candidate keys + segmentation (PHASE3 §2.5, §2.6)
# ---------------------------------------------------------------------------

ALL_KEYS = [
    f"{t}-{mode}"
    for mode in ("major", "minor")
    for t in ("c", "db", "d", "eb", "e", "f", "f#", "g", "ab", "a",
              "bb", "b")
]


def _key_rank(name: str, score: int) -> tuple:
    k = TH.Key.parse(name)
    return (-score, abs(k.signature), 0 if k.mode == "major" else 1,
            k.tonic_pc)


def passing_keys(steps: list[dict], names: list[str]) -> dict[str, set]:
    """key name -> set of step indices whose display candidate passes
    R0. Steps without a harmonic identity pass everywhere (transparent —
    PHASE3 §2.6)."""
    out = {}
    for name in names:
        key = TH.Key.parse(name)
        passed = set()
        for i, s in enumerate(steps):
            if s["quality"] is None:
                passed.add(i)
            elif _r0(s["root_pc"], s["quality"], key):
                passed.add(i)
        out[name] = passed
    return out


def rank_keys(steps: list[dict], names: list[str], top: int = 3,
              durations: list | None = None) -> list:
    """Duration-weighted when durations (beats per step) are given —
    data, not a tuned weight (RHYTHM R3): a chord held four bars argues
    harder than a passing eighth."""
    per_key = passing_keys(steps, names)
    if durations:
        beats = {
            n: sum(durations[i] for i in per_key[n]) for n in per_key
        }
        scored = sorted(
            per_key,
            key=lambda n: (-beats[n],) + _key_rank(n, len(per_key[n])),
        )
        return [
            {"key": n, "passes": len(per_key[n]), "of": len(steps),
             "beats": beats[n], "of_beats": sum(durations)}
            for n in scored[:top]
        ]
    scored = sorted(per_key, key=lambda n: _key_rank(n, len(per_key[n])))
    return [
        {"key": n, "passes": len(per_key[n]), "of": len(steps)}
        for n in scored[:top]
    ]


def segment(steps: list[dict], names: list[str]) -> list[dict]:
    per_key = passing_keys(steps, names)
    segments = []
    i = 0
    n = len(steps)
    while i < n:
        live = {k for k, passed in per_key.items() if i in passed}
        j = i
        while j + 1 < n:
            nxt = {k for k in live if j + 1 in per_key[k]}
            if not nxt:
                break
            live = nxt
            j += 1
        ranked = sorted(live, key=lambda k: _key_rank(k, 0))
        segments.append({
            "steps": list(range(i, j + 1)),
            "keys": ranked[:3],
        })
        i = j + 1
    return segments


# ---------------------------------------------------------------------------
# analyze (PHASE3 §2)
# ---------------------------------------------------------------------------

def analyze(steps: list[dict], keys: list[str] | None = None,
            timeline: list | None = None) -> dict:
    """steps[i]: {grip, name, named, midi, root_pc, quality, bass_pc,
    pitches (spelled, low->high)} — built by the service from the
    library + derived caches (display candidate = chosen else top)."""
    key_names = keys if keys else ALL_KEYS
    for name in key_names:
        TH.Key.parse(name)  # instructive validation up front

    bass_line = [
        {"step": i, "pitch": s["pitches"][0] if s["pitches"] else None,
         "midi": s["midi"][0]}
        for i, s in enumerate(steps)
    ]
    bass_motion = [
        bass_line[i + 1]["midi"] - bass_line[i]["midi"]
        for i in range(len(steps) - 1)
    ]

    pairs = []
    for i in range(len(steps) - 1):
        a, b = steps[i], steps[i + 1]
        vm = voice_matching(a["midi"], b["midi"])
        spell_a = dict(zip(sorted(a["midi"]), a["pitches"]))
        spell_b = dict(zip(sorted(b["midi"]), b["pitches"]))
        common_pcs = sorted(
            {m % 12 for m in a["midi"]} & {m % 12 for m in b["midi"]}
        )
        pc_spell_a = {m % 12: p for m, p in spell_a.items()}
        pairs.append({
            "from_step": i, "to_step": i + 1,
            "common_tones": [
                "".join(ch for ch in pc_spell_a[pc] if not ch.isdigit())
                for pc in common_pcs
            ],
            "voice_leading": {
                "total": vm["total"],
                "motions": [
                    {"from": spell_a[x], "to": spell_b[y],
                     "semitones": y - x}
                    for x, y in vm["pairs"]
                ],
                "left": [spell_a[x] for x in vm["left"]],
                "entered": [spell_b[y] for y in vm["entered"]],
            },
        })

    durations = (
        [t["duration_beats"] for t in timeline] if timeline else None
    )
    ranked = rank_keys(steps, key_names, durations=durations)
    numerals = {}
    for entry in ranked:
        key = TH.Key.parse(entry["key"])
        numerals[entry["key"]] = [
            None if s["quality"] is None
            else roman_numeral(s["root_pc"], s["quality"], s["bass_pc"],
                               key)
            for s in steps
        ]

    segments = segment(steps, key_names)
    modulations = [
        {
            "at_step": segments[i + 1]["steps"][0],
            "from_keys": segments[i]["keys"],
            "to_keys": segments[i + 1]["keys"],
        }
        for i in range(len(segments) - 1)
    ]

    out_steps = [
        {k: s[k] for k in ("grip", "name", "named", "midi")}
        for s in steps
    ]
    if timeline:
        for s, t in zip(out_steps, timeline):
            beats_per_bar = t["meter"][0]
            s.update({
                "rhythm": t["rhythm"],
                "onset_beats": t["onset_beats"],
                "duration_beats": t["duration_beats"],
                "bar": int(t["onset_beats"] // beats_per_bar) + 1,
                "beat": (t["onset_beats"] % beats_per_bar) + 1,
            })
    return {
        "steps": out_steps,
        "bass_line": bass_line,
        "bass_motion": bass_motion,
        "pairs": pairs,
        "keys": ranked,
        "numerals": numerals,
        "segments": segments,
        "modulations": modulations,
    }
