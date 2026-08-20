"""The Docket's mark, as inline SVG.

Inlined into every served page rather than linked. The server binds to loopback
and the page has to render with no network access at all, so an external image
or a web font is not an option — which is also why the wordmark uses the system
stack the rest of the interface already uses.

Geometry is from the identity: a 64-unit canvas with a 14-unit corner radius, a
margin rule at x=14.6, and four matters on a 10.5 pitch, ragged right. The top
matter is disposed of — gold, struck through, solid marker — and the three
below it wait. Markers straddle the rule so the list still reads as a list when
colour is removed.

Colours come from the page's own tokens rather than being hardcoded, so the
mark follows the theme without a second copy of it. The favicon is the one
exception: it is a standalone document and cannot see the page's variables, so
it carries literal values.
"""

from __future__ import annotations

# Four matters. The first is disposed of; the rest are open.
_ROWS = (
    # (bar_y, bar_width, marker_y)
    (15.0, 26, 14.8),
    (25.5, 26, 25.3),
    (36.0, 21, 35.8),
    (46.5, 15, 46.3),
)


def icon(size: int = 32, label: str = "The Docket") -> str:
    """The mark at any size, themed by the page's tokens."""
    parts = [
        f'<svg viewBox="0 0 64 64" width="{size}" height="{size}" '
        f'class="dk-icon" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{label}">',
        '<rect width="64" height="64" rx="14" fill="var(--brand-ground)"/>',
        '<rect x="14.6" y="13" width="2.4" height="38" fill="var(--brand-ink)"/>',
    ]
    for index, (bar_y, width, marker_y) in enumerate(_ROWS):
        disposed = index == 0
        bar = "var(--brand-accent)" if disposed else "var(--brand-ink)"
        parts.append(
            f'<rect x="24" y="{bar_y}" width="{width}" height="5" fill="{bar}"/>'
        )
        if disposed:
            # The strike is the ground showing through, which is why a disposed
            # matter still reads once colour is removed.
            parts.append(
                f'<rect x="24" y="{bar_y + 1.65}" width="{width}" height="1.7" '
                f'fill="var(--brand-ground)"/>'
            )
            parts.append(
                '<rect x="12.3" y="14" width="7" height="7" '
                'fill="var(--brand-accent)"/>'
            )
        else:
            parts.append(
                f'<rect x="13.1" y="{marker_y}" width="5.4" height="5.4" '
                f'fill="var(--brand-ground)" stroke="var(--brand-ink)" '
                f'stroke-width="1.6"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def animated_icon(size: int = 44, label: str = "The Docket") -> str:
    """The mark with the caret working down the rule, clearing each matter.

    Used only where something has just finished, so the motion reads as the
    docket being cleared rather than as decoration. Honours reduced motion via
    the stylesheet.
    """
    parts = [
        f'<svg viewBox="0 0 64 64" width="{size}" height="{size}" '
        f'class="dk-icon dk-icon-live" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{label}">',
        '<rect width="64" height="64" rx="14" fill="var(--brand-ground)"/>',
        '<rect x="14.6" y="13" width="2.4" height="38" fill="var(--brand-ink)"/>',
    ]
    for index, (bar_y, width, _marker_y) in enumerate(_ROWS):
        parts.append(
            f'<rect x="24" y="{bar_y}" width="{width}" height="5" '
            f'fill="var(--brand-ink)" class="dk-bar dk-bar-{index}"/>'
        )
    for _index, (_bar_y, _width, marker_y) in enumerate(_ROWS):
        parts.append(
            f'<rect x="13.1" y="{marker_y}" width="5.4" height="5.4" '
            f'fill="var(--brand-ground)" stroke="var(--brand-ink)" '
            f'stroke-width="1.6"/>'
        )
    parts.append(
        '<rect x="12.3" y="14" width="7" height="7" '
        'fill="var(--brand-accent)" class="dk-caret"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


# Standalone document: no access to the page's variables, so literal colours.
# Three matters rather than four and no strike — at 16px the fourth row and the
# strike both close up into noise.
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<rect width="16" height="16" rx="3.5" fill="#f7f6f3"/>'
    '<rect x="3.4" y="3" width="1.2" height="10" fill="#1c1a17"/>'
    '<rect x="6.6" y="3.7" width="6.6" height="1.6" fill="#a07d2c"/>'
    '<rect x="2.5" y="3.7" width="3" height="1.6" fill="#a07d2c"/>'
    '<rect x="6.6" y="7.2" width="6.6" height="1.6" fill="#1c1a17"/>'
    '<rect x="2.5" y="7.2" width="3" height="1.6" fill="#1c1a17"/>'
    '<rect x="6.6" y="10.7" width="4.4" height="1.6" fill="#1c1a17"/>'
    '<rect x="2.5" y="10.7" width="3" height="1.6" fill="#1c1a17"/>'
    "</svg>"
)


def favicon_link() -> str:
    """A data-URI favicon, so the page still needs nothing from the network."""
    from urllib.parse import quote

    return (
        '<link rel="icon" href="data:image/svg+xml,'
        f'{quote(FAVICON_SVG, safe="")}">'
    )


def wordmark(icon_px: int = 30, tagline: str = "") -> str:
    """Icon plus name, horizontally.

    Per the identity: type at 0.65x the icon height, gap at 0.35x, horizontal
    only, never italic or all caps.
    """
    line = '<div class="dk-name">The Docket</div>'
    if tagline:
        line = (
            '<div class="dk-stack">'
            f"{line}"
            f'<div class="dk-tagline">{tagline}</div>'
            "</div>"
        )
    return f'<div class="dk-lockup">{icon(icon_px)}{line}</div>'


FOOTER = (
    '<footer class="dk-foot">'
    '<span class="dk-foot-name">The Docket</span>'
    '<span class="dk-foot-sep">·</span>'
    '<a href="https://mipyip.com" target="_blank" rel="noopener noreferrer">mipyip.com</a>'
    '<span class="dk-foot-sep">·</span>'
    "<span>&copy; 2026 MipYip</span>"
    '<span class="dk-foot-sep">·</span>'
    "<span>MIT</span>"
    "</footer>"
)
