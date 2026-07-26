# Rhythm — Design Draft (rev 3)

Status: **draft, offered for ratification — not implemented.** Rev 3
incorporates the second (adversarial) review of rev 2 (see git
history): four blockers — SMF PPQ under meter change, string indexing
on reentrant tunings, swing endpoint warp, the audio substrate — plus
findings 5–8 and the minors, resolved inline at their homes. Rev 1's
resolutions were verified closed by that review; nothing reopened.
House rules from [DESIGN.md](DESIGN.md) apply: deterministic,
documented, mechanical — never tuned weights.

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
four at once. 960/beat exactly represents triplets (320) and
quintuplets (192); septuplets snap at ~0.1% error — accepted. The
tool interface accepts beats as numbers or fraction strings ("1/3");
snap rule: nearest tick, **round half up** — the rounding rule
everywhere in this document (snapping, arp spacing, swing warp, tempo
meta). SMF emits at a **fixed PPQ constant** converted from this grid
by integer multiplication (§6) — the storage grid never changes.

## 3. The event form

```jsonc
{"at": 2400,         // ticks from container start (2400 = beat 3.5)
 "dur": 480,         // ticks, > 0
 "velocity": 96,     // 1-127 (0 is MIDI note-off; forbidden in storage)
 "note": ...}        //   {"string": 3}          physical sounding index
                     //   {"string": "bass"}     symbolic: lowest PITCH
                     //   {"strings": [1,2,3]}   chord hit ("up": true)
                     //   {"strings": "all"}
                     //   {"arp": "up"|"down"}
                     //   {"pitch": "D4"}        melody parts only
```

**String indexing (re-decided after the second review):** rev 2 fused
two notions that coincide on most guitars and split on reentrant
instruments — *which string is the bass* (a pitch fact) and *the order
a strum crosses strings* (a physical fact). The standard high-G
ukulele (G4-C4-E4-A4), inside DESIGN §5.1's representable set and this
project's stated audience, is reentrant: the lowest pitch lives on
physical string 2, and a pitch-sorted strum order is one no hand
produces. So:

* **Indices are physical.** They address the grip's sounding-strings
  list in stored physical order (grips store low→high, DESIGN §5.1;
  muted strings don't count): 1 = the lowest physical sounding string.
  Physical indices are stable under grip edits — raising one fretted
  note past a neighbor renumbers nothing.
* **The bass is symbolic.** `{"string": "bass"}` resolves at
  realization to the lowest-*pitched* sounding string. On
  non-reentrant grips that is index 1; on the high-G uke it is
  physical string 2. `bass-strum` expands to the symbolic form — that
  is what keeps it portable across x-x-8-7-8-x, a six-string grip,
  and a uke.
* **Traversal is physical.** Default order is index 1→n (a
  down-strum; also `{"arp":"up"}`); `"up": true` on a chord hit and
  `{"arp":"down"}` reverse to n→1. On a reentrant instrument the
  default strum therefore hits the high G first — the characteristic
  jangle, representable because traversal follows the hand, not the
  pitch sort. Fixtured on the high-G uke.
* **Overflow drops per index.** A chord hit `{"strings":[1,2,5]}` on
  a 4-sounding grip drops index 5 and sounds the rest; a
  single-string event whose index overflows drops whole. Warning code
  `pattern_string_missing` fires once per dropped index, index in
  detail.

Chord hits carry one velocity; edge-accented strums are written as
per-string events — no per-string velocity array will be added to the
chord form.

## 4. Meter, accents, grouping, swing

`meter: [num, denom]`, denom ∈ {2,4,8,16}; the beat is the denom-note;
a bar is `num` beats; `tempo` is BPM of that beat (20–300).

**Grouping** (drives accents and SMF clicks): num=1 groups as `[1]`;
compound meters (num>3, divisible by 3) group in 3s; otherwise 2s with
a trailing 3 when num is odd (7/8 = 2+2+3). A pattern or sequence may
override with explicit `grouping: [..]` summing to num. Two defaults
are **known wrong sometimes and documented as such, not bugs**: 8/8 is
often felt 3+3+2 (default gives 2+2+2+2) and 6/4 is genuinely
ambiguous between 3+3 (the default, via the compound test) and 2+2+2
— both are what `grouping` overrides are for. The default stays
mechanical.

**Accent placement function** (macro defaults; any event may
override): bar start 108; first beat of each subsequent group 100;
other on-beats 88; off-beat onsets 76. The ladder values remain
reviewable data; this function is the spec.

**Swing:** `swing: {"subdivision": <ticks>, "ratio": {"num":2,"den":3}}`
— subdivision is **mandatory** (no default; a meter-blind default
means swung sixteenths in 6/8). Semantics: swing is a
**piecewise-linear bijection of the time axis applied to intervals,
not points** — each event's *both endpoints* (`at` and `at+dur`) map
independently through the warp of the pair each falls in, so
durations warp with their onsets, the let-ring policy's
dur-to-next-onset contract survives swing, and MIDI note-offs land at
swung positions. Ratio is the off-beat's position in the pair, exact
rational, 1/2 = straight, open interval (0,1). Warped ticks round
half up when inexact. **Anchor:** pairs tile from the pattern's start
(tick 0 of each pattern instance) — meaningful whenever a pattern's
length is not a multiple of 2·subdivision. **Layering:** a pattern's
own `swing` overrides the governing sequence/section value for the
steps it plays on and never composes with it; `"swing": null` — on a
pattern or a child section — explicitly forces straight under a swung
parent (the codebase's explicit-null vocabulary).

## 5. Patterns, built-ins, attachment

`rhythms` are named library vocabulary (slug names; removal refused
while assigned; dangling hand-edited names get the dangling-tuning
treatment: load flagged, `describe_workspace` reports, touching tools
error instructively). A user pattern is `{length_ticks, meter, swing?,
events}` stored **fully expanded** — verbs (`strum`, `bass`, `arp-up`,
…) are authoring macros expanded at definition time with accent-map
velocities and this duration policy: **let ring** — each expanded
hit's `dur` runs to the next event's onset (the last to pattern end);
arp notes ring to the end of the arp event's span. `length_ticks` is
an **integer in ticks** — no float length; the authoring interface
accepts beats (numbers or fractions) and converts at definition by
§2's snap rule. Arp spacing likewise: n notes across `dur` place at
k·dur/n, each snapped per §2.

**Built-ins are meter-parametric spec functions, not stored objects**
(the one exception to stored-expanded, exactly as `standard` is a
built-in tuning): `whole` = one strum spanning the bar; `quarters` =
a strum on every beat; `bass-strum` = symbolic bass (`{"string":
"bass"}`) on group starts, strum on other beats; `arp-up` = one
bar-spanning arp. They instantiate against the governing meter at
realization; their definitions live here and are immutable.

A user pattern whose `meter` differs from the sequence's is **refused
at assignment** (`meter_mismatch`); a mismatch created *after*
assignment by a hand edit gets the dangling treatment above — load
flagged, reported, touching tools error instructively. No silent
reinterpretation either way.

Attachment is unchanged from rev 1 (plain-list sequences untouched;
object form adds `meter`, `tempo`, `swing?`, default `rhythm`,
per-step `{rhythm, repeat}`; `@ref` inheritance). **Validation
(decided):** any rhythm assignment — default or per-step — requires
the governing object to carry `meter` (built-ins are meter-parametric;
parametric on nothing is undefined); `render_audio` and `export_midi`
additionally require `tempo`; `analyze` needs `meter` for its timeline
and without one degrades to Phase-3 behavior (§6). **Meter/tempo
inheritance (decided):** a child carrying its own `meter` must carry
its own `tempo` (validation error otherwise); tempo never crosses a
meter change. Fixture: a 4/4 song with a 6/8 bridge. Steps with no
assignment realize as `whole`. Consequences accepted and fixtured:
non-bar-multiple spans start later steps mid-bar (harmonic rhythm
across barlines is real); events ringing past a step boundary bind
pitch at onset (the old string keeps ringing under the new chord).

## 6. Consumers

* **`analyze`:** timeline (1-based `bar:beat` readouts — `at` ticks
  are 0-based internally, envelopes speak 1-based) requires `meter`;
  without one, analyze degrades to today's Phase-3 behavior (no
  timeline, ordinal key scoring). With one, key scores gain `ticks` =
  Σ step spans (repeat included) over R0-passing steps — velocity
  does **not** weight; ties fall back to the Phase-3 ordinal chain
  (passes, |signature|, major-first, tonic PC). Metric placement and
  per-event articulation are reported, not ranked.
* **`render_audio`:** deterministic Karplus–Strong audition
  (requires `tempo`), honoring velocity and swing. **Substrate
  (decided):** 44 100 Hz, 16-bit PCM, mono WAV. Each voice
  synthesizes in integer arithmetic at nominal peak
  (velocity/127)·(32767/8) — headroom divisor **8**, a stated
  constant; voices sum in int32; hard clip at ±32767 on conversion to
  int16. No normalizer — absolute amplitude survives, so the velocity
  test is a defined peak-sample ratio. Per-pitch damping: the loop
  loss is set per pitch so decay-to-silence time is approximately
  pitch-uniform (one documented decay-seconds constant deriving a
  per-pitch loss table), not the naive length-dependent decay that
  drowns trebles under ringing basses. **One file per sequence**
  (`<seq>__audition.wav`, overwrite) — a **deliberate exception** to
  the renders/ `<prefix>__<renderhash8>` convention: overwrite
  semantics are the no-GC answer here; the hash convention stays
  enforceable everywhere else. Pure-Python synthesis: latency of
  seconds per audition is accepted and stated; cross-platform
  byte-equality is a CI-verified property (integer arithmetic, no
  libm). The 12 ms strum stagger is a **realization-only ornament**:
  applied here, absent from `analyze` and both exports.
* **The bus:** `export_timeline` JSON carries **both** `events_stored`
  (straight grid + swing parameter) and `events` (realized ticks,
  swing applied); the content hash is computed over the realized form.
  JSON is the primary artifact for cdp-mcp. `export_midi` emits
  format-1 SMF at **fixed PPQ 3840** — one header `division` for the
  whole file, so meter changes (the 4/4-with-6/8-bridge fixture) need
  no per-file decision: each section converts stored ticks to SMF
  ticks by the integer multiplication **16/denom** (denom 2 → ×8, 4 →
  ×4, 8 → ×2, 16 → ×1). Tempo meta = (60e6/tempo)×(denom/4) µs per
  quarter, **rounded half up to an integer** (the field is a 3-byte
  integer; the rounding is spec, not a frozen accident);
  time-signature clicks = 96/denom clocks (×3 for compound meters —
  the dotted-beat convention DAWs expect). Channel 1, no program
  change. Velocities 1–127; overlapping same-pitch notes truncate at
  retrigger (note-off before the new note-on). No stagger in MIDI.
  One caveat stated so it isn't reported as a bug: DAWs display
  quarter-note BPM, which for compound meters matches neither `tempo`
  (denom-note BPM) nor the felt dotted beat — inherent to MIDI.

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
verb"). The canonical form is defined **here, independent of any
implementation** — the serializer follows this order, never the
reverse: pattern keys `length_ticks`, `meter`, `swing`, `events`;
event keys `at`, `dur`, `velocity`, `note`; note-form keys `string` |
`strings`, `up` | `arp` | `pitch`; swing keys `subdivision`, `ratio`
(`num`, `den`); sequence rhythm keys `meter`, `tempo`, `swing`,
`rhythm`, then steps, a step's keys item, `rhythm`, `repeat`. 2-space
indent JSON; integer ticks (no floats anywhere in stored time). Both
git diffs and content hashes feed on this order.

## 9. Testing (sketch)

Tick snapping (1/3 in → 320 ticks); grouping + accent goldens for 4/4,
3/4, 6/8, 7/8, plus num=1; macro-expansion goldens incl. duration
policy and symbolic-bass expansion; swing warp (pair interior points
move; **durations/offsets warp with onsets** — the note-off golden;
explicit-null pattern and child both force straight; anchor at
pattern start); the reentrant high-G-uke fixture (strum order
physical, `"bass"` resolves to physical string 2); meter-mismatch
refusal at assignment + dangling flag on post-assignment hand edit;
4/4-with-6/8-bridge inheritance fixture **extended into `export_midi`
as an SMF byte-golden containing the meter change**; mid-bar step
starts; physical indexing on sparse grips + per-index
`pattern_string_missing`; rhythm-without-meter validation errors;
weighted-vs-ordinal key flip with the tie fallback; audition
determinism + velocity peak ratio + single-file overwrite + WAV
header/format golden (44.1 kHz mono 16-bit, headroom clip); SMF
byte-goldens (tempo-meta rounding per meter, time-sig metas,
truncate-at-retrigger, no velocity 0, channel 1); export JSON
carrying stored + realized.

## 10. Status for ratification

Rev 2's four open questions are answered by the second review and
adopted: (1) storage stays 960/beat, SMF emits at fixed PPQ 3840 as
an emission constant; (2) the grouping default stays mechanical, with
num=1 patched and 8/8, 6/4 documented as overridable misses; (3) the
accent ladder values stand; (4) the single-`division` header was the
real DAW fight (resolved by fixed PPQ) and the quarter-note-BPM
display caveat is stated. No open questions remain. This revision is
offered for ratification; implementation starts only on acceptance.
