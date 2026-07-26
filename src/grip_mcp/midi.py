"""SMF export (RHYTHM_DESIGN §6).

Format-1, fixed PPQ 3840 — one header `division` for the whole file, so
meter changes need no per-file decision: each section converts stored
ticks (960 per meter beat) to SMF ticks by the integer multiplication
16/denom. Tempo meta = (60e6/tempo)*(denom/4) microseconds per quarter,
rounded half up (spec, not a frozen accident). Time-signature clicks =
96/denom clocks, x3 for compound meters (the dotted-beat convention
DAWs expect). Channel 1, no program change; velocities 1-127;
overlapping same-pitch notes truncate at retrigger; no stagger in MIDI.

Caveat stated so it isn't reported as a bug: DAWs display quarter-note
BPM, which for compound meters matches neither `tempo` (denom-note BPM)
nor the felt dotted beat — inherent to MIDI.
"""

from __future__ import annotations

import struct
from fractions import Fraction

from .rhythm import SMF_PPQ, round_half_up


def _vlq(n: int) -> bytes:
    """Variable-length quantity."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _factor(denom: int) -> int:
    return 16 // denom  # 2->8, 4->4, 8->2, 16->1: integer by construction


def _is_compound(num: int) -> bool:
    return num > 3 and num % 3 == 0


def _track(chunks: list[tuple[int, int, bytes]]) -> bytes:
    """chunks: (abs_smf_tick, priority, payload) — offs before ons at
    the same tick (priority 0 before 1)."""
    chunks = sorted(chunks, key=lambda c: (c[0], c[1]))
    data = bytearray()
    t = 0
    for tick, _prio, payload in chunks:
        data += _vlq(tick - t) + payload
        t = tick
    data += _vlq(0) + b"\xff\x2f\x00"  # end of track
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def write_smf(sections: list[dict], events: list[dict],
              total_ticks: int) -> bytes:
    """sections: [{at, meter, tempo, ...}] (tempo validated by caller);
    events: realized events with at/dur/velocity/midi."""
    # Per-section SMF tick offsets (cumulative; conversion per section).
    secs = []
    smf_at = 0
    for i, sec in enumerate(sections):
        end = (sections[i + 1]["at"] if i + 1 < len(sections)
               else total_ticks)
        f = _factor(sec["meter"][1])
        secs.append({"at": sec["at"], "end": end, "f": f,
                     "smf_at": smf_at, "meter": sec["meter"],
                     "tempo": sec["tempo"]})
        smf_at += (end - sec["at"]) * f

    def conv(t: int) -> int:
        s = next(s for s in reversed(secs) if s["at"] <= t)
        return s["smf_at"] + (t - s["at"]) * s["f"]

    # Track 0: tempo + time-signature map (emit only on change).
    metas: list[tuple[int, int, bytes]] = []
    prev_sig = prev_tempo = None
    for s in secs:
        num, denom = s["meter"]
        clicks = 96 // denom * (3 if _is_compound(num) else 1)
        sig = bytes([num, denom.bit_length() - 1, clicks, 8])
        if sig != prev_sig:
            metas.append((s["smf_at"], 0, b"\xff\x58\x04" + sig))
            prev_sig = sig
        uspq = round_half_up(
            Fraction(60_000_000, s["tempo"]) * Fraction(denom, 4))
        if uspq != prev_tempo:
            metas.append((s["smf_at"], 1,
                          b"\xff\x51\x03" + struct.pack(">I", uspq)[1:]))
            prev_tempo = uspq

    # Track 1: notes, channel 1 (wire 0), no program change.
    # Collect (on, off, key, vel); truncate at retrigger per key;
    # exact-duplicate onsets merge (max velocity, longest ring).
    notes: dict = {}
    for e in events:
        k = (e["midi"], conv(e["at"]))
        off = conv(e["at"] + e["dur"])
        if k in notes:
            notes[k][0] = max(notes[k][0], e["velocity"])
            notes[k][1] = max(notes[k][1], off)
        else:
            notes[k] = [e["velocity"], off]
    per_key: dict[int, list[tuple[int, int, int]]] = {}
    for (midi, on), (vel, off) in sorted(notes.items()):
        per_key.setdefault(midi, []).append((on, off, vel))
    msgs: list[tuple[int, int, bytes]] = []
    for midi, lst in per_key.items():
        lst.sort()
        for i, (on, off, vel) in enumerate(lst):
            if i + 1 < len(lst):
                off = min(off, lst[i + 1][0])  # truncate at retrigger
            off = max(off, on + 1)
            msgs.append((on, 1, bytes([0x90, midi, vel])))
            msgs.append((off, 0, bytes([0x80, midi, 0])))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, SMF_PPQ)
    return header + _track(metas) + _track(msgs)
