# Rhythm Notation — Design (rev 2, ratified)

Status: **ratified 2026-07-26; implemented.** The final review's two
gate conditions were discharged at the gate: (1) the mechanical check
of ratified RHYTHM rev 3 found zero occurrences of `define_rhythm`,
`set_rhythm`, or `set_sequence` — the binding in §5 contradicts no
ratified clause (the rev-1 naming is the only naming that ever
existed in text, and it did not survive into revs 2–3); (2) the `@v`
range rule is in §2/§4. The remaining editorial pins from that review
are folded in below. Rev 2 incorporates the adversarial review of
rev 1 (see git history): four blockers — the counting-row lexical
ambiguity, two missing representability conditions, the string-9 cap,
the tool-name reconciliation — plus findings 5–7, resolved inline.
Depends on [RHYTHM_DESIGN.md](RHYTHM_DESIGN.md) (ratified rev 3);
nothing here changes that model. House rules from
[DESIGN.md](DESIGN.md) apply: deterministic, documented, mechanical —
never tuned weights.

## 0. Scope and authority

Notation is **derived presentation and authoring sugar — never
authoritative**. Storage stays fully-expanded events (RHYTHM_DESIGN
§5); no library schema changes; content hashes and the bus are
untouched. The notation layer is two pure functions and the places
their strings ride:

* `render_notation(pattern) -> text` — from a stored (expanded)
  pattern.
* `parse_notation(text) -> (meter, swing?, grouping?, authoring
  events)` — the parse target is **authoring events**, which then run
  the ordinary definition pipeline (verb expansion, accent-map
  velocities, let-ring durations). One expansion machine, not two.

Why engine-side and not `descriptions/` prose: the closing doctrine
(DESIGN §6.3) — wherever a description asks the LLM to do the right
thing, first make the wrong thing impossible. An LLM hand-rendering
tick JSON into a grid will eventually drop an ampersand; a server
string cannot be mangled, only relayed. Symmetrically, this is the
**echo-verify for rhythm**: as resolved pitches are the self-check for
reversed string arrays (§6.1), the rendered grid coming back from
`set_rhythm` is the self-check for a misplaced onset — the user reads
the same line the engine stored.

A payoff worth naming (from review): because storage is straight grid
plus swing parameter, **swung patterns still render on-grid** — the
swing lives in the header, the grid stays clean. The grid only loses
genuinely mixed straight/triplet figures, which is the rare honest
case.

## 1. The grid form

A notation is a header line, comment lines, and one line per bar.
**Comments are legal anywhere; the first non-comment line is the
header** (order beyond that is bars in order):

```
4/4 swing 2:3 @ 1/2
# 1 & 2 & 3 & 4 &
B D D . B D D .
```

**Comments (grammar rule):** any line beginning `#` is ignored by the
parser. Render emits the counting row as a comment — this closes the
rev-1 ambiguity where a beat-grid counting row (`1 2 3 4`) was
lexically indistinguishable from a bar playing strings 1–4, and it
houses the fallback reason lines of §3 in the same rule.

**Header:** `num/denom [swing N:D @ <beats>] [grouping a+b+c]` — the
meter is the pattern's meter (patterns bind to one meter,
RHYTHM_DESIGN §5); swing's subdivision displays in beats (fraction
form, `@ 1/2` = 480 ticks), matching the beats-in interface; grouping
only when it overrides the default. `swing straight` renders an
explicit `"swing": null`. **Canonical fraction form** everywhere a
fraction renders (headers, list onsets, durations): lowest terms,
proper mixed number `b+n/d` (`7/2` beats of length is `7/2`; the
onset one-and-a-third beats past bar start is `2+1/3`); `swing N:D`
likewise lowest terms. Always exactly representable on the 960 grid,
so zero-loss holds — the canonical spelling is what goldens pin.

**Grid resolution** (deterministic): the coarsest step from the
ladder — beat 960, halves 480, triplets 320, quarters 240, eighths
120 (of a beat) — that lands every onset. Formally: the largest
ladder value dividing gcd of all onsets and 960. Sextuplets (160) are
deliberately a fallback, not a rung.

**Counting row** (rendered as a comment; never required on input):
beats count from 1; `&` at halves; `e`/`a` at quarters (`1 e & a`);
`t`/`l` at triplet thirds (`1 t l`); `.` fillers on the 120 grid.
Purely visual — maximally human, since the parser never reads it.

**Bar lines:** one line per bar, whole bars only, slots separated by
whitespace, optional `|` at the ends ignored. The parser infers the
grid step from the slot count (`slots = num * 960/step` must land on
a ladder step, every line the same count) — padding is free. An
all-`.` line is legal: a rest bar.

## 2. Tokens

Per-slot, exactly one token:

| token | note form |
|---|---|
| `.` | no onset |
| `D` | `{"strings": "all"}` (down-strum: physical 1→n) |
| `U` | `{"strings": "all", "up": true}` |
| `B` | `{"string": "bass"}` (symbolic — lowest pitch; a doubled-unison tie breaks to the lowest physical index, pinning the shipped realization) |
| `3`, `12` | `{"string": n}` (physical sounding index; multi-digit legal — slots are whitespace-separated, so `12` is lexically unambiguous) |
| `[135]` | `{"strings": [1,3,5]}` — compact form, single-digit indices only |
| `[1,10,12]` | comma form, any indices; render emits compact when all ≤ 9, comma form otherwise |
| `[135]^` | `^` reverses traversal; binds inside the bracket form, before any accent mark |
| `A` | `{"arp": "up"}` (spans to the next onset, let-ring) |
| `V` | `{"arp": "down"}` |

The vocabulary is total over the data model: any physical sounding
index renders (blocking finding 3). No mute/chuck token — no
percussive-mute event exists in the model, and notation must never
say what storage can't.

**Accents** (deterministic both ways, keyed to the accent placement
function of RHYTHM_DESIGN §4): a token renders **plain** when its
stored velocity equals `accent_velocity(at)` for its position — the
expansion default, so default patterns render with no accent ink at
all. `>D` marks velocity 108 where the map says less; `(D)` marks 76
where the map says more; anything else renders the exact escape
`D@93`. Parse inverts: plain → the map value, `>` → 108, `( )` → 76,
`@v` → v.

**Accent micro-grammar:** exactly one of {plain, `>` prefix, `( )`
wrap, `@v` suffix} per token — `>` and `( )` are mutually exclusive,
`@v` excludes both (`>D@93` is an error); `^` binds inside the
bracket before any accent (`>[1,3,5]^` is well-formed). **`@v`
enforces 1–127 at parse** — `D@0` and `D@128` are instructive
refusals (velocity 0 is MIDI note-off, forbidden in storage;
RHYTHM §3). The escape reopens no door the storage invariant closed. **Redundant
accent ink is accepted and normalized**, not refused: `>D` written at
a bar start (where the map already says 108) parses to 108 and
re-renders plain — the echo showing the canonical form is the echo
doing its job. Consequently byte-exactness is a property of
**parse-after-render** (the §6 identity on events), not of
render-after-parse, which normalizes text.

**Velocities are data once stored** (consistent with expanded
storage): plain tokens bake against the header's meter and grouping
at definition. There is no partial-edit path for patterns —
`set_rhythm` is whole-replacement, so velocities re-derive on any
legitimate redefinition; a *hand edit* that moves the grouping under
stored velocities makes notation render accent escapes everywhere,
which is the map moving under data — accepted and stated, not a
round-trip bug.

**Durations:** the grid shows onsets; let-ring (the §5 default) is
implied and needs no ink. Stored durations deviating from let-ring
are **not grid-representable** — list form, never a grid that hides
the cut. (A staccato-notation extension is a future decision, not a
silent approximation.)

## 3. List form (the total fallback)

Any pattern renders in list form; grid-unrepresentable ones render
*only* this way. Non-integer lengths use the fraction form:

```
4/4 length 7/2
@ 1     B
@ 2+1/3 D dur 1/3
@ 3     D@93
```

`@ <beats>` (1-based, fraction-friendly, matching bar:beat readouts),
token, optional `dur <beats>` when not let-ring. Fully
round-trippable with zero loss; the grid is the readable subset, the
list is the honest superset. Render picks: grid when representable,
list otherwise, with **every applicable reason emitted as its own
comment line, in the order listed below** — the fallback explanation
never under-reports. The named representability conditions (each with
its reason string, blocking finding 2):

* `# off-grid onsets` — onsets fitting no ladder step.
* `# explicit durations` — durations deviating from let-ring.
* `# partial bar` — length not a whole-bar multiple (RHYTHM §5
  accepts these; the grid form has no length field, so whole bars
  only — no short final lines).
* `# simultaneous events` — two events at one tick (the fingerstyle
  pinch storing bass and chord at different velocities). A compound
  token (`B+[35]`) waits for demand; the named fallback does not.

## 4. Parsing rules (strict, instructive)

* Slot counts must be consistent and land on a ladder step; the
  error names the count and the nearest valid grids.
* The dotless idiom is **refused, not guessed**: guitarists write
  "D D U U D U" for what is actually `D . D U . U D U`, and the
  placement is genuinely ambiguous — the refusal shows the dotted
  form(s) and asks. No silent reinterpretation, same posture as
  meter_mismatch.
* Unknown tokens, malformed brackets or escapes, mixed accent marks:
  errors name the token and the vocabulary.
* **Header/parameter agreement, uniformly:** meter, swing, grouping,
  and **length** may each arrive in the notation or as a tool
  parameter (grid notation *implies* length as bar count × bar
  ticks; list notation states it); when both are present they must
  agree — disagreement is an error naming both values
  (`notation_conflict`), never a preference.
* `@v` outside 1–127 refuses instructively (§2) — the one parse rule
  guarding a storage invariant.

## 5. Surfacing (no new tools)

Tool-name note (blocking finding 4, verified mechanically at the
gate): ratified RHYTHM rev 3 contains zero occurrences of
`define_rhythm`, `set_rhythm`, or `set_sequence` — as does rev 2;
the rev-1 naming (`define_rhythm` defines, `set_rhythm(sequence,…)`
attaches) is the only naming that ever existed in text, carried
forward by revs 2–3 only as the attachment *data model* ("unchanged
from rev 1"'s parenthetical), never as tool names. The implemented
surface — `set_rhythm` defines patterns; `set_sequence` attaches
them — therefore contradicts no ratified clause. This doc binds to
the shipped names; no supersession occurs.

* `set_rhythm` accepts `notation: <text>` XOR `events` (+`length`);
  meter/swing/grouping come from the header or the existing
  parameters under §4's agreement rule.
* `set_rhythm`'s **response always carries `notation`** (rendered
  from what was stored) — the echo-verify. `list_rhythms` carries it
  per pattern.
* **Secondary verify at attachment** (from review): `set_sequence`'s
  response echoes notation for **the patterns assigned in this call**
  (the default `rhythm` and per-step rhythms named in the call, not
  every pattern a large song touches — response-size thresholds are
  real, DESIGN §6.2's inline cutoff being the precedent), keyed per
  distinct **(pattern, governing meter)** pair — under mixed-meter
  `@ref` structures the same built-in previews once per meter it
  will realize in. Built-ins render there in the **actual governing
  meter** — known at attachment, so the preview is exact, not an
  example.
* In `list_rhythms`, where no meter context exists, built-ins render
  as a fixed 4/4 example, labeled (`# in 4/4; adapts to the
  governing meter`) — and `bass-strum` alone carries a second
  labeled line in 6/8, since group-start logic is the one built-in
  behavior a 4/4 example cannot exhibit.
* `analyze`'s timeline steps already name their rhythm; the
  descriptions (bumped) instruct: *present the engine's notation
  verbatim; never draw your own grid*.

## 6. Round trip and testing (sketch)

Property: for every **grid-representable** pattern (onsets on a
ladder grid, let-ring durations, single event per tick, whole-bar
length), `parse(render(p))` re-expands to exactly `p` —
fixture-pinned and fuzzed over randomized representable patterns;
with the comment rule the property now closes at every grid
resolution including the beat grid. Goldens: the four built-ins in
4/4, 3/4, 6/8, 7/8 (accent-plain by construction); the swung-bass
demo (`B D D . B D D .` under the swing header); accent escapes and
redundant-ink normalization (`>D` at a bar start re-renders plain);
multi-digit and comma-bracket indices; each §3 reason line on a
pattern constructed to trigger exactly it; list-form round trips
including `length 7/2` and explicit durations; every §4 refusal with
its message, `notation_conflict` per field; whitespace/padding/`|`
robustness; all-`.` rest bars; odd-meter counting rows (7/8 at the
beat grid counts `1 2 3 4 5 6 7` — the beat is the eighth) pinned
before anyone argues about them; the `bass-strum` 6/8 preview line.
From the final review: `[12]` compact (strings 1 and 2) versus bare
`12` (string twelve) — the one plausible confusion the vocabulary
permits; the mixed-meter attachment echo (one preview per (pattern,
meter) pair); a `swing straight` header round trip; a pattern
triggering multiple §3 reasons at once (every applicable comment, in
order); `@0`/`@128` refusals.

## 7. Non-goals

Sequence-level strips (chords × bars × pattern names) stay LLM
presentation over the analyze timeline — no engine string for them
in this increment. Staff/tab rendering, PNG notation, stored
notation fields, and percussive-mute tokens are out. Melody-part
notation waits for melody parts.

## 8. Review resolutions (rev 1 → rev 2)

All five rev-1 open questions were answered by the review and are
adopted: token set stands (`D`/`U` guitarist convention; no mute
token; compound `+` deferred); `@v` stays in the grid — exiling it
would demote whole patterns to list form for one odd velocity, and
the placement function keeps the default noise floor at zero;
counting tokens `1 e & a` / `1 t l` stand, free to be human now that
the row is a comment; built-in previews are the fixed labeled 4/4
example plus `bass-strum`'s 6/8 line, with exact-meter previews at
attachment; the 120 rung stays (its cost is paid only by patterns
that use it) and 160 stays a fallback.

The final review ratified conditionally; both conditions were
discharged at the gate (see Status) and its editorial pins — the `@v`
range rule, `length` in the uniform agreement rule, canonical
fraction form, multi-reason fallback comments, comments-anywhere
placement, attachment-echo scoping, the symbolic-bass tie — are
folded into §§1–6 above. No open questions remain.
