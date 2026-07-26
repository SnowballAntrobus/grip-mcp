# Rhythm Notation — Design Draft (rev 1)

Status: **draft, awaiting review — not implemented.** Depends on
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

## 1. The grid form

A notation is a header line, an optional counting row, and one line
per bar:

```
4/4 swing 2:3 @ 1/2
1 & 2 & 3 & 4 &
B D D . B D D .
```

**Header:** `num/denom [swing N:D @ <beats>] [grouping a+b+c]` — the
meter is the pattern's meter (patterns bind to one meter,
RHYTHM_DESIGN §5); swing's subdivision displays in beats (fraction
form, `@ 1/2` = 480 ticks), matching the beats-in interface; grouping
only when it overrides the default. `swing straight` renders an
explicit `"swing": null`.

**Grid resolution** (deterministic): the coarsest step from the
ladder — beat 960, halves 480, triplets 320, quarters 240, eighths
120 (of a beat) — that lands every onset. Formally: the largest
ladder value dividing gcd of all onsets and 960. Onsets fitting no
ladder step (septuplets; 320/240 mixtures with gcd 80; sextuplet 160)
fall back to list form (§3) — stated, never squeezed onto a lying
grid.

**Counting row** (render always emits it; parse ignores it): beats
count from 1; `&` at halves; `e`/`a` at quarters (`1 e & a`); `t`/`l`
at triplet thirds (`1 t l`); `.` fillers on the 120 grid. Purely
visual — alignment is by whitespace-separated field, not by column.

**Bar lines:** one line per bar, slots separated by whitespace,
optional `|` at the ends ignored. The parser infers the grid step
from the slot count (`slots = num * 960/step` must land on a ladder
step, every line the same count) — so the counting row never needs to
be typed, and padding is free.

## 2. Tokens

Per-slot, one token:

| token | note form |
|---|---|
| `.` | no onset |
| `D` | `{"strings": "all"}` (down-strum: physical 1→n) |
| `U` | `{"strings": "all", "up": true}` |
| `B` | `{"string": "bass"}` (symbolic — lowest pitch) |
| `3` | `{"string": 3}` (physical sounding index, 1-9) |
| `[135]` | `{"strings": [1,3,5]}`; `[135]^` reverses traversal |
| `A` | `{"arp": "up"}` (spans to the next onset, let-ring) |
| `V` | `{"arp": "down"}` |

**Accents** (deterministic both ways, keyed to the accent placement
function of RHYTHM_DESIGN §4): a token renders **plain** when its
stored velocity equals `accent_velocity(at)` for its position — the
expansion default, so default patterns render with no accent ink at
all. `>D` marks velocity 108 where the map says less; `(D)` marks 76
where the map says more; anything else renders the exact escape
`D@93`. Parse inverts exactly: plain → the map value, `>` → 108,
`( )` → 76, `@v` → v. Round trip is byte-exact.

**Durations:** the grid shows onsets; let-ring (the §5 default) is
implied and needs no ink. A pattern whose stored durations deviate
from let-ring is **not grid-representable** — it renders in list form
(§3), never as a grid that hides the cut. (A staccato-notation
extension is a future decision, not a silent approximation.)

## 3. List form (the total fallback)

Any pattern renders in list form; grid-unrepresentable ones render
*only* this way:

```
4/4 length 4
@ 1     B
@ 2+1/3 D dur 1/3
@ 3     D@93
```

`@ <beats>` (1-based, fraction-friendly, matching bar:beat readouts),
token, optional `dur <beats>` when not let-ring. Fully round-trippable
with zero loss; the grid is the readable subset, the list is the
honest superset. Render picks: grid when representable, list
otherwise, with a one-word reason (`# off-grid onsets` /
`# explicit durations`).

## 4. Parsing rules (strict, instructive)

* Slot counts must be consistent and land on a ladder step; the error
  names the count and the nearest valid grids.
* The dotless idiom is **refused, not guessed**: guitarists write
  "D D U U D U" for what is actually `D . D U . U D U`, and the
  placement is genuinely ambiguous — the refusal shows the dotted
  form(s) and asks. No silent reinterpretation, same posture as
  meter_mismatch.
* Unknown tokens, indices past 9, malformed escapes: errors name the
  token and the vocabulary.
* A header meter disagreeing with an explicit `meter` argument is an
  error (`meter_mismatch` family), not a preference.

## 5. Surfacing (no new tools)

* `set_rhythm` accepts `notation: <text>` XOR `events` (+`length`);
  meter/swing/grouping come from the header or the existing
  parameters — both present must agree.
* `set_rhythm`'s **response always carries `notation`** (rendered
  from what was stored) — the echo-verify. `list_rhythms` carries it
  per pattern. Built-ins are meter-parametric, so they render as a
  fixed 4/4 example, labeled (`# in 4/4; adapts to the governing
  meter`) — deterministic and context-free; the rejected alternative
  (render in each meter some sequence currently uses) makes the
  listing depend on unrelated state. [Open question 4.]
* `analyze`'s timeline steps already name their rhythm; the LLM
  presents grids on request by relaying `list_rhythms` strings — the
  descriptions (bumped) instruct: *present the engine's notation
  verbatim; never draw your own grid*.

## 6. Round trip and testing (sketch)

Property: for every **grid-representable** pattern (onsets on a
ladder grid, let-ring durations, token-vocabulary note forms),
`parse(render(p))` re-expands to exactly `p` — fixture-pinned and
fuzzed over randomized representable patterns. Goldens: the four
built-ins rendered in 4/4, 3/4, 6/8, 7/8 (accent-plain by
construction); the swung-bass demo (`B D D . B D D .` with the swing
header); accent escapes; list-form round trips including explicit
durations; every §4 refusal with its message; whitespace/padding/`|`
robustness. Odd-meter counting rows (7/8 at the beat grid counts
`1 2 3 4 5 6 7` — the beat is the eighth; at 480 it doubles to
fourteen slots) are goldens precisely because they are the rows most
worth pinning before anyone argues about them.

## 7. Non-goals

Sequence-level strips (chords × bars × pattern names) stay LLM
presentation over the analyze timeline — no engine string for them in
this increment. Staff/tab rendering, PNG notation, and stored
notation fields are out. Melody-part notation waits for melody parts.

## 8. Open questions for review

1. Token letters: `D`/`U`/`B`/`A`/`V` and `[135]^` — right set? (`D`
   follows the guitarist convention over verb initials.)
2. Accent ink: `>` / `( )` / `@v` escape — acceptable noise floor,
   or should `@v` be list-form-only?
3. Triplet counting tokens `1 t l` (and `.` fillers at 120) — or a
   different convention you actually count in?
4. Built-in previews in `list_rhythms`: fixed 4/4 example, or render
   in each meter currently in use by some sequence?
5. Grid ladder: is 120 (32nds) worth its readability cost, or should
   the ladder stop at 240/320 with list form beyond?
