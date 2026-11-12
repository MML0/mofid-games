#!/usr/bin/env python3
"""Export an editable vector design kit for Adobe Illustrator into hocky/design/.

    python3 tools/export_design_kit.py

Everything is rebuilt as clean SVG from the game's real geometry, colours and current settings
(config/settings.json), so the vectors line up 1:1 with what the game draws. It also writes:
  - LandHockey_DesignKit.pdf  (vector, one artboard per page; rendered by headless Chrome/Edge)
  - outlined versions of the Persian text (needs PyMuPDF: `pip install pymupdf`; skipped if missing)
  - palette (.ase for Adobe apps, .json, .css, .svg), fonts, reference screenshots and the player guide.
Uses only pure-Python parts of the game, so any Python 3.10+ works (no pygame needed).
"""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from land_hockey.config import Config  # noqa: E402
from land_hockey.core.collisions import PaddleShape  # noqa: E402
from land_hockey.core.geometry import Geometry, pp  # noqa: E402
from land_hockey.paths import FONTS_DIR, SETTINGS_PATH  # noqa: E402
from land_hockey.powerups import registry  # noqa: E402
from land_hockey.render.colors import boost, hex_rgb, mix  # noqa: E402

OUT = ROOT / "design"
FONT = "'IRANSansX', sans-serif"
FONT_W = {400: "IRANSansX-Regular", 500: "IRANSansX-Medium", 700: "IRANSansX-Bold", 900: "IRANSansX-Black"}


def hx(c) -> str:
    return "#%02X%02X%02X" % tuple(int(v) for v in c[:3])


def f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def svg(w, h, body, title="", defs="", bg=None) -> str:
    bgr = f'<rect id="Artboard_background" width="{f(w)}" height="{f(h)}" fill="{bg}"/>' if bg else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{f(w)}px" height="{f(h)}px" viewBox="0 0 {f(w)} {f(h)}">\n'
            f'<title>{escape(title)}</title>\n<defs>{defs}</defs>\n{bgr}\n{body}\n</svg>\n')


def is_rtl(s: str) -> bool:
    return any(0x0590 <= ord(ch) <= 0x08FF or 0xFB1D <= ord(ch) <= 0xFEFF for ch in s)


def text(x, y, s, size, color="#FFFFFF", weight=700, anchor="middle", extra="") -> str:
    """Live text. Persian runs get direction="rtl" so punctuation like ! and «» lands on the correct side
    (text-anchor is relative to the writing direction, so start/end are swapped for RTL)."""
    fam = f"'{FONT_W.get(weight, 'IRANSansX-Bold')}', {FONT}"
    if is_rtl(s) and "direction=" not in extra:
        anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
        extra += ' direction="rtl" unicode-bidi="embed"'
    return (f'<text x="{f(x)}" y="{f(y)}" font-family="{fam}" font-weight="{weight}" font-size="{f(size)}" '
            f'fill="{color}" text-anchor="{anchor}" dominant-baseline="central" {extra}>{escape(s)}</text>')


def write(rel: str, content: str) -> Path:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ======================================================================= palette
def palette(cfg) -> dict:
    b = cfg["colors.projection_boost"]
    c = {k: hex_rgb(cfg[f"colors.{k}"]) for k in ("p1", "p2", "neutral_ball", "ball_core", "good", "bad", "neutral",
                                                 "smart", "arena_inner", "arena_outer", "lines", "goal", "wall",
                                                 "wall_hatch", "text", "timer_final")}
    c["p1_glow"], c["p2_glow"] = boost(c["p1"], b), boost(c["p2"], b)
    c["p1_core"], c["p2_core"] = mix(c["p1_glow"], (255, 255, 255), 0.55), mix(c["p2_glow"], (255, 255, 255), 0.55)
    c["wall_glow"] = boost(c["wall"], 0.2)
    c["orb_body"] = (6, 22, 30)
    c["brand_dark_blue"] = (0, 76, 106)
    return c


PALETTE_NAMES = {
    "p1": "Player 1 · Turquoise (brand)", "p1_glow": "Player 1 · glow / trail", "p1_core": "Player 1 · trail core",
    "p2": "Player 2 · Purple (brand)", "p2_glow": "Player 2 · glow / trail", "p2_core": "Player 2 · trail core",
    "neutral_ball": "Ball · untouched", "ball_core": "Ball · core", "good": "Power-up · good (green)",
    "bad": "Power-up · bad (red)", "neutral": "Power-up · neutral (violet)", "smart": "Smart hit · gold",
    "goal": "Goal line (brand red)", "wall": "Bumper wall", "wall_glow": "Bumper wall · glow",
    "wall_hatch": "Wall base / pattern", "arena_inner": "Arena · center", "arena_outer": "Arena · edge",
    "lines": "Arena lines", "text": "Text", "timer_final": "Timer · final seconds", "orb_body": "Orb body",
    "brand_dark_blue": "Mofid dark blue (brand)",
}


def write_ase(path: Path, colors: dict) -> None:
    """Adobe Swatch Exchange (.ase): one group with RGB process colours."""
    def name_block(name):
        u = (name + "\0").encode("utf-16-be")
        return struct.pack(">H", len(u) // 2) + u

    blocks = []
    grp = name_block("Land Hockey")
    blocks.append(struct.pack(">HI", 0xC001, len(grp)) + grp)
    for key, rgb in colors.items():
        payload = name_block(PALETTE_NAMES.get(key, key)) + b"RGB " + struct.pack(
            ">fff", *(v / 255.0 for v in rgb[:3])) + struct.pack(">H", 2)
        blocks.append(struct.pack(">HI", 0x0001, len(payload)) + payload)
    blocks.append(struct.pack(">HI", 0xC002, 0))
    path.write_bytes(b"ASEF" + struct.pack(">HHI", 1, 0, len(blocks)) + b"".join(blocks))


def export_palette(c) -> str:
    cols = {k: c[k] for k in PALETTE_NAMES}
    (OUT / "palette").mkdir(parents=True, exist_ok=True)
    write_ase(OUT / "palette" / "LandHockey_colors.ase", cols)
    write("palette/colors.json", json.dumps({k: {"hex": hx(v), "rgb": list(v[:3]), "name": PALETTE_NAMES[k]}
                                             for k, v in cols.items()}, ensure_ascii=False, indent=2))
    write("palette/colors.css", ":root {\n" + "".join(f"  --{k.replace('_', '-')}: {hx(v)};  /* {PALETTE_NAMES[k]} */\n"
                                                      for k, v in cols.items()) + "}\n")
    sw, cols_n = 150, 5
    rows = (len(cols) + cols_n - 1) // cols_n
    W, H = cols_n * (sw + 30) + 30, rows * (sw + 90) + 100
    body = [text(30, 50, "Land Hockey — colour palette", 28, "#13252E", 900, "start")]
    for i, (k, v) in enumerate(cols.items()):
        x, y = 30 + (i % cols_n) * (sw + 30), 90 + (i // cols_n) * (sw + 90)
        body.append(f'<g id="swatch_{k}"><rect x="{x}" y="{y}" width="{sw}" height="{sw}" rx="18" fill="{hx(v)}" '
                    f'stroke="#DCE7EB"/>' + text(x, y + sw + 22, PALETTE_NAMES[k], 13, "#13252E", 700, "start")
                    + text(x, y + sw + 44, f"{hx(v)}  ·  RGB {v[0]},{v[1]},{v[2]}", 12, "#5C7480", 400, "start") + "</g>")
    content = svg(W, H, "\n".join(body), "Palette", bg="#FFFFFF")
    write("palette/palette.svg", content)
    return content


# ======================================================================= icons
def icon_body(name: str, S: float = 100.0, color: str = "#FFFFFF") -> str:
    """SVG port of render/icons.py draw_icon (same proportions)."""
    c = S / 2
    lw = max(2.0, S * 0.075)
    out = []

    def line(a, b, w=lw):
        out.append(f'<line x1="{f(a[0])}" y1="{f(a[1])}" x2="{f(b[0])}" y2="{f(b[1])}" stroke="{color}" '
                   f'stroke-width="{f(w)}" stroke-linecap="round"/>')

    def poly(pts, fill=True, w=lw):
        d = " ".join(f"{f(x)},{f(y)}" for x, y in pts)
        if fill:
            out.append(f'<polygon points="{d}" fill="{color}"/>')
        else:
            out.append(f'<polygon points="{d}" fill="none" stroke="{color}" stroke-width="{f(w)}" stroke-linejoin="round"/>')

    def pline(pts, w=lw):
        d = " ".join(f"{f(x)},{f(y)}" for x, y in pts)
        out.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{f(w)}" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')

    def circ(x, y, r, w=0):
        if w:
            out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="none" stroke="{color}" stroke-width="{f(w)}"/>')
        else:
            out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{color}"/>')

    def bar(cx, cy, w, h):
        out.append(f'<rect x="{f(cx - w / 2)}" y="{f(cy - h / 2)}" width="{f(w)}" height="{f(h)}" rx="{f(h / 2)}" fill="{color}"/>')

    def head(tip, ang, size):
        l = (tip[0] - size * math.cos(ang - 0.55), tip[1] - size * math.sin(ang - 0.55))
        r = (tip[0] - size * math.cos(ang + 0.55), tip[1] - size * math.sin(ang + 0.55))
        poly([tip, l, r])

    if name == "expand":
        bar(c, c, S * 0.36, S * 0.16)
        for d in (-1, 1):
            tip = (c + d * S * 0.46, c)
            line((c + d * S * 0.22, c), tip)
            head(tip, 0 if d > 0 else math.pi, S * 0.16)
    elif name == "shrink":
        bar(c, c, S * 0.22, S * 0.16)
        for d in (-1, 1):
            tip = (c + d * S * 0.15, c)
            line((c + d * S * 0.46, c), tip)
            head(tip, math.pi if d > 0 else 0, S * 0.15)
        circ(c, c - S * 0.3, S * 0.06)
    elif name == "speed_up":
        poly([(c + S * 0.08, c - S * 0.44), (c - S * 0.2, c + S * 0.04), (c - S * 0.02, c + S * 0.04),
              (c - S * 0.1, c + S * 0.44), (c + S * 0.22, c - S * 0.08), (c + S * 0.03, c - S * 0.08)])
    elif name == "slow_down":
        pline([(c - S * 0.42 + S * 0.84 * k / 30, c - S * 0.08 + S * 0.1 * math.sin(k / 30 * math.tau * 1.5)) for k in range(31)])
        y = c + S * 0.18
        pline([(c - S * 0.16, y), (c, y + S * 0.14), (c + S * 0.16, y)])
    elif name == "chaos":
        for flip in (1, -1):
            pts = [(c - S * 0.4 + S * 0.72 * t, c + flip * S * 0.26 * math.cos(t * math.pi)) for t in (k / 20 for k in range(21))]
            pline(pts)
            a = math.atan2(pts[-1][1] - pts[-3][1], pts[-1][0] - pts[-3][0])
            head((pts[-1][0] + S * 0.06, pts[-1][1]), a, S * 0.16)
    elif name == "double_ball":
        circ(c - S * 0.12, c + S * 0.06, S * 0.2, lw)
        circ(c + S * 0.14, c - S * 0.08, S * 0.2)
    elif name == "trajectory":
        pts = [(c - S * 0.4 + S * 0.62 * t, c + S * 0.36 - S * 0.62 * t + S * 0.25 * math.sin(t * math.pi)) for t in (k / 8 for k in range(9))]
        for x, y in pts[:-1]:
            circ(x, y, S * 0.04)
        circ(c + S * 0.26, c - S * 0.26, S * 0.15, max(2, lw - 1))
        circ(c + S * 0.26, c - S * 0.26, S * 0.05)
    elif name == "dim_ball":
        r = S * 0.34
        circ(c, c, r, lw)
        out.append(f'<path d="M {f(c)} {f(c - r)} A {f(r)} {f(r)} 0 0 0 {f(c)} {f(c + r)} Z" fill="{color}"/>')
    elif name == "shield":
        poly([(c, c - S * 0.42), (c + S * 0.34, c - S * 0.28), (c + S * 0.3, c + S * 0.12), (c, c + S * 0.42),
              (c - S * 0.3, c + S * 0.12), (c - S * 0.34, c - S * 0.28)], fill=False)
        line((c - S * 0.08, c - S * 0.14), (c - S * 0.08, c + S * 0.16))
        line((c + S * 0.08, c - S * 0.14), (c + S * 0.08, c + S * 0.16))
    elif name == "bull":
        circ(c, c + S * 0.1, S * 0.2)
        for d in (-1, 1):
            pts = []
            for k in range(13):
                t = k / 12
                a = math.pi * (0.95 - 0.75 * t)
                pts.append((c + d * (S * 0.14 + S * 0.24 * (1 - math.cos(a)) * 0.6), c - S * 0.02 - S * 0.34 * math.sin(math.pi * t * 0.6)))
            pline(pts, lw + 1)
    elif name == "trophy":
        poly([(c - S * 0.26, c - S * 0.36), (c + S * 0.26, c - S * 0.36), (c + S * 0.2, c - S * 0.02),
              (c + S * 0.08, c + S * 0.1), (c - S * 0.08, c + S * 0.1), (c - S * 0.2, c - S * 0.02)])
        for d in (-1, 1):
            circ(c + d * S * 0.27, c - S * 0.2, S * 0.12, lw)
        bar(c, c + S * 0.2, S * 0.08, S * 0.2)
        bar(c, c + S * 0.36, S * 0.4, S * 0.1)
    else:
        poly([(c, c - S * 0.4), (c + S * 0.3, c), (c, c + S * 0.4), (c - S * 0.3, c)])
    return "\n".join(out)


def orb_body(icon: str, cls: str, c: dict, r: float = 60, icon_scale: float = 0.62, glow=True, uid="o") -> tuple[str, str]:
    """Orb badge centred in a (4r x 4r) box. Returns (defs, body)."""
    col = hx(c["good"] if cls == "good" else c["bad"] if cls == "bad" else c["neutral"])
    C = 2 * r
    defs = (f'<radialGradient id="glow_{uid}" cx="{f(C)}" cy="{f(C)}" r="{f(2 * r)}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{col}" stop-opacity="0.55"/><stop offset="0.5" stop-color="{col}" stop-opacity="0.22"/>'
            f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>')
    lw = max(3.0, r / 4.5)
    parts = []
    if glow:
        parts.append(f'<g id="Glow"><circle cx="{f(C)}" cy="{f(C)}" r="{f(2 * r)}" fill="url(#glow_{uid})"/></g>')
    parts.append(f'<g id="Body"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r)}" fill="{hx(c["orb_body"])}" fill-opacity="0.92"/></g>')
    if cls == "bad":
        dash = 2 * math.pi * r / 14
        parts.append(f'<g id="Ring"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r)}" fill="none" stroke="{col}" stroke-width="{f(lw)}" '
                     f'stroke-dasharray="{f(dash * 0.6)} {f(dash * 0.4)}"/>'
                     f'<circle cx="{f(C)}" cy="{f(C)}" r="{f(r - lw - 2)}" fill="none" stroke="{col}" stroke-opacity="0.35" stroke-width="2"/></g>')
    else:
        parts.append(f'<g id="Ring"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r)}" fill="none" stroke="{col}" stroke-width="{f(lw)}"/></g>')
    isz = 2 * r * icon_scale
    parts.append(f'<g id="Icon" transform="translate({f(C - isz / 2)} {f(C - isz / 2)}) scale({f(isz / 100)})">{icon_body(icon)}</g>')
    parts.append(f'<g id="Lifetime_ring"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r + 7)}" fill="none" stroke="#6E6E6E" stroke-width="2" '
                 f'stroke-dasharray="{f(2 * math.pi * (r + 7) * 0.7)} 9999" transform="rotate(-90 {f(C)} {f(C)})"/></g>')
    return defs, "\n".join(parts)


# ======================================================================= arena geometry → SVG
class Arena:
    def __init__(self, cfg, c):
        self.cfg, self.c, self.g = cfg, c, Geometry(cfg)

    def P(self, r, a_deg):
        g = self.g
        a = math.radians(a_deg)
        return (g.cx + r * math.cos(a), g.cy - r * math.sin(a))

    def arc_d(self, r, a0, a1):
        x0, y0 = self.P(r, a0)
        x1, y1 = self.P(r, a1)
        large = 1 if (a1 - a0) % 360 > 180 else 0
        return f"M {f(x0)} {f(y0)} A {f(r)} {f(r)} 0 {large} 0 {f(x1)} {f(y1)}"

    def band_d(self, r_in, r_out, a0, a1):
        large = 1 if (a1 - a0) % 360 > 180 else 0
        o0, o1, i1, i0 = self.P(r_out, a0), self.P(r_out, a1), self.P(r_in, a1), self.P(r_in, a0)
        return (f"M {f(o0[0])} {f(o0[1])} A {f(r_out)} {f(r_out)} 0 {large} 0 {f(o1[0])} {f(o1[1])} "
                f"L {f(i1[0])} {f(i1[1])} A {f(r_in)} {f(r_in)} 0 {large} 1 {f(i0[0])} {f(i0[1])} Z")

    # ---- layers
    def defs(self) -> str:
        g, c = self.g, self.c
        stops = "".join(f'<stop offset="{f(t)}" stop-color="{hx(mix(c["arena_inner"], c["arena_outer"], t ** 0.8))}"/>'
                        for t in (0, .25, .5, .75, .9, 1))
        face = g.wall_face / g.R
        wall = hx(c["wall"])
        return (f'<radialGradient id="arena_bg" cx="{f(g.cx)}" cy="{f(g.cy)}" r="{f(g.mask_r)}" gradientUnits="userSpaceOnUse">{stops}</radialGradient>'
                f'<radialGradient id="wall_glow" cx="{f(g.cx)}" cy="{f(g.cy)}" r="{f(g.R)}" gradientUnits="userSpaceOnUse">'
                f'<stop offset="{f(face)}" stop-color="{wall}" stop-opacity="0.55"/>'
                f'<stop offset="{f(face + (1 - face) * 0.7)}" stop-color="{wall}" stop-opacity="0.08"/>'
                f'<stop offset="1" stop-color="{wall}" stop-opacity="0"/></radialGradient>')

    def background(self):
        g = self.g
        return (f'<g id="Background"><rect width="{g.W}" height="{g.H}" fill="#000000"/>'
                f'<circle cx="{f(g.cx)}" cy="{f(g.cy)}" r="{f(g.mask_r)}" fill="url(#arena_bg)"/></g>')

    def center_line(self):
        g, c = self.g, self.c
        a = 90 + g.rot
        x0, y0 = self.P(g.wall_face - 8, a)
        x1, y1 = self.P(g.wall_face - 8, a + 180)
        return (f'<g id="Center_line"><line x1="{f(x0)}" y1="{f(y0)}" x2="{f(x1)}" y2="{f(y1)}" stroke="{hx(c["lines"])}" '
                f'stroke-opacity="{f(self.cfg["arena.center_line_alpha"])}" stroke-width="2" stroke-dasharray="16 12"/></g>')

    def tracks(self):
        g, c = self.g, self.c
        out = []
        for i in (0, 1):
            lo, hi = g.paddle_range(i, 0)
            col = hx(c["p1_glow"] if i == 0 else c["p2_glow"])
            out.append(f'<path d="{self.arc_d(g.paddle_back_radius(i), lo, hi)}" fill="none" stroke="{col}" '
                       f'stroke-opacity="{f(min(1, self.cfg["arena.track_alpha"] * 1.6))}" stroke-width="3.2" '
                       f'stroke-linecap="round" stroke-dasharray="0.1 9"/>')
        return '<g id="Paddle_tracks">' + "".join(out) + "</g>"

    def slots(self):
        g, c = self.g, self.c
        r = self.cfg["powerups.orb_radius"] + 5
        return ('<g id="Orb_slots">' + "".join(
            f'<circle cx="{f(g.cx + x)}" cy="{f(g.cy - y)}" r="{f(r)}" fill="none" stroke="{hx(c["lines"])}" '
            f'stroke-opacity="{f(min(1, self.cfg["center_zone.slot_ring_alpha"] * 1.4))}" stroke-width="1.5"/>'
            for x, y in g.slots) + "</g>")

    def rim(self):
        g, c = self.g, self.c
        w = self.cfg["arena.rim_line_width"]
        return (f'<g id="Rim"><circle cx="{f(g.cx)}" cy="{f(g.cy)}" r="{f(g.R)}" fill="none" stroke="{hx(c["lines"])}" '
                f'stroke-opacity="0.18" stroke-width="{f(w * 4)}"/><circle cx="{f(g.cx)}" cy="{f(g.cy)}" r="{f(g.R)}" fill="none" '
                f'stroke="{hx(c["lines"])}" stroke-opacity="0.75" stroke-width="{f(w)}"/></g>')

    def goals(self):
        g, c = self.g, self.c
        lw = self.cfg["goals.line_width"]
        gl = self.cfg["goals.glow"]
        col = hx(c["goal"])
        out = []
        for i, arc in enumerate(g.goals):
            d = self.arc_d(g.R, arc.start, arc.end)
            out.append(f'<g id="Goal_P{i + 1}">'
                       + "".join(f'<path d="{d}" fill="none" stroke="{col}" stroke-opacity="{f(a * gl)}" stroke-width="{f(lw * m)}"/>'
                                 for m, a in ((7, .07), (4, .14), (2.2, .3)))
                       + f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{f(lw)}"/>'
                       + f'<path d="{d}" fill="none" stroke="{hx(mix(c["goal"], (255, 255, 255), .5))}" stroke-opacity="0.8" stroke-width="{f(lw * .3)}"/></g>')
        return '<g id="Goals">' + "".join(out) + "</g>"

    def walls(self):
        g, c = self.g, self.c
        wc, base = hx(c["wall"]), hx(mix(c["wall_hatch"], (0, 0, 0), .45))
        hi = hx(mix(c["wall"], (255, 255, 255), .35))
        t, face = g.t, g.wall_face
        out = []
        for i, w in enumerate(g.walls):
            a0, a1 = w.start, w.end
            parts = [f'<path id="Halo_{i}" d="{self.arc_d(face, a0 + 1, a1 - 1)}" fill="none" stroke="{wc}" stroke-opacity="0.16" '
                     f'stroke-width="{f(t * 2.4)}" stroke-linecap="round"/>',
                     f'<path id="Base_{i}" d="{self.band_d(face, g.R, a0, a1)}" fill="{base}" fill-opacity="0.92"/>',
                     f'<path id="Energy_{i}" d="{self.band_d(face, g.R, a0, a1)}" fill="url(#wall_glow)"/>']
            diamonds = []
            a = a0 + 5
            mid = face + t * 0.55
            while a < a1 - 3:
                cx, cy = self.P(mid, a)
                ar = math.radians(a)
                ux, uy = math.cos(ar), -math.sin(ar)
                vx, vy = -uy, ux
                s1, s2 = t * .24, t * .38
                pts = [(cx + ux * s1, cy + uy * s1), (cx + vx * s2, cy + vy * s2), (cx - ux * s1, cy - uy * s1), (cx - vx * s2, cy - vy * s2)]
                diamonds.append('<polygon points="' + " ".join(f"{f(x)},{f(y)}" for x, y in pts) + f'" fill="{wc}" fill-opacity="0.28"/>')
                a += 5
            parts.append(f'<g id="Pattern_{i}">' + "".join(diamonds) + "</g>")
            parts.append(f'<path id="Face_glow_{i}" d="{self.arc_d(face, a0, a1)}" fill="none" stroke="{wc}" stroke-opacity="0.3" stroke-width="7"/>')
            parts.append(f'<path id="Face_line_{i}" d="{self.arc_d(face, a0, a1)}" fill="none" stroke="{hi}" stroke-width="2.8"/>')
            parts.append(f'<path id="Outer_edge_{i}" d="{self.arc_d(g.R - .5, a0, a1)}" fill="none" stroke="{wc}" stroke-opacity="0.45" stroke-width="1"/>')
            for j, a in enumerate((a0, a1)):
                x, y = self.P(g.R - t / 2, a)
                parts.append(f'<g id="Emitter_{i}_{j}"><circle cx="{f(x)}" cy="{f(y)}" r="{f(t * 1.5)}" fill="{wc}" fill-opacity="0.12"/>'
                             f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(t * .78)}" fill="{base}"/>'
                             f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(t * .78)}" fill="none" stroke="{wc}" stroke-opacity="0.9" stroke-width="1.6"/>'
                             f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(t * .3)}" fill="{hi}"/></g>')
            out.append(f'<g id="Wall_{"top" if i == 0 else "bottom"}">' + "".join(parts) + "</g>")
        return '<g id="Bumper_walls">' + "".join(out) + "</g>"

    def paddle(self, i, ratio=None, local=False):
        cfg, g, c = self.cfg, self.g, self.c
        w = pp(cfg, i, "width")
        ratio = pp(cfg, i, "shape_ratio") if ratio is None else ratio
        lo, hi = g.paddle_range(i, w)
        th = (lo + hi) / 2
        sh = PaddleShape(th, g.paddle_back_radius(i), w, ratio)
        pts = [(g.cx + x, g.cy - y) for x, y in sh.outline(48)]
        inner = [(g.cx + x, g.cy - y) for x, y in sh.outline(48, inset=6.0)][3:-3]
        team, glow = (c["p1"], c["p1_glow"]) if i == 0 else (c["p2"], c["p2_glow"])
        if local:  # move to a tight local box
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ox, oy = min(xs) - 24, min(ys) - 24
            pts = [(x - ox, y - oy) for x, y in pts]
            inner = [(x - ox, y - oy) for x, y in inner]
        d = "M " + " L ".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"
        dd = "M " + " L ".join(f"{f(x)} {f(y)}" for x, y in inner)
        body = (f'<g id="Paddle_P{i + 1}">'
                f'<path id="Glow" d="{d}" fill="none" stroke="{hx(glow)}" stroke-opacity="0.22" stroke-width="16" stroke-linejoin="round"/>'
                f'<path id="Fill" d="{d}" fill="{hx(mix(team, (0, 0, 0), .38))}"/>'
                f'<path id="Inner_highlight" d="{dd}" fill="none" stroke="{hx(mix(team, (255, 255, 255), .12))}" stroke-width="5" stroke-linecap="round"/>'
                f'<path id="Edge" d="{d}" fill="none" stroke="{hx(glow)}" stroke-width="3.5" stroke-linejoin="round"/>'
                f'<path id="Edge_highlight" d="{d}" fill="none" stroke="{hx(mix(glow, (255, 255, 255), .55))}" stroke-width="1.2" stroke-linejoin="round"/></g>')
        if local:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return body, max(xs) + 24, max(ys) + 24
        return body

    def hud(self):
        g, c, cfg = self.g, self.c, self.cfg
        (tx, ty) = g.timer_pos
        out = [f'<g id="Timer">' + text(g.cx + tx, g.cy - ty, "60", cfg["hud.timer_size"], hx(c["text"]), 900) + "</g>"]
        for i, val in ((0, "3"), (1, "5")):
            x, y = g.score_pos[i]
            col = hx(c["p1_glow"] if i == 0 else c["p2_glow"])
            out.append(f'<g id="Score_P{i + 1}">' + text(g.cx + x, g.cy - y, val, cfg["hud.score_size"], col, 900) + "</g>")
        return '<g id="HUD">' + "".join(out) + "</g>"

    def mask(self):
        g = self.g
        return (f'<g id="Mask_outside_circle"><path fill="#000000" fill-rule="evenodd" d="M0 0 H{g.W} V{g.H} H0 Z '
                f'M {f(g.cx - g.mask_r)} {f(g.cy)} a {f(g.mask_r)} {f(g.mask_r)} 0 1 0 {f(2 * g.mask_r)} 0 '
                f'a {f(g.mask_r)} {f(g.mask_r)} 0 1 0 {f(-2 * g.mask_r)} 0 Z"/></g>')


def ball_body(c, owner, r=14, smart=False, uid="b") -> tuple[str, str, float]:
    col = c["neutral_ball"] if owner is None else (c["p1_glow"] if owner == 0 else c["p2_glow"])
    ring = c["smart"] if smart else col
    G = r * 3.0
    C = G
    defs = (f'<radialGradient id="bglow_{uid}" cx="{f(C)}" cy="{f(C)}" r="{f(G)}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{hx(col)}" stop-opacity="0.85"/><stop offset="0.35" stop-color="{hx(col)}" stop-opacity="0.35"/>'
            f'<stop offset="1" stop-color="{hx(col)}" stop-opacity="0"/></radialGradient>')
    body = (f'<g id="Glow"><circle cx="{f(C)}" cy="{f(C)}" r="{f(G)}" fill="url(#bglow_{uid})"/></g>'
            f'<g id="Ring"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r + 3)}" fill="none" stroke="{hx(ring)}" stroke-width="3"/></g>'
            f'<g id="Core"><circle cx="{f(C)}" cy="{f(C)}" r="{f(r)}" fill="{hx(c["ball_core"])}"/>'
            f'<circle cx="{f(C + r * .25)}" cy="{f(C + r * .25)}" r="{f(r * .45)}" fill="{hx(mix(c["ball_core"], col, .35))}" fill-opacity="0.8"/></g>')
    return defs, body, 2 * G


def trail_body(c, owner, cfg, length=260.0, r=14, uid="t") -> tuple[str, str, float, float]:
    """Comet trail pointing right (head at the right end). Returns (defs, body, w, h)."""
    col = c["p1_glow"] if owner == 0 else c["p2_glow"]
    core = c["p1_core"] if owner == 0 else c["p2_core"]
    head, fall = cfg["trails.head_size"], cfg["trails.falloff"]
    W, H = length + 4 * r, 8 * r
    cy = H / 2
    hx0 = length + r * 1.5

    def shape(scale):
        top, bot = [], []
        n = 40
        for k in range(n + 1):
            age = k / n
            kk = (1 - age) ** fall
            half = r * head * (0.22 + 0.78 * kk) * scale
            x = hx0 - length * age
            top.append((x, cy - half))
            bot.append((x, cy + half))
        pts = top + bot[::-1]
        return "M " + " L ".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"

    defs = (f'<linearGradient id="tg_{uid}" x1="{f(hx0 - length)}" y1="0" x2="{f(hx0)}" y2="0" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{hx(col)}" stop-opacity="0"/><stop offset="0.55" stop-color="{hx(col)}" stop-opacity="0.35"/>'
            f'<stop offset="1" stop-color="{hx(col)}" stop-opacity="0.9"/></linearGradient>'
            f'<linearGradient id="tc_{uid}" x1="{f(hx0 - length * .6)}" y1="0" x2="{f(hx0)}" y2="0" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{hx(core)}" stop-opacity="0"/><stop offset="1" stop-color="{hx(core)}" stop-opacity="1"/></linearGradient>')
    sparks = []
    for k in range(14):
        t = (k * 0.618) % 1.0
        x = hx0 - length * (0.1 + 0.8 * t)
        y = cy + math.sin(k * 2.3) * r * (0.4 + 1.2 * t)
        sparks.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(1 + 1.2 * (1 - t))}" fill="{hx(core)}" fill-opacity="{f(0.9 * (1 - t))}"/>')
    body = (f'<g id="Glow"><path d="{shape(2.4)}" fill="url(#tg_{uid})" opacity="0.45"/></g>'
            f'<g id="Trail"><path d="{shape(1.0)}" fill="url(#tg_{uid})"/></g>'
            f'<g id="Core"><path d="{shape(0.42)}" fill="url(#tc_{uid})"/></g>'
            f'<g id="Sparkles">' + "".join(sparks) + "</g>")
    return defs, body, W, H


# ======================================================================= exports
def export_all() -> None:
    cfg = Config.load(SETTINGS_PATH)
    c = palette(cfg)
    A = Arena(cfg, c)
    g = A.g
    W, H = g.W, g.H
    types = registry.all_types()
    if OUT.exists():
        for sub in ("svg", "palette", "text", "pdf"):
            shutil.rmtree(OUT / sub, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    sheets = []  # (title, svg) pages for the PDF kit

    # ---- arena: full layered artboard + each layer on its own aligned artboard
    paddle_layers = '<g id="Paddles">' + A.paddle(0) + A.paddle(1) + "</g>"
    sx, sy = g.slots[0] if g.slots else (0, 120)
    od, ob = orb_body("expand", "good", c, cfg["powerups.orb_radius"], uid="arena")
    orb_layer = (f'<g id="Sample_orb" transform="translate({f(g.cx + sx - 2 * cfg["powerups.orb_radius"])} '
                 f'{f(g.cy - sy - 2 * cfg["powerups.orb_radius"])})">{ob}</g>')
    bd, bb, bsz = ball_body(c, 0, cfg["ball.radius"], uid="arena")
    td, tb, tw, th = trail_body(c, 0, cfg, 240, cfg["ball.radius"], uid="arena")
    bx, by = g.cx - 60, g.cy + 70
    ball_layer = (f'<g id="Sample_ball_and_trail"><g transform="translate({f(bx - tw + 2.5 * cfg["ball.radius"])} {f(by - th / 2)})">{tb}</g>'
                  f'<g transform="translate({f(bx - bsz / 2)} {f(by - bsz / 2)})">{bb}</g></g>')
    defs = A.defs() + od + bd + td
    layers = [A.background(), A.center_line(), A.tracks(), A.slots(), A.rim(), A.goals(), A.walls(), A.hud(),
              orb_layer, ball_layer, paddle_layers, A.mask()]
    full = svg(W, H, "\n".join(layers), "Land Hockey — arena (all layers)", defs)
    write("svg/arena/arena_full.svg", full)
    sheets.append(("Arena — all layers", full))
    for name, layer in (("background", A.background()), ("center_line", A.center_line()), ("paddle_tracks", A.tracks()),
                        ("orb_slots", A.slots()), ("rim", A.rim()), ("goal_lines", A.goals()), ("bumper_walls", A.walls()),
                        ("hud_timer_scores", A.hud()), ("paddles_in_place", paddle_layers), ("mask_outside_circle", A.mask())):
        write(f"svg/arena/layers/{name}.svg", svg(W, H, layer, f"Arena layer — {name}", A.defs()))

    # ---- paddles (local)
    for i in (0, 1):
        for label, ratio in (("current", None), ("semicircle", 1.0)):
            body, w2, h2 = A.paddle(i, ratio, local=True)
            write(f"svg/elements/paddle_P{i + 1}_{label}.svg", svg(w2, h2, body, f"Paddle P{i + 1} ({label} shape)"))
    # ---- balls and trails
    for owner, label in ((None, "neutral"), (0, "P1"), (1, "P2")):
        d, b, s = ball_body(c, owner, cfg["ball.radius"], uid=label)
        write(f"svg/elements/ball_{label}.svg", svg(s, s, b, f"Ball ({label})", d))
    d, b, s = ball_body(c, 0, cfg["ball.radius"], smart=True, uid="smart")
    write("svg/elements/ball_smart_gold_ring.svg", svg(s, s, b, "Ball (smart hit)", d))
    for owner, label in ((0, "P1"), (1, "P2")):
        d, b, w2, h2 = trail_body(c, owner, cfg, 300, cfg["ball.radius"], uid=label)
        write(f"svg/elements/trail_comet_{label}.svg", svg(w2, h2, b, f"Comet trail ({label})", d))
    # ---- icons + orbs
    icon_names = {tid: t.icon for tid, t in types.items()}
    icon_names["trophy"] = "trophy"
    for tid, ic in icon_names.items():
        write(f"svg/icons/{tid}.svg", svg(100, 100, f'<g id="Icon_{tid}">{icon_body(ic)}</g>', f"Icon — {tid} (white, 100×100)"))
        write(f"svg/icons/{tid}_dark.svg", svg(100, 100, f'<g id="Icon_{tid}">{icon_body(ic, color="#13252E")}</g>', f"Icon — {tid} (dark)"))
    orb_r = 60
    orbs_sheet = []
    for k, (tid, t) in enumerate(types.items()):
        cls = cfg[f"powerups.types.{tid}.class"]
        d, b = orb_body(t.icon, cls, c, orb_r, cfg["powerups.icon_scale"], uid=tid)
        write(f"svg/orbs/orb_{tid}.svg", svg(4 * orb_r, 4 * orb_r, b, f"Orb — {tid} ({cls})", d))
        for alt in ("good", "bad"):
            if alt != cls:
                d2, b2 = orb_body(t.icon, alt, c, orb_r, cfg["powerups.icon_scale"], uid=f"{tid}_{alt}")
                write(f"svg/orbs/variants/orb_{tid}_{alt}.svg", svg(4 * orb_r, 4 * orb_r, b2, f"Orb — {tid} ({alt})", d2))
        x, y = 40 + (k % 5) * 260, 120 + (k // 5) * 330
        orbs_sheet.append((d, f'<g id="orb_{tid}" transform="translate({x} {y})">{b}'
                              + text(2 * orb_r, 4 * orb_r + 20, t.name, 15, "#FFFFFF", 700)
                              + text(2 * orb_r, 4 * orb_r + 44, f"{tid} · {cls}", 12, "#8FB3C0", 400) + "</g>"))
    sheet = svg(1340, 820, text(40, 60, "Power-up orbs", 30, "#FFFFFF", 900, "start") + "".join(b for _, b in orbs_sheet),
                "Power-up orbs", "".join(d for d, _ in orbs_sheet), bg="#06202C")
    write("svg/orbs/_all_orbs_sheet.svg", sheet)
    sheets.append(("Power-up orbs", sheet))
    icons_sheet = [text(40, 60, "Icons (white on dark, 100×100 artboards)", 30, "#FFFFFF", 900, "start")]
    for k, (tid, ic) in enumerate(icon_names.items()):
        x, y = 50 + (k % 6) * 210, 120 + (k // 6) * 230
        icons_sheet.append(f'<g id="icon_{tid}"><rect x="{x}" y="{y}" width="150" height="150" rx="24" fill="#0B3142"/>'
                           f'<g transform="translate({x + 25} {y + 25}) scale(1)">{icon_body(ic)}</g>'
                           + text(x + 75, y + 175, tid, 14, "#8FB3C0", 400) + "</g>")
    sheet = svg(1340, 620, "".join(icons_sheet), "Icons", bg="#06202C")
    write("svg/icons/_all_icons_sheet.svg", sheet)
    sheets.append(("Icons", sheet))

    # ---- elements sheet
    parts, defs = [text(40, 60, "Paddles, balls and trails", 30, "#FFFFFF", 900, "start")], ""
    x = 60
    for i in (0, 1):
        for ratio in (None, 1.0):
            body, w2, h2 = A.paddle(i, ratio, local=True)
            parts.append(f'<g transform="translate({x} 110)">{body}</g>')
            parts.append(text(x + w2 / 2, 110 + h2 + 20, f"P{i + 1} · {'current' if ratio is None else 'semicircle'}", 13, "#8FB3C0", 400))
            x += w2 + 50
    x = 60
    for owner, label in ((None, "neutral"), (0, "P1"), (1, "P2")):
        d, b, s = ball_body(c, owner, 22, uid="sheet" + label)
        defs += d
        parts.append(f'<g transform="translate({x} 380)">{b}</g>' + text(x + s / 2, 380 + s + 16, f"ball · {label}", 13, "#8FB3C0", 400))
        x += s + 40
    for k, (owner, label) in enumerate(((0, "P1"), (1, "P2"))):
        d, b, w2, h2 = trail_body(c, owner, cfg, 320, 16, uid="sheet" + label)
        defs += d
        parts.append(f'<g transform="translate({560} {330 + k * 140})">{b}</g>' + text(560 + w2 / 2, 330 + k * 140 + h2 + 8, f"comet trail · {label}", 13, "#8FB3C0", 400))
    sheet = svg(1100, 650, "".join(parts), "Elements", defs, bg="#06202C")
    write("svg/elements/_all_elements_sheet.svg", sheet)
    sheets.append(("Paddles, balls and trails", sheet))

    # ---- palette
    sheets.append(("Palette", export_palette(c)))

    # ---- typography and Persian messages (live text)
    typo = [text(1040, 70, "تایپوگرافی لند هاکی", 34, "#13252E", 900, "end"),
            text(1040, 190, "لند هاکی", 110, "#004C6A", 900, "end"),
            text(40, 190, "LAND HOCKEY", 40, "#00A796", 700, "start", 'letter-spacing="10"'),
            text(1040, 300, "IRANSansX Black — عنوان‌ها و اعداد", 22, "#5C7480", 400, "end"),
            text(1040, 380, "0 1 2 3 4 5 6 7 8 9", 64, "#13252E", 900, "end", 'direction="ltr"'),
            text(1040, 460, "اعداد بازی همیشه لاتین هستند (60، 7، 3·2·1).", 22, "#5C7480", 400, "end"),
            text(1040, 540, "IRANSansX Bold — پیام‌ها: «پدلت بزرگ شد!»", 30, "#13252E", 700, "end"),
            text(1040, 610, "IRANSansX Regular — متن توضیحی و راهنما.", 26, "#13252E", 400, "end")]
    typo_svg = svg(1080, 680, "".join(typo), "Typography", bg="#FFFFFF")
    write("text/typography_live.svg", typo_svg)
    msgs = []
    for path, p in Config().schema.items():
        if path.startswith("text.") and p.kind == "str" and cfg[path]:
            msgs.append((path, cfg[path]))
    for tid in types:
        for key in ("toast_collector", "toast_opponent"):
            v = cfg[f"powerups.types.{tid}.{key}"]
            if v:
                msgs.append((f"powerups.types.{tid}.{key}", v))
    rows = []
    for k, (key, val) in enumerate(msgs):
        y = 120 + k * 58
        rows.append(f'<g id="msg_{key.replace(".", "_")}">' + text(1040, y, val, 30, "#13252E", 700, "end")
                    + text(40, y, key, 13, "#8AA0AA", 400, "start", 'direction="ltr"') + "</g>")
    msg_svg = svg(1080, 140 + len(msgs) * 58, text(1040, 50, "همه‌ی پیام‌های فارسی بازی", 32, "#004C6A", 900, "end") + "".join(rows),
                  "Persian messages", bg="#FFFFFF")
    write("text/persian_messages_live.svg", msg_svg)
    write("text/persian_messages.json", json.dumps(dict(msgs), ensure_ascii=False, indent=2))
    lockup = svg(1080, 520, text(540, 200, "لند هاکی", 170, "#FFFFFF", 900)
                 + f'<rect x="420" y="330" width="240" height="8" rx="4" fill="{hx(c["p1"])}"/>'
                 + text(540, 400, "LAND HOCKEY", 46, hx(c["p1_glow"]), 700, "middle", 'letter-spacing="14"'),
                 "Title lockup", bg="#062A3A")
    write("text/title_lockup_live.svg", lockup)
    sheets.append(("Title lockup", lockup))
    sheets.append(("Typography", typo_svg))
    sheets.append(("Persian messages", msg_svg))

    # ---- fonts, reference screenshots, guide
    (OUT / "fonts").mkdir(parents=True, exist_ok=True)
    for ttf in FONTS_DIR.glob("*.ttf"):
        shutil.copy2(ttf, OUT / "fonts" / ttf.name)
    guide = ROOT / "docs" / "LandHockey_Guide_FA.pdf"
    if guide.exists():
        (OUT / "guide").mkdir(exist_ok=True)
        shutil.copy2(guide, OUT / "guide" / guide.name)
    venv_py = ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        ref = OUT / "reference_screenshots"
        shutil.rmtree(ref, ignore_errors=True)
        subprocess.run([str(venv_py), str(ROOT / "main.py"), "--screenshot-states", str(ref), "--seed", "21"],
                       env={"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "PATH": "/usr/bin:/bin"},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    build_pdf(sheets)
    print(f"design kit written to {OUT}")


# ======================================================================= PDF kit (+ outlined text)
BROWSERS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "google-chrome", "chromium"]


def build_pdf(sheets) -> None:
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if browser is None:
        print("Chrome/Edge not found: skipping the PDF kit")
        return
    faces = "".join(f'@font-face{{font-family:"{fam}";src:url("../fonts/{fam}.ttf")}}'
                    f'@font-face{{font-family:"IRANSansX";font-weight:{w};src:url("../fonts/{fam}.ttf")}}'
                    for w, fam in FONT_W.items())
    pages = []
    for title, s in sheets:
        body = s.split("?>", 1)[1]
        pages.append(f'<section><div class="t">{escape(title)}</div>{body}</section>')
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{faces}'
            '@page{size:1200px 1200px;margin:0} body{margin:0;background:#0A1F29;font-family:"IRANSansX"}'
            'section{width:1200px;height:1200px;display:flex;flex-direction:column;align-items:center;justify-content:center;'
            'break-after:page;gap:18px} section svg{max-width:1120px;max-height:1080px;width:auto;height:auto}'
            '.t{color:#8FB3C0;font-size:18px;letter-spacing:2px}</style></head><body>'
            + "".join(pages) + "</body></html>")
    tmp = OUT / "pdf" / "_kit.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(html, encoding="utf-8")
    pdf = OUT / "LandHockey_DesignKit.pdf"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                    "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", tmp.as_uri()],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(OUT / "pdf", ignore_errors=True)
    try:
        import pymupdf
    except ImportError:
        print("PyMuPDF not installed: skipping outlined-text SVGs (pip install pymupdf)")
        return
    doc = pymupdf.open(pdf)
    titles = [t for t, _ in sheets]
    for name, page_title in (("typography_outlined.svg", "Typography"), ("persian_messages_outlined.svg", "Persian messages")):
        if page_title in titles and titles.index(page_title) < len(doc):
            page = doc[titles.index(page_title)]
            (OUT / "text" / name).write_text(page.get_svg_image(text_as_path=True), encoding="utf-8")
    if "Title lockup" in titles:
        page = doc[titles.index("Title lockup")]
        (OUT / "text" / "title_lockup_outlined.svg").write_text(page.get_svg_image(text_as_path=True), encoding="utf-8")


if __name__ == "__main__":
    export_all()
