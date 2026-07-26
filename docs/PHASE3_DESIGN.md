# Phase 3 — Analysis: Design Note

Status: v1.0 · 2026-07-26 · companion to DESIGN.md §9 (Phase 3), same
house rules: deterministic, documented, mechanical — never tuned
weights; the server analyzes by published rules, the LLM interprets and
the musician decides.

DESIGN §9 gives Phase 3 one line: "`analyze(sequence)` — Roman numerals
in candidate keys, bass-line extraction, common tones, voice-leading
distance (per-voice semitone motion with crossing penalties), modulation
detection; foreign-bass slash candidates; music21 promoted to core."
This note pins each clause to a rule an implementer (and a fixture) can
hold.

## 1. Decisions up front

**D1 — music21 stays an oracle, is not promoted to core.** The §4 bet
("dependency weight deferred for Phase-3 option value") anticipated
needing m21 *inside* the engine for Roman numerals. It turned out the
frozen table + line-of-fifths machinery already carry everything Roman
numerals need, deterministically; importing m21's analysis would trade
fixture-pinned rules for library heuristics — the opposite of the house
style. m21's genuine core need is Phase 4 (MusicXML/MIDI emission).
So: numerals are computed by our rules and *oracled* against
`music21.roman.romanNumeralFromChord` where m21 can express them —
exactly the Milestone-0 relationship, extended. The §4 checkpoint
("if Phase 3 slips, revisit") closes with the opposite finding: the
option wasn't needed for analysis at all.

**D2 — analysis reads the user's vocabulary first.** Every step's
harmonic identity is its **display candidate**: `chosen` if set, else
the context-free top (§5.2.3's display rule, applied to analysis). The
musician's recorded hearing outranks the ranking. Steps are the
flattened sequence (`@references` expanded).

**D3 — analysis is read-only and derived.** `analyze` writes nothing
(no history entry) and caches nothing; it recomputes from library +
derived caches on every call, like context rankings (§7.5).

## 2. `analyze(sequence, keys?)` — the output contract

### 2.1 Steps

`steps[i] = {grip, name, named, midi, root, quality, bass}` — name is
the display candidate's canonical name (or the user's chosen), `named`
mirrors the working-title flag. Grips whose candidate set is empty
(single-PC grips) carry `quality: null` and participate only in the
bass line and voice leading.

### 2.2 Bass line

`bass_line = [{step, pitch, midi}]` plus `motion = [semitones]` between
adjacent basses (signed). Spelling: the step's own display spelling.

### 2.3 Common tones

Per adjacent pair: the PC intersection of sounding sets, spelled per
the EARLIER step's display candidate (documented choice; the later
step may respell — spelling belongs to interpretations, §5.2).

### 2.4 Voice leading

Per adjacent pair, over sounded MIDI notes (doublings included):

* Matching rule: the **minimal-total-|semitone| monotone matching**
  between the two sorted note lists, computed by dynamic programming;
  when cardinalities differ, the DP chooses which notes of the longer
  list go unmatched. Monotone matching is provably minimal under L1 for
  sorted lists and **never crosses** — the doc's "crossing penalties"
  are satisfied by construction rather than by a weight (a weight
  would violate the house rule; a matching that cannot cross needs no
  penalty). Ties in the DP break toward matching lower notes first
  (deterministic).
* Output: `{total, motions: [{from, to, semitones}], entered: [...],
  left: [...]}`, pitches spelled per their own step's display
  candidate. `total` = Σ|semitones| over matched voices.
* This is also where hammer-on/pull-off gesture pairs land by design:
  two adjacent grips, one voice moving, everything else `0` — the
  representation chosen when ornaments were reverted.

### 2.5 Roman numerals in candidate keys

* **Candidate keys**: all 24 (12 tonics × major/minor), scored by the
  count of steps whose display candidate passes **R0** (§7.2's frozen
  rule, minor's V/V7 admission included). Ranked by (score desc,
  |signature| asc, major before minor, tonic PC asc); the top 3 are
  reported (`keys` overrides with an explicit `context_key` list).
* **Numeral, mechanically**: respell the root in the key (Key.spell +
  the A5.1 overflow fallback); degree = letter distance from the tonic
  letter (1–7); chromatic prefix = (root_lof − diatonic_degree_lof)/7
  rendered as `b`/`#` repetitions (`bVII`, `#IV`); numeral case: rows
  containing interval 4 → upper, interval 3 → lower, neither → upper.
* **Suffix**: the row's name production, with one transformation — rows
  whose minor third the case already conveys drop their leading `m`
  (`m`→∅, `m7`→`7`, `m6`→`6`, `madd9`→`add9`, `mMaj7`→`Maj7`,
  `m7b5`→`7b5`); `dim`/`dim7` keep their names. Non-tertian rows keep
  their full suffix on an uppercase numeral (`Vsus4`, `I5`, `IIq4`).
  Inversions append `/bass` in the key's spelling. No figured-bass
  figures in V1 of analysis (append-a-figure is an additive change).
* Per reported key: `numerals = [string|null]` (null where the step
  fails R0 in that key — chromatic *to that key*, stated not judged).

### 2.6 Modulation detection

Greedy left-to-right segmentation: extend the current segment while
some key passes R0 for **every** step in it (track the running
intersection of per-step passing-key sets); on empty intersection,
close the segment and start a new one. Steps passing in *no* key
(fully chromatic verticalities) are **transparent** — they join any
segment without constraining it (documented; prevents degenerate
one-step segments). Output: `segments = [{steps: [i..j],
keys: [ranked]}]` and `modulations = [{at_step, from_keys, to_keys}]`.
One segment = no modulation detected. This is segmentation by
membership, not cadence inference — honest scoping; the LLM narrates
what the segments suggest.

## 3. Foreign-bass slash candidates (spec; lands as its own change)

The identify pipeline gains a third R1 class: `root-is-bass (0) <
inversion (1) < foreign bass (2)`. Generation: for inputs with ≥ 2
distinct PCs above a bass whose PC is **not** in a candidate row's tone
set, cover the non-bass PC set as usual and emit `X<suffix>/<bass>`
with the bass spelled canonically (context: key-respelled), `inversion:
null`, and the bass listed in `intervals_from_root` but never in
`missing`. Everything else (R0/R2/R3, tie-break) applies unchanged;
foreign-bass candidates can never outrank a chord-tone reading of the
same content (R1 guarantees it).

This is the doc's "additive" change class: engine_version → 1.1.0 in
both engines (reference + implementation, parity maintained), caches
invalidate, fixtures regenerate, and the change arrives with its own
fixtures (the classic C/D; a pedal-point case). Deliberately **not**
bundled with `analyze` — one engine-touching change per commit.

## 4. Testing

Numerals oracled against `music21.roman.romanNumeralFromChord` for
tertian rows across all 24 keys (optional dep, as ever). Analysis
tests use hand-checkable progressions (I–vi–IV–V in C; the same grips
respelled under `a-minor`; a two-key sequence for segmentation; a
gesture pair for single-voice motion) plus determinism and
@reference-flattening checks. The Gm/Em song gets an analysis snapshot
test so its output is pinned and reviewable, not asserted by hand.
