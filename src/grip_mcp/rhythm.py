"""Rhythm engine (docs/RHYTHM_DESIGN.md, ratified rev 3).

Time is integer ticks at 960 per meter beat; the single rounding rule
everywhere is round half up (§2). Indices are physical, the bass is
symbolic, traversal is physical (§3). Swing is a piecewise-linear
bijection of the time axis applied to intervals — both endpoints warp
(§4). Built-ins are meter-parametric spec functions, the documented
exception to stored-expanded (§5). Deterministic, documented,
mechanical — never tuned weights.
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction

TICKS_PER_BEAT = 960
SMF_PPQ = 3840          # fixed emission constant (§6); storage grid unchanged
DENOMS = (2, 4, 8, 16)
BUILTINS = ("whole", "quarters", "bass-strum", "arp-up")

# Accent placement function (§4): the function is the spec; the values
# are reviewable data.
ACCENT_BAR_START = 108
ACCENT_GROUP_START = 100
ACCENT_ON_BEAT = 88
ACCENT_OFF_BEAT = 76

MAX_REPEAT = 128
TEMPO_MIN, TEMPO_MAX = 20, 300


class RhythmError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# §2: the tick grid
# ---------------------------------------------------------------------------

def round_half_up(x: Fraction) -> int:
    """The one rounding rule of the whole design (§2)."""
    return int((Fraction(x) + Fraction(1, 2)).__floor__())


def parse_beats(x, what: str = "value") -> Fraction:
    """Beats as a number or a fraction string ("1/3", "3.5", and the
    canonical mixed form "2+1/3" — NOTATION_DESIGN §1)."""
    try:
        if isinstance(x, bool):
            raise ValueError
        if isinstance(x, (int, float)):
            return Fraction(x)
        if isinstance(x, str):
            return sum((Fraction(p) for p in x.split("+")), Fraction(0))
    except (ValueError, ZeroDivisionError, TypeError):
        pass
    raise RhythmError(
        "bad_beats",
        f"{what} {x!r} is not a beat count (number or fraction string "
        "like '1/3' or '2+1/3')",
    )


def snap_ticks(x, what: str = "value") -> int:
    """Beats -> integer ticks; nearest tick, round half up (§2)."""
    t = round_half_up(parse_beats(x, what) * TICKS_PER_BEAT)
    if t < 0:
        raise RhythmError("bad_beats", f"{what} {x!r} is negative")
    return t


# ---------------------------------------------------------------------------
# §4: meter, grouping, accents
# ---------------------------------------------------------------------------

def validate_meter(meter) -> list[int]:
    if (not isinstance(meter, (list, tuple)) or len(meter) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool)
                       for v in meter)):
        raise RhythmError("bad_meter", "meter must be [num, denom]")
    num, denom = meter
    if denom not in DENOMS:
        raise RhythmError(
            "bad_meter", f"meter denom {denom} not in {list(DENOMS)}"
        )
    if not 1 <= num <= 32:
        raise RhythmError("bad_meter", f"meter num {num} out of range 1-32")
    return [num, denom]


def validate_tempo(tempo) -> int:
    if (not isinstance(tempo, int) or isinstance(tempo, bool)
            or not TEMPO_MIN <= tempo <= TEMPO_MAX):
        raise RhythmError(
            "bad_tempo",
            f"tempo {tempo!r} must be an integer BPM of the meter beat, "
            f"{TEMPO_MIN}-{TEMPO_MAX}",
        )
    return tempo


def default_grouping(num: int) -> list[int]:
    """§4: num=1 -> [1]; compound -> 3s; else 2s with a trailing 3 when
    odd. 8/8 (2+2+2+2, often felt 3+3+2) and 6/4 (3+3 vs 2+2+2) are the
    documented, overridable misses."""
    if num == 1:
        return [1]
    if num > 3 and num % 3 == 0:
        return [3] * (num // 3)
    if num % 2 == 1:
        return [2] * ((num - 3) // 2) + [3]
    return [2] * (num // 2)


def validate_grouping(grouping, num: int) -> list[int]:
    if (not isinstance(grouping, list) or not grouping
            or not all(isinstance(g, int) and not isinstance(g, bool)
                       and g >= 1 for g in grouping)
            or sum(grouping) != num):
        raise RhythmError(
            "bad_grouping",
            f"grouping {grouping!r} must be positive integers summing to "
            f"the meter's num ({num})",
        )
    return list(grouping)


def group_start_beats(grouping: list[int]) -> set[int]:
    starts, acc = set(), 0
    for g in grouping:
        starts.add(acc)
        acc += g
    return starts


def accent_velocity(at: int, meter: list[int], grouping: list[int]) -> int:
    """Bar start 108; first beat of each subsequent group 100; other
    on-beats 88; off-beat onsets 76 (§4)."""
    bar = meter[0] * TICKS_PER_BEAT
    pos = at % bar
    if pos % TICKS_PER_BEAT:
        return ACCENT_OFF_BEAT
    beat = pos // TICKS_PER_BEAT
    if beat == 0:
        return ACCENT_BAR_START
    if beat in group_start_beats(grouping):
        return ACCENT_GROUP_START
    return ACCENT_ON_BEAT


# ---------------------------------------------------------------------------
# §4: swing — proportional pair warp of BOTH endpoints
# ---------------------------------------------------------------------------

def validate_swing(swing) -> dict:
    """{"subdivision": ticks, "ratio": {"num": a, "den": b}} — mandatory
    subdivision; ratio exact rational in the open interval (0, 1)."""
    if not isinstance(swing, dict):
        raise RhythmError("bad_swing", "swing must be an object")
    sub = swing.get("subdivision")
    if not isinstance(sub, int) or isinstance(sub, bool) or sub < 1:
        raise RhythmError(
            "bad_swing",
            "swing.subdivision (ticks) is mandatory — there is no "
            "meter-blind default (a default would mean swung sixteenths "
            "in 6/8)",
        )
    ratio = swing.get("ratio")
    if (not isinstance(ratio, dict)
            or not isinstance(ratio.get("num"), int)
            or not isinstance(ratio.get("den"), int)
            or isinstance(ratio.get("num"), bool)
            or isinstance(ratio.get("den"), bool)
            or not 0 < ratio["num"] < ratio["den"]):
        raise RhythmError(
            "bad_swing",
            "swing.ratio must be {num, den} with 0 < num/den < 1 "
            "(1/2 = straight)",
        )
    return {"subdivision": sub,
            "ratio": {"num": ratio["num"], "den": ratio["den"]}}


def warp_tick(t: int, swing: dict | None) -> int:
    """Piecewise-linear bijection of the time axis (§4). Pairs tile
    from tick 0 of the pattern instance; the off-point of each pair
    maps to 2*sub*ratio. Applied to both endpoints of every event."""
    if swing is None:
        return t
    s = swing["subdivision"]
    r = Fraction(swing["ratio"]["num"], swing["ratio"]["den"])
    pair = 2 * s
    k, rem = divmod(t, pair)
    mid = pair * r  # warped position of the straight midpoint
    if rem <= s:
        w = Fraction(rem) * mid / s
    else:
        w = mid + Fraction(rem - s) * (pair - mid) / s
    return k * pair + round_half_up(w)


# ---------------------------------------------------------------------------
# §3: note forms (indices physical, bass symbolic, traversal physical)
# ---------------------------------------------------------------------------

_VERBS = {
    "strum": {"strings": "all"},
    "bass": {"string": "bass"},
    "arp": {"arp": "up"},
    "arp-up": {"arp": "up"},
    "arp-down": {"arp": "down"},
}


def validate_note(note) -> dict:
    if not isinstance(note, dict):
        raise RhythmError("bad_note", f"note {note!r} must be an object")
    keys = set(note) - {"up"}
    if keys == {"string"}:
        v = note["string"]
        if v == "bass":
            return {"string": "bass"}
        if isinstance(v, int) and not isinstance(v, bool) and v >= 1:
            return {"string": v}
        raise RhythmError(
            "bad_note",
            f"string {v!r} must be a physical sounding index (1 = lowest "
            "physical sounding string) or 'bass' (symbolic: lowest "
            "PITCHED sounding string)",
        )
    if keys == {"strings"}:
        v = note["strings"]
        out: dict = {}
        if v == "all":
            out["strings"] = "all"
        elif (isinstance(v, list) and v
                and all(isinstance(i, int) and not isinstance(i, bool)
                        and i >= 1 for i in v)
                and len(set(v)) == len(v)):
            out["strings"] = list(v)
        else:
            raise RhythmError(
                "bad_note",
                f"strings {v!r} must be 'all' or a non-empty list of "
                "distinct physical sounding indices",
            )
        if "up" in note:
            if note["up"] is not True:
                raise RhythmError("bad_note", "up, when present, is true")
            out["up"] = True
        return out
    if keys == {"arp"}:
        if note["arp"] in ("up", "down"):
            return {"arp": note["arp"]}
        raise RhythmError("bad_note", "arp must be 'up' or 'down'")
    if keys == {"pitch"}:
        raise RhythmError(
            "melody_not_yet",
            "pitch events belong to melody parts — a fast-follow in its "
            "own reviewed increment (RHYTHM_DESIGN §7); patterns address "
            "strings",
        )
    raise RhythmError(
        "bad_note",
        f"note {note!r} is not one of {{string}}, {{strings[, up]}}, "
        "{arp}",
    )


def validate_velocity(v) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 127:
        raise RhythmError(
            "bad_velocity",
            f"velocity {v!r} must be 1-127 (0 is MIDI note-off; "
            "forbidden in storage)",
        )
    return v


# ---------------------------------------------------------------------------
# §5: patterns — authoring macros expand at definition; stored expanded
# ---------------------------------------------------------------------------

def expand_events(raw_events, length_ticks: int, meter: list[int],
                  grouping: list[int]) -> list[dict]:
    """Authoring events -> stored events: verbs to note forms, missing
    velocities from the accent function, missing durations by let-ring
    (dur runs to the next onset; the last to pattern end)."""
    if not isinstance(raw_events, list):
        raise RhythmError("bad_events", "events must be a list")
    norm = []
    for i, raw in enumerate(raw_events):
        if not isinstance(raw, dict) or "at" not in raw:
            raise RhythmError("bad_events",
                              f"event {i} must be an object with 'at'")
        at = snap_ticks(raw["at"], f"event {i} at")
        if at >= length_ticks:
            raise RhythmError(
                "bad_events",
                f"event {i} onset {at} is not inside the pattern "
                f"(length {length_ticks} ticks)",
            )
        if ("note" in raw) == ("verb" in raw):
            raise RhythmError(
                "bad_events",
                f"event {i}: exactly one of note or verb "
                f"(verbs: {sorted(_VERBS)})",
            )
        if "verb" in raw:
            if raw["verb"] not in _VERBS:
                raise RhythmError(
                    "bad_events",
                    f"event {i} verb {raw['verb']!r}; "
                    f"known: {sorted(_VERBS)}",
                )
            note = dict(_VERBS[raw["verb"]])
        else:
            note = validate_note(raw["note"])
        dur = (snap_ticks(raw["dur"], f"event {i} dur")
               if raw.get("dur") is not None else None)
        if dur == 0:
            raise RhythmError("bad_events", f"event {i} dur is 0 ticks")
        vel = (validate_velocity(raw["velocity"])
               if raw.get("velocity") is not None else None)
        norm.append({"at": at, "dur": dur, "velocity": vel, "note": note})
    norm.sort(key=lambda e: e["at"])  # stable: same-onset order preserved
    out = []
    for i, ev in enumerate(norm):
        dur = ev["dur"]
        if dur is None:  # let ring (§5)
            nxt = next((n["at"] for n in norm[i + 1:]
                        if n["at"] > ev["at"]), length_ticks)
            dur = max(1, nxt - ev["at"])
        vel = ev["velocity"]
        if vel is None:
            vel = accent_velocity(ev["at"], meter, grouping)
        out.append({"at": ev["at"], "dur": dur, "velocity": vel,
                    "note": ev["note"]})
    return out


def builtin_pattern(name: str, meter: list[int],
                    grouping: list[int]) -> dict:
    """§5: meter-parametric spec functions — immutable, never stored
    (the one exception to stored-expanded, exactly as 'standard' is a
    built-in tuning)."""
    num = meter[0]
    bar = num * TICKS_PER_BEAT
    starts = group_start_beats(grouping)
    if name == "whole":
        events = [{"at": 0, "dur": bar, "velocity": ACCENT_BAR_START,
                   "note": {"strings": "all"}}]
    elif name == "quarters":
        events = [
            {"at": b * TICKS_PER_BEAT, "dur": TICKS_PER_BEAT,
             "velocity": accent_velocity(b * TICKS_PER_BEAT, meter,
                                         grouping),
             "note": {"strings": "all"}}
            for b in range(num)
        ]
    elif name == "bass-strum":
        events = [
            {"at": b * TICKS_PER_BEAT, "dur": TICKS_PER_BEAT,
             "velocity": accent_velocity(b * TICKS_PER_BEAT, meter,
                                         grouping),
             "note": ({"string": "bass"} if b in starts
                      else {"strings": "all"})}
            for b in range(num)
        ]
    elif name == "arp-up":
        events = [{"at": 0, "dur": bar, "velocity": ACCENT_BAR_START,
                   "note": {"arp": "up"}}]
    else:
        raise RhythmError("unknown_rhythm",
                          f"no built-in {name!r}; built-ins: "
                          f"{list(BUILTINS)}")
    return {"length_ticks": bar, "meter": list(meter), "events": events}


def validate_pattern(pat: dict) -> None:
    """Structural check for stored (possibly hand-edited) patterns."""
    if not isinstance(pat, dict):
        raise RhythmError("bad_rhythm", "pattern must be an object")
    lt = pat.get("length_ticks")
    if not isinstance(lt, int) or isinstance(lt, bool) or lt < 1:
        raise RhythmError("bad_rhythm",
                          "length_ticks must be a positive integer "
                          "(no floats anywhere in stored time)")
    meter = validate_meter(pat.get("meter"))
    grouping = (validate_grouping(pat["grouping"], meter[0])
                if pat.get("grouping") is not None
                else default_grouping(meter[0]))
    if "swing" in pat and pat["swing"] is not None:
        validate_swing(pat["swing"])
    events = pat.get("events")
    if not isinstance(events, list):
        raise RhythmError("bad_rhythm", "events must be a list")
    for i, ev in enumerate(events):
        if (not isinstance(ev, dict)
                or not isinstance(ev.get("at"), int)
                or not isinstance(ev.get("dur"), int)
                or isinstance(ev.get("at"), bool)
                or isinstance(ev.get("dur"), bool)
                or ev["at"] < 0 or ev["at"] >= lt or ev["dur"] < 1):
            raise RhythmError(
                "bad_rhythm",
                f"event {i}: at/dur must be integer ticks with "
                f"0 <= at < length_ticks and dur >= 1",
            )
        validate_velocity(ev.get("velocity"))
        validate_note(ev.get("note"))


# ---------------------------------------------------------------------------
# §8: canonical serialization (schema order, independent of any code)
# ---------------------------------------------------------------------------

_ORDER = {
    "pattern": ("length_ticks", "meter", "swing", "grouping", "events"),
    "event": ("at", "dur", "velocity", "note"),
    "note": ("string", "strings", "up", "arp", "pitch"),
    "swing": ("subdivision", "ratio"),
    "ratio": ("num", "den"),
    "sequence": ("meter", "tempo", "swing", "grouping", "rhythm", "steps"),
    "step": ("item", "rhythm", "repeat"),
    "realized": ("at", "dur", "velocity", "midi", "pitch", "string",
                 "step", "grip"),
}


def ordered(d: dict, kind: str) -> dict:
    """Rebuild d in the §8 canonical key order (unknown keys last,
    sorted). The serializer follows the spec, never the reverse."""
    order = _ORDER[kind]
    out = {}
    for k in order:
        if k in d:
            v = d[k]
            if k == "swing" and isinstance(v, dict):
                v = {"subdivision": v["subdivision"],
                     "ratio": {"num": v["ratio"]["num"],
                               "den": v["ratio"]["den"]}}
            elif k == "note" and isinstance(v, dict):
                v = ordered(v, "note")
            elif k == "events" and isinstance(v, list):
                v = [ordered(e, "event") for e in v]
            elif k == "steps" and isinstance(v, list):
                v = [s if isinstance(s, str) else ordered(s, "step")
                     for s in v]
            out[k] = v
    for k in sorted(set(d) - set(order)):
        out[k] = d[k]
    return out


def canonical_pattern(pat: dict) -> dict:
    return ordered(pat, "pattern")


def canonical_sequence(seq: dict) -> dict:
    return ordered(seq, "sequence")


def content_hash(realized_events: list[dict]) -> str:
    """The content hash is computed over the realized form (§6) —
    exactly the exported keys, in canonical order; realization-internal
    fields never enter the hash."""
    blob = json.dumps(
        [{k: e[k] for k in _ORDER["realized"]} for e in realized_events],
        separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------
# §5: the sequence walk — meter/tempo/swing inheritance over @refs
# ---------------------------------------------------------------------------

def seq_steps(seq) -> list:
    return seq["steps"] if isinstance(seq, dict) else seq


def step_item(step) -> str:
    return step["item"] if isinstance(step, dict) else step


def assigned_rhythms(seq) -> list[str]:
    """Rhythm names a sequence assigns (default + per-step)."""
    if not isinstance(seq, dict):
        return []
    names = []
    if seq.get("rhythm") is not None:
        names.append(seq["rhythm"])
    for s in seq["steps"]:
        if isinstance(s, dict) and s.get("rhythm") is not None:
            names.append(s["rhythm"])
    return names


def walk_sequence(lib: dict, name: str, ctx: dict | None = None,
                  _stack: tuple = ()) -> list[dict]:
    """Flatten to per-step rhythm contexts. A child carrying its own
    meter must carry its own tempo — tempo never crosses a meter change
    (§5). swing: key present with null = forced straight; key absent =
    inherit (the explicit-null vocabulary)."""
    if name in _stack:
        raise RhythmError(
            "sequence_cycle",
            f"sequence {name!r} contains itself: "
            f"{' -> '.join(_stack + (name,))}",
        )
    if name not in lib["sequences"]:
        raise RhythmError(
            "unknown_sequence",
            f"sequence {name!r} not found; known: "
            f"{sorted(lib['sequences'])}",
        )
    seq = lib["sequences"][name]
    new_ctx = dict(ctx or {})
    if isinstance(seq, dict):
        if ctx is not None and "meter" in seq and "tempo" not in seq:
            raise RhythmError(
                "child_meter_requires_tempo",
                f"sequence {name!r} carries its own meter but no tempo; "
                "tempo never crosses a meter change (RHYTHM_DESIGN §5)",
            )
        for k in ("meter", "tempo", "grouping", "rhythm", "swing"):
            if k in seq:
                new_ctx[k] = seq[k]
    out = []
    for step in seq_steps(seq):
        item = step_item(step)
        if item.startswith("@"):
            out.extend(walk_sequence(lib, item[1:], new_ctx,
                                     _stack + (name,)))
            continue
        rname = None
        if isinstance(step, dict) and step.get("rhythm") is not None:
            rname = step["rhythm"]
        elif new_ctx.get("rhythm") is not None:
            rname = new_ctx["rhythm"]
        repeat = 1
        if isinstance(step, dict) and step.get("repeat") is not None:
            repeat = step["repeat"]
            if (not isinstance(repeat, int) or isinstance(repeat, bool)
                    or not 1 <= repeat <= MAX_REPEAT):
                raise RhythmError(
                    "bad_repeat",
                    f"repeat {repeat!r} must be 1-{MAX_REPEAT}",
                )
        out.append({
            "grip": item,
            "rhythm": rname,
            "repeat": repeat,
            "meter": new_ctx.get("meter"),
            "tempo": new_ctx.get("tempo"),
            "swing": new_ctx.get("swing"),
            "grouping": new_ctx.get("grouping"),
        })
    return out


# ---------------------------------------------------------------------------
# §3 + §6: realization against grips
# ---------------------------------------------------------------------------

def _resolve_note(note: dict, sounding: list[dict], dropped: list) -> list:
    """-> traversal-ordered [(sounding 1-based index, midi, pitch)].
    Indices physical; 'bass' = lowest-PITCHED sounding string; default
    traversal 1->n (a down-strum), 'up'/'arp down' reverse (§3).
    Overflow drops per index into `dropped`."""
    n = len(sounding)

    def pick(i):
        return (i, sounding[i - 1]["midi"], sounding[i - 1]["pitch"])

    if "string" in note:
        if note["string"] == "bass":
            if not n:
                return []
            i = min(range(1, n + 1), key=lambda i: sounding[i - 1]["midi"])
            return [pick(i)]
        if note["string"] > n:
            dropped.append(note["string"])
            return []
        return [pick(note["string"])]
    if "strings" in note:
        idxs = (list(range(1, n + 1)) if note["strings"] == "all"
                else list(note["strings"]))
        kept = []
        for i in idxs:
            if i > n:
                dropped.append(i)
            else:
                kept.append(i)
        if note.get("up"):
            kept.reverse()
        return [pick(i) for i in kept]
    # arp: all sounding strings, physical order; "down" reverses
    idxs = list(range(1, n + 1))
    if note["arp"] == "down":
        idxs.reverse()
    return [pick(i) for i in idxs]


def realize(lib: dict, name: str, grips_info: dict) -> dict:
    """Full realization: sections, steps with spans, events on the
    straight grid (events_stored) and swing-applied (events). Warp is
    anchored at tick 0 of each pattern instance; a pattern's own swing
    overrides the governing value and never composes (§4).

    grips_info: gid -> {"sounding": [{"string", "midi", "pitch"}],
    "name": display}. Raises RhythmError for dangling rhythms, meter
    mismatches, or a missing meter (touching tools error instructively).
    """
    steps_ctx = walk_sequence(lib, name)
    if not steps_ctx:
        raise RhythmError("empty_sequence",
                          f"sequence {name!r} has no steps")
    rhythms = lib.get("rhythms") or {}
    sections: list[dict] = []
    steps_out: list[dict] = []
    stored_events: list[dict] = []
    real_events: list[dict] = []
    warnings: list[dict] = []
    seen_drops: set = set()
    cursor = 0
    for idx, sc in enumerate(steps_ctx):
        if sc["meter"] is None:
            raise RhythmError(
                "no_meter",
                f"sequence {name!r} has rhythm to realize but step {idx} "
                f"({sc['grip']!r}) has no governing meter; set meter "
                "(and tempo) on the sequence (RHYTHM_DESIGN §5)",
            )
        meter = validate_meter(sc["meter"])
        grouping = (validate_grouping(sc["grouping"], meter[0])
                    if sc["grouping"] is not None
                    else default_grouping(meter[0]))
        rname = sc["rhythm"] or "whole"
        if rname in BUILTINS:
            pat = builtin_pattern(rname, meter, grouping)
        else:
            pat = rhythms.get(rname)
            if pat is None:
                raise RhythmError(
                    "dangling_rhythm",
                    f"step {idx} assigns rhythm {rname!r} which is not "
                    f"defined; known: {sorted(rhythms)} + built-ins "
                    f"{list(BUILTINS)}",
                )
            validate_pattern(pat)
            if pat["meter"] != meter:
                raise RhythmError(
                    "meter_mismatch",
                    f"rhythm {rname!r} is in meter {pat['meter']} but "
                    f"step {idx} is governed by {meter}; no silent "
                    "reinterpretation (RHYTHM_DESIGN §5)",
                )
        # Layering: a pattern's own swing overrides the governing value
        # and never composes; null (present) forces straight.
        swing = pat["swing"] if "swing" in pat else sc["swing"]
        if swing is not None:
            swing = validate_swing(swing)
        if (not sections
                or sections[-1]["meter"] != meter
                or sections[-1]["tempo"] != sc["tempo"]
                or sections[-1]["swing"] != sc["swing"]
                or sections[-1]["grouping"] != grouping):
            sections.append({"at": cursor, "meter": meter,
                             "tempo": sc["tempo"],
                             "swing": sc["swing"],
                             "grouping": grouping})
        ginfo = grips_info[sc["grip"]]
        sounding = ginfo["sounding"]
        span = pat["length_ticks"] * sc["repeat"]
        steps_out.append({"index": idx, "grip": sc["grip"],
                          "name": ginfo.get("name"), "at": cursor,
                          "span": span, "rhythm": rname,
                          "repeat": sc["repeat"]})
        for k in range(sc["repeat"]):
            inst = cursor + k * pat["length_ticks"]
            for ev in pat["events"]:
                dropped: list = []
                notes = _resolve_note(ev["note"], sounding, dropped)
                for i in dropped:
                    key = (sc["grip"], rname, i)
                    if key not in seen_drops:
                        seen_drops.add(key)
                        warnings.append({
                            "code": "pattern_string_missing",
                            "detail": {"step": idx, "grip": sc["grip"],
                                       "rhythm": rname, "string": i,
                                       "sounding": len(sounding)},
                        })
                if not notes:
                    continue
                is_arp = "arp" in ev["note"]
                is_chord = "strings" in ev["note"]
                for j, (sidx, midi, pitch) in enumerate(notes):
                    if is_arp:
                        off = round_half_up(
                            Fraction(ev["dur"] * j, len(notes)))
                        s_at = ev["at"] + off
                    else:
                        s_at = ev["at"]
                    s_end = ev["at"] + ev["dur"]  # rings to span end
                    w_at = warp_tick(s_at, swing)
                    w_end = warp_tick(s_end, swing)
                    base = {"velocity": ev["velocity"], "midi": midi,
                            "pitch": pitch, "string": sidx,
                            "step": idx, "grip": sc["grip"]}
                    stored_events.append({
                        "at": inst + s_at,
                        "dur": max(1, s_end - s_at), **base})
                    real_events.append({
                        "at": inst + w_at,
                        "dur": max(1, w_end - w_at), **base,
                        "order": j if is_chord else 0})
        cursor += span
    key = lambda e: (e["at"], e["step"], e["string"])  # noqa: E731
    stored_events.sort(key=key)
    real_events.sort(key=key)
    # Bar:beat positions (1-based readouts; ticks 0-based internally).
    # A section (meter change) starts a fresh bar; bars count on.
    bar_base = 0
    for i, sec in enumerate(sections):
        end = sections[i + 1]["at"] if i + 1 < len(sections) else cursor
        bar_len = sec["meter"][0] * TICKS_PER_BEAT
        sec["bar_base"] = bar_base
        span = end - sec["at"]
        bar_base += -(-span // bar_len)  # ceil
    for st in steps_out:
        sec = next(s for s in reversed(sections) if s["at"] <= st["at"])
        bar_len = sec["meter"][0] * TICKS_PER_BEAT
        rel = st["at"] - sec["at"]
        st["bar"] = sec["bar_base"] + rel // bar_len + 1
        st["beat"] = (rel % bar_len) // TICKS_PER_BEAT + 1
        st["tick_in_beat"] = rel % TICKS_PER_BEAT
        st["placement"] = (
            "bar_start" if rel % bar_len == 0
            else "on_beat" if st["tick_in_beat"] == 0
            else "off_beat"
        )
    return {
        "sections": sections,
        "steps": steps_out,
        "events_stored": stored_events,
        "events": real_events,
        "total_ticks": cursor,
        "warnings": warnings,
    }


def require_tempo(rz: dict, tool: str) -> None:
    missing = [s["at"] for s in rz["sections"] if s["tempo"] is None]
    if missing:
        raise RhythmError(
            "no_tempo",
            f"{tool} requires tempo (BPM of the meter beat) on the "
            "sequence; sections starting at ticks "
            f"{missing} have none (RHYTHM_DESIGN §5)",
        )
    for s in rz["sections"]:
        validate_tempo(s["tempo"])


def export_events(events: list[dict]) -> list[dict]:
    """Strip realization-internal fields (traversal order feeds only
    the audio stagger — absent from analyze and both exports)."""
    return [
        ordered({k: e[k] for k in _ORDER["realized"]}, "realized")
        for e in events
    ]
