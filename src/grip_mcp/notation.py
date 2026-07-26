"""Rhythm notation (docs/NOTATION_DESIGN.md, ratified rev 2).

Derived presentation and authoring sugar — never authoritative. Two
pure functions: render_notation (stored pattern -> text) and
parse_notation (text -> authoring events for the ordinary definition
pipeline). One expansion machine, not two. Engine-side by the closing
doctrine: a server string cannot be mangled, only relayed — the
echo-verify for rhythm.
"""

from __future__ import annotations

from fractions import Fraction

from .rhythm import (
    ACCENT_BAR_START, ACCENT_OFF_BEAT, RhythmError, TICKS_PER_BEAT,
    accent_velocity, default_grouping, validate_meter, validate_swing,
)

LADDER = (960, 480, 320, 240, 120)  # sextuplets (160) are a fallback

# §3: the named representability conditions, in emission order.
REASON_OFF_GRID = "# off-grid onsets"
REASON_DURATIONS = "# explicit durations"
REASON_PARTIAL_BAR = "# partial bar"
REASON_SIMULTANEOUS = "# simultaneous events"


# ---------------------------------------------------------------------------
# Canonical fractions (lowest terms, proper mixed number b+n/d)
# ---------------------------------------------------------------------------

def frac_str(f: Fraction) -> str:
    f = Fraction(f)
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(f.numerator, f.denominator)
    if whole == 0:
        return f"{f.numerator}/{f.denominator}"
    return f"{whole}+{rem}/{f.denominator}"


def parse_frac(s: str, what: str) -> Fraction:
    try:
        return sum((Fraction(part) for part in s.split("+")), Fraction(0))
    except (ValueError, ZeroDivisionError):
        raise RhythmError(
            "bad_notation",
            f"{what} {s!r} is not a fraction (forms: 2, 1/3, 2+1/3)",
        ) from None


def _frac_ticks(f: Fraction, what: str) -> int:
    t = f * TICKS_PER_BEAT
    if t.denominator != 1 or t < 0:
        raise RhythmError(
            "bad_notation",
            f"{what} {frac_str(f)} does not land on the 960-tick grid",
        )
    return int(t)


# ---------------------------------------------------------------------------
# Representability (§2, §3)
# ---------------------------------------------------------------------------

def _gcd_all(values, base: int) -> int:
    from math import gcd
    g = base
    for v in values:
        g = gcd(g, v)
    return g


def grid_step(onsets) -> int | None:
    g = _gcd_all(onsets, TICKS_PER_BEAT)
    for step in LADDER:
        if g % step == 0:
            return step
    return None


def _let_ring_durs(events, length_ticks: int) -> list[int]:
    out = []
    for i, e in enumerate(events):
        nxt = next((n["at"] for n in events[i + 1:] if n["at"] > e["at"]),
                   length_ticks)
        out.append(max(1, nxt - e["at"]))
    return out


def fallback_reasons(pattern: dict) -> list[str]:
    """Every applicable reason, in §3's listed order; empty list means
    grid-representable."""
    events = pattern["events"]
    onsets = [e["at"] for e in events]
    reasons = []
    if grid_step(onsets) is None:
        reasons.append(REASON_OFF_GRID)
    ring = _let_ring_durs(events, pattern["length_ticks"])
    if any(e["dur"] != r for e, r in zip(events, ring)):
        reasons.append(REASON_DURATIONS)
    bar = pattern["meter"][0] * TICKS_PER_BEAT
    if pattern["length_ticks"] % bar != 0:
        reasons.append(REASON_PARTIAL_BAR)
    if len(set(onsets)) != len(onsets):
        reasons.append(REASON_SIMULTANEOUS)
    return reasons


# ---------------------------------------------------------------------------
# Token rendering (§2)
# ---------------------------------------------------------------------------

def _core_token(note: dict) -> str:
    if note.get("strings") == "all":
        return "U" if note.get("up") else "D"
    if "strings" in note:
        idxs = note["strings"]
        inner = ("".join(str(i) for i in idxs) if all(i <= 9 for i in idxs)
                 else ",".join(str(i) for i in idxs))
        return f"[{inner}]" + ("^" if note.get("up") else "")
    if note.get("string") == "bass":
        return "B"
    if "string" in note:
        return str(note["string"])
    return "A" if note["arp"] == "up" else "V"


def _ink(tok: str, velocity: int, at: int, meter, grouping) -> str:
    m = accent_velocity(at, meter, grouping)
    if velocity == m:
        return tok
    if velocity == ACCENT_BAR_START:
        return ">" + tok
    if velocity == ACCENT_OFF_BEAT:
        return f"({tok})"
    return f"{tok}@{velocity}"


# ---------------------------------------------------------------------------
# Render (§1, §3)
# ---------------------------------------------------------------------------

def _header(pattern: dict, with_length: bool) -> str:
    num, denom = pattern["meter"]
    parts = [f"{num}/{denom}"]
    if "swing" in pattern:
        sw = pattern["swing"]
        if sw is None:
            parts.append("swing straight")
        else:
            r = Fraction(sw["ratio"]["num"], sw["ratio"]["den"])
            parts.append(
                f"swing {r.numerator}:{r.denominator} @ "
                f"{frac_str(Fraction(sw['subdivision'], TICKS_PER_BEAT))}"
            )
    if "grouping" in pattern:
        parts.append("grouping " + "+".join(str(g)
                                            for g in pattern["grouping"]))
    if with_length:
        parts.append("length " + frac_str(
            Fraction(pattern["length_ticks"], TICKS_PER_BEAT)))
    return " ".join(parts)


_COUNT_240 = {0: None, 240: "e", 480: "&", 720: "a"}
_COUNT_320 = {0: None, 320: "t", 640: "l"}


def _count_token(tick_in_bar: int, step: int) -> str:
    off = tick_in_bar % TICKS_PER_BEAT
    beat = tick_in_bar // TICKS_PER_BEAT + 1
    if off == 0:
        return str(beat)
    if step == 480:
        return "&"
    if step == 320:
        return _COUNT_320[off]
    if step == 240:
        return _COUNT_240[off]
    return _COUNT_240.get(off) or "."  # 120 grid: named quarters, . fills


def render_notation(pattern: dict) -> str:
    """Grid when representable, list otherwise — with every applicable
    reason as its own comment line, in order (§3)."""
    reasons = fallback_reasons(pattern)
    if reasons:
        return _render_list(pattern, reasons)
    return _render_grid(pattern)


def _render_grid(pattern: dict) -> str:
    meter = pattern["meter"]
    grouping = pattern.get("grouping") or default_grouping(meter[0])
    events = pattern["events"]
    step = grid_step([e["at"] for e in events])
    bar = meter[0] * TICKS_PER_BEAT
    slots = bar // step
    bars = pattern["length_ticks"] // bar
    by_at = {e["at"]: e for e in events}
    count_row = [_count_token(k * step, step) for k in range(slots)]
    rows = [count_row]
    for b in range(bars):
        row = []
        for k in range(slots):
            at = b * bar + k * step
            e = by_at.get(at)
            row.append("." if e is None else
                       _ink(_core_token(e["note"]), e["velocity"], at,
                            meter, grouping))
        rows.append(row)
    widths = [max(len(r[k]) for r in rows) for k in range(slots)]
    out = [_header(pattern, with_length=False)]
    out.append("# " + " ".join(t.ljust(w) for t, w in
                               zip(count_row, widths)).rstrip())
    for row in rows[1:]:
        out.append(" ".join(t.ljust(w) for t, w in
                            zip(row, widths)).rstrip())
    return "\n".join(out)


def _render_list(pattern: dict, reasons: list[str]) -> str:
    meter = pattern["meter"]
    grouping = pattern.get("grouping") or default_grouping(meter[0])
    events = pattern["events"]
    ring = _let_ring_durs(events, pattern["length_ticks"])
    out = [_header(pattern, with_length=True)]
    out.extend(reasons)
    onsets = [frac_str(Fraction(e["at"], TICKS_PER_BEAT) + 1)
              for e in events]
    w = max((len(o) for o in onsets), default=0)
    for e, o, r in zip(events, onsets, ring):
        line = (f"@ {o.ljust(w)} "
                f"{_ink(_core_token(e['note']), e['velocity'], e['at'], meter, grouping)}")
        if e["dur"] != r:
            line += " dur " + frac_str(Fraction(e["dur"], TICKS_PER_BEAT))
        out.append(line.rstrip())
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Parse (§4)
# ---------------------------------------------------------------------------

_SIMPLE = {"D": {"strings": "all"},
           "U": {"strings": "all", "up": True},
           "B": {"string": "bass"},
           "A": {"arp": "up"},
           "V": {"arp": "down"}}

_VOCAB = ("'.', D, U, B, A, V, a string index (3, 12), [135], "
          "[1,10,12], with optional ^ inside-bracket reverse, and one "
          "of '>tok', '(tok)', 'tok@v'")


def _parse_token(tok: str) -> tuple[dict, int | None]:
    """-> (note form, explicit velocity or None). Enforces the accent
    micro-grammar and the 1-127 range (@0 is MIDI note-off, forbidden
    in storage)."""
    s = tok
    vel = None
    if s.startswith("("):
        if not s.endswith(")") or len(s) < 3:
            raise RhythmError("bad_notation",
                              f"malformed ghost mark {tok!r}")
        s = s[1:-1]
        vel = ACCENT_OFF_BEAT
        if s.startswith(">") or "@" in s:
            raise RhythmError(
                "bad_notation",
                f"{tok!r} mixes accent marks — exactly one of plain, "
                ">tok, (tok), tok@v",
            )
    elif s.startswith(">"):
        s = s[1:]
        vel = ACCENT_BAR_START
        if s.startswith("("):
            raise RhythmError(
                "bad_notation",
                f"{tok!r} mixes accent marks — exactly one of plain, "
                ">tok, (tok), tok@v",
            )
    if "@" in s:
        if vel is not None:
            raise RhythmError(
                "bad_notation",
                f"{tok!r} mixes accent marks — exactly one of plain, "
                ">tok, (tok), tok@v",
            )
        s, _, v = s.rpartition("@")
        if not v.isdigit():
            raise RhythmError("bad_notation",
                              f"velocity escape in {tok!r} is not a number")
        vel = int(v)
        if not 1 <= vel <= 127:
            raise RhythmError(
                "bad_velocity",
                f"@{vel} in {tok!r}: velocity must be 1-127 (0 is MIDI "
                "note-off, forbidden in storage)",
            )
    if s in _SIMPLE:
        return dict(_SIMPLE[s]), vel
    if s.isdigit():
        n = int(s)
        if n < 1:
            raise RhythmError("bad_notation",
                              f"string index in {tok!r} must be >= 1")
        return {"string": n}, vel
    if s.startswith("["):
        up = s.endswith("^")
        if up:
            s = s[:-1]
        if not s.endswith("]") or len(s) < 3:
            raise RhythmError("bad_notation",
                              f"malformed bracket form {tok!r}")
        inner = s[1:-1]
        if "," in inner:
            parts = inner.split(",")
        else:
            parts = list(inner)
        if not all(p.isdigit() and int(p) >= 1 for p in parts):
            raise RhythmError("bad_notation",
                              f"bad indices in {tok!r}")
        idxs = [int(p) for p in parts]
        if len(set(idxs)) != len(idxs):
            raise RhythmError("bad_notation",
                              f"duplicate indices in {tok!r}")
        note = {"strings": idxs}
        if up:
            note["up"] = True
        return note, vel
    raise RhythmError(
        "bad_notation",
        f"unknown token {tok!r}; vocabulary: {_VOCAB}",
    )


def _auth_event(at_ticks: int, note: dict, vel: int | None,
                dur_ticks: int | None = None) -> dict:
    ev = {"at": frac_str(Fraction(at_ticks, TICKS_PER_BEAT)),
          "note": note}
    if vel is not None:
        ev["velocity"] = vel
    if dur_ticks is not None:
        ev["dur"] = frac_str(Fraction(dur_ticks, TICKS_PER_BEAT))
    return ev


def parse_notation(text: str) -> dict:
    """-> {meter, events (authoring), length_ticks, length_implied,
    [swing], [grouping]} — swing/grouping keys present iff the header
    specified them. Comments (# lines) legal anywhere; the first
    non-comment line is the header."""
    if not isinstance(text, str) or not text.strip():
        raise RhythmError("bad_notation", "notation is empty")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    header, body = lines[0].split(), lines[1:]
    out: dict = {}
    if "/" not in header[0]:
        raise RhythmError(
            "bad_notation",
            f"header must start with the meter (num/denom); got "
            f"{header[0]!r}",
        )
    try:
        num, denom = (int(x) for x in header[0].split("/"))
    except ValueError:
        raise RhythmError("bad_notation",
                          f"bad meter {header[0]!r}") from None
    meter = validate_meter([num, denom])
    out["meter"] = meter
    i = 1
    length_ticks = None
    while i < len(header):
        key = header[i]
        if key == "swing":
            if i + 1 < len(header) and header[i + 1] == "straight":
                out["swing"] = None
                i += 2
                continue
            if i + 3 >= len(header) or header[i + 2] != "@":
                raise RhythmError(
                    "bad_notation",
                    "swing header form: 'swing N:D @ <beats>' or "
                    "'swing straight'",
                )
            try:
                rn, rd = (int(x) for x in header[i + 1].split(":"))
            except ValueError:
                raise RhythmError(
                    "bad_notation",
                    f"bad swing ratio {header[i + 1]!r}") from None
            sub = _frac_ticks(parse_frac(header[i + 3],
                                         "swing subdivision"),
                              "swing subdivision")
            out["swing"] = validate_swing(
                {"subdivision": sub, "ratio": {"num": rn, "den": rd}})
            i += 4
        elif key == "grouping":
            try:
                out["grouping"] = [int(x)
                                   for x in header[i + 1].split("+")]
            except (ValueError, IndexError):
                raise RhythmError("bad_notation",
                                  "grouping header form: 'grouping "
                                  "a+b+c'") from None
            i += 2
        elif key == "length":
            if i + 1 >= len(header):
                raise RhythmError("bad_notation", "length needs a value")
            length_ticks = _frac_ticks(
                parse_frac(header[i + 1], "length"), "length")
            i += 2
        else:
            raise RhythmError(
                "bad_notation",
                f"unknown header token {key!r} (known: swing, grouping, "
                "length)",
            )
    is_list = bool(body) and all(ln.startswith("@") for ln in body)
    if body and not is_list and any(ln.startswith("@") for ln in body):
        raise RhythmError("bad_notation",
                          "mixed grid lines and '@' list lines")
    events = []
    if is_list:
        if length_ticks is None:
            raise RhythmError("bad_notation",
                              "list form requires 'length' in the header")
        for ln in body:
            toks = ln.split()
            if len(toks) not in (3, 5) or toks[0] != "@" or (
                    len(toks) == 5 and toks[3] != "dur"):
                raise RhythmError(
                    "bad_notation",
                    f"list line {ln!r}; form: '@ <beats> <token> "
                    "[dur <beats>]'",
                )
            at = _frac_ticks(parse_frac(toks[1], "onset") - 1, "onset")
            if at >= length_ticks:
                raise RhythmError(
                    "bad_notation",
                    f"onset {toks[1]} is past the pattern length",
                )
            note, vel = _parse_token(toks[2])
            dur = (_frac_ticks(parse_frac(toks[4], "dur"), "dur")
                   if len(toks) == 5 else None)
            events.append(_auth_event(at, note, vel, dur))
        out["length_implied"] = False
    else:
        if not body:
            raise RhythmError("bad_notation",
                              "grid form needs at least one bar line")
        rows = [ln.replace("|", " ").split() for ln in body]
        counts = {len(r) for r in rows}
        if len(counts) != 1:
            raise RhythmError(
                "bad_notation",
                f"bar lines carry different slot counts {sorted(counts)}; "
                "every line is one whole bar on the same grid",
            )
        slots = counts.pop()
        bar = meter[0] * TICKS_PER_BEAT
        step = bar // slots if slots and bar % slots == 0 else None
        if step not in LADDER:
            valid = [meter[0] * m for m in (1, 2, 3, 4, 8)]
            raise RhythmError(
                "bad_notation",
                f"{slots} slots per line don't land on a grid in "
                f"{meter[0]}/{meter[1]} (valid counts: {valid}). Write "
                "placements explicitly with '.' rests — the dotless "
                "idiom 'D D U U D U' is ambiguous until dotted (e.g. "
                "'D . D U . U D U' over 8 slots).",
            )
        implied = len(rows) * bar
        if length_ticks is not None and length_ticks != implied:
            raise RhythmError(
                "notation_conflict",
                f"header length {frac_str(Fraction(length_ticks, 960))} "
                f"disagrees with {len(rows)} bar line(s) "
                f"({frac_str(Fraction(implied, 960))} beats)",
            )
        length_ticks = implied
        for b, row in enumerate(rows):
            for k, tok in enumerate(row):
                if tok == ".":
                    continue
                note, vel = _parse_token(tok)
                events.append(_auth_event(b * bar + k * step, note, vel))
        out["length_implied"] = True
    out["length_ticks"] = length_ticks
    out["events"] = events
    return out
