"""Programmatic app icon (no binary assets needed at runtime)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

STATUS_COLORS = {
    "online": (34, 197, 94),
    "connecting": (245, 158, 11),
    "offline": (113, 113, 122),
    "unpaired": (239, 68, 68),
    "rejected": (239, 68, 68),
}


def make_icon(size: int = 64, status: str | None = None) -> Image.Image:
    """Purple rounded tile with a three-node network glyph and an optional
    status dot."""
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # vertical gradient tile
    top, bottom = (139, 92, 246), (99, 54, 214)
    tile = Image.new("RGBA", (s, s))
    td = ImageDraw.Draw(tile)
    for y in range(s):
        t = y / s
        td.line([(0, y), (s, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.24), fill=255)
    img.paste(tile, (0, 0), mask)

    # network glyph: three nodes connected
    w = (255, 255, 255, 255)
    nodes = [(0.30, 0.34), (0.70, 0.34), (0.50, 0.70)]
    pts = [(int(x * s), int(y * s)) for x, y in nodes]
    lw = int(s * 0.055)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        d.line([pts[a], pts[b]], fill=w, width=lw)
    r = int(s * 0.095)
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=w)

    if status in STATUS_COLORS:
        dr = int(s * 0.17)
        cx, cy = s - dr - int(s * 0.02), s - dr - int(s * 0.02)
        d.ellipse([cx - dr - lw, cy - dr - lw, cx + dr + lw, cy + dr + lw], fill=(15, 15, 20, 255))
        d.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=STATUS_COLORS[status] + (255,))

    return img.resize((size, size), Image.LANCZOS)


def save_ico(path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    make_icon(256).save(path, format="ICO", sizes=[(n, n) for n in sizes])


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "netsync.ico")
    save_ico(out)
    make_icon(256).save(out.with_suffix(".png"))
    print(f"wrote {out}")
