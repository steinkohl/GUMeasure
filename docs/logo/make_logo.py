"""Builds the gumeasure logo as SVG: a mark and a wordmark in outlines.

The mark is a normal distribution over its ±U interval: the value, its expanded uncertainty
and the GUM behind both. The wordmark is Inter SemiBold (SIL Open Font Licence), converted to
outlines so the logo needs no font. Colours switch with prefers-color-scheme.

Run with fonttools installed: `python docs/logo/make_logo.py docs/logo`
"""

import math
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = Path(sys.argv[1])
FONT = TTFont("/usr/share/fonts/opentype/inter/Inter-SemiBold.otf")

STYLE = """<style>
  .ink { fill: #17232e; } .inks { stroke: #17232e; }
  .acc { fill: #0f7c8c; } .accs { stroke: #0f7c8c; }
  .soft { fill: #0f7c8c; fill-opacity: 0.16; }
  @media (prefers-color-scheme: dark) {
    .ink { fill: #e8eef3; } .inks { stroke: #e8eef3; }
    .acc { fill: #4cc3d4; } .accs { stroke: #4cc3d4; }
    .soft { fill: #4cc3d4; fill-opacity: 0.22; }
  }
</style>"""


def text_path(text: str, x: float, baseline: float, size: float) -> tuple[str, float]:
    """SVG path data of text in outlines, and the advance width."""
    glyphs = FONT.getGlyphSet()
    cmap = FONT.getBestCmap()
    scale = size / FONT["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    cursor = x
    for ch in text:
        name = cmap[ord(ch)]
        tp = TransformPen(pen, (scale, 0, 0, -scale, cursor, baseline))
        glyphs[name].draw(tp)
        cursor += glyphs[name].width * scale
    return pen.getCommands(), cursor - x


def mark(ox: float, oy: float, s: float) -> str:
    """The mark in a box of s × s at (ox, oy): a normal curve over its ±U interval."""
    left, right = ox + 0.08 * s, ox + 0.92 * s
    base = oy + 0.66 * s
    top = oy + 0.12 * s
    mid = (left + right) / 2
    sigma = (right - left) / 6.4
    k = 2.0  # the shaded band is ±2σ, the expanded uncertainty

    def y(x: float) -> float:
        return base - (base - top) * math.exp(-0.5 * ((x - mid) / sigma) ** 2)

    n = 160
    xs = [left + (right - left) * i / n for i in range(n + 1)]
    curve = " ".join(f"{'M' if i == 0 else 'L'}{x:.2f},{y(x):.2f}" for i, x in enumerate(xs))
    a, b = mid - k * sigma, mid + k * sigma
    band_xs = [a + (b - a) * i / 80 for i in range(81)]
    band = (
        f"M{a:.2f},{base:.2f} "
        + " ".join(f"L{x:.2f},{y(x):.2f}" for x in band_xs)
        + f" L{b:.2f},{base:.2f} Z"
    )
    w = 0.055 * s  # stroke width
    bar_y = oy + 0.84 * s
    cap = 0.07 * s
    interval = (
        f"M{a:.2f},{bar_y:.2f} L{b:.2f},{bar_y:.2f} "
        f"M{a:.2f},{bar_y - cap:.2f} L{a:.2f},{bar_y + cap:.2f} "
        f"M{b:.2f},{bar_y - cap:.2f} L{b:.2f},{bar_y + cap:.2f}"
    )
    return f"""<g fill="none" stroke-linecap="round" stroke-linejoin="round">
  <path class="soft" stroke="none" d="{band}"/>
  <path class="inks" stroke-width="{w:.2f}" d="{curve}"/>
  <path class="inks" stroke-width="{w:.2f}" d="M{left:.2f},{base:.2f} L{right:.2f},{base:.2f}"/>
  <path class="accs" stroke-width="{w:.2f}" d="M{mid:.2f},{top:.2f} L{mid:.2f},{base:.2f}"/>
  <path class="accs" stroke-width="{w:.2f}" d="{interval}"/>
  <circle class="acc" stroke="none" cx="{mid:.2f}" cy="{bar_y:.2f}" r="{1.6 * w:.2f}"/>
</g>"""


def svg(width: float, height: float, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        f'width="{width:g}" height="{height:g}" role="img" aria-label="{title}">\n'
        f"<title>{title}</title>\n{STYLE}\n{body}\n</svg>\n"
    )


# Full logo: mark and wordmark.
S = 128
size = 74
baseline = 88
gum, w1 = text_path("gum", S + 18, baseline, size)
rest, w2 = text_path("easure", S + 18 + w1, baseline, size)
width = S + 18 + w1 + w2 + 6
logo = mark(0, 0, S) + f'\n<path class="acc" d="{gum}"/>\n<path class="ink" d="{rest}"/>'
(OUT / "logo.svg").write_text(svg(round(width), S, logo, "gumeasure"), encoding="utf-8")
# The mark alone, square, for avatars and favicons.
(OUT / "logo-mark.svg").write_text(svg(S, S, mark(0, 0, S), "gumeasure"), encoding="utf-8")
print(round(width), S)
