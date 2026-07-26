"""Fretboard rendering (DESIGN §6.4, §8).

One SVG template, two orientations (chart default / neck); all text is
laid out against the bundled font's real metrics and drawn as glyph
paths, so on-disk SVGs survive machines without the font and PNG
rasterization needs no font machinery. Deterministic output: bundled
metrics, fixed palette + theme, no timestamps.

The renderer draws plain data — the server layer computes label strings
(notes / intervals / fingers) from theory, keeping this module free of
music knowledge beyond X/O conventions.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib import resources

RENDERER_VERSION = "1.0.0"

INLINE_MAX_PX = 1200


class RenderError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --- bundled font -----------------------------------------------------------

@lru_cache(maxsize=1)
def _font() -> dict:
    data = (
        resources.files("grip_mcp") / "data" / "fonts" / "liberation_sans.json"
    ).read_bytes()
    return json.loads(data)


def text_width(s: str, size: float) -> float:
    f = _font()
    upem = f["units_per_em"]
    return sum(f["advances"].get(ch, f["advances"][" "]) for ch in s) \
        * size / upem


def truncate(s: str, size: float, max_width: float) -> str:
    if text_width(s, size) <= max_width:
        return s
    ell = "…"
    while s and text_width(s + ell, size) > max_width:
        s = s[:-1]
    return s + ell


def draw_text(x: float, y: float, s: str, size: float, fill: str,
              anchor: str = "middle") -> str:
    """Text as glyph paths: <g> translating each glyph along the baseline."""
    f = _font()
    upem = f["units_per_em"]
    scale = size / upem
    width = text_width(s, size)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    parts = []
    cursor = 0.0
    for ch in s:
        d = f["paths"].get(ch)
        adv = f["advances"].get(ch, f["advances"][" "])
        if d:
            parts.append(
                f'<path transform="translate({x + cursor:.2f} {y:.2f}) '
                f'scale({scale:.5f})" d="{d}" fill="{fill}"/>'
            )
        cursor += adv * scale
    return "".join(parts)


# --- themes -----------------------------------------------------------------

THEMES = {
    "light": {
        "bg": "#ffffff", "fg": "#1c1c1c", "grid": "#5a5a5a",
        "dot": "#1c1c1c", "muted": "#8a8a8a", "badge_bg": "#e8e4d8",
        "badge_fg": "#4a4232",
    },
    "dark": {
        "bg": "#20211f", "fg": "#ececec", "grid": "#9a9a9a",
        "dot": "#ececec", "muted": "#8a8a8a", "badge_bg": "#4a4232",
        "badge_fg": "#e8e4d8",
    },
}

# --- geometry constants (abstract px) ---------------------------------------

SG = 24          # string gap
FG = 30          # fret gap
DOT_R = 8.5
TOP_PAD = 16     # above X/O row
XO_H = 18        # X/O row height
LABEL_H = 20     # per-string label band
NAME_H = 24      # name band
SIDE_PAD = 26    # room for position numeral


def fret_window(frets: list[int | None]) -> tuple[int, int]:
    """(start_fret, n_rows). From fretted notes only; min 4 rows; all-open
    falls back to 1..4 with the nut (DESIGN §8)."""
    fretted = [f for f in frets if f is not None and f > 0]
    if not fretted:
        return 1, 4
    lo, hi = min(fretted), max(fretted)
    n = max(hi - lo + 1, 4)
    if hi <= n:  # window can include fret 1 -> show the nut
        return 1, n
    return lo, n


def barre_runs(frets, fingers) -> list[tuple[int, int, int]]:
    """Contiguous same-finger-same-fret runs (len >= 2) ->
    [(fret, s_from, s_to)]. Drawn in all label modes."""
    if not fingers:
        return []
    runs = []
    i, n = 0, len(frets)
    while i < n:
        f, d = frets[i], fingers[i] if i < len(fingers) else None
        if f is None or f <= 0 or d in (None,):
            i += 1
            continue
        j = i
        while (
            j + 1 < n
            and frets[j + 1] == f
            and (fingers[j + 1] if j + 1 < len(fingers) else None) == d
        ):
            j += 1
        if j > i:
            runs.append((f, i, j))
        i = j + 1
    return runs


# --- single-grip chart ------------------------------------------------------

def chart_size(n_strings: int, n_rows: int) -> tuple[float, float]:
    w = SIDE_PAD * 2 + SG * (n_strings - 1)
    h = TOP_PAD + XO_H + FG * n_rows + LABEL_H + NAME_H + 10
    return w, h


def draw_grip(g: dict, theme: dict, labels_mode: str,
              ox: float = 0.0, oy: float = 0.0) -> tuple[str, float, float]:
    """One grip -> (svg fragment, width, height).

    g: {frets, fingers?, string_labels?, name, capo}
    """
    frets = g["frets"]
    fingers = g.get("fingers") or []
    n = len(frets)
    start, rows = fret_window(frets)
    w, h = chart_size(n, rows)
    x0 = ox + SIDE_PAD
    grid_top = oy + TOP_PAD + XO_H
    grid_bot = grid_top + FG * rows
    fg, grid, dot = theme["fg"], theme["grid"], theme["dot"]
    out = []

    def sx(i):  # string x (low -> high, left -> right)
        return x0 + SG * i

    # nut or position numeral
    if start == 1:
        out.append(
            f'<rect x="{sx(0) - 1.5:.2f}" y="{grid_top - 4:.2f}" '
            f'width="{SG * (n - 1) + 3:.2f}" height="4" fill="{fg}"/>'
        )
    else:
        out.append(draw_text(x0 - 10, grid_top + FG * 0.65, f"{start}fr",
                             11, fg, anchor="end"))
    # grid
    for i in range(n):
        out.append(
            f'<line x1="{sx(i):.2f}" y1="{grid_top:.2f}" x2="{sx(i):.2f}" '
            f'y2="{grid_bot:.2f}" stroke="{grid}" stroke-width="1.2"/>'
        )
    for r in range(rows + 1):
        y = grid_top + FG * r
        out.append(
            f'<line x1="{sx(0):.2f}" y1="{y:.2f}" x2="{sx(n - 1):.2f}" '
            f'y2="{y:.2f}" stroke="{grid}" stroke-width="1.2"/>'
        )
    # X/O row
    for i, f in enumerate(frets):
        cy = oy + TOP_PAD + XO_H / 2
        if f is None:
            r = 4.6
            out.append(
                f'<path d="M {sx(i) - r:.2f} {cy - r:.2f} L {sx(i) + r:.2f} '
                f'{cy + r:.2f} M {sx(i) - r:.2f} {cy + r:.2f} L '
                f'{sx(i) + r:.2f} {cy - r:.2f}" stroke="{theme["muted"]}" '
                f'stroke-width="1.8" fill="none"/>'
            )
        elif f == 0:
            out.append(
                f'<circle cx="{sx(i):.2f}" cy="{cy:.2f}" r="4.8" '
                f'fill="none" stroke="{fg}" stroke-width="1.8"/>'
            )
    # barres beneath dots
    for fret, s_from, s_to in barre_runs(frets, fingers):
        if not (start <= fret < start + rows):
            continue
        y = grid_top + FG * (fret - start) + FG / 2
        out.append(
            f'<rect x="{sx(s_from) - DOT_R:.2f}" y="{y - DOT_R:.2f}" '
            f'width="{sx(s_to) - sx(s_from) + 2 * DOT_R:.2f}" '
            f'height="{2 * DOT_R:.2f}" rx="{DOT_R:.2f}" fill="{dot}" '
            f'opacity="0.85"/>'
        )
    # dots
    for i, f in enumerate(frets):
        if f is None or f == 0:
            continue
        if not (start <= f < start + rows):
            continue
        y = grid_top + FG * (f - start) + FG / 2
        out.append(
            f'<circle cx="{sx(i):.2f}" cy="{y:.2f}" r="{DOT_R:.2f}" '
            f'fill="{dot}"/>'
        )
    # per-string labels beneath the grid (all label modes; §8)
    if labels_mode != "none":
        labels = g.get("string_labels") or [None] * n
        if labels_mode == "fingers":
            labels = [
                None if (f is None or f == 0) else
                ("T" if d == 0 else (str(d) if d is not None else None))
                for f, d in zip(frets, list(fingers) + [None] * n)
            ]
        for i, lab in enumerate(labels[:n]):
            if lab:
                out.append(draw_text(sx(i), grid_bot + 14.5, str(lab), 10, fg))
    # capo badge
    if g.get("capo"):
        txt = f"capo {g['capo']}"
        tw = text_width(txt, 10) + 10
        bx = ox + w - SIDE_PAD - tw + 14
        out.append(
            f'<rect x="{bx:.2f}" y="{oy + 2:.2f}" width="{tw:.2f}" '
            f'height="14" rx="7" fill="{theme["badge_bg"]}"/>'
        )
        out.append(draw_text(bx + tw / 2, oy + 12.5, txt, 10,
                             theme["badge_fg"]))
    # name band (truncated; full name lives in the response text)
    name = g.get("name") or ""
    if name:
        shown = truncate(name, 13, w - 8)
        out.append(draw_text(ox + w / 2, grid_bot + LABEL_H + 16, shown,
                             13, fg))
    return "".join(out), w, h


# --- documents --------------------------------------------------------------

def _document(body: str, w: float, h: float, theme: dict) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} '
        f'{h:.0f}" width="{w:.0f}" height="{h:.0f}">'
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="{theme["bg"]}"/>'
        f"{body}</svg>"
    )


def render_chart(grips: list[dict], options: dict | None = None) -> dict:
    """grips -> {"svg": ..., "width": ..., "height": ..., "hash": ...}.

    options: labels ("notes"|"intervals"|"fingers"|"none"), theme, columns,
    title, orientation ("chart"|"neck").
    """
    options = dict(options or {})
    theme_name = options.get("theme", "light")
    if theme_name not in THEMES:
        raise RenderError(
            "unknown_theme",
            f"theme {theme_name!r}; known: {sorted(THEMES)}",
        )
    labels_mode = options.get("labels", "notes")
    if labels_mode not in ("notes", "intervals", "fingers", "none"):
        raise RenderError(
            "unknown_labels",
            f"labels {labels_mode!r}; known: notes, intervals, fingers, none",
        )
    orientation = options.get("orientation", "chart")
    if orientation not in ("chart", "neck"):
        raise RenderError(
            "unknown_orientation",
            f"orientation {orientation!r}; known: chart, neck",
        )
    theme = THEMES[theme_name]
    columns = int(options.get("columns") or min(len(grips), 4))
    title = options.get("title")

    # Grid layout: cells sized to the largest chart (mixed tunings render
    # per-grip: own string count, own capo badge).
    sizes = [chart_size(len(g["frets"]), fret_window(g["frets"])[1])
             for g in grips]
    cell_w = max(s[0] for s in sizes)
    cell_h = max(s[1] for s in sizes)
    rows = (len(grips) + columns - 1) // columns
    title_h = 30 if title else 0
    W = cell_w * min(columns, len(grips))
    H = title_h + cell_h * rows

    body = []
    if title:
        body.append(draw_text(W / 2, 20, truncate(title, 15, W - 16), 15,
                              theme["fg"]))
    for i, g in enumerate(grips):
        r, c = divmod(i, columns)
        gw = chart_size(len(g["frets"]), fret_window(g["frets"])[1])[0]
        ox = c * cell_w + (cell_w - gw) / 2
        oy = title_h + r * cell_h
        frag, _, _ = draw_grip(g, theme, labels_mode, ox, oy)
        body.append(frag)

    svg_body = "".join(body)
    if orientation == "neck":
        # Same template, rotated geometry: low string nearest the viewer
        # (bottom), nut/low frets to the left.
        svg = _document(
            f'<g transform="translate(0 {W:.0f}) rotate(-90)">{svg_body}</g>',
            H, W, theme,
        )
        W, H = H, W
    else:
        svg = _document(svg_body, W, H, theme)
    return {
        "svg": svg,
        "width": W,
        "height": H,
        "hash": render_hash(grips, options),
    }


def render_hash(grips: list[dict], options: dict) -> str:
    """Render hash ≠ identity hash: covers resolved grips INCLUDING
    fingers, every option, and the renderer version (§6.4)."""
    blob = json.dumps([grips, options, RENDERER_VERSION], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def to_png(svg: str, width: float) -> bytes:
    """Rasterize via resvg bindings (no subprocess). Inline copies cap at
    1200 px wide; full resolution stays on disk as SVG."""
    import resvg_py
    zoom = min(2.0, INLINE_MAX_PX / max(width, 1))
    data = resvg_py.svg_to_bytes(svg_string=svg, zoom=zoom)
    return bytes(data)
