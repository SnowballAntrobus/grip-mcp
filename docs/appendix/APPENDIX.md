# grip-mcp — Milestone-0 Appendix

Status: draft pending freeze-gate review · companion to
[DESIGN.md](../DESIGN.md) §13 and to the quality table
(`src/grip_mcp/data/qualities.toml`, the single source of truth for rows,
tiers, tie-break order, discounts, and families).

Everything here is a *decision*, versioned with the table. The meta-test
(`tests/test_table_meta.py`) mechanically enforces the parts a test can
enforce; the rest is frozen prose an implementer may rely on verbatim.

## A1. Name grammar (canonical candidate names)

ASCII, case-sensitive, parse-unambiguous. A canonical name is:

```
<root> <suffix> [ "/" <bass> ]

root   := letter accidental?          letter := A|B|C|D|E|F|G
bass   := letter accidental?
accidental := "bb" | "##" | "b" | "#"     (greedy: longest accidental wins)
suffix := a quality-row `name` from the table ("" = major triad)
```

* The root parse is greedy on the accidental; no suffix begins with `b` or
  `#`, so `Abb` is A-double-flat major, never `Ab` + a `b` suffix.
* Suffix matching is exact and case-sensitive: `m7` ≠ `M7`. The full
  production set is the `name` column of the table.
* Double accidentals appear in *member* spellings (`Ebdim7` contains `Dbb`;
  `D#aug`'s fifth spells `A##`) and are legal in the bass slot:
  `D#aug/A##`. Canonical *roots* never need doubles context-free (the
  canonical root table is single-accidental), but context-key respelling
  keeps roots single-accidental too (see A5); the grammar admits doubles
  everywhere for forward compatibility.

### A1.1 Dyad token encoding (open question 2 — decided)

Dyad names are `dy` + token, with the fixed token set
`m2 M2 m3 M3 P4 A4 m6 M6 m7 M7` used verbatim, case-sensitively:
`Gdym3` (G minor-third dyad), `GdyM3` (G major-third dyad), `CdyA4`.

Rationale: the doc's rejected encodings (`Gm3`, `AA4`) collide with the
quality-suffix parse; `dy` is a two-character prefix no other suffix shares,
and interval-token case (m/M, P, A) is already load-bearing in the token set
itself. Case-sensitivity is a documented property of the whole grammar, so
the dyad tokens introduce no new rule. `coll` is the literal suffix `coll`
(`F#coll`).

There is no `dyP5`: PC distance 7 generates only `X5` (the tier-1 `5` row),
and distance 5 additionally yields the inverted fifth `X5/<bass>` through
ordinary table generation of the `5` row. No other inverted dyad
orientations exist.

## A2. `chosen` reference grammar and tier rule (decision 49)

Input normalization, then parse, then three-tier resolution against the
grip's **full** cached context-free candidate set.

**Normalization:** Unicode accidentals map to ASCII before parsing:
`♯`→`#`, `♭`→`b`, `𝄪`→`##`, `𝄫`→`bb`. Nothing else is rewritten; the
grammar is otherwise case-sensitive.

**Parse:** `<root><suffix?></bass?>` per A1, except the *accepted suffix
set* is wider than the name grammar: (quality names) ∪ (family names) —
the `name` and `family` columns of the table. Root and bass are resolved to
pitch classes only; input spelling never survives into storage (`"F#m"`,
`"Gbm"`, `"Gm/A#"` are the same request).

**Tiers** (first tier producing ≥ 1 match wins; a unique match normalizes
and stores; multiple matches error listing them; zero matches at all tiers
is a miss → partial success per DESIGN §6.1):

1. **Exact canonical match** — the input string, post-normalization, equals
   a candidate's canonical name.
2. **Root-PC + exact quality row** — the suffix names a specific table
   quality (it is a `name`); match candidates with that root PC and quality.
   `"Bsus4"` on Q → the one B-rooted `sus4` candidate → stores
   `Bsus4/F#`. A supplied `/bass` filters by bass PC at this tier and the
   next.
3. **Root-PC + family** — the suffix is a `family` value; match candidates
   whose row carries that family and root PC. `"Bsus"` on Q → `Bsus4/F#`
   and `B7sus4/F#` both carry family `sus` → ambiguity error listing both.

A suffix that is *both* a quality name and a family name (e.g. `m`, `q4`,
`5`, `dim`, `aug`, `7`) resolves at tier 2 first by construction; tier 3 is
reached only when tier 2 matched nothing.

**Family assignments** (the `family` column; single-valued):
`dy` (all dyads) · `5` · `maj` {maj, maj7, 6} · `m` {m, m7, m6, mMaj7,
madd9} · `dim` {dim, dim7, m7b5} · `aug` {aug} · `sus` {sus2, sus4, 7sus4}
· `7` {7} · `add` {add9} · `q4` · `coll`.
The doc fixes only `sus` ⊇ {sus4, 7sus4} and `m` ∋ m (the `"Bsus"` and
`"Gm"` examples); the rest is a freeze-gate decision — argue there.

## A3. `context_key` grammar

`<tonic>-<mode>`, lowercase. Tonic: letter `a`–`g` + optional single ASCII
accidental (`b`/`#`) — the full single-accidental enharmonic set, so
`c#-major` ≠ `db-major` end-to-end. Mode: `major` | `minor` (natural-minor
basis for R0, plus the admitted V/V7 — DESIGN §7.2). Double-accidental
tonics are not part of the V1 grammar (grammar changes are versioned;
DESIGN §10 migrations).

## A4. Tie-break "root letter" (R-tiebreak, component 1)

Alphabetical letter order `A < B < C < D < E < F < G` — **not** C-rooted
pitch order. Pinned by the Q fixture: `Bsus4/F#` ranks above `Esus2/F#`
(and `B7sus4/F#` above `Eadd9/F#`) at the tie-break rung; C-rooted order
would invert both. After letter, the quality-order column decides; as a
deterministic backstop (unreachable given dedup + coverage geometry, but
cheap) root PC ascending is the final component.

## A5. Line-of-fifths respelling under `context_key`

Line-of-fifths index of a spelling: `LoF(letter, acc) = base(letter) +
7·acc` with `base` F=−1, C=0, G=1, D=2, A=3, E=4, B=5.

* **Key anchor** = the signature `s`: for major keys, `LoF(tonic)`; for
  minor keys, `LoF(tonic) − 3` (relative major; natural-minor basis). The
  `c#-major` anchor is +7; `db-major` is −5 — the same PCs spell
  differently end-to-end.
* **Diatonic roots** respell as the scale spells them (letters sequential
  from the tonic; accidentals forced by the PCs).
* **Chromatic roots**: candidate spellings of the PC with accidental ∈
  {♭, ♮, ♯}; choose the one minimizing `|LoF − s|`; ties break sharp-side.
  At signature 0, PC 6: F♯ (+6) vs G♭ (−6) → F♯.
* Members then stack from the respelled root per the `degrees` column, as
  always.

**Honesty note for the freeze review:** DESIGN §5.2.1 claims the exact tie
"exists only at signature 0 … no other key can tie." Under `|LoF − s|`
every signature has one tritone-related pair at distance 6 (s=1: C♯ +7 vs
D♭ −5), so ties are not unique to signature 0 — but every such tie breaks
sharp-side to the conventional spelling (C♯ in G major; B♮ in F major via
its |LoF − s| win). The *behavior* the doc fixes (PC 6 → F♯ in C/a) holds;
the uniqueness claim does not survive the arithmetic. Flagged in REVIEW.md
rather than silently repaired.

## A6. Octave and pitch-name conventions

Scientific pitch notation, C4 = MIDI 60, octave number follows the
**letter**: `Cb4` is MIDI 59 (sounds B3), `B#3` is MIDI 60. Tuning pitch
strings (`"E2"`, `"F#3"`) accept single accidentals.

## A7. Reserved names

Slugs (grip ids, sequence names, tuning names): `[a-z0-9_-]`, ≤ 40 chars,
no consecutive underscores; `strip` and `adhoc` are reserved (render
filename prefixes). The built-in tuning name `standard` is immutable.

## A8. q4 arity at the freeze (floor-text tension — decided, flagged)

DESIGN §7.1's floor line reads "`q4` = stacks of 2–3 perfect fourths (3–4
notes)", but the membership criterion (§13: a quality enters the freeze
only if a Set A or B fixture requires it) and the fixtured Q context
ranking (`Bsus4/F#` at context #2) jointly exclude the 4-note row: it would
generate a root-position `F#`-rooted quartal candidate on Q that passes R0
in `e-minor` and lands at context #2 ahead of `Bsus4/F#`. The freeze floor
therefore carries the 3-note `q4` only; the 4-note stack remains an
*additive* table change (engine_version bump) whenever a fixture arrives
that wants it. Full argument: REVIEW.md.
