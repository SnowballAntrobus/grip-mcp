# Rhythm — Design Draft

Status: **draft, awaiting review — not implemented.** House rules from
[DESIGN.md](DESIGN.md) apply: deterministic, documented, mechanical —
never tuned weights; the server realizes and validates, the client LLM
suggests, the musician decides. Process rule: any design surface not
specified in DESIGN.md gets a reviewed design document before
implementation. This is that document for rhythm.

## 1. Motivation

DESIGN.md defers rhythm to "Someday" and routes interop through Phase 4
(MIDI/MusicXML/audio export). Both orderings are revised here, for
three reasons:

* Rhythm bears on harmonic analysis. A chord held four bars argues for
  a key harder than a passing eighth; a strummed chord and an
  arpeggiated one are different statements; metric placement matters.
  `analyze` ([PHASE3_DESIGN.md](PHASE3_DESIGN.md)) cannot see any of
  this today, and suggesting rhythms is part of the client LLM's task.
* The `exports/` bus (DESIGN.md §3) should carry **structured harmony
  and rhythm**, not rendered audio: grip-mcp supplies base harmony and
  melody that cdp-mcp builds on. Phase 4's WAV export is the wrong
  artifact; the timeline is the right one. Phases 4 and 5 stay tabled
  except the MIDI sliver this document un-tables (§6).
* Sequences need to be **auditionable** — hearable as audio previews —
  without that audio being an export product.

The representation must be *detailed*. Two references set the bar.
Hooktheory/Hookpad places everything on a true beat grid — measures,
fractional beat onsets, per-note durations, meter and tempo as
first-class, swing as a setting — which is what makes rhythm both
expressible and analyzable. MIDI's event model — onset, duration,
pitch, velocity — can encode essentially any rhythmic statement
(accents and strong beats, swing, ghost notes) and is the interchange
language downstream tools already read. This design adopts MIDI's
semantics on a beat-denominated grid. Anything less (e.g. a small
vocabulary of strum/arpeggio verbs without dynamics) cannot say what
players actually play.

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
  beat readouts in analysis derive from this — specified and tested.
* **Velocity is first-class.** A strong beat is simply a louder event.
  Authoring macros (§3) apply a documented default accent map —
  downbeat 108, secondary strong beat 100, other on-beats 88,
  off-beats 76 — and any event may override it. The map is spec data
  in this document; reviewers should treat the numbers as proposals.
* **Swing is a stored parameter, applied at realization.**
  `swing: {"subdivision": 0.5, "ratio": 0.67}` on a pattern or
  arrangement shifts each off-beat onset at that subdivision to the
  ratio point (0.67 ≈ triplet swing). Straight-grid events plus a
  parameter keep patterns editable and analyzable; fully literal
  micro-timing remains expressible by writing the onset floats
  directly. Both are honest; neither is privileged.
* Grip-relative note forms skip strings a grip mutes, so patterns are
  portable across shapes and tunings. `pitch` events are forbidden in
  patterns and required in melody parts (§5).

## 3. Rhythms are vocabulary; verbs are authoring sugar

`library.json` gains `"rhythms"`: named, reusable patterns, matching
the product's vocabulary-first model (grips, tunings, sequences —
DESIGN.md §1, §5). A pattern = `{length_beats, meter, swing?, events}`
with §2 events. Lifecycle mirrors tunings: slug names; a small
immutable built-in set (`whole`, `quarters`, `bass-strum`, `arp-up`);
`remove_rhythm` refuses while any sequence assigns the pattern.

Convenience verbs (`strum`, `bass`, `arp-up`, …) are accepted by
`define_rhythm` as **authoring macros only**: they expand at definition
time into explicit events with accent-map velocities. Stored form is
always the expanded, fully inspectable grid — nothing hidden behind a
verb.

## 4. Attachment: sequences gain assignments, not new syntax

Sequence items stay grip ids / `@refs`. A sequence may additionally
carry `meter`, `tempo` (20–300 BPM of the meter beat), `swing?`, a
default `rhythm`, and per-step overrides `steps: {index: {rhythm?,
repeat?}}` (a step's span = pattern length × repeat, in beats).
Storage: a sequence is a plain list (harmonic order only, exactly as
today) or an object `{items, ...}`; every reader normalizes, so
existing libraries are untouched. Set via `set_rhythm(sequence, ...)`.
`@ref` inheritance: a referenced sequence uses its own assignments
where it has them and inherits the parent's default where it doesn't —
sections keep their feels inside a song. Steps with no assignment
anywhere realize as `whole` (a documented default, not an error).

## 5. Melody parts

DESIGN.md's frame has grip-mcp supplying base harmony **and melody**.
`pitch` events make melody representable with the same machinery: a
sequence may carry named `parts` — event lists with absolute pitches,
same grid/velocity/swing — realized in parallel with the chord
timeline. Analysis labels each melody note chord-tone or
non-chord-tone against the step sounding at its onset (mechanical
membership, no judgment). Absolute pitches, not scale degrees, are
stored (the DESIGN.md §5.2 posture: ground truth is pitch; degrees are
derivable through analysis). Scope question for review: first build or
immediately after (§9.1).

## 6. Consumers

* **`analyze`**: gains a timeline (true bar/beat placement per step)
  and duration-weighted key scoring — R0 passes weighted by beats held
  (data, not a tuned weight). Unrhythmed sequences analyze exactly as
  today. With melody parts: per-note chord-tone labeling.
* **`render_audio`** (new): the audition path — deterministic
  Karplus–Strong plucked-string synthesis (dependency-free delay-line
  arithmetic, seeded excitation: same request, same bytes) honoring
  velocity (amplitude) and swing; one WAV into `grip/renders/` beside
  the PNGs. A preview, not an export.
* **The `exports/` bus** (first writes under DESIGN.md §3's naming):
  `export_timeline` — annotated JSON (`grip__<seq>__<hash8>.json`:
  chosen names first, events verbatim, analysis summary) for
  structured consumers such as cdp-mcp — and `export_midi` — a
  standard `.mid` (format 1: tempo/meter meta track, chord track, one
  track per melody part, velocities intact) via a small deterministic
  SMF emitter, no new dependencies. This un-tables exactly the MIDI
  sliver of Phase 4, nothing else.

## 7. Determinism and versioning

Realization, synthesis, and both exports are pure functions of library
content + parameters; export filenames carry content hashes and
overwrite idempotently (the DESIGN.md §6.4 posture). Schema: `rhythms`
and sequence-object fields are additive; `schema_version` unchanged;
absent fields mean what absence means today.

## 8. Testing (sketch)

Grid semantics (6/8 vs 3/4 bar math; the denominator changes the
beat's duration in seconds); velocity defaults and overrides; swing
realization (ratio moves off-beats; straight and literal onsets
untouched); macro-expansion goldens (verb in → exact stored events
out); lifecycle (built-ins immutable, referenced-pattern removal
refused, plain-list sequences untouched on disk); @ref inheritance;
duration weighting that flips a key ranking a step count cannot;
melody-vs-harmony labeling; audition determinism with velocity audible
in amplitude; SMF byte-goldens; export naming/scoping.

## 9. Open questions for this review

1. Melody parts (§5) in the first build, or immediately after?
2. The accent-map ladder 108/100/88/76 (§2) — adjust?
3. Default swing subdivision 0.5 (eighths) — correct default?
4. Bus artifacts: both JSON and `.mid` (§6)? Which should cdp-mcp
   treat as primary?
5. Hooktheory stores melody as scale degrees; this design stores
   absolute pitches. Any case where degree storage is actually needed?
