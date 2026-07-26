# grip-mcp — Design Document

Status: v1.0 — Accepted for implementation · Date: 2026-07-25 Working title: `grip-mcp`

Revision notes (v0.10 → v1.0, from twelfth and final review): `chosen` resolution rebuilt as three tiers (exact canonical → root-PC + exact quality row → root-PC + family), making the `Bsus4`/`Bsus` fixture pair a specification rather than a contradiction, with the reference grammar (accepted suffixes = quality names ∪ family names; Unicode-accidental normalization; PC-resolved slash bass) filed in the appendix; decision 38 amended to match `default_tuning` (which gains call-time resolution semantics, lifecycle-reference status, and its setter tool `update_project_defaults`); fresh-project reads defined (absent files = empty library, mirroring expected-absent writes); the `Cdim/Gb` divergence test named; the Phase-2b tension warning honestly scoped; the `opens_fretted` field/code reconciliation. This version is additionally self-contained: the v0.8–v0.10 "unchanged from vX" compressions are re-inlined, so an implementer needs no prior draft.

## 1. Motivation and the load-bearing idea

Composing on guitar is grip-first: shapes are found by hand, and their theoretical identity comes second, negotiated in context — the same fretting can be B5sus4/F♯ or a quartal voicing depending on what surrounds it. Existing tools invert this (name-first, GUI-bound) and interrupt a conversational workflow.

`grip-mcp` is an MCP server that gives an LLM a deterministic fretboard engine — identify, library, render — with the conversation as the control surface. The product is a shared vocabulary that persists across sessions. `chosen` is the mechanism: once the musician says "that's my Gm," every future conversation speaks their names instead of re-litigating theory. Identify and render exist in service of that vocabulary; capture, resume, and presentation are therefore first-class design surfaces (§6).

The server explicitly targets experimental and alternative-tuning players — the population least served by name-first tools, because in DADGAD or open C their shapes have no standard names; grip-first capture and personal vocabulary are not conveniences there but the only workable model. The tuning-agnostic data model is the foundation; §9's Phases 2b and 5 build the workflow.

Division of labor: the server is opinionated but fully specified — every ordering follows documented, deterministic rules (§7), never tuned weights — and reports where each ordering was decided (`decided_at`) rather than asserting confidence. The LLM supplies taste, chooses among candidates, and persists the choice. The server ranks by published rules; the LLM decides and records. The context-free top answer is the most literal complete reading, not the most musically suggestive one (§7.3); promotion is the LLM's job.

Second server in a planned ecosystem (first: `cdp-mcp` for sound transformation).

## 2. Goals and non-goals

V1 goals: (1) identify — fret positions → ranked candidates, total over inputs with ≥ 2 distinct pitch classes, fully specified spelling; (2) library with first-class chosen readings; (3) sequences; (4) inline rendering; (5) tuning-agnostic model incl. capo derivations and `default_tuning`; (6) the highest-frequency flows — capture with a user name, resume — cost one successful call in their common case.

Non-goals for V1: voicing search, key/scale overlays, voice-leading analysis, playability scoring, audio/MIDI export, tab, rhythm, foreign-bass slash candidates, live-performance turn economics (compose-and-reflect is the workflow; chat speed is correct for it).

## 3. Ecosystem architecture

Filesystem federation (chosen over a shared framework — premature — and full independence — loses cross-tool workflows): independent servers plus a shared convention, files as the interchange bus.

`MUSIC_PROJECT_ROOT` env var (default `~/music_projects/`); each server exposes `set_project(name)`, owns a namespaced subdirectory, and never writes outside it except the shared `exports/`:

```
~/music_projects/gm-em-song/
  grip/
    library.json        # source of truth: grips, sequences, tunings, chosen, default_tuning
    derived.json        # caches (gitignored, regenerable, atomic writes)
    .gitignore          # written at first write; contains "derived.json"
    renders/            # PNG + SVG (user's git policy)
  cdp/
  exports/              # cross-tool bus: .mid, .wav, .musicxml
```

Tunings live only in `grip/library.json`; no `project.json` until a second server needs shared metadata. `exports/` filenames: `<server>__<name>__<hash8>.<ext>` — `__` is the separator, hence slugs forbid consecutive underscores. Every tool response carries `{ "project": … }` for drift visibility. cdp-mcp should adopt `set_project` (aliasing `set_session`) and the envelope field in its next minor release, with a `MUSIC_MCP_CONVENTIONS.md`. Extract `music-mcp-common` only when a third server makes duplication obvious.

## 4. Stack

* Python ≥ 3.11, cdp-mcp-style packaging (`pyproject.toml`, `uv`, entry point `grip-mcp`), official `mcp` SDK, stdio transport.
* Theory core: dependency-free interval-table code over MIDI numbers, driven by the Milestone-0 quality table.
* music21 (BSD): optional dependency group `grip-mcp[m21]` — test oracle and Phase-3 spikes only; promoted to core in Phase 3. Stated bet: dependency weight deferred for Phase-3 option value (Roman numerals, MusicXML, MIDI). Checkpoint: if Phase 2 ships and Phase 3 slips two milestones, revisit.
* Rendering: hand-built SVG → PNG via `resvg` bindings (prebuilt binary wheels; the operative claim is no native install step; checklist: verify Windows and macOS arm64 wheel coverage before freezing — the contingency is a parallel direct-draw renderer sharing the layout code, a real second renderer, which is why the check comes first). One bundled OFL font; all text lays out against its metrics; on-disk SVGs carry labels as glyph paths so the vector deliverable survives machines without the font.
* No subprocesses, no network.

## 5. Data model

### 5.1 Grip, library, slugs, lifecycle

```jsonc
// library.json (source of truth; human-editable; git-friendly)
{
  "schema_version": 1,
  "default_tuning": "standard",
  "tunings": {
    "standard": ["E2", "A2", "D3", "G3", "B3", "E4"],
    "standard-capo3": { "from": "standard", "capo": 3 }
  },
  "grips": {
    "gm-1": {
      "label": "Gm first inversion",
      "tuning": "standard",                       // always concrete — see default_tuning rules
      "strings": [null, null, 8, 7, 8, null],     // low→high; null=muted, 0=open, n=fret
      "fingers": [null, null, 2, 1, 3, null],
      "tags": ["intro"],
      "chosen": "Gm/Bb",                           // canonical candidate name
      "created": "2026-07-25T00:00:00Z"
      // optional: "derived_from": {"id": "...", "semitones": n}
    }
  },
  "sequences": { "intro": ["gm-o", "pass", "gm-1", "b5"] }
}
```

```jsonc
// derived.json (gitignored; regenerated freely; atomic temp+rename writes —
// concurrent regeneration is content-identical given same inputs+engine)
{
  "schema_version": 1,
  "engine_version": "1.0.0",
  "grips": {
    "gm-1": {
      "input_hash": "…",   // hash(strings, RESOLVED tuning pitches, engine_version)
      "midi": [46, 50, 55],
      "candidates": [ /* FULL context-free set; truncation is response-shaping only */ ]
    }
  }
}
```

Slug rule (grip ids, sequence names, tuning names): `[a-z0-9_-]`, ≤ 40 chars, no consecutive underscores; reserved: `strip`, `adhoc` (render filename prefixes). Display names live in `label`, free-form Unicode.

Grip rules: `strings` length = resolved tuning length (string count is a property of the tuning; 7/8-string, bass, ukulele all representable). `fingers`: `null` on muted/open strings; on fretted strings `null` = unspecified, `0` = thumb, `1–4` = index→pinky; contiguous same-finger-same-fret runs render as barres in all label modes. Sequences may repeat ids and may mix tunings (strips render per-grip: own string count, own capo badge). `remove_grip` refuses while referenced by a sequence unless `force`, counting any occurrence; `rename_grip` rewrites all occurrences atomically. `update_grip`: shallow merge; explicit `null` deletes optional fields; rejects `id` and `created` in the patch; merged result re-validated as a complete grip; caches re-derived; newly-staled `chosen` surfaced immediately with the new top candidate.

`default_tuning`: applied by capture tools (`identify`, `add_grip`, `transpose` raw form) when `tuning` is omitted; resolution happens at call time and the resolved concrete name is stored on the grip — grips never reference the default implicitly (otherwise editing it would retroactively reinterpret every grip captured under it: the v0.1 tuning-cache hole reborn one level up). Envelopes echo the resolved tuning so the LLM never guesses. Set via `update_project_defaults(default_tuning)` (§6) or hand edit. The default is a lifecycle reference: `remove_tuning` refuses while a tuning is the `default_tuning`; a hand edit that dangles it gets the same flag-and-instructive-error treatment as dangling grip references.

`chosen` — storage: the stored value is always a canonical name (§5.2 grammar). Stale values (engine upgrades that no longer produce the name) are flagged `"stale": true`, never silently discarded; name-grammar changes ship load-time migration mappings rather than relying on staleness.

`chosen` — resolution (shared by `add_grip` and `set_reading`), three tiers: input is Unicode-normalized (`♯`→`#`, `♭`→`b`) then parsed as root (+ optional suffix + optional `/bass`); root and bass resolve by pitch class, so `"F#m"`, `"Gbm"`, and `"Gm/A#"` all resolve (input spelling never survives into storage — the sole spelling-preserving surface in the system is `context_key`). Resolution against the full candidate set:

1. Exact canonical match.
2. Root-PC + exact quality row (suffix names a specific table quality): `"Bsus4"` on Q → the one B-rooted `sus4` candidate → normalizes to `Bsus4/F#`. A supplied `/bass` filters by bass PC.
3. Root-PC + family (suffix names a family): `"Bsus"` on Q → both `Bsus4/F#` and `B7sus4` carry family `sus` → ambiguity error listing both; `"Gm"` on gm-1 → unique `m`-row hit → `Gm/Bb`.

A unique selection at any tier normalizes and stores; multiple matches error with the candidates; no match is a miss (partial success — see §6.1). The accepted suffix set — quality names ∪ family names — is the reference grammar, an appendix artifact alongside the tier rule; the twelfth review showed the v0.10 two-tier rule contradicted its own worked example (`"Bsus4"` fell to family matching and ambiguated), which is exactly the class of drift the appendix + meta-test exist to catch.

Tuning lifecycle: the built-in `standard` is immutable. `define_tuning(name, pitches? | from?+capo?)` refuses to redefine any name referenced by grips or by `default_tuning`; `from`-chains nest, resolved recursively with cycle detection at definition and load; `remove_tuning` refuses while referenced. Hand edits that dangle a reference: load succeeds flagged; `describe_workspace` reports it; tools touching affected grips error instructively. Capo frets are capo-relative (absolute pitch = open + capo + fret); renders badge "capo N".

Deferred creation, both directions: no files or directories exist until the first write, which creates `grip/`, `.gitignore`, `library.json`, and `derived.json` in one consistent step, and the pre-write integrity check treats absent-file as expected-absent, not conflict. Reads mirror it: a project with no files on disk reads as an empty library (no grips or sequences; tunings table containing `standard`; `default_tuning: "standard"`), never as an error.

### 5.2 Enharmonic spelling and the canonical name grammar

Ground truth is MIDI numbers; spelling belongs to interpretations:

1. Roots: canonical table `C, Db, D, Eb, E, F, F#, G, Ab, A, Bb, B`. Under `context_key`, roots respell as the key spells them (line-of-fifths proximity for chromatic roots; the exact tie exists only at signature 0 — PC 6 in C/a — and breaks sharp-side; no other key can tie).
2. Members: strict interval stacking from the respelled root (the chain that makes `c#-major` and `db-major` differ end-to-end). Doubles admitted: grammar `bb`/`##`, renders `𝄫`/`𝄪` where glyphs exist. `coll` — the one quality with no interval structure — spells members per the canonical root table applied to each PC.
3. Display spelling for a grip follows `chosen` if set, else the top-ranked candidate; the sharps fallback is reachable only for inputs with < 2 distinct pitch classes.
4. Name grammar: ASCII, versioned, parse-unambiguous; accidentals `b`/`#`/`bb`/`##`; quality suffixes from the frozen table; slash bass `/Bb`. Dyad and `coll` suffixes must be unambiguous under the grammar's parse (`Gm3`, `AA4` are not); the dyad interval-token set is fixed — `m2 M2 m3 M3 P4 A4 m6 M6 m7 M7` — with only the casing/encoding open (question 2). Working proposal: `dy` + token (`Gdym3`), `coll` literal (`F#coll`).
5. `context_key` grammar: `<tonic>-<mode>`, lowercase, full enharmonic tonic set (`c#-major` ≠ `db-major`); modes `major` | `minor` (natural-minor basis for R0).
6. Transposition-covariance tests assert on pitch classes mod 12, never spellings.

## 6. MCP tool surface and interaction design (V1)

Tools: `list_projects` · `set_project` · `update_project_defaults` · `describe_workspace` · `identify` · `add_grip` · `get_grip` / `list_grips` · `update_grip` · `rename_grip` · `remove_grip` · `set_reading` · `transpose` · `set_sequence` / `list_sequences` / `remove_sequence` · `render(ids? | sequence?)` · `define_tuning` / `remove_tuning`.

Response envelope: every response carries `{ "project": … }`; every mutating response additionally carries `stored: true|false` and `warnings: [{code, detail}]` — codes include `chosen_miss`, `render_failed`, `chosen_staled`, `opens_fretted` (whose `detail` carries the count, reconciling the v0.9 field with the v0.10 code) — so the LLM distinguishes partial successes without parsing English.

### 6.1 Capture

* `add_grip(id, strings, tuning?, fingers?, label?, tags?, chosen?, render=true)` — one call in the common case, specified to succeed in it: `chosen` resolves per §5.1's three tiers ("add my Gm shape, x x 8 7 8 x, call it Gm" stores `chosen: "Gm/Bb"`); atomicity in both directions — a `chosen` miss is partial success (grip stores, `chosen_miss` warning with suggestions; repair is a follow-up `set_reading`, never a re-send), and a render failure is partial success (`render_failed`; the direct-draw contingency makes this a real path). The response prominently echoes resolved pitches low→high plus the top reading — the self-check for the one error structured validation can't catch, a reversed string array — and the default-on diagram is the primary verification channel (a shape-reader confirms a chart in half a second; the pitch echo catches octave/tuning errors diagrams can't).
* `identify(strings, tuning?, context_key?, render=false)` — preview without storing; replaces the deleted `render_adhoc`. `interval_root: "auto"` resolves against the ranking computed in that call (contextual if `context_key` was passed), not the cached context-free top — the same grip may legitimately render differently by route, deliberately.
* `transpose(id?, strings?+tuning?, semitones, save_as?, render?)` — exactly-one-of named parameters (`id` xor `strings`; with raw `strings`, `tuning` resolves via `default_tuning` when omitted — amending decision 38, which previously said "required" and contradicted §5.1). `fingers` carry verbatim for closed shapes (same hand, new position); previously-open now-fretted strings get `null` fingers and the `opens_fretted` warning (correct pitches, changed hand shape — one integer prevents confidently emitting a hand-impossible grip as "the same chord up 4"). Below-fret-0 errors instructively, in capo-relative terms ("would fall below the capo") on capo-derived tunings. On `save_as`: `chosen` transposes covariantly by re-derivation — the covariance property guarantees the transposed candidate exists, so the implementation looks up that candidate and takes its canonical name, never transforming the old string (naive respelling diverges from member-stacking spelling — see the `Cdim/Gb` test, §11); `derived_from` provenance records.

The name→shape bridge (a stated design property): V1 cannot compute "show me a standard Gm barre," but the LLM proposes shapes from its own knowledge and the echo-back + identify loop verifies them — LLM shape-hallucination converted into a checked operation, an adequate bridge until Phase 2a's `find_voicings`.

### 6.2 Sessions

* The fork trap is closed mechanically: `set_project(name, create=false)` refuses to create by default, listing close-match existing projects in the refusal; creation requires explicit `create: true` (whose description instructs LLM-side user confirmation — belt, not suspenders); directories defer to first write, so even a confirmed switch litters nothing.
* `list_projects` scans `MUSIC_PROJECT_ROOT` ecosystem-wide (the user's mental model is "my projects," not "my grip projects"), reporting `grips: 0` for projects without a `grip/` namespace and skipping malformed entries with a warning rather than crashing.
* `update_project_defaults(default_tuning)` — single-field for V1, growing only if needed; validates the tuning exists; standard envelope.
* `describe_workspace` inlines, below a size threshold (≤ 64 grips, question 4): the grip list (ids, labels, `chosen` with stale flags, tags), the sequences, and the tunings table incl. `default_tuning` and any dangling-reference flags — session resume is one call and the LLM speaks the user's vocabulary from its first reply. Above threshold: counts + a prompt to `list_grips`.

### 6.3 The presentation contract

All of §7's rigor produces output the musician never sees — the client LLM mediates, and left uninstructed it will parrot "that's a minor-third dyad" at someone who just played their Gm. MCP tool descriptions and the server-level `instructions` field are first-class, versioned, reviewed design artifacts (a `descriptions/` module) encoding: the top candidate is the most literal reading, not "the answer" — present it alongside contextual readings and, above all, the user's stored `chosen` names, leading with the user's name when a grip matches the library; `decided_at` calibration (tie-break ≈ maximally ambiguous, unique ≈ no contest); the name→shape bridge; created-vs-opened confirmation; the bulk-capture idiom (batch adds pass `render: false` per grip and finish with one strip render). The description-contract test is honestly scoped: a keyword check that catches deleted text, not ignored text.

Closing doctrine, with the `create` gate as the worked example: wherever a description asks the LLM to do the right thing, first check whether the API can make the wrong thing impossible.

### 6.4 Render mechanics

Options: `orientation` (`"chart"` default / `"neck"`), `labels` (`"notes"`/`"intervals"`/`"fingers"`/`"none"`), `interval_root` (pitch or `"auto"` = chosen's root, else top candidate's), `columns`, `title`, `fret_window` (auto), `theme`. Render hash ≠ identity hash: covers resolved grips including fingers, every option, and the renderer version (the identity hash excludes fingers — correct for identification, disqualifying for renders). Filenames `<prefix>__<renderhash8>` with prefix = grip id | sequence name | `strip` | `adhoc`; identical requests overwrite idempotently; no GC in V1 (documented). Inline copies ≤ 1200 px wide; full resolution on disk. `truncated: n` = candidates omitted from the response. Errors everywhere are structured and instructive (both lengths on mismatch, closest-match suggestions on unknown names) — the primary caller is an LLM that self-corrects given a good message.

## 7. The identify pipeline

### 7.1 Candidate generation — specified and total over ≥ 2 distinct PCs

Fretted strings map through the resolved tuning to MIDI (octaves preserved; the bass matters). Input contract by distinct-PC count: 0 → error; exactly 1 (any string count — {E2, E4}, an all-unison strum) → pitch report with the doubling noted, no candidates; ≥ 2 → full generation:

* Search space: all 12 root PCs (non-sounding roots included — that is what makes rootless fragments exist) × the frozen quality table. Floor: interval dyads; `5`; maj/min/dim/aug; `sus2`/`sus4`; `6`/`m6`; `7`/`maj7`/`m7`/`m7b5`/`dim7`/`mMaj7`/`7sus4`; `add9`/`madd9`; `q4` = stacks of 2–3 perfect fourths (3–4 notes).
* Exact PC cover: sounding PCs ⊆ chord tones; missing tones assumable, foreign tones never. Foreign-bass slash chords: Phase 3.
* Dyads: one interval-dyad candidate rooted at the bass, named by simple PC interval (PC distance 6 = `A4`, sharp-leaning; registral spread lives in `midi` and the `reading`); PC distance 7 generates only `X5`; distance 5 additionally generates the inverted-fifth `X5/<bass>`; no other inverted orientations.
* Dedup rule: duplicates iff same root and same chord-tone set; table rows beat special-case generators. Cross-root PC-set coincidences are deliberately kept and R1-sorted — C6/Am7, Cm6/Am7♭5, dim7/aug rotations, sus2/sus4 rotation, Q's three-way sus2/sus4/q4 — the relative-ambiguity case handled correctly by construction; do not "fix" these. Meta-test: no input yields two same-root same-set candidates.
* Totality catch-all: iff no table quality covers the set, `coll` (root at bass, zero missing) generates at the bottom of R3 — it exists only when nothing else does, so it can never outrank a table reading (the Freddie Green shell {G, B, F} is covered by `G7` and generates no `coll`).
* Truncation: the full set is computed and cached; responses return the top 8 + `truncated`.

### 7.2 Ranking: strict lexicographic, no weights

* R0 (only with `context_key`): binary diatonic membership over the candidate's complete chord-tone set — sounding and assumed. Tertian: root on a scale degree, quality matching that degree's diatonic quality; minor keys use natural minor plus the raised-leading-tone V major triad and V7, admitted purely by quality + degree — no "confirmed" predicate; the consequence that a bare 5̂+7̂ dyad's V-triad shadow passes R0 is accepted as correct (it is the dominant gesture) and fixtured. Non-tertian: all chord tones diatonic and root on a scale degree.
* R1: root-is-bass readings above inversions.
* R2 (tuple, lexicographic): (1) root assumed missing?; (2) missing tones minus the row's discounted set — per-row table data, default {perfect fifth above the root}, dim and aug discount nothing (their altered fifths are defining; consequence, fixtured: `Xm` (−P5) beats `Xdim` (−d5) at R2.2); (3) total missing.
* R3: dyad/`5` < triads < sevenths < add/sus/sixth (`sus2, sus4, 7sus4, add9, madd9, 6, m6`) < `q4` < `coll`; every row carries a tier; no memberless tiers.
* Tie-break: root letter, then the table's quality-order column.

`decided_at`: `"R0" | "R1" | "R2" | "R3" | "tiebreak" | "unique"` — the rung at which #1 separated from #2, asserted without certainty language; the LLM interprets.

### 7.3 Worked consequences — illustrations checked against the reference script

Shadow rule (making enumeration mechanical): every dyad {X, X+k} casts root-at-bass shadows — table qualities rooted at X whose tone set contains X+k — sitting between the complete dyad and the inversion class. Exemplary: {X, X+5} → Xsus4 (−5); {X, X+3} → Xm (−5) plus the k=3 family (m7/m6/mMaj7/dim); {X, X+2} → Xsus2 (−5) plus add9/madd9. The rule's definition is complete; lists are illustrations. (History that motivates the reference script: v0.3 missed Esus2; v0.4 never derived B5/F♯; v0.5 derived it and missed F♯sus4; v0.6's context claim miscomputed a diatonic set. Hand-application of rules is 0-for-4; the script applies them.)

* Gm-O ({G, B♭}, bass G): `m3` dyad → `Gm` (−D) → fragments · decided_at R2.
* PASS ({A, B♭}, bass A — minor second; the grip sounds a compound minor ninth, stated in the `reading` though the name is `m2`): dyad tops; rivals are inversion-class or rootless · decided_at R1 (no floor quality rooted at A contains B♭).
* B5/F♯ ({F♯, B}): `P4` dyad → `F#sus4` (−C♯) → `B5/F#` → `Bm` (−D) → `Bsus2` (−C♯) → also `B` (−D♯), `Bsus4` (−E) → fragments · decided_at R2. The conversation's own name is the third candidate — the canonical argument for `chosen`.
* B5 ({B, F♯}, root position): `B5` over shadows `Bsus2` (−C♯), `Bsus4` (−E), `Bm` (−D), `B` (−D♯) · decided_at R2 — and `Bsus2` vs `Bsus4` tie through R2 and R3 with the same root: the first fixture exercising the quality-order tie-break column directly.
* Q ({F♯, B, E}, bass F♯): context-free `F#q4` → `F#7sus4` (−C♯) → `Bsus4/F#` → `Esus2/F#` → fragments (`Eadd9` −G♯, `Emadd9` −G, `B7sus4` −A) · decided_at R2. Under `e-minor` (E–F♯–G–A–B–C–D): C♯ is chromatic, so `F#7sus4` fails R0 alongside `Eadd9`; passers are `F#q4`, `Bsus4/F#`, `Esus2/F#`, `Emadd9/F#`, `B7sus4/F#`; top unchanged, context #2 `Bsus4/F#` · context decided_at R1. The dominant-function hearing is the LLM's to promote.
* {B, D♯} in `e-minor`: context-free, `M3` dyad over `B` (−F♯) at R2.3 · decided_at R2. In context the dyad fails R0 (D♯ chromatic, non-tertian) while `B` (−F♯) passes as the admitted V triad · top `B` (−F♯), decided_at R0 — the first R0-decided and first R0-failure fixture.
* Freddie Green shell ({G, B, F}): `G7` tops, `coll` suppressed; the rung floats with the frozen table version (a 9th/13th addition would end its uniqueness), asserted by the script, not prose.

### 7.4 Output / 7.5 Cache

Per candidate: `name`, `root`, `quality`, `bass`, `inversion` (semantics per table row; `null` for `q4`/`coll`/dyads), `intervals_from_root`, `missing`, spelled `pitches`, one-line `reading`; per response: `decided_at`, `truncated`. `derived.json` holds the full context-free set and its `decided_at`; `context_key` results are computed on demand, never cached, and responses label which ranking they carry; `set_reading` and `chosen` resolution run against the cached full set.

## 8. Rendering design

One SVG template, two orientations; chart default (nut bar when the window includes fret 0, X/O markers above strings, position numeral, finger dots, labels beneath). Fret window: from fretted notes only (min 4-fret window); open strings always draw as O markers regardless of window; all-open grips fall back to window 1–4 with the nut. Barres draw in all label modes. Text: fixed label band against the bundled font's real metrics; over-long names truncate with ellipsis in the image, full name in the response text; on-disk SVGs carry glyph paths; double-accidental glyphs per §5.2. Mixed-tuning strips render per-grip. Deterministic output: bundled font, fixed palette + `theme`, no embedded timestamps.

## 9. Roadmap

* Phase 2a — search & overlays: `find_voicings(chord, key?, near_fret?, tuning, constraints)` with a playability model (span ≤ 4–5 frets, ≤ 4 fretted notes + opens, barre detection, thumb-over) — retiring the name→shape bridge; `render_neck(overlay=key|scale|pitch_set, range)`. Tuning-parameterized from day one.
* Phase 2b — instrument-tuning workflow (independent of 2a; ship in either order): `set_instrument_tuning(name)` — the project-scoped declaration (question 5's lean) superseding bare `default_tuning` with history; `retune_plan(from, to)` — per-string semitone deltas with direction and suggested order, warning on large deltas by direction + magnitude heuristics only (per-string-set accuracy would need gauge data the model doesn't have — tuning a plain G up a fourth may be a broken string, but the server can't know the string is plain; it can say "up 5 semitones is aggressive"); rendered tuning cards via the strip machinery. Arithmetic plus rendering — a phase, not a milestone.
* Phase 3 — analysis: `analyze(sequence)` — Roman numerals in candidate keys, bass-line extraction, common tones, voice-leading distance (per-voice semitone motion with crossing penalties), modulation detection; foreign-bass slash candidates; music21 promoted to core.
* Phase 4 — interop: sequence → MIDI/MusicXML into `exports/`; audio (Karplus–Strong / FluidSynth) → WAV for cdp-mcp; possible tab export.
* Phase 5 — tuning recommendation (consumes 2a's playability and 3's analysis): `suggest_tunings(...)` over explicit objectives — open-string membership in a target key (drones), minimized fretting difficulty for an existing sequence (re-voice the user's own song; vocabulary and `derived_from` make it tractable), retune distance from the declared tuning (2b's deltas as cost) — returning ranked tunings each with a `retune_plan` and re-voiced previews. Deliberately late: every ingredient must exist for recommendations to beat trivia.
* Someday: rhythm on sequences, deeper capo semantics, left-handed rendering.

## 10. State, concurrency, security

Reads are always fresh (content hash authoritative; mtime stat only as a cheap pre-check); fresh-project reads = empty library (§5.1). The pre-write hash check guarantees file integrity and catches external modification within a call's read-to-write window; it does not prevent semantic last-writer-wins across windows — an accepted, stated V1 posture, mitigated by freshness. Writes atomic (temp + rename) with `.bak`, for `derived.json` too; first write bootstraps all four artifacts in one consistent step with absent-as-expected semantics. `schema_version` in both files; load-time migrations incl. name-grammar and `context_key`-grammar mappings. Writes confined to `grip/` (+ `exports/` in Phase 4), resolve-then-verify path scoping; JSON-schema validation before touching state; no subprocesses, no network.

## 11. Testing

* Reference derivation script: standalone, sharing only the quality table with the implementation; computes candidate sets, rankings, diatonic sets, R0 verdicts, and context-mode rankings — all fixture expectations are its reviewed output, never hand derivations. Every error class found across twelve reviews has a mechanical check; reviews can only argue with decisions.
* Table content checks: m21 oracle validates tertian rows' tone sets mechanically; non-tertian rows (where the only content bug lived) get the harder human pass at freeze.
* Table-totality meta-test: every row — including special-case-generated dyads, `5`, `coll` — has: R3 tier, name production, spelling rule, inversion semantics, tie-break position, R2 discounted set, family; no memberless tiers; dedup holds over random inputs.
* Theory tests: Sets A and B with script-generated expectations — A: Gm-O, PASS, Gm-1, B5, G-dy, B5/F♯ (with the F♯sus4 shadow), Q (context ripple included), thumb-B5, {B, D♯}-in-`e-minor`; B: open-position folk chords, the {G, B, F} shell (top = G7, `coll` suppressed, rung script-asserted), drop-2 voicings, a DADGAD fixture, the `Xm`-vs-`Xdim` discount ordering, the B5 same-root tie-break. Property tests: transposition covariance (PCs mod 12), tuning covariance, ranking stability, totality over random sets including doubled-PC and single-PC-multi-string inputs, shadow presence.
* Resolution tests: three-tier `chosen` (exact; `"Bsus4"`-on-Q unique at tier 2; `"Bsus"`-on-Q ambiguous at tier 3; enharmonic inputs `"F#m"`/`"Gbm"`/`"Gm/A#"`; miss → partial success); covariant re-derivation incl. the named divergence case — `Cdim/Gb`, where member stacking spells the bass G♭ but the root table spells PC 6 F♯, separating re-derivation from naive respelling.
* Interaction tests: create-gate (typo slug → refusal with close matches, nothing on disk); first-write bootstrap; fresh-project empty reads; `default_tuning` resolution + envelope echo + lifecycle refusals; envelope warning codes each observable; `transpose` fields (fingers carry, `opens_fretted` detail count, capo-relative errors, omitted-`tuning` default resolution); render-failure partial success; resume completeness (sequences, tunings, stale flags inline); `list_projects` foreign/malformed entries; `strip`/`adhoc` reservations; description-contract keyword check.
* Render tests: normalized-SVG goldens; rasterization smoke; render-hash distinctness across options.
* Acceptance test: `set_project(create=true)` → empty-read → `add_grip` × Set A (one with `chosen`, one bulk with `render: false`) → `set_sequence` → `render(sequence)` → `identify(Q, context_key="e-minor", render=true)` → `set_reading` (valid, ambiguous, miss) → `transpose(save_as)` with covariant `chosen` → external-edit simulation. No optional deps; unconditional CI.

## 12. Resolved decisions (ledger)

Decisions 1–48 stand as accumulated (chart default; slugs + reserved names; capo-relative frets; no `project.json`; lexicographic ranking with per-row R2 discounts; flat-side root table with the signature-0 tie; music21 optional; context-free cache; `decided_at`; conditional `coll`; bass-rooted dyads with the P4 exception; member doubles; distinct-PC totality; total R3 tiers; `A4` naming and `X5` exclusivity; full-set `set_reading`; render-hash independence; script-generated fixtures; shadow rule; complete-set R0; dedup with kept coincidences; q4 arity; parse-unambiguous dyad/`coll` names; the data appendix; mechanical V exemption; script-computed R0; one-call capture with render-by-default; `render_adhoc` deleted; mechanical create gate; `transpose` semantics; exactly-one-of house pattern (with `render(ids?|sequence?)` listed as conforming); resume completeness; versioned descriptions; the name→shape bridge; resolve-and-normalize `chosen`; capture atomicity; family as a table column; enharmonic inputs by construction; covariant re-derivation; `default_tuning` in V1; the warnings envelope; ecosystem-wide `list_projects`; tunings as product target). New in v1.0:

49. `chosen` resolution is three-tier (exact → quality row → family), with the reference grammar (quality ∪ family suffixes, Unicode normalization, PC-resolved slash bass) frozen in the appendix.
50. Decision 38 amended: `tuning` with raw `strings` resolves via `default_tuning` when omitted; envelopes echo the resolution.
51. `update_project_defaults` exists, single-field, validating and lifecycle-aware.
52. `default_tuning` resolves at call time; grips store concrete tuning names; the default is a lifecycle reference.
53. Fresh-project reads are empty libraries, never errors.

## 13. Milestone 0 and remaining open questions

Milestone 0 — the frozen table: a checked-in machine-readable table (JSON/TOML) serving as spec appendix, meta-test input, reference-script input, and implementation table. Columns per row: quality id, name production, chord-tone set, R3 tier, tie-break position, inversion semantics, spelling notes, R2 discounted set, family. Plus the appendix artifacts: dyad token encoding, accidental grammar, `context_key` strings, the `chosen` reference grammar and tier rule, and the `descriptions/` module. Membership criterion: a quality enters the freeze only if a Set A or B fixture requires it (as top or documented shadow), arriving with its fixture. Change classes: additive = engine_version bump, caches invalidated, display spellings and rungs may shift (cheap, not invisible); breaking (remove/rename) = load-time `chosen` migration. Sequencing: table format + meta-test + reference script → populate the floor → gate + oracle content check → human review of non-tertian rows → freeze. Milestone 0 exits when the gate passes and both fixture sets regenerate clean.

Open questions (all decisions, no gaps):

1. Ship `context_key` in V1? Leaning ship — R0 is mechanical and script-covered.
2. Dyad token encoding/casing — appendix decides under parse-unambiguity.
3. cdp-mcp conventions PR and `MUSIC_MCP_CONVENTIONS.md`: same release or doc first?
4. `describe_workspace` inline threshold (64 is a guess; confirm against client context budgets).
5. `set_instrument_tuning` scope (Phase 2b): project-scoped declaration with `since` — leaning yes; the acknowledged wrinkle (two projects declaring contradictory states for one physical guitar) stays open deliberately, since the server tracks declarations, not guitars.

Shipping note: twelve reviews moved the failure surface from designs that would fail a user, to rules that were wrong, to wording that would mislead an implementer — and the remedy at each layer was the same: make it mechanical. What remains lives in Milestone 0, which is one review of data with the meta-test running. Build order: Milestone 0 tooling → table freeze → V1 per §6 → Phase 2b early if the experimental-tuning audience is the wedge. The first library this server manages should be the Gm/Em song its fixtures came from.
