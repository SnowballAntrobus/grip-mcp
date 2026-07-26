"""Audition synthesis (RHYTHM_DESIGN §6): deterministic Karplus-Strong.

Substrate (decided): 44100 Hz, 16-bit PCM, mono WAV. Each voice
synthesizes in integer arithmetic at nominal peak
(velocity/127)*(32767/8) — headroom divisor 8, a stated constant;
voices sum in int32; hard clip at +/-32767 on conversion to int16. No
normalizer — absolute amplitude survives, so the velocity test is a
defined peak-sample ratio. Per-pitch damping: the loop loss is set per
pitch so decay-to-silence time is approximately pitch-uniform (one
documented decay-seconds constant deriving a per-pitch loss), not the
naive length-dependent decay that drowns trebles under ringing basses.

Cross-platform byte-equality: all per-sample math is integer; the
per-pitch constants derive through the decimal module (pure spec-driven
arithmetic, no platform libm). Pure Python: latency of seconds per
audition is accepted and stated. The 12 ms strum stagger is a
realization-only ornament — applied here, absent from analyze and both
exports.
"""

from __future__ import annotations

import struct
from decimal import Decimal, localcontext
from fractions import Fraction

from .rhythm import TICKS_PER_BEAT, round_half_up

SAMPLE_RATE = 44100
HEADROOM = 8                 # stated constant (§6)
DECAY_60DB_SECONDS = 15      # Decimal tenths: 1.5 s to -60 dB, all pitches
STAGGER_SAMPLES = 529        # 12 ms at 44100 Hz, round half up
FADE_SAMPLES = 512           # deterministic click-free voice tail
_FP = 15                     # fixed-point bits for the loop gain


def _pitch_constants(midi: int) -> tuple[int, int]:
    """-> (delay-line length L, loop gain in Q15 fixed point).

    freq = 440 * 2^((midi-69)/12); L = round(SR/freq); the KS loop's
    two-point average passes ~once per L samples, so a per-pass gain of
    10^(-3 / (freq * T)) reaches -60 dB at T seconds for every pitch.
    Derived via decimal (deterministic, no libm), then frozen to Q15.
    """
    with localcontext() as ctx:
        ctx.prec = 40
        freq = Decimal(440) * (Decimal(2)
                               ** (Decimal(midi - 69) / Decimal(12)))
        L = round_half_up(Fraction(SAMPLE_RATE) / Fraction(freq))
        exponent = Decimal(-30) / (freq * Decimal(DECAY_60DB_SECONDS))
        gain = Decimal(10) ** exponent
        g_fp = round_half_up(Fraction(gain) * (1 << _FP))
    return max(2, L), min(g_fp, (1 << _FP) - 1)


def _lcg_noise(seed: int, n: int, amp: int) -> list[int]:
    """Deterministic excitation in [-amp, amp]."""
    x = seed & 0x7FFFFFFF
    out = []
    span = 2 * amp + 1
    for _ in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(x % span - amp)
    return out


def synthesize(sections: list[dict], events: list[dict],
               total_ticks: int) -> bytes:
    """Realized events (with the audio-only traversal `order`) -> WAV
    bytes. Tempo is validated present by the caller."""
    # Cumulative sample offset per section (exact Fractions; round at
    # use — no drift).
    secs = []
    sample_at = Fraction(0)
    for i, sec in enumerate(sections):
        end = (sections[i + 1]["at"] if i + 1 < len(sections)
               else total_ticks)
        spt = Fraction(60 * SAMPLE_RATE, sec["tempo"] * TICKS_PER_BEAT)
        secs.append({"at": sec["at"], "spt": spt, "sample_at": sample_at})
        sample_at += (end - sec["at"]) * spt

    def sample_of(t: int) -> int:
        s = next(s for s in reversed(secs) if s["at"] <= t)
        return round_half_up(s["sample_at"] + (t - s["at"]) * s["spt"])

    voices = []
    max_end = round_half_up(sample_at)
    for n_ev, e in enumerate(events):
        start = sample_of(e["at"]) + e.get("order", 0) * STAGGER_SAMPLES
        dur = max(FADE_SAMPLES + 1, sample_of(e["at"] + e["dur"])
                  - sample_of(e["at"]))
        amp = round_half_up(Fraction(e["velocity"] * 32767, 127 * HEADROOM))
        seed = (n_ev * 2654435761 + e["midi"] * 40503 + 12345) & 0x7FFFFFFF
        voices.append((start, dur, amp, seed, e["midi"]))
        max_end = max(max_end, start + dur)

    acc = [0] * max_end
    const_cache: dict[int, tuple[int, int]] = {}
    for start, dur, amp, seed, midi in voices:
        if midi not in const_cache:
            const_cache[midi] = _pitch_constants(midi)
        L, g_fp = const_cache[midi]
        buf = _lcg_noise(seed, L, amp)
        pos = 0
        fade_from = dur - FADE_SAMPLES
        for i in range(dur):
            a = buf[pos]
            v = a
            if i >= fade_from:
                v = a * (dur - i) // FADE_SAMPLES
            acc[start + i] += v
            b = buf[(pos + 1) % L]
            buf[pos] = (g_fp * (a + b)) >> (_FP + 1)
            pos = (pos + 1) % L

    frames = bytearray()
    for v in acc:
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        frames += struct.pack("<h", v)
    data = bytes(frames)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
           + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                                   SAMPLE_RATE * 2, 2, 16)
           + b"data" + struct.pack("<I", len(data)))
    return hdr + data


def duration_seconds(sections: list[dict], total_ticks: int) -> Fraction:
    total = Fraction(0)
    for i, sec in enumerate(sections):
        end = (sections[i + 1]["at"] if i + 1 < len(sections)
               else total_ticks)
        total += Fraction((end - sec["at"]) * 60,
                          sec["tempo"] * TICKS_PER_BEAT)
    return total
