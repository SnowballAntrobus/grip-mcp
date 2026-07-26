# Milestone-0 Freeze-Gate Review

Status: **awaiting human review** — the table is at `table_version 0.1.0`
and freezes to `1.0.0` when this review closes. Per DESIGN §13, the gate
sequence was: table format + meta-test + reference script → floor
population → gate + oracle content check → **human review of non-tertian
rows** (this document) → freeze.

Everything below is either (a) a row the doc explicitly routes to the
human pass, (b) a decision the doc left open that I made and here submit,
or (c) a divergence between DESIGN §7.3's prose illustrations and strict
rule application — which the doc itself anticipates ("hand-application of
rules is 0-for-4; the script applies them"; fixture expectations are the
script's reviewed output, never hand derivations). Nothing was silently
repaired.

## 1. Gate status (mechanical, all green)

* Meta-test: 17 checks — row totality (every column on every row incl.
  dyads/`5`/`coll`), no memberless tiers, degrees-realize-tones, discount
  policy, families, parse-unambiguity of the full accepted suffix set,
  X5 exclusivity, `Gm3`/`AA4` stay rejected.
* music21 oracle: 35 checks — tone sets AND degree-stacked member
  spellings for all 14 tertian rows, plus sus2/sus4/7sus4 (m21 can
  express them; a bonus beyond the doc's tertian obligation). Agrees on
  every row, including `dim7`'s B𝄫.
* Fixture sets A and B: 31 fixtures, script-generated, regenerate
  byte-identical (`generate_fixtures.py --check`).
* Full suite: 796 passed, 17 skipped (single-PC random draws skipping the
  transposition-covariance case), no optional deps required.
* Membership criterion enforced by test: every table row is required by
  some fixture as top or root-at-bass shadow.

## 2. Non-tertian rows for the human pass (DESIGN §11)

The oracle cannot express these; the doc says they get "the harder human
pass at freeze." The only historical content bug lived here.

| row | tones | degrees | tier | discount | family | notes |
|---|---|---|---|---|---|---|
| `dym2`…`dyM7` (10) | {0,k}, k ∈ 1,2,3,4,5,6,8,9,10,11 | 1 + b2/2/b3/3/4/#4/b6/6/b7/7 | 1 | ∅ | `dy` | PC distance 6 = `A4` sharp-leaning (`#4`); no `dyP5` — distance 7 is `X5` only |
| `5` | {0,7} | 1, 5 | 1 | ∅ | `5` | inverted `X5/<bass>` for distance-5 inputs falls out of ordinary generation |
| `q4` | {0,5,10} | 1, 4, b7 | 5 | ∅ | `q4` | **3-note only** — see §4.1 below |
| `coll` | input set | (canonical per PC) | 6 | ∅ | `coll` | generated iff nothing covers; root at bass; zero missing |

Sus rows (`sus2`, `sus4`, `7sus4`) are non-tertian by the doc's R0
taxonomy but were mechanically oracled anyway (m21 agrees on all three);
glance at them if you like: {0,2,7}/1,2,5 · {0,5,7}/1,4,5 ·
{0,5,7,10}/1,4,5,b7, all discount {7}, all family `sus`.

## 3. Open-question decisions submitted for ratification

1. **Dyad token encoding (open question 2):** `dy` + token verbatim,
   case-sensitive — `Gdym3` vs `GdyM3`. Parse-unambiguous (meta-tested);
   interval-token case was already load-bearing. APPENDIX A1.1.
2. **Quality-order column (tie-break):** within tiers — dyads by interval
   size then `5`; **maj before m** before dim before aug; sevenths
   7, maj7, m7, m7b5, dim7, mMaj7; tier 4 exactly in the doc's R3
   parenthetical order (sus2, sus4, 7sus4, add9, madd9, 6, m6 — which
   pins the fixtured Bsus2 < Bsus4 tie-break). One flip to argue: the
   doc's B5/F♯ prose lists `Bm` before `B`, implying m-first at the
   bare-fifth shadow tie; I chose conventional maj-first. One integer
   swap + fixture regeneration if you want m-first.
3. **Family column (beyond the doc's fixed `sus` and `m` examples):**
   `maj` {maj, maj7, 6} · `m` {m, m7, m6, mMaj7, madd9} · `dim`
   {dim, dim7, m7b5} · `aug` · `7` {7} · `add` {add9} · `dy` · `5` ·
   `q4` · `coll`. Consequences: `"Bdim"` on a grip with only Bm7♭5
   resolves to it at tier 3; `"Cmaj"` with both C and Cmaj7 present is an
   instructive ambiguity error; `"C7"` never falls through to 7sus4
   (7sus4's single family slot went to `sus`, which the Bsus fixture
   requires).
4. **Tie-break "root letter" = alphabetical** (A < B < … < G), pinned by
   the fixtured Q ordering (Bsus4/F# above Esus2/F#); root-PC ascending
   as an unreachable determinism backstop. APPENDIX A4.
5. **`context_key` tonic set:** single accidentals only in V1 (A3).

## 4. Doc-vs-script divergences (the reason this gate exists)

### 4.1 q4 arity (floor text vs membership criterion) — **decision needed**

§7.1's floor says "stacks of 2–3 perfect fourths (3–4 notes)"; the freeze
carries the 3-note row only. Two independent grounds: (a) no Set A/B
fixture requires the 4-note stack (§13's membership criterion); (b) the
4-note row would cover Q's {F♯,B,E} with one missing tone as a
*root-position* F♯-rooted candidate that **passes R0 in e-minor** and
lands at context #2 — displacing the fixtured `Bsus4/F#` #2 that §7.3
documents. The 4-note stack also stays fully covered meanwhile (it reads
as a 7sus4 inversion). Adding it later is an additive change
(engine_version bump) that arrives with its own fixture. APPENDIX A8.

### 4.2 B5/F♯ enumeration (§7.3)

Prose: dyad → F#sus4 → B5/F# (third) → Bm → Bsus2 → also B, Bsus4.
Script: `F#dyP4, F#sus4, F#q4, F#7sus4, B5/F#, B/F#, Bm/F#, Bsus2/F#,
Bsus4/F#, …` — R1 puts the whole root-at-bass class (including the
F#q4 and F#7sus4 shadows the prose omitted) above every inversion, so
B5/F# sits **fifth**. The chosen argument gets *stronger*. Same class of
omission as v0.5's missed F♯sus4.

### 4.3 Triads-vs-sus shadow order (§7.3, both B5 fixtures)

Prose lists Bsus2/Bsus4 before Bm/B; R3 (triads < add/sus) puts the
triad shadows first once R2 ties. Script order after `B5`:
`B, Bm, Bsus2, Bsus4, …`. The prose's own named tie-break claim
(Bsus2 vs Bsus4 by quality-order) survives intact.

### 4.4 Q fragment order (§7.3)

Prose parenthesis: (Eadd9, Emadd9, B7sus4). All three tie at R2 (one
non-discounted miss) in tier 4; the alphabetical letter tie-break puts
`B7sus4/F#` before the two E-rooted readings:
`…, B7sus4/F#, Eadd9/F#, Emadd9/F#`. The documented passer set and
context #2 in e-minor are unaffected (script reproduces §7.3's context
claims exactly).

### 4.5 {B, D♯} in e-minor: decided_at is R2, not R0 (§7.3)

The doc admits V **and V7** "purely by quality + degree" — so B7
(−F♯, −A) passes R0 alongside the B triad and becomes #2. #1 vs #2 then
separate at R2, and `decided_at` = "R2", not the prose's "R0". The
substantive claims survive: the dyad *is* the first R0 failure, B (−F♯)
*is* the top, exactly two candidates pass. If you want this fixture to be
the first R0-*decided* one as the prose says, the admit set would have to
drop V7 — which §7.2 forbids. Prose slip, not a rule problem.

### 4.6 Line-of-fifths tie uniqueness (§5.2.1)

"The exact tie exists only at signature 0 … no other key can tie" is not
true of `|LoF − signature|`: every signature has one tritone-related pair
at distance 6 (G major: C♯ +7 vs D♭ −5). All such ties break sharp-side
to the conventional spelling, and the fixed behavior (PC 6 → F♯ in C/a)
holds, so nothing observable changes — but the uniqueness *claim* should
be amended in the next doc revision. APPENDIX A5.

### 4.7 Reference-engine output shape

`identify()`'s result carries §7.4's fields plus `root_is_bass` /
`root_sounds` / `r0_pass` (used by tests and the membership check) and
`mode` ("context-free" | "context" — §7.5's "responses label which
ranking they carry"). This is the *reference* shape; the V1 MCP response
envelope (project, stored, warnings) is a separate, later artifact.

## 5. What closing this review does

* `table_version` → `1.0.0` (freeze commit; both fixture sets regenerate
  under it byte-identically).
* Any flip you order here (quality-order, families, q4 arity) is a table
  edit + `generate_fixtures.py` + suite run — all consequences are
  mechanical from this point on.
* Milestone 0 exits; V1 per DESIGN §6 begins on a frozen table.
