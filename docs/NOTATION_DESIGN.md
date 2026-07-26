# Rhythm Notation — Design Draft (rev 2)

Status: **draft, offered for ratification — not implemented.** Rev 2
incorporates the adversarial review of rev 1 (see git history): four
blockers — the counting-row lexical ambiguity, two missing
representability conditions, the string-9 cap, the tool-name
reconciliation — plus findings 5–7, resolved inline. Depends on
[RHYTHM_DESIGN.md](RHYTHM_DESIGN.md) (ratified rev 3); nothing here
changes that model. House rules from [DESIGN.md](DESIGN.md) apply:
deterministic, documented, mechanical — never tuned weights.

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

A notation is a header line, comment lines (ignored by parse), and
one line per bar:

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
explicit `"swing": null`.

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
| `B` | `{"string": "bass"}` (symbolic — lowest pitch) |
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
bracket before any accent (`>[1,3,5]^` is well-formed). **Redundant
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
list otherwise, with the reason as a comment line. The named
representability conditions (each with its reason string, blocking
finding 2):

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
* **Header/parameter agreement, uniformly:** meter, swing, and
  grouping may each arrive in the header or as a tool parameter;
  when both are present they must agree — disagreement is an error
  naming both values (`notation_conflict`), never a preference.

## 5. Surfacing (no new tools)

Tool-name note (blocking finding 4): the implemented surface —
`set_rhythm` defines patterns; `set_sequence` attaches them —
follows ratified RHYTHM rev 3, which names no definition tool;
rev 1's `define_rhythm`/`set_rhythm(sequence, ...)` split did not
survive that document's own full-text rev 2 rewrite. This doc binds
to the shipped names; no supersession of any ratified clause occurs.

* `set_rhythm` accepts `notation: <text>` XOR `events` (+`length`);
  meter/swing/grouping come from the header or the existing
  parameters under §4's agreement rule.
* `set_rhythm`'s **response always carries `notation`** (rendered
  from what was stored) — the echo-verify. `list_rhythms` carries it
  per pattern.
* **Secondary verify at attachment** (from review): `set_sequence`'s
  response echoes the notation of each distinct assigned pattern.
  Built-ins render there in the sequence's **actual governing meter**
  — known at attachment, so the preview is exact, not an example.
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
that use it) and 160 stays a fallback. No open questions remain.
This revision is offered for ratification; implementation starts
only on acceptance.
