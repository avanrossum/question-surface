#!/usr/bin/env python3
"""Write the standalone brand SVGs used outside the served pages.

The served pages inline the mark and colour it with their own tokens. A README
cannot do either: GitHub strips inline SVG from markdown, and a file referenced
by <img> is a separate document with no access to anything. So these carry
literal colours and ship as files, generated from the same geometry as
`docket/brand.py` so the two cannot drift.

    python3 scripts/make_brand_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docket.brand import _ROWS  # noqa: E402

OUT = ROOT / "docs" / "images"

THEMES = {
    "light": {"ground": "#f2efe8", "ink": "#1c1a17", "accent": "#a07d2c",
              "type": "#1c1a17", "sub": "#4a463e"},
    "dark": {"ground": "#26231e", "ink": "#f4f1ea", "accent": "#d4ab5a",
             "type": "#f4f1ea", "sub": "#a8a294"},
}

FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, "
        "system-ui, Helvetica, Arial, sans-serif")


def mark(colours: dict, x: float, y: float, size: float) -> str:
    """The icon, drawn at an offset so it can sit in a wider canvas."""
    scale = size / 64.0
    def sx(v: float) -> float:
        return round(x + v * scale, 2)
    def sy(v: float) -> float:
        return round(y + v * scale, 2)
    def s(v: float) -> float:
        return round(v * scale, 2)

    parts = [
        f'<rect x="{sx(0)}" y="{sy(0)}" width="{s(64)}" height="{s(64)}" '
        f'rx="{s(14)}" fill="{colours["ground"]}"/>',
        f'<rect x="{sx(14.6)}" y="{sy(13)}" width="{s(2.4)}" height="{s(38)}" '
        f'fill="{colours["ink"]}"/>',
    ]
    for index, (bar_y, width, marker_y) in enumerate(_ROWS):
        disposed = index == 0
        fill = colours["accent"] if disposed else colours["ink"]
        parts.append(
            f'<rect x="{sx(24)}" y="{sy(bar_y)}" width="{s(width)}" '
            f'height="{s(5)}" fill="{fill}"/>'
        )
        if disposed:
            parts.append(
                f'<rect x="{sx(24)}" y="{sy(bar_y + 1.65)}" width="{s(width)}" '
                f'height="{s(1.7)}" fill="{colours["ground"]}"/>'
            )
            parts.append(
                f'<rect x="{sx(12.3)}" y="{sy(14)}" width="{s(7)}" '
                f'height="{s(7)}" fill="{colours["accent"]}"/>'
            )
        else:
            parts.append(
                f'<rect x="{sx(13.1)}" y="{sy(marker_y)}" width="{s(5.4)}" '
                f'height="{s(5.4)}" fill="{colours["ground"]}" '
                f'stroke="{colours["ink"]}" stroke-width="{s(1.6)}"/>'
            )
    return "".join(parts)


def wordmark(theme: str, tagline: str = "") -> str:
    """Icon plus name, per the identity's lockup rules."""
    c = THEMES[theme]
    icon_size = 56.0
    gap = icon_size * 0.35            # 0.35x icon height
    type_size = icon_size * 0.65      # 0.65x icon height
    text_x = icon_size + gap
    height = 72.0
    icon_y = (height - icon_size) / 2

    if tagline:
        name_y = icon_y + icon_size * 0.44
        sub = (
            f'<text x="{text_x}" y="{icon_y + icon_size * 0.82}" '
            f'font-family="{FONT}" font-size="14" font-weight="400" '
            f'fill="{c["sub"]}">{tagline}</text>'
        )
    else:
        name_y = height / 2 + type_size * 0.35
        sub = ""

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 330 {height:g}" '
        f'width="330" height="{height:g}" role="img" aria-label="The Docket">'
        f"{mark(c, 0, icon_y, icon_size)}"
        f'<text x="{text_x}" y="{name_y:g}" font-family="{FONT}" '
        f'font-size="{type_size:g}" font-weight="600" letter-spacing="-0.7" '
        f'fill="{c["type"]}">The Docket</text>'
        f"{sub}"
        "</svg>"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for theme in THEMES:
        for suffix, tag in (("", ""), ("-tagline", "better questions from your agent")):
            path = OUT / f"wordmark-{theme}{suffix}.svg"
            path.write_text(wordmark(theme, tag) + "\n", encoding="utf-8")
            written.append(path)
        icon_path = OUT / f"icon-{theme}.svg"
        icon_path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
            f'width="64" height="64" role="img" aria-label="The Docket">'
            f"{mark(THEMES[theme], 0, 0, 64)}</svg>\n",
            encoding="utf-8",
        )
        written.append(icon_path)
    for path in written:
        print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
