# Rhythm — Design Draft (rev 2)

Status: **draft, awaiting second review — not implemented.** Rev 2
incorporates a full review of rev 1 (see git history); the findings'
resolutions are inlined at their homes. House rules from
[DESIGN.md](DESIGN.md) apply: deterministic, documented, mechanical —
never tuned weights.

## 0. Supersessions (explicit, clause by clause)

* DESIGN.md §9: rhythm is promoted from "Someday"; Phase 4's MIDI
  export sliver is un-tabled (§6 here); the remainder of Phases 4 and 5
  stays tabled.
* PHASE3_DESIGN.md §2.5: key scoring gains a duration-weighted variant
  when a timeline exists (§6 here, aggregation fully specified).
* No other accepted clause changes. Future drafts must extend this
  section rather than amend by side effect.

## 1. Motivation

(As rev 1, trimmed to what §6 delivers.) Rhythm bears on harmonic
analysis — duration enters key ranking; metric placement and
articulation are *reported* for the client LLM to reason over, and
only duration enters ranking. The `exports/` bus should carry
structured harmony+rhythm, not rendered audio. Sequences must be
auditionable. The bar for expressiveness is Hooktheory's beat grid and
MIDI's event model: onset, duration, pitch, velocity — accents, swing,
ghost notes all sayable.

## 2. Time is integer ticks

**All onsets and durations are integers at 960 ticks per meter beat.**
Floats cannot represent triplets, make swing membership an epsilon
hazard, and destabilize content hashes and SMF goldens; ticks fix all
four at once. The tool interface accepts beats as numbers or fraction
strings ("1/3"); snap rule: nearest tick, round half up, documented
here. SMF emits at PPQ derived from the same grid (§6).

## 3. The event form

```jsonc
{"at": 2400,         // ticks from container start (2400 = beat 3.5)
 "dur": 480,         // ticks, > 0
 "velocity": 96,     // 1-127 (0 is MIDI note-off; forbidden in storage)
 "note": ...}        //   {"string": 3}          sounding-string index
                     //   {"strings": [1,2,3]}   chord hit ("up": true)
                     //   {"strings": "all"}
                     //   {"arp": "up"|"down"}
                     //   {"pitch": "D4"}        melody parts only
```

**String indexing (decided):** indices address the grip's
**sounding-strings list, 1 = the lowest-pitched sounding string**. Not
physical strings (a pattern's "1" is always the sounding bass — that
is what makes `bass-strum` portable across x-x-8-7-8-x and a
six-string grip), and not the guitarist's 1-=-highest convention
(grips store low→high, DESIGN §5.1; the convention is stated here once
and everywhere). An index past the sounding count drops the event with
warning code `pattern_string_missing`. `"up": true` and `arp:"down"`
mean highest-pitched first; default order is lowest first.

Chord hits carry one velocity; edge-accented strums are written as
per-string events — no per-string velocity array will be added to the
chord form.

## 4. Meter, accents, grouping, swing

`meter: [num, denom]`, denom ∈ {2,4,8,16}; the beat is the denom-note;
a bar is `num` beats; `tempo` is BPM of that beat (20–300).

**Grouping** (drives accents and SMF clicks): compound meters (num>3,
divisible by 3) group in 3s; otherwise 2s with a trailing 3 when num
is odd (7/8 = 2+2+3). A pattern or sequence may override with explicit
`grouping: [..]` summing to num.

**Accent placement function** (macro defaults; any event may
override): bar start 108; first beat of each subsequent group 100;
other on-beats 88; off-beat onsets 76. The ladder values remain
reviewable data; this function is the spec.

**Swing:** `swing: {"subdivision": <ticks>, "ratio": {"num":2,"den":3}}`
— subdivision is **mandatory** (no default; a meter-blind default
means swung sixteenths in 6/8). Semantics: a proportional time-warp of
each subdivision pair — every onset inside the pair maps by the warp,
so a pickup inside a swung pair moves coherently; ratio is the
off-beat's position in the pair, exact rational, 1/2 = straight, open
interval (0,1). Warped ticks round half up when inexact. A child
section may set `"swing": null` explicitly to force straight under a
swung parent (the codebase's explicit-null vocabulary).

## 5. Patterns, built-ins, attachment

`rhythms` are named library vocabulary (slug names; removal refused
while assigned; dangling hand-edited names get the dangling-tuning
treatment: load flagged, `describe_workspace` reports, touching tools
error instructively). A user pattern is `{length_beats, meter, swing?,
events}` stored **fully expanded** — verbs (`strum`, `bass`, `arp-up`,
…) are authoring macros expanded at definition time with accent-map
velocities and this duration policy: **let ring** — each expanded
hit's `dur` runs to the next event's onset (the last to pattern end);
arp notes ring to the end of the arp event's span.

**Built-ins are meter-parametric spec functions, not stored objects**
(the one exception to stored-expanded, exactly as `standard` is a
built-in tuning): `whole` = one strum spanning the bar; `quarters` =
a strum on every beat; `bass-strum` = bass on group starts, strum on
other beats; `arp-up` = one bar-spanning arp. They instantiate against
the governing meter at realization; their definitions live here and
are immutable.

A user pattern whose `meter` differs from the sequence's is **refused
at assignment** (`meter_mismatch`) — no silent reinterpretation.

Attachment is unchanged from rev 1 (plain-list sequences untouched;
object form adds `meter`, `tempo`, `swing?`, default `rhythm`,
per-step `{rhythm, repeat}`; `@ref` inheritance). **Meter/tempo
inheritance (decided):** a child carrying its own `meter` must carry
its own `tempo` (validation error otherwise); tempo never crosses a
meter change. Fixture: a 4/4 song with a 6/8 bridge. Steps with no
assignment realize as `whole`. Consequences accepted and fixtured:
non-bar-multiple spans start later steps mid-bar (harmonic rhythm
across barlines is real); events ringing past a step boundary bind
pitch at onset (the old string keeps ringing under the new chord).

## 6. Consumers

* **`analyze`:** timeline (1-based `bar:beat` readouts — `at` ticks
  are 0-based internally, envelopes speak 1-based); key scores gain
  `ticks` = Σ step spans (repeat included) over R0-passing steps —
  velocity does **not** weight; ties fall back to the Phase-3 ordinal
  chain (passes, |signature|, major-first, tonic PC). Metric placement
  and per-event articulation are reported, not ranked.
* **`render_audio`:** deterministic Karplus–Strong audition honoring
  velocity (amplitude ∝ velocity/127; tested as a peak-sample ratio)
  and swing. **One file per sequence** (`<seq>__audition.wav`,
  overwrite) — answering the no-GC posture. Pure-Python synthesis:
  latency of seconds per audition is accepted and stated; cross-
  platform byte-equality is a CI-verified property (arithmetic avoids
  platform libm). The 12 ms strum stagger is a **realization-only
  ornament**: applied here, absent from `analyze` and both exports.
* **The bus:** `export_timeline` JSON carries **both** `events_stored`
  (straight grid + swing parameter) and `events` (realized ticks,
  swing applied); the content hash is computed over the realized form.
  JSON is the primary artifact for cdp-mcp. `export_midi` emits
  format-1 SMF at PPQ 960/(4/denom-quarter mapping): tempo meta =
  (60e6/tempo)×(denom/4) µs per quarter; time-signature clicks =
  96/denom clocks (×3 for compound meters — the dotted-beat
  convention DAWs expect). Velocities 1–127; overlapping same-pitch
  notes truncate at retrigger (note-off before the new note-on). No
  stagger in MIDI.

Warning codes introduced: `pattern_string_missing`, `dangling_rhythm`,
`meter_mismatch`.

## 7. Melody parts — fast follow, not first build

Adopted from review: the first build lands patterns + attachment +
timeline + both exports; `parts` (absolute-pitch events, per-note
chord-tone labeling at the **onset** step — suspensions mislabel by
stated simplification) follow immediately after, in their own reviewed
increment. Committed now: parts transpose by the same semitone map
whenever sequence-level transposition exists — melody is never
stranded by the covariance story. Degree storage stays rejected
(absolute pitch is ground truth; degrees derive through analysis).

## 8. Serialization

Expanded storage is diff-noisy by design ("nothing hidden behind a
verb"); the canonical form is: insertion-ordered keys as written by
the serializer, integer ticks (no floats anywhere in stored time),
2-space-indent JSON — both git diffs and content hashes feed on it.

## 9. Testing (sketch)

Tick snapping (1/3 in → 320 ticks); grouping + accent goldens for 4/4,
3/4, 6/8, 7/8; macro-expansion goldens incl. duration policy; swing
warp (pair interior points move; explicit-null child forces straight);
meter-mismatch refusal; 4/4-with-6/8-bridge inheritance fixture;
mid-bar step starts; sounding-string indexing on sparse grips +
`pattern_string_missing`; weighted-vs-ordinal key flip with the tie
fallback; audition determinism + velocity peak ratio + single-file
overwrite; SMF byte-goldens (tempo/time-sig metas per meter, truncate-
at-retrigger, no velocity 0); export JSON carrying stored + realized.

## 10. Open for the second review

1. PPQ 960 per meter beat — sufficient resolution, or 3840?
2. The grouping default (3s for compound, 2+trailing-3 for odd) — any
   meter you use where this guesses wrong?
3. Accent ladder values (function now specified).
4. Anything in §6's SMF mapping that fights your DAW of choice?
