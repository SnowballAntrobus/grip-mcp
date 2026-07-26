"""Phase R: rhythm vocabulary, timeline realization, Karplus-Strong
audition (docs/RHYTHM_DESIGN.md). Deterministic throughout."""

from __future__ import annotations

import math
import struct

from . import store as ST

PLAYS = ("strum", "strum-up", "bass", "arp-up", "arp-down")

BUILTIN_RHYTHMS = {
    "whole": {
        "length_beats": 4, "meter": [4, 4],
        "events": [{"at": 0, "dur": 4, "play": "strum"}],
    },
    "quarters": {
        "length_beats": 4, "meter": [4, 4],
        "events": [{"at": i, "dur": 1, "play": "strum"} for i in range(4)],
    },
    "bass-strum": {
        "length_beats": 4, "meter": [4, 4],
        "events": [
            {"at": 0, "dur": 1, "play": "bass"},
            {"at": 1, "dur": 1, "play": "strum"},
            {"at": 2, "dur": 1, "play": "bass"},
            {"at": 3, "dur": 1, "play": "strum"},
        ],
    },
    "arp-up": {
        "length_beats": 4, "meter": [4, 4],
        "events": [{"at": 0, "dur": 4, "play": "arp-up"}],
    },
}

DEFAULT_TEMPO = 100


def all_rhythms(lib: dict) -> dict:
    out = dict(BUILTIN_RHYTHMS)
    out.update(lib.get("rhythms") or {})
    for name in BUILTIN_RHYTHMS:  # immutable, like `standard`
        out[name] = BUILTIN_RHYTHMS[name]
    return out


def validate_rhythm(name: str, r: dict) -> None:
    ST.validate_slug(name, "rhythm name")
    if name in BUILTIN_RHYTHMS:
        raise ST.StoreError("immutable_rhythm",
                            f"built-in rhythm {name!r} is immutable")
    lb = r.get("length_beats")
    if not (isinstance(lb, (int, float)) and lb > 0):
        raise ST.StoreError("bad_rhythm", "length_beats must be > 0")
    meter = r.get("meter", [4, 4])
    if not (isinstance(meter, list) and len(meter) == 2
            and all(isinstance(x, int) and x > 0 for x in meter)):
        raise ST.StoreError("bad_rhythm", "meter must be [beats, unit]")
    events = r.get("events")
    if not isinstance(events, list) or not events:
        raise ST.StoreError("bad_rhythm", "events must be a non-empty list")
    for e in events:
        if not isinstance(e, dict) or not {"at", "dur", "play"} <= set(e):
            raise ST.StoreError("bad_rhythm",
                                "each event needs {at, dur, play}")
        if not (isinstance(e["at"], (int, float)) and 0 <= e["at"] < lb):
            raise ST.StoreError(
                "bad_rhythm", f"event at={e['at']} outside [0, {lb})")
        if not (isinstance(e["dur"], (int, float)) and e["dur"] > 0):
            raise ST.StoreError("bad_rhythm", "event dur must be > 0")
        p = e["play"]
        if isinstance(p, list):
            if not p or not all(isinstance(s, int) and s >= 1 for s in p):
                raise ST.StoreError(
                    "bad_rhythm", "string lists are 1-based ints")
        elif p not in PLAYS:
            raise ST.StoreError(
                "bad_rhythm",
                f"play {p!r}; known: {PLAYS} or a 1-based string list")


def seq_entry(lib: dict, name: str) -> dict:
    """Normalize a sequence to {items, tempo, rhythm, steps} (R2)."""
    raw = lib["sequences"][name]
    if isinstance(raw, list):
        return {"items": raw, "tempo": None, "rhythm": None, "steps": {}}
    return {
        "items": raw.get("items", []),
        "tempo": raw.get("tempo"),
        "rhythm": raw.get("rhythm"),
        "steps": raw.get("steps", {}),
    }


def rhythm_references(lib: dict, rhythm_name: str) -> list[str]:
    refs = []
    for sname in lib["sequences"]:
        e = seq_entry(lib, sname)
        if e["rhythm"] == rhythm_name or any(
            s.get("rhythm") == rhythm_name for s in e["steps"].values()
        ):
            refs.append(sname)
    return refs


def flatten_with_rhythm(lib: dict, name: str,
                        inherited_default: str | None = None,
                        _stack: tuple = ()) -> list[dict]:
    """Flattened steps with per-step rhythm resolution (R2 inheritance:
    a referenced sequence uses its own assignments, inheriting the
    parent default where it has none)."""
    if name in _stack:
        raise ST.StoreError(
            "sequence_cycle",
            f"sequence {name!r} contains itself: "
            f"{' -> '.join(_stack + (name,))}",
        )
    if name not in lib["sequences"]:
        raise ST.StoreError(
            "unknown_sequence",
            f"sequence {name!r} not found; known: "
            f"{sorted(lib['sequences'])}",
        )
    e = seq_entry(lib, name)
    default = e["rhythm"] or inherited_default
    out = []
    for i, item in enumerate(e["items"]):
        if item.startswith("@"):
            out.extend(flatten_with_rhythm(
                lib, item[1:], default, _stack + (name,)))
        else:
            ov = e["steps"].get(str(i), {})
            out.append({
                "grip": item,
                "rhythm": ov.get("rhythm") or default or "whole",
                "repeat": int(ov.get("repeat", 1)),
                "assigned": bool(ov.get("rhythm") or default),
            })
    return out


def realize(lib: dict, steps: list[dict], grip_data: dict) -> list[dict]:
    """steps (from flatten_with_rhythm) + grip_data[gid] = {strings,
    midis_by_string} -> timeline steps with absolute-beat events (R3)."""
    rhythms = all_rhythms(lib)
    out = []
    cursor = 0.0
    for s in steps:
        r = rhythms.get(s["rhythm"])
        if r is None:
            raise ST.StoreError(
                "unknown_rhythm",
                f"rhythm {s['rhythm']!r} not defined; known: "
                f"{sorted(rhythms)}",
            )
        gd = grip_data[s["grip"]]
        sounding = [(i, m) for i, m in enumerate(gd["midis_by_string"])
                    if m is not None]
        dur_total = r["length_beats"] * s["repeat"]
        events = []
        for rep in range(s["repeat"]):
            base = cursor + rep * r["length_beats"]
            for e in r["events"]:
                events.extend(
                    _realize_event(e, base, sounding)
                )
        out.append({
            "grip": s["grip"],
            "rhythm": s["rhythm"],
            "repeat": s["repeat"],
            "onset_beats": cursor,
            "duration_beats": dur_total,
            "meter": r["meter"],
            "events": events,
        })
        cursor += dur_total
    return out


def _realize_event(e: dict, base: float, sounding: list) -> list[dict]:
    at = base + e["at"]
    p = e["play"]
    if not sounding:
        return []
    if p == "bass":
        notes = [min(sounding, key=lambda t: t[1])[1]]
        return [{"at": at, "dur": e["dur"], "midis": notes, "stagger": 0}]
    if p in ("strum", "strum-up"):
        order = sorted(m for _, m in sounding)
        if p == "strum-up":
            order.reverse()
        return [{"at": at, "dur": e["dur"], "midis": order,
                 "stagger": 0.012}]
    if p in ("arp-up", "arp-down"):
        order = sorted(m for _, m in sounding)
        if p == "arp-down":
            order.reverse()
        slot = e["dur"] / len(order)
        return [
            {"at": at + k * slot, "dur": slot, "midis": [m], "stagger": 0}
            for k, m in enumerate(order)
        ]
    # explicit 1-based string list; muted strings skip (portability)
    by_string = dict(sounding)
    notes = [by_string[s - 1] for s in p if (s - 1) in by_string]
    if not notes:
        return []
    return [{"at": at, "dur": e["dur"], "midis": notes, "stagger": 0.012}]


# ---------------------------------------------------------------------------
# Audition: deterministic Karplus-Strong (R4)
# ---------------------------------------------------------------------------

SR = 22050


def _ks_note(freq: float, seconds: float, seed: int) -> list[float]:
    n = max(2, int(SR / freq))
    # Seeded LCG excitation: deterministic, dependency-free.
    state = (seed * 2654435761 + 1) % (2 ** 32)
    buf = []
    for _ in range(n):
        state = (state * 1664525 + 1013904223) % (2 ** 32)
        buf.append((state / 2 ** 31) - 1.0)
    out = []
    total = int(seconds * SR)
    i = 0
    for _ in range(total):
        cur = buf[i]
        nxt = buf[(i + 1) % n]
        avg = 0.498 * (cur + nxt)
        buf[i] = avg
        out.append(cur)
        i = (i + 1) % n
    return out


def synthesize(timeline: list[dict], tempo: int) -> bytes:
    """Timeline -> 16-bit mono WAV bytes. Same input, same bytes."""
    spb = 60.0 / tempo
    events = []
    for step in timeline:
        for ev in step["events"]:
            events.append(ev)
    if not events:
        raise ST.StoreError("empty_timeline", "nothing to synthesize")
    end_beats = max(
        e["at"] + e["dur"] + len(e["midis"]) * e.get("stagger", 0)
        for e in events
    )
    total = int((end_beats * spb + 1.0) * SR)
    mix = [0.0] * total
    for idx, e in enumerate(sorted(events,
                                   key=lambda x: (x["at"], x["midis"]))):
        for k, midi in enumerate(e["midis"]):
            onset = e["at"] * spb + k * e.get("stagger", 0)
            freq = 440.0 * (2 ** ((midi - 69) / 12))
            ring = min(e["dur"] * spb + 0.35, 2.5)
            note = _ks_note(freq, ring, seed=midi * 1000 + idx)
            start = int(onset * SR)
            for j, v in enumerate(note):
                if start + j < total:
                    mix[start + j] += v * 0.28
    peak = max(1.0, max(abs(v) for v in mix))
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, v / peak)) * 32000))
        for v in mix
    )
    import io
    import wave
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    return out.getvalue()
