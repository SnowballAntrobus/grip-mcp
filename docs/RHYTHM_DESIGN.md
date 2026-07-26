# Phase R — Rhythm: Design Note

Status: SUPERSEDED — see RHYTHM2_DESIGN.md for why (no velocity, no
swing, underspecified meter) and for the replacement model. Kept as the
record of the shipped implementation it describes. Promotes rhythm from
DESIGN §9's "Someday"; Phases 4 and 5 are tabled. House rules apply:
deterministic, documented, mechanical; the server realizes and
validates, the LLM suggests, the musician decides.

Why rhythm before Phases 4/5: (a) rhythm bears on
harmonic analysis, and suggesting rhythms is part of the task — playing
a chord and arpeggiating it are different statements; (b) what cdp-mcp
wants from grip-mcp is **structured rhythm + harmony**, not audio —
grip-mcp supplies base harmony/melody that cdp-mcp builds on, so the
§3 `exports/` bus carries a timeline document, not a WAV; (c) audio
exists here only as **audition** — a preview artifact beside the PNGs.

## R1. Rhythms are vocabulary

`library.json` gains `"rhythms"`: named, reusable, **grip-agnostic**
patterns — the same gallop applies to any shape in any tuning.

```jsonc
"rhythms": {
  "gallop": {
    "length_beats": 4,          // pattern span, in meter beats
    "meter": [4, 4],
    "events": [                 // onsets; rests are simply gaps
      {"at": 0,   "dur": 1,   "play": "bass"},
      {"at": 1,   "dur": 0.5, "play": "strum"},
      {"at": 1.5, "dur": 0.5, "play": "strum-up"},
      {"at": 2,   "dur": 2,   "play": "arp-up"}
    ]
  }
}
```

`play` ∈ `strum` (all sounding strings, low first) · `strum-up` (high
first) · `bass` (lowest sounding string) · `arp-up` / `arp-down`
(sounding strings distributed evenly across the event's duration) ·
an explicit 1-based string list (strings a grip mutes are skipped —
patterns stay portable across shapes). Validation: slug name; events
inside `[0, length_beats)`; `dur > 0`; overlaps allowed (let strings
ring). Built-ins, immutable like `standard`: `whole` (one strum held),
`quarters` (four down-strums), `bass-strum` (alternating), `arp-up`
(even eighth arpeggio). Lifecycle: `remove_rhythm` refuses while any
sequence references the pattern.

## R2. Attachment: sequences gain assignments, not new syntax

Sequence items stay grip ids / `@refs`. A sequence may additionally
carry `tempo` (BPM, beat = the meter beat) and rhythm assignments:
a `rhythm` default plus per-step overrides `steps: {index: {rhythm?,
repeat?}}` (index into the sequence's own items; `repeat` = pattern
repetitions, default 1 — a step's duration is `length_beats × repeat`).
Storage: a sequence is a plain list (harmonic order only, exactly as
today) or an object `{items, tempo?, rhythm?, steps?}`; every reader
normalizes. Set via `set_rhythm(sequence, rhythm?, tempo?, steps?)`.
`@ref` inheritance: a referenced sequence uses its **own** assignments
where it has them, inheriting the parent's default where it doesn't —
sections keep their feels inside a song.

## R3. The timeline

Realization (shared by analyze, audition, and export): walk the
flattened sequence accumulating beat offsets; each step contributes its
pattern's events with absolute onsets, realized against the grip's
sounding strings/MIDI. Steps without any assignment (no default
anywhere) realize as `whole` — a documented default, not an error.

`analyze` on a rhythm-bearing sequence adds `timeline` (per step:
onset_beats, duration_beats, bar, beat, rhythm) and its key scores gain
`beats` — R0 passes **weighted by duration** (data, not a tuned
weight): a chord held four bars argues for a key harder than a passing
eighth. Ranking: beats desc, then passes, then the Phase-3 tie-break.
Unrhythmed sequences analyze exactly as before. Pattern events do not
change a step's harmonic identity (an arpeggio sounds the same PC set);
they are realization, reported for the LLM to reason about.

## R4. Audition (not export)

`render_audio(sequence, tempo?)` → one WAV in `grip/renders/`
(`<seq>__<hash8>.wav`), deterministic end to end: Karplus–Strong
plucked strings (dependency-free delay-line synthesis; excitation
seeded per note from (midi, onset index) — same request, same bytes,
render-hash idempotency like the PNGs). Strums stagger 12 ms per string
in direction order; notes ring for their event duration into a natural
decay; 22.05 kHz 16-bit mono via stdlib `wave`. FluidSynth stays a
someday-optional upgrade (native install — against §4's doctrine).

## R5. The bus document (what cdp-mcp actually wants)

`export_timeline(sequence, tempo?)` →
`exports/grip__<sequence>__<hash8>.json` (§3 naming; first write to the
shared bus, path-scoped like everything else):

```jsonc
{ "format": "grip-timeline", "version": 1,
  "project": ..., "sequence": ..., "tempo": ..., "meter": ...,
  "steps": [ { "grip", "name",          // the user's chosen name first
               "named", "onset_beats", "duration_beats",
               "midi", "pitches",
               "events": [{"at", "dur", "midis"}] } ],
  "keys": [...], "numerals": {...} }    // the analysis summary
```

Harmony + rhythm + voicing + the user's vocabulary, structured — the
base material cdp-mcp fleshes out. WAV export for cdp is explicitly
NOT this phase (tabled with Phase 4).

## R6. Testing

Lifecycle (built-ins immutable, referenced-rhythm removal refused,
legacy plain-list sequences untouched); realization (offsets, repeats,
@ref inheritance, string-list skipping on muted strings, arp division);
analysis (duration weighting flips a key ranking a step-count tie
cannot; unrhythmed unchanged); audition (WAV header, deterministic
bytes across calls); export (naming, scoping, chosen-name-first).
