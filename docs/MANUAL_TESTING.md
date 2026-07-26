# grip-mcp — Manual Shakedown Checklist

The automated suite proves the server obeys the spec. What it cannot
prove is the thing §6.3 exists for: whether a *client LLM, mediating for
you*, actually behaves — leads with your names, presents the top
candidate as a reading rather than "the answer," repairs instead of
re-sending. The description-contract test only catches deleted text;
**this checklist is the test for ignored text.** Work in natural
language throughout — the conversation is the control surface.

## 0. Setup

- [ ] `uv` installed on the Mac (`brew install uv` if not).
- [ ] Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "grip": {
      "command": "uvx",
      "args": ["--from", "/Users/dgm/Desktop/GRIP-MCP", "grip-mcp"]
    }
  }
}
```

- [ ] Restart Claude Desktop; confirm the `grip` server shows 23 tools.
      (First launch resolves `mcp` + `resvg-py`; give it a moment.)
- [ ] Renders and libraries will land under `~/music_projects/` —
      keep a Finder window on it.

## 1. Project + the create gate (§6.2)

- [ ] Say: *"set up a grip project called gm-em-song"* → it should be
      **created** (and Claude should say created, not opened).
- [ ] Check disk: `~/music_projects/gm-em-song` should **not exist yet**
      (creation defers to first write; a confirmed switch litters nothing).
- [ ] New conversation. Say: *"open my grip project gm-em-sog"* (typo).
      → Expect a refusal that suggests `gm-em-song`, **not** a silently
      forked new project. This is the fork trap; it must be impossible.
- [ ] *"what's in this project?"* → empty library, standard tuning,
      no error.

## 2. Capture — one call in the common case (§6.1)

- [ ] Say: *"add my Gm shape, x x 8 7 8 x, fingers x x 2 1 3 x — call
      it Gm"* → one tool call; stored; **chosen = Gm/Bb**; a chart
      appears (renders/ on disk).
- [ ] **Watch the presentation**: the literal top reading is `Bb6` —
      Claude should lead with *your* name ("your Gm", "Gm/Bb") and
      offer Bb6 as the literal reading, not the other way round. This
      is the core §6.3 behavior; if it parrots "that's a Bb6," the
      descriptions failed at their job.
- [ ] Verify the pitch echo: Bb3 D4 G4, low→high. Open the PNG: X X on
      the outer strings, dots at 8-7-8, "7fr" numeral.
- [ ] Bulk capture: *"add the rest of the song without rendering each:
      gm-o = 3 1 x x x x, pass = 5 x x 3 x x, b5 = x 2 4 x x x"* →
      three stores, no per-grip renders (the render=false idiom).
- [ ] Deliberate mistake: *"add test1, x x 8 7 8"* (5 values) → error
      naming both lengths (5 vs 6), nothing stored.
- [ ] Reversed-array trap: *"add test2: x 8 7 8 x x — wait, is that
      right?"* → the echo/diagram should let you (and Claude) catch a
      shape that isn't yours. Remove test grips after.

## 3. Identify + context (§7)

- [ ] *"what could 2 2 2 x x x be?"* → top `F#q4`, alternatives incl.
      `F#7sus4`, `Bsus4/F#`; **nothing stored**. decided_at is R2 —
      Claude should present alternatives as live, not settled.
- [ ] *"and in E minor?"* → same top, `Bsus4/F#` at #2; `F#7sus4` now
      flagged out of key. The dominant-function hearing is Claude's to
      offer — see if it does.
- [ ] *"add that as q"* then *"q is my Bsus4"* → set_reading stores
      `Bsus4/F#` (tier 2: your suffix + root PC picked the inversion).
- [ ] *"call q Bsus"* → ambiguity listing `Bsus4/F#` and `B7sus4/F#`;
      Claude should **ask you**, not guess.
- [ ] *"call q Gm"* → miss with suggestions; the earlier `Bsus4/F#`
      must survive.

## 4. Resume — the product's whole point (§1, §6.2)

- [ ] **New conversation.** Say: *"open gm-em-song — where were we?"*
      → one describe_workspace call; Claude speaks `Gm/Bb` and
      `Bsus4/F#` from its first reply. If it re-derives theory names
      instead of using yours, the vocabulary loop is broken — this is
      the most important checkbox in the file.

## 5. Sequences + strips (§6.4)

- [ ] *"the intro is gm-o, pass, gm-1, b5 — render it"* → one strip
      PNG, four charts, name bands showing your chosen names where set.
- [ ] Render it again, same options → same filename (idempotent), no
      duplicate files piling up.
- [ ] *"remove gm-o"* → refusal (referenced by intro, counts given);
      then *"force it"* → removed AND dropped from the sequence.
      Re-add it and restore the sequence after.

## 6. Transpose (§6.1)

- [ ] *"take gm-1 up two semitones and save as am-1"* → strings
      x x 10 9 10 x, fingers carried verbatim, **chosen becomes Am/C**
      (covariant re-derivation), derived_from recorded.
- [ ] *"transpose an open E shape 0 2 2 1 0 0 up 2"* → correct pitches
      plus the opens_fretted warning (count 3) — Claude should say the
      hand shape changed, not "same chord up 2."
- [ ] Capo error path: define `standard-capo3` (from standard, capo 3),
      add a grip on it, transpose down past fret 0 → the error should
      speak capo-relative ("below the capo").

## 7. Tunings + Phase 2b (§9)

- [ ] *"define dadgad: D2 A2 D3 G3 A3 D4"* then *"my guitar's in dadgad
      now for this project"* → declaration with since; default_tuning
      follows; capture without naming a tuning now resolves to dadgad
      (check the envelope echo).
- [ ] *"how do I get from standard to dadgad?"* → retune plan: strings
      1, 5, 6 down 2; suggested order downs-first; **no** string-gauge
      claims — heuristic language only.
- [ ] *"plan standard → open C (C2 G2 C3 G3 C4 E4)"* → the low-E drop
      of 4 gets the slack warning; nothing stronger.
- [ ] Try *"delete dadgad"* while declared → refusal pointing at
      set_instrument_tuning.
- [ ] Strum all-open in dadgad, capture it → top `Dsus4` — the
      alternative-tuning capture loop working end to end.

## 8. Phase 2a — voicings + neck (§9)

- [ ] *"show me Gm voicings"* → chart strip; shapes are playable; the
      3-5-5-3-3-3 barre appears with barre detected. Claude should
      **never** invent a shape by itself anymore — every fretting it
      shows should come from find_voicings or your own grips.
- [ ] *"Gm voicings around the 10th fret"* → window moves.
- [ ] *"Gm with the Bb on the bottom"* → every result's bass is Bb.
- [ ] *"voicings for Gsus"* → instructive refusal listing sus2 / sus4 /
      7sus4 (family vs quality).
- [ ] *"Dsus4 voicings in dadgad"* → all-open tops the list.
- [ ] *"show me E minor across the neck"* → overlay PNG: E's filled,
      others ringed, correct spellings.
- [ ] *"same but in dadgad"* → overlay repositions per tuning.

## 9. Files, hand edits, git (§3, §10)

- [ ] Open `grip/library.json` — human-readable, your names intact,
      grips carry concrete tuning names (never "default").
- [ ] Hand-edit a label in library.json, then ask Claude about that
      grip → fresh read sees your edit immediately.
- [ ] Break the JSON on purpose (delete a comma), ask again →
      instructive error, no crash, no data loss; fix it back.
- [ ] `git init` the project folder if you like: derived.json is
      already gitignored by the bootstrap; library.json + renders diff
      cleanly.

## 10. Judgment calls to note (not pass/fail)

- [ ] Does decided_at calibration come through? (tie-break presented as
      genuinely ambiguous; "unique" presented plainly.)
- [ ] Are readings *offered* or *asserted*? The server ranks; Claude
      decides and records; **you** name.
- [ ] Anything where you had to fight the tool or repeat yourself —
      that's a descriptions bug (§6.3 is a versioned design artifact;
      file it like one).
- [ ] Whatever felt missing: does it want Phase 3 (analysis: Roman
      numerals, voice-leading) or something the roadmap doesn't have?

---
Found something? The fix lands in one of exactly three places: the
frozen table (content), the engines (rules — fixture-pinned), or
`descriptions/` (presentation). Knowing which is half the report.
