"""Build-time font-data extraction (not a runtime dependency).

Reads Liberation Sans Regular (SIL OFL 1.1) and writes
src/grip_mcp/data/fonts/liberation_sans.json: units-per-em, per-character
advance widths, and per-character glyph outlines as SVG path data (y-down,
already flipped). The renderer lays out ALL text against these metrics
and draws it as paths, so on-disk SVGs survive machines without the font
(DESIGN §8) and rasterization needs no font machinery at all.

Requires fonttools (dev environment only):
    python tools/build_font_data.py [path-to-LiberationSans-Regular.ttf]
"""

import json
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

DEFAULT_TTF = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
OUT = (
    Path(__file__).resolve().parent.parent
    / "src" / "grip_mcp" / "data" / "fonts" / "liberation_sans.json"
)

# Every character the renderer may draw (ASCII printable + ellipsis).
CHARS = [chr(c) for c in range(0x20, 0x7F)] + ["…"]


def main() -> int:
    ttf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TTF
    font = TTFont(ttf_path)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]

    advances, paths = {}, {}
    for ch in CHARS:
        gname = cmap.get(ord(ch))
        if gname is None:
            continue
        advances[ch] = hmtx[gname][0]
        pen = SVGPathPen(glyphs)
        # Flip to y-down SVG space at extraction time (scale 1, -1).
        glyphs[gname].draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
        d = pen.getCommands()
        if d:
            paths[ch] = d

    name = font["name"]
    data = {
        "family": name.getDebugName(1),
        "version": name.getDebugName(5),
        "license": "SIL Open Font License 1.1 "
                   "(https://openfontlicense.org); Liberation Fonts, "
                   "(c) 2012 Red Hat Inc., Reserved Font Name Liberation.",
        "units_per_em": upem,
        "ascender": font["hhea"].ascender,
        "descender": font["hhea"].descender,
        "advances": advances,
        "paths": paths,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size/1024:.0f} KiB, {len(paths)} glyph paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
