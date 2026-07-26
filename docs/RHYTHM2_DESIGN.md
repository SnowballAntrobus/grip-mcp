# Rhythm v2 — Design Draft

Status: **draft, awaiting review — not implemented.** Supersedes
[RHYTHM_DESIGN.md](RHYTHM_DESIGN.md) (the current `rhythm.py`
implementation), which remains in place until this document is
ratified. House rules from [DESIGN.md](DESIGN.md) apply throughout:
deterministic, documented, mechanical — never tuned weights; the server
realizes and validates, the client LLM suggests, the musician decides.

Process rule this document also records: any design surface not
specified in DESIGN.md gets a reviewed design document **before**
implementation. The first rhythm implementation shipped from an
unreviewed note and its event model proved inadequate; this draft is
the corrective, and the gate.

## 1. Why the current rhythm model is inadequate

The shipped model (RHYTHM_DESIGN.md) represents a pattern as events
carrying one of five "play verbs" (`strum`, `strum-up`, `bass`,
`arp-up`, `arp-down`) or a string list. That vocabulary can say *that*
a chord is arpeggiated rather than struck, but it cannot say anything
detailed:

* **No dynamics.** There is no velocity, so no strong beats, no
  accents, no ghost notes — every onset is equally loud. Meter without
  dynamics is arithmetic, not feel.
* **No swing.** Every subdivision is straight; there is no way to say
  "eighths swung at a triplet ratio," nor to micro-place an onset.
* **Weak meter semantics.** `length_beats` and `tempo` exist, but the
  relationship between the meter's denominator and the beat unit is
  unspecified; 6/8 versus 3/4 is not actually representable as a
  difference.
* **No melody.** Events can only reference a grip's strings, so the
  library can hold base *harmony* but not the melody lines the project
  intends to carry alongside it (see the export contract in
  [PHASE3_DESIGN.md](PHASE3_DESIGN.md) and the `exports/` bus in
  DESIGN.md §3).

Prior art that gets this right: Hooktheory/Hookpad represents music on
a true beat grid — measures, fractional beat onsets, per-note
durations, meter and tempo as first-class, swing as a setting — and
that grid is what makes rhythm both expressible and analyzable. MIDI
is the other reference point: onset, duration, pitch, velocity is a
representation that can encode essentially any rhythmic statement
(accent, swing, ghosts) and is already the interchange language every
downstream tool reads. Rhythm v2 adopts MIDI's semantics on a
beat-denominated grid.

## 2. The representation: one universal event form

Used everywhere — patterns, performances, melody parts:

```jsonc
{"at": 2.5,          // onset in beats from the container's start; float
                     //   (2.5 = the "and" of beat 3 in 4/4)
 "dur": 0.5,         // duration in beats; float > 0
 "velocity": 96,     // 0-127, MIDI convention exactly; default 96
 "note": ...}        // WHAT sounds — one of:
                     //   {"string": 3}          grip-relative, 1-based
                     //   {"strings": [1,2,3]}   chord hit (12 ms stagger;
                     //                            "up": true reverses)
                     //   {"strings": "all"}     every sounding string
                     //   {"arp": "up"|"down"}   sounding strings spread
                     //                            evenly across `dur`
                     //   {"pitch": "D4"}        absolute (melody; not
                     //                            grip-relative at all)
```

* **Beats are meter beats.** An arrangement's `meter: [num, denom]`
  (denom ∈ {2, 4, 8, 16}) defines the beat: in 6/8 a beat is an
  eighth; a bar is `num` beats; `tempo` is BPM *of that beat*. Bar and
  beat readouts in analysis derive from this — specified and tested,
  not assumed.
* **Velocity is first-class.** A strong beat is simply a louder event.
  Authoring macros (§3) apply a documented default accent map —
  downbeat 108, secondary strong beat 100, other on-beats 88,
  off-beats 76 — and any event may override it. The map is spec data
  in this document, not a hidden weight; reviewers should treat the
  numbers as proposals.
* **Swing is a stored parameter, applied at realization.**
  `swing: {"subdivision": 0.5, "ratio": 0.67}` on a pattern or
  arrangement shifts each off-beat onset at that subdivision to the
  ratio point (0.67 ≈ triplet swing). Storing straight-grid events
  plus a parameter keeps patterns editable and analyzable; fully
  literal micro-timing remains expressible by writing the onset floats
  directly. Both are honest; neither is privileged.
* Grip-relative note forms skip strings the grip mutes, so patterns
  stay portable across shapes (the property worth keeping from the
  current model). `pitch` events are forbidden inside patterns and
  required inside melody parts (§5).

## 3. Patterns stay vocabulary; verbs become authoring macros

`library.json`'s `rhythms` remain named, reusable objects with the
existing lifecycle (slug names; built-ins immutable; removal refused
while assigned). A pattern's **stored truth becomes an event list** in
the §2 form. The current play verbs survive only as authoring sugar:
`define_rhythm` accepts verb-form events and expands them at
definition time into explicit events with accent-map velocities —
what is stored is always the expanded, fully inspectable grid.
Built-ins (`whole`, `quarters`, `bass-strum`, `arp-up`) are
re-expressed in the new form under the same names.

## 4. Arrangement semantics

Per-sequence assignment is unchanged in shape (a default pattern,
per-step `{rhythm, repeat}` overrides, `@section` inheritance — see
RHYTHM_DESIGN.md R2) and gains the container fields the grid needs:
`meter` (validated, as §2), `tempo` (20–300 BPM of the meter beat),
`swing` (optional). A step's span is pattern length × repeat, in
beats.

## 5. Melody parts

The project's own framing (DESIGN.md §1, §3; PHASE3_DESIGN.md) has
grip-mcp supplying **base harmony and melody** to the ecosystem.
`pitch` events make melody representable with the same machinery: a
sequence may carry named `parts` — event lists with absolute pitches,
same grid, velocity, and swing — realized in parallel with the chord
timeline. Analysis labels each melody note chord-tone or
non-chord-tone against the step sounding at its onset (mechanical
membership, no judgment). Scope question for review: include in the
first v2 build, or land the chord-timeline rework alone first.

## 6. Consumers

* **`analyze`**: true bar/beat placement per step; duration-weighted
  key scoring (retained from the current model — that part was sound);
  with melody parts, per-note chord-tone labeling.
* **`render_audio`**: same audition role (deterministic Karplus–Strong
  WAV in `renders/`), now honoring velocity (amplitude) and swing.
* **The `exports/` bus** (DESIGN.md §3) offers two artifacts:
  `export_timeline` — the annotated JSON (chosen names, analysis
  summary, events verbatim) for structured consumers such as cdp-mcp —
  and `export_midi` — a standard `.mid` (format 1: tempo/meter meta
  track, chord track, one track per melody part, velocities intact),
  written as a small deterministic SMF emitter with no new
  dependencies. This un-tables exactly the MIDI sliver of the parked
  Phase 4, nothing else.

## 7. Migration

No meaningful rhythm data predates this change, so the event grammar
is replaced outright; a load-time expansion (the same one the §3
macros use) upgrades any verb-form pattern on read, so a library
written under the current model loads clean. `set_rhythm` assignments
keep their shape. Nothing a client learned to say stops working —
verb-form input remains valid at the tool boundary forever; it simply
stores expanded.

## 8. Testing (sketch)

Grid semantics (6/8 vs 3/4 bar math; denominator changes the beat's
duration in seconds); velocity defaults and overrides; swing
realization (ratio moves off-beats, straight and literal onsets
untouched); macro-expansion goldens (verb in → exact stored events
out); melody-vs-harmony labeling; audition determinism with velocity
audible in amplitude; SMF byte-goldens; migration (verb-form pattern
loads as expanded v2); all current rhythm tests re-pointed.

## 9. Open questions for this review

1. Melody parts in the first v2 build, or immediately after (§5)?
2. The accent-map ladder 108/100/88/76 (§2) — adjust?
3. Default swing subdivision 0.5 (eighths) — correct default?
4. Bus artifacts: both JSON and `.mid`, or one (§6)? Which should
   cdp-mcp treat as primary?
5. Hooktheory stores melody as scale degrees; this design stores
   absolute pitches (tuning-agnostic ground truth, degrees derivable
   through analysis — the DESIGN.md §5.2 posture). Any case where
   degree storage is actually needed?
