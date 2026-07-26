# Rhythm v2 — Design Draft (FOR REVIEW — not implemented)

Status: **draft awaiting review** · 2026-07-26 · supersedes
RHYTHM_DESIGN.md (Phase R), which remains running until this is
ratified. Process note, adopted as a rule going forward: any surface
not specified in DESIGN.md gets a reviewed design doc **before**
implementation — Phase R skipped that gate and missed accordingly.

## 1. What Phase R got wrong (the review it never had)

Phase R optimized for grip-agnostic *reuse* (five play-verbs: strum,
bass, arp…) and bought it by making the event model **too poor to say
anything detailed**: no velocity (no strong beats, no accents, no ghost
notes), no swing, no way to place an articulation on the "and" of 3
with its own weight, and meter/tempo semantics that were hand-waved
(beats untethered from the time signature's denominator). Hooktheory's
representation is the counter-example: everything sits on a real beat
grid — measures, fractional beat onsets, durations, per-note detail —
and that grid is what makes both *expressing* and *analyzing* rhythm
possible. The user's framing is adopted wholesale: **we might as well
speak MIDI's language directly** — onset, duration, pitch-or-string,
velocity — because it can express anything (accents, swing, ghosts)
and it is already the interchange form everyone downstream reads.

## 2. The representation: MIDI-semantics events on a beat grid

One universal event form, used everywhere (patterns, performances,
melody):

```jsonc
{"at": 2.5,          // onset in beats from the container's start; float
                     //   (2.5 = the "and" of beat 3 in 4/4)
 "dur": 0.5,         // duration in beats; float
 "velocity": 96,     // 0-127, MIDI convention exactly; default 96
 "note": ...}        // WHAT sounds — one of:
                     //   {"string": 3}            grip-relative (portable)
                     //   {"strings": [1,2,3]}     chord hit (12ms stagger,
                     //                              "up": true reverses)
                     //   {"strings": "all"}       every sounding string
                     //   {"pitch": "D4"}          absolute (melody; not
                     //                              grip-relative at all)
```

* **Beats are meter beats**: the arrangement's `meter: [num, denom]`
  defines them (in 6/8, a beat is an eighth; bar = `num` beats). BPM is
  beats per minute *of that beat*. This is stated, tested, and visible
  in bar/beat readouts — not hand-waved.
* **Velocity is first-class**: strong beats are just louder events.
  Authoring sugar (below) applies a documented default accent map
  (downbeat 108, mid-bar strong beat 100, weak 88, off-grid 76) that
  the LLM/user can override per event — defaults are data in the doc,
  not hidden weights.
* **Swing is stored as a parameter, applied at realization**:
  `swing: {"subdivision": 0.5, "ratio": 0.67}` on a pattern or
  arrangement shifts every off-beat event at that subdivision to the
  ratio point (0.67 ≈ triplet swing). Storing straight-grid + parameter
  keeps patterns editable and analyzable; literal micro-timed onsets
  remain expressible by just… writing the floats. Both honest.

## 3. Patterns stay vocabulary; verbs become sugar

`rhythms` remain named library objects — that part of Phase R was
right — but a pattern's stored truth is an **event list** in the form
above (grip-relative `string`/`strings` notes only; `pitch` is not
allowed in a pattern, keeping them portable). The Phase R verbs
(`strum`, `bass`, `arp-up`…) survive as **authoring macros**:
`define_rhythm` accepts them and expands to explicit events at
definition time (an arp verb becomes n placed events with real onsets
and the accent-map velocities). Stored form is always the expanded,
fully-detailed grid — inspectable, editable event by event, nothing
hidden. Built-ins get re-expressed in the new form (same names).

## 4. Arrangement semantics

Per-sequence assignment survives from Phase R (default pattern +
per-step `{rhythm, repeat}` + `@section` inheritance) and gains the
missing container fields: `tempo` (BPM of the meter beat, 20–300),
`meter` (validated `[num, denom]`, denom ∈ {2,4,8,16}), `swing`
(optional, as above). A step's span = pattern length × repeat, in
beats; bar/beat positions derive from the meter correctly.

## 5. Melody parts (scope decision for review)

The stated product frame — grip-mcp supplies **base harmony and
melody** — plus `pitch` events make melody representable now: a named
`part` attached to a sequence (parallel to its chord timeline), events
with absolute pitches, same grid/velocity/swing. Proposed as **in
scope** for v2 (it is the same machinery), but flagged for review since
it widens the surface: `set_part(sequence, name, events)`, realized
into the timeline, analyzable against the harmony (non-chord-tone
flags per step — mechanical, no judgment).

## 6. What downstream consumers get

* `analyze`: timeline with true bar/beat; duration-weighted key scores
  (kept from Phase R — that part was sound); NEW: metric placement per
  step and, with melody parts, per-note chord-tone/non-chord-tone
  labeling.
* `render_audio`: unchanged role (deterministic Karplus–Strong
  audition) but honors velocity (amplitude scaling) and swing.
* **The bus**: two artifacts per export. `export_timeline` (JSON,
  annotated with chosen names + analysis — cdp-mcp's structured
  source) now embeds the detailed events verbatim; and
  `export_midi` — a standard `.mid` (format 1: tempo/meter meta +
  chord track + melody tracks, velocities intact), hand-written SMF
  (small, dependency-free, deterministic) since "we might just want
  MIDI directly" deserves the literal answer. Un-tabling exactly the
  MIDI sliver of Phase 4, nothing else.

## 7. Migration from Phase R

Schema: `rhythms` entries gain `"events_v2"`… no — clean break, since
no meaningful rhythm data exists in the wild yet: v2 replaces the
event grammar outright; a load-time migration expands any Phase-R
verb-form pattern to v2 events (the same expansion the sugar uses), so
even a library that used Phase R for a day loads clean. `set_rhythm`
assignments are unchanged in shape. Phase R's five play-verbs disappear
from storage but survive as macros, so nothing the LLM learned to say
stops working.

## 8. Testing (sketch)

Grid semantics (6/8 bar/beat math; denominator changes beat length in
seconds); velocity defaults + overrides; swing realization (0.67 ratio
moves the and-of-beat, straight notes untouched; literal-float swing
untouched by the parameter); macro expansion goldens (verb in → exact
events out); melody part against harmony (chord-tone labeling);
deterministic audition with velocity audible in amplitude; SMF
byte-golden (deterministic .mid); migration (Phase-R pattern loads as
expanded v2); everything Phase R already tests re-pointed.

## 9. Open questions FOR THIS REVIEW

1. **Melody parts now or later?** (§5 — my lean: now, same machinery.)
2. **Velocity accent-map defaults** (§2): the 108/100/88/76 ladder is a
   proposal — pick your numbers; they're spec data.
3. **Swing default subdivision** 0.5 (eighths) — right for your
   playing?
4. **`.mid` on the bus alongside the JSON** (§6): yes/no, and should
   cdp-mcp prefer one?
5. Anything Hooktheory does that this still can't say? (Their
   scale-degree-relative melody storage is the one thing deliberately
   NOT adopted — absolute pitches keep us tuning-agnostic; degrees are
   derivable through analysis.)
