# grip-mcp

An MCP server that gives an LLM a deterministic fretboard engine — **identify,
library, render** — with the conversation as the control surface.

Composing on guitar is grip-first: shapes are found by hand, and their
theoretical identity comes second, negotiated in context. `grip-mcp` captures
grips, identifies them against a fully specified, deterministic ranking
pipeline (no tuned weights), and persists the musician's own `chosen` names so
every future conversation speaks their vocabulary instead of re-litigating
theory.

The full specification is in [docs/DESIGN.md](docs/DESIGN.md) (v1.0, accepted
for implementation). Grammar and data-format decisions frozen at Milestone 0
live in [docs/appendix/APPENDIX.md](docs/appendix/APPENDIX.md).

## Repository layout

```
src/grip_mcp/               the package (V1 server lands here)
  data/qualities.toml       the frozen quality table — single source of truth
                            (spec appendix, meta-test input, reference-script
                            input, and implementation table)
  descriptions/             versioned tool descriptions + server instructions
tools/reference/            standalone reference derivation script; shares
                            ONLY the quality table with the implementation —
                            all fixture expectations are its reviewed output
tests/                      meta-tests, fixture sets A/B, property tests
docs/                       design doc + Milestone-0 appendix
```

## Status

Milestone 0 complete: the quality table is frozen at 1.0.0 (gate review
record: [REVIEW.md](REVIEW.md)). Next: V1 per DESIGN.md §6. Roadmap: §9.

## Development

```
uv sync                      # dev group (pytest); no runtime deps yet
uv run pytest                # unconditional suite — no optional deps required
uv sync --extra m21          # adds the music21 oracle checks
uv run pytest
```

Second server in a planned ecosystem (first: `cdp-mcp` for sound
transformation). Filesystem federation conventions: DESIGN.md §3.
