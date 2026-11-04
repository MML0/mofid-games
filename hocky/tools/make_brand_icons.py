"""Bake the brand book's vector icons and bull into assets/brand as transparent PNGs.

    python3 tools/make_brand_icons.py /path/to/Brnadbook-V04.pdf ["/path/to/Game Icons.pdf"]

Needs PyMuPDF, but only for this step: the game just loads the PNGs. The shapes are redrawn from the PDF's own
vector paths, in their own colors, so nothing is traced or restyled.

The second, optional PDF holds the group's sub-brands, one per page. Each is rendered as it is, on its white page and
cropped to the logo, for the coins' pale faces (brand_*.png). The group logo, group_stacked.png, is the client's own
white PNG (Asset 71) copied in by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent.parent / "assets" / "brand"
SIZE = 512  # pixels per icon
ICON_PAGE = 20
HEADER_PAGE = 4
GRID_X, GRID_Y, CELL = 93.6, 128.0, 54.55
LABEL_INK = 0.5  # the icon captions are the only mid grey on the page
# the sub-brands' PDF, page by page
BRANDS = ("easytrader", "mofid_app", "jet", "boursview2", "boursview", "life_insurance", "academy_mofid",
          "ayar", "hami", "tavan", "hamnang", "atieh", "gold")
BRAND_PX = 640  # the longest side of a baked sub-brand
# name: (column, row) in the book's icon table
ICONS = {
    "check": (1, 0), "money": (4, 0), "pie": (10, 0), "assets": (11, 0),
    "plane": (2, 1), "stairs": (5, 1), "binoculars": (6, 1), "academy": (9, 1),
    "dataviz": (7, 2), "donut": (8, 2),
    "star": (1, 3), "chart": (7, 3),
    "low_risk": (6, 4), "return": (7, 4), "risk": (10, 4),
    "badge": (0, 5), "market_map": (6, 5),
    "financial": (0, 6), "game": (5, 6),
}


def draw_paths(page, paths) -> None:
    shape = page.new_shape()
    for path in paths:
        for item in path["items"]:
            kind = item[0]
            if kind == "l":
                shape.draw_line(item[1], item[2])
            elif kind == "re":
                shape.draw_rect(item[1])
            elif kind == "qu":
                shape.draw_quad(item[1])
            elif kind == "c":
                shape.draw_bezier(item[1], item[2], item[3], item[4])
        shape.finish(fill=path.get("fill"), color=path.get("color"), width=path.get("width") or 0,
                     even_odd=path.get("even_odd", True), closePath=path.get("closePath", False),
                     fill_opacity=path.get("fill_opacity") or 1, stroke_opacity=path.get("stroke_opacity") or 1,
                     lineCap=max(path.get("lineCap") or (0,)), lineJoin=int(path.get("lineJoin") or 0))
    shape.commit()


def bake(paths, name: str, width: int = 0) -> None:
    """Redraw `paths` alone on a transparent page with a small margin: a square, or `width` pixels wide at its own shape."""
    box = pymupdf.Rect(paths[0]["rect"])
    for path in paths[1:]:
        box |= path["rect"]
    side = max(box.width, box.height) * 1.04
    page_w, page_h = (box.width * 1.02, box.height * 1.02) if width else (side, side)
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    dx, dy = (page_w - box.width) / 2 - box.x0, (page_h - box.height) / 2 - box.y0
    moved = []
    for path in paths:
        items = []
        for item in path["items"]:
            new = [item[0]]
            for v in item[1:]:
                new.append(v + pymupdf.Point(dx, dy) if isinstance(v, pymupdf.Point) else
                           pymupdf.Rect(v) + (dx, dy, dx, dy) if isinstance(v, pymupdf.Rect) else
                           pymupdf.Quad(*(pt + pymupdf.Point(dx, dy) for pt in v)) if isinstance(v, pymupdf.Quad) else v)
            items.append(tuple(new))
        moved.append({**path, "items": items})
    draw_paths(page, moved)
    z = width / page_w if width else SIZE / side
    page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=True).save(OUT / f"{name}.png")


def bake_brands(path: str) -> None:
    """Each page's logo on its own white ground, cropped with a small margin. Near-white is made pure white, so the
    coin can lay it over its face by multiplying and no square shows around it."""
    import numpy as np

    doc = pymupdf.open(path)
    for name, page in zip(BRANDS, doc):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(6, 6), alpha=False)
        a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(np.int16)
        a = np.where(a.min(axis=2, keepdims=True) >= 238, 255, a)
        ink = np.argwhere(a.min(axis=2) < 230)
        (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
        m = int(max(y1 - y0, x1 - x0) * 0.04)
        y0, x0, y1, x1 = max(0, y0 - m), max(0, x0 - m), min(pix.height, y1 + m), min(pix.width, x1 + m)
        crop = np.ascontiguousarray(a[y0:y1, x0:x1].astype(np.uint8))
        out = pymupdf.Pixmap(pymupdf.csRGB, crop.shape[1], crop.shape[0], crop.tobytes(), False)
        k = BRAND_PX / max(out.width, out.height)
        if k < 1:
            out = pymupdf.Pixmap(out, int(out.width * k), int(out.height * k), None)
        out.save(OUT / f"brand_{name}.png")


def main() -> None:
    doc = pymupdf.open(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    drawings = doc[ICON_PAGE - 1].get_drawings()
    for name, (col, row) in ICONS.items():
        cell = pymupdf.Rect(GRID_X + col * CELL, GRID_Y + row * CELL, GRID_X + (col + 1) * CELL, GRID_Y + (row + 1) * CELL)
        inner = cell + (1, 1, -1, -1)
        paths = []
        for path in drawings:
            r = pymupdf.Rect(path["rect"])
            if not inner.contains(r) or path.get("fill") is None and path.get("color") is None:
                continue
            fill = path.get("fill")
            if fill and all(abs(v - LABEL_INK) < 0.08 for v in fill):  # a caption letter
                continue
            paths.append(path)
        if not paths:
            raise SystemExit(f"nothing found for {name} at {col},{row}")
        bake(paths, name)
    bull = doc[HEADER_PAGE - 1].get_drawings()[0]  # the page header's logo starts with the bull
    bake([bull], "bull")
    print(f"{len(ICONS) + 1} files in {OUT}")
    if len(sys.argv) > 2:
        bake_brands(sys.argv[2])
        print(f"{len(BRANDS)} sub-brands in {OUT}")


if __name__ == "__main__":
    main()
