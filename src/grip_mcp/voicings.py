"""Voicing search with a playability model (DESIGN §9, Phase 2a).

Retires the name→shape bridge: instead of the LLM proposing shapes from
its own knowledge and verifying via identify, the server enumerates them
— exact by construction, tuning-parameterized from day one (frets are
capo-relative automatically, because the search runs over the resolved
tuning's sounding pitches).

Everything here follows the design doc's house rule: deterministic,
documented rules, never tuned weights.

Playability model (per §9):
* span: fretted notes fit inside `max_span` frets (default 4, cap 5);
  open strings are free.
* fingers: at most 4. Plain count when ≤ 4; otherwise a barre is
  attempted at the lowest fretted fret — feasible iff, from the lowest
  string carrying that fret to the top string, every string is fretted
  at or above it (opens and mutes inside a barre are impossible); the
  barre costs one finger plus one per note above the barre fret.
  `allow_thumb` lets the thumb take the lowest string's fretted note
  (thumb-over), freeing a finger.
* mutes: outer mutes are free; inner mutes (between the lowest and
  highest sounding strings) are permitted but ranked down.

Coverage: the sounding PC set must equal the chord's tone set — no
foreign tones, nothing missing. With `allow_omissions`, tones in the
row's R2 discounted set (the frozen table's own data) may be absent.
A slash bass is a hard constraint on the lowest sounding PC; without
one, root-in-bass ranks first but inversions are listed.

Ranking — strict lexicographic, documented, no weights:
  W0  bass is the root first (skipped when a slash bass constrains it)
  W1  |position − near_fret| when near_fret is given
  W2  fewer inner mutes
  W3  more sounding strings
  W4  fewer fretted notes (opens are free)
  W5  lower position
  W6  smaller span
  W7  lower (bassier) lowest sounding string
  W8  the fret tuple itself (total determinism)
"""

from __future__ import annotations

from . import theory as TH

DEFAULT_CONSTRAINTS = {
    "max_span": 4,          # ≤ 5
    "max_fretted": 4,       # the FINGER budget: a barre is one finger
    "allow_thumb": False,
    "allow_omissions": False,
    "allow_inner_mutes": True,
    "max_fret": 12,         # ≤ 15
}
_LIMITS = {"max_span": 5, "max_fret": 15}


class VoicingError(ValueError):
    pass


def _check_constraints(constraints: dict | None) -> dict:
    c = dict(DEFAULT_CONSTRAINTS)
    for k, v in (constraints or {}).items():
        if k not in DEFAULT_CONSTRAINTS:
            raise VoicingError(
                f"unknown constraint {k!r}; known: "
                f"{sorted(DEFAULT_CONSTRAINTS)}"
            )
        c[k] = v
    for k, cap in _LIMITS.items():
        if c[k] > cap:
            raise VoicingError(f"{k} caps at {cap} (got {c[k]})")
    return c


def _fingering(frets: list, barre, thumb: bool, budget: int = 4):
    """Deterministic fingering suggestion under a finger budget (§9's
    '≤ 4 fretted notes + opens' is a FINGER budget: a barre is one
    finger covering its run). Returns (fingers, feasible)."""
    fingers: list[int | None] = [None] * len(frets)
    fretted = [(f, i) for i, f in enumerate(frets) if f and f > 0]
    if not fretted:
        return fingers, True
    used = 0
    remaining = list(fretted)
    if thumb:
        f, i = min(fretted, key=lambda t: t[1])  # lowest string
        fingers[i] = 0
        remaining = [t for t in remaining if t[1] != i]
    if barre is not None:
        bf, bs = barre
        for f, i in list(remaining):
            if f == bf and i >= bs:
                fingers[i] = 1
                remaining.remove((f, i))
        used = 1
    next_fingers = [d for d in (1, 2, 3, 4) if d > used][:budget - used]
    remaining.sort()  # by fret, then string
    if len(remaining) > len(next_fingers):
        return fingers, False
    for (f, i), d in zip(remaining, next_fingers):
        fingers[i] = d
    return fingers, True


def _playability(frets: list, c: dict):
    """-> dict | None (None = unplayable under the model)."""
    fretted = [(f, i) for i, f in enumerate(frets) if f and f > 0]
    n_fretted = len(fretted)
    if not fretted:
        fingers, _ = _fingering(frets, None, False)
        return {"fretted": 0, "span": 0, "position": 0, "barre": None,
                "thumb": False, "fingers": fingers}
    lo = min(f for f, _ in fretted)
    hi = max(f for f, _ in fretted)
    span = hi - lo + 1
    if span > c["max_span"]:
        return None

    def barre_at():
        """Feasible barre at the lowest fret, or None."""
        strings_at_lo = [i for f, i in fretted if f == lo]
        if len(strings_at_lo) < 2:
            return None
        bs = min(strings_at_lo)
        for i in range(bs, len(frets)):
            if frets[i] is None or frets[i] == 0 or frets[i] < lo:
                return None  # open/mute/below inside a barre: impossible
        return (lo, bs)

    # Prefer the plainest feasible model: no barre, no thumb; then thumb;
    # then barre; then barre+thumb. Deterministic order.
    attempts = [(None, False)]
    if c["allow_thumb"]:
        attempts.append((None, True))
    b = barre_at()
    if b is not None:
        attempts.append((b, False))
        if c["allow_thumb"]:
            attempts.append((b, True))
    for barre, thumb in attempts:
        fingers, ok = _fingering(frets, barre, thumb, c["max_fretted"])
        if ok:
            return {
                "fretted": n_fretted, "span": span, "position": lo,
                "barre": ({"fret": barre[0], "from_string": barre[1] + 1}
                          if barre else None),
                "thumb": thumb, "fingers": fingers,
            }
    return None


def find_voicings(tuning_pitches: list[str], chord: str,
                  key: str | None = None, near_fret: int | None = None,
                  constraints: dict | None = None) -> dict:
    c = _check_constraints(constraints)
    root_pc, qid, bass_pc = TH.parse_chord_name(chord)
    tbl = TH.load_table()
    row = tbl["qualities"][qid]
    tones = {(root_pc + t) % 12 for t in row["tones"]}
    required = tones
    if c["allow_omissions"]:
        required = tones - {
            (root_pc + t) % 12 for t in row["discount"]
        }
        required |= {root_pc}
    opens = [TH.parse_pitch(p) for p in tuning_pitches]
    n = len(opens)
    members = TH.member_spellings(root_pc, qid, key)

    found: dict[tuple, dict] = {}
    span = c["max_span"]
    for pos in range(1, max(2, c["max_fret"] - span + 2)):
        options = []
        for om in opens:
            opts: list[int | None] = [None]
            if om % 12 in tones:
                opts.append(0)
            for f in range(pos, min(pos + span, c["max_fret"] + 1)):
                if (om + f) % 12 in tones:
                    opts.append(f)
            options.append(opts)

        def walk(i: int, cur: list):
            if i == n:
                _consider(cur)
                return
            for o in options[i]:
                cur.append(o)
                walk(i + 1, cur)
                cur.pop()

        def _consider(cur: list):
            frets = tuple(cur)
            if frets in found:
                return
            sounding = [(om + f, i) for i, (om, f) in
                        enumerate(zip(opens, cur)) if f is not None]
            if len(sounding) < len(required):
                return
            pcs = {m % 12 for m, _ in sounding}
            if not (required <= pcs <= tones):
                return
            midis = sorted(m for m, _ in sounding)
            low = midis[0] % 12
            if bass_pc is not None and low != bass_pc:
                return
            if not c["allow_inner_mutes"]:
                idxs = [i for _, i in sounding]
                if any(cur[i] is None
                       for i in range(min(idxs), max(idxs) + 1)):
                    return
            play = _playability(list(frets), c)
            if play is None:
                return
            inner = sum(
                1 for i in range(
                    min(i for _, i in sounding),
                    max(i for _, i in sounding) + 1,
                )
                if cur[i] is None
            )
            found[frets] = {
                "strings": list(frets),
                "fingers": play["fingers"],
                "midi": midis,
                "pitches": [TH.pitch_str(members[m % 12], m)
                            for m in midis],
                "string_pitches": [
                    None if f is None
                    else TH.pitch_str(members[(om + f) % 12], om + f)
                    for om, f in zip(opens, cur)
                ],
                "bass": TH.lof_str(members[low]),
                "position": play["position"],
                "span": play["span"],
                "fretted": play["fretted"],
                "barre": play["barre"],
                "thumb": play["thumb"],
                "inner_mutes": inner,
                "sounding": len(sounding),
                "root_in_bass": low == root_pc,
            }

        walk(0, [])

    def rank(v: dict) -> tuple:
        return (
            0 if (bass_pc is not None or v["root_in_bass"]) else 1,   # W0
            abs(v["position"] - near_fret) if near_fret is not None
            else 0,                                                   # W1
            v["inner_mutes"],                                         # W2
            -v["sounding"],                                           # W3
            v["fretted"],                                             # W4
            v["position"],                                            # W5
            v["span"],                                                # W6
            min(i for i, f in enumerate(v["strings"])
                if f is not None),                                    # W7
            tuple(-1 if f is None else f for f in v["strings"]),      # W8
        )

    ranked = sorted(found.values(), key=rank)
    return {
        "chord": TH.chord_name(root_pc, qid, bass_pc, key),
        "quality": qid,
        "tones": [TH.lof_str(members[pc]) for pc in sorted(tones)],
        "voicings": ranked,
        "constraints": c,
    }
