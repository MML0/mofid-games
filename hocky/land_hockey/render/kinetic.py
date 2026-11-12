"""Kinetic typography backdrop: a Python port of the Brik "circle wave kinetic typography" sketch.

The field follows the sketch's draw() exactly. For every grid cell, with d the distance to the wave center:

    stretch = map(sin(phase + d * frequency), -1, 1, min_stretch, max_stretch)   horizontal glyph scale
    color   = palette[(floor(d / ring_width) + swap_shift) % 3]                  ring color
    char    = chars[floor(d / (ring_width / 2)) % len(chars)]                    ring letter

The game adds a second sine that only touches opacity, a fade toward the rim, and letter rings independent of the
color rings. Two deliberate changes make it animatable. `phase` accumulates speed * 60 * dt, because the sketch's
frameCount * speed jumps whenever speed changes. And distances are measured in `unit` scaled pixels, so a
slider means the same thing on the game canvas as on the sketch's canvas.

KineticField draws one frame from KineticParams. KineticBackdrop is the director: it holds a base look for each
game state and plays MOMENTS, keyframe tracks over the same sliders, on goals, countdown beats and match end.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pygame

from ..paths import FONTS_DIR
from .colors import boost, hex_rgb, mix, scale

SITE_CANVAS = (1080, 1350)  # the sketch's canvas in the reference page; sliders are in these pixels
REF_SIZE = 1207.0  # its geometric mean: game canvases scale distances by REF_SIZE / arena diameter
TICKS = 60.0  # the sketch counts frames at 60 fps

BRAND_MARKS = "•+-×/"  # the five identity marks from the brand book's graphics page, drawn as vectors
MARK_ALIASES = str.maketrans({"●": "•", "−": "-", "–": "-"})
MARK_SCALE = 0.62  # marks sit at cap height
STRIP = re.compile("[‌‍ً-ٟ!؟?.،,:؛]")


def is_rtl_char(ch: str) -> bool:
    return "֐" <= ch <= "ࣿ" or "יִ" <= ch <= "ﻼ"


def clean_chars(text: str, space_marks: bool = True) -> str:
    """Prepare a string for the rings: upper case, no joiners or punctuation, spaces become brand dots."""
    s = STRIP.sub("", str(text or "")).upper().translate(MARK_ALIASES)
    if space_marks:
        s = s.replace(" ", "•")
    return s or "•"


@dataclass
class KineticParams:
    """Every control of the sketch, under the same names and units, plus the extras the moments animate."""

    density: float = 28
    chars: str = "MICAEL RENDER"
    speed: float = 0.06
    frequency: float = 0.03
    min_stretch: float = 0.25
    max_stretch: float = 2.6
    ring_width: float = 75
    colors: tuple = ((0, 255, 184), (0, 248, 179), (205, 236, 216))
    color_swap: bool = False
    swap_interval: float = 140
    font_scale: float = 0.9  # the sketch fixes textSize at spacingY * 0.9
    opacity: float = 1.0
    cx: float = 0.0  # wave center, as a fraction of the half canvas (0, 0 = middle)
    cy: float = 0.0
    reveal_outer: float = 1.0  # only rings inside this fraction of the field are drawn
    reveal_inner: float = 0.0  # and outside this one: together they make an expanding annulus
    wipe: float = 0.0  # 0..1: the next text, `chars_next`, has spread this far from the center
    chars_next: str = ""
    split: float = 0.0  # 0..1: the far side of split_dir takes side_colors / side_chars and calms down
    split_dir: tuple = (1.0, 0.0)
    side_colors: tuple = ()
    side_chars: str = ""
    side_stretch: float = 0.8
    max_overlap: float = 0.0  # no letter grows wider than this many cells; 0 = no limit, as in the sketch
    letter_width: float = 0.0  # width of one letter ring; 0 = half a color ring, as in the sketch
    op_speed: float = 0.025  # the opacity wave: a second sine with its own speed and frequency
    op_frequency: float = 0.003
    op_min: float = 1.0  # 1 and 1 switch it off, as in the sketch
    op_max: float = 1.0
    op_sharpness: float = 1.0  # above 1 the valleys last longer and the peaks are shorter, like a pulse
    edge_start: float = 0.0  # letters fade from this fraction of the radius...
    edge_end: float = 0.0  # ...to nothing at this one; equal values switch the fade off


FLOAT_PARAMS = ("density", "speed", "frequency", "min_stretch", "max_stretch", "ring_width", "font_scale", "opacity",
                "cx", "cy", "reveal_outer", "reveal_inner", "split", "letter_width", "op_speed", "op_frequency",
                "op_min", "op_max")
SNAP_PARAMS = ("density", "ring_width", "letter_width")  # these never glide: every step would shift the whole grid
REVEAL_SOFTNESS = 70.0  # reference pixels over which the reveal's edges fade
EDGE_TIGHTEN = np.clip((np.arange(256, dtype=np.float32) - 40.0) * 255.0 / 150.0, 0, 255).astype(np.uint8)  # alpha curve


def latin_font_path(name: str = "") -> str | None:
    """A named font from assets/fonts, else pygame's bundled FreeSansBold, a Helvetica-style bold.

    The file is named explicitly because Font(None, size) silently renders the default font at 0.6875 * size."""
    p = FONTS_DIR / name if name else Path(pygame.__file__).parent / pygame.font.get_default_font()
    return str(p) if p.exists() else None


class KineticField:
    """Draws the grid. Stretched glyphs are cached by exact pixel width, so a frame is one Surface.blits call."""

    MAX_SPRITES = 9000

    def __init__(self, size, unit: float = 1.0, rotation: float = 0.0, clip=None,
                 latin_font: str = "", persian_font: str = "IRANSansX-Black.ttf", budget: int | None = None,
                 ink_centered: bool = False):
        self.size = (int(size[0]), int(size[1]))
        self.unit = float(unit)
        self.rotation = float(rotation) % 360
        self.clip = clip  # (cx, cy, r): cells outside this circle are skipped (the arena mask hides them anyway)
        # New sprites allowed per frame, and with it coarser widths. None draws every width exactly, like the sketch.
        # In the game a moment can hit a cold cache; a few cells appearing a frame late beats a dropped frame.
        self.budget = budget
        # True centers each letter's visible shape on its cell and keeps one cell on the exact middle of the field.
        # False keeps the sketch's alignment on the font's line box, which sits a little off center.
        self.ink_centered = ink_centered
        # Ink-centered glyphs (the game) are built at 4x and reduced, then their edges are tightened, so small letters
        # stay crisp on the floor. The site view keeps the sketch's plain 2x glyphs.
        self.oversample = 4 if ink_centered else 2
        self.latin_font, self.persian_font = latin_font, persian_font
        self.phase = 0.0
        self.op_phase = 0.0
        self.frames = 0.0
        self._alpha_used = False
        self._fonts: dict = {}
        self._glyph_ids: dict[str, int] = {}
        self._glyphs: list[str] = []
        self._mids: dict = {}
        self._widths: dict[int, np.ndarray] = {}
        self._sprites: dict[int, dict] = {}
        self._sprite_n = 0
        self._cids: dict[tuple, int] = {}
        self._colors: list[tuple] = []
        self._grids: dict[int, tuple] = {}
        self._dist_key = None
        self._dist = None
        self._rng = np.random.default_rng(7)

    # ------------------------------------------------------------------ time
    def advance(self, dt: float, p: KineticParams) -> None:
        self.phase = (self.phase + p.speed * TICKS * dt) % (2 * math.pi * 1024)
        self.op_phase = (self.op_phase + p.op_speed * TICKS * dt) % (2 * math.pi * 1024)
        self.frames += TICKS * dt

    # ------------------------------------------------------------------ glyphs
    def _font(self, ch: str, px: int) -> pygame.font.Font:
        rtl = is_rtl_char(ch)
        k = (rtl, px)
        f = self._fonts.get(k)
        if f is None:
            path = str(FONTS_DIR / self.persian_font) if rtl else latin_font_path(self.latin_font)
            try:
                f = pygame.font.Font(path, px)
            except (FileNotFoundError, OSError, pygame.error):
                f = pygame.font.Font(None, px)
            if rtl and hasattr(f, "set_script"):
                try:
                    f.set_script("Arab")
                    f.set_direction(pygame.DIRECTION_RTL)
                except (AttributeError, pygame.error):
                    pass
            self._fonts[k] = f
        return f

    @staticmethod
    def _mark(ch: str, side: int) -> pygame.Surface:
        """A brand mark in white on a transparent square. Proportions come from the brand book: a 3x3 grid."""
        n = side * 3
        u = n / 3.0
        s = pygame.Surface((n, n), pygame.SRCALPHA)
        white = (255, 255, 255, 255)
        if ch == "•":
            pygame.draw.circle(s, white, (n / 2, n / 2), n / 2)
        elif ch == "-":
            s.fill(white, (0, u, n, u))
        elif ch == "+":
            s.fill(white, (0, u, n, u))
            s.fill(white, (u, 0, u, n))
        elif ch in ("/", "×"):
            t = n * 0.25  # half of the bar's corner cut
            pygame.draw.polygon(s, white, [(0, n - t), (t, n), (n, t), (n - t, 0)])
            if ch == "×":
                pygame.draw.polygon(s, white, [(0, t), (t, 0), (n, n - t), (n - t, n)])
        return pygame.transform.smoothscale(s, (side, side))

    def _gid(self, ch: str) -> int:
        i = self._glyph_ids.get(ch)
        if i is None:
            i = len(self._glyphs)
            self._glyph_ids[ch] = i
            self._glyphs.append(ch)
            self._widths.clear()
        return i

    def _mid(self, gid: int, px: int) -> tuple:
        """White glyph at several times the font size, trimmed vertically: (surface, advance width at px, vertical offset)."""
        k = (gid, px)
        m = self._mids.get(k)
        if m is None:
            ch = self._glyphs[gid]
            if ch == " ":
                m = (None, 0.0, 0.0)
            elif ch in BRAND_MARKS:
                side = max(2, int(px * MARK_SCALE) * self.oversample)
                m = (self._mark(ch, side), side / self.oversample, 0.0)
            else:
                full = self._font(ch, px * self.oversample).render(ch, True, (255, 255, 255))
                box = full.get_bounding_rect()
                if box.w == 0 or box.h == 0:
                    m = (None, 0.0, 0.0)
                elif self.ink_centered:
                    m = (full.subsurface(box).copy(), box.w / self.oversample, 0.0)
                else:
                    trim = pygame.Rect(0, box.y, full.get_width(), box.h)
                    # p5's CENTER middle-aligns on the line box; caps then sit a touch above true center
                    m = (full.subsurface(trim).copy(), full.get_width() / 2.0,
                         (box.centery - full.get_height() / 2.0) / 2.0)
            self._mids[k] = m
        return m

    def _width_table(self, px: int) -> np.ndarray:
        t = self._widths.get(px)
        if t is None or len(t) != len(self._glyphs):
            t = np.array([self._mid(i, px)[1] for i in range(len(self._glyphs))], dtype=np.float32)
            self._widths[px] = t
        return t

    def _cid(self, rgb) -> int:
        rgb = tuple(int(v) for v in rgb[:3])
        i = self._cids.get(rgb)
        if i is None:
            i = len(self._colors)
            self._cids[rgb] = i
            self._colors.append(rgb)
        return i

    def _make_sprite(self, key: int, px: int) -> tuple:
        w, cid, gid = key & 0xFFF, (key >> 12) & 0xFFF, key >> 24
        mid, _, voff = self._mid(gid, px)
        s = pygame.transform.smoothscale(mid, (max(1, w), max(1, mid.get_height() // self.oversample)))
        s.fill(self._colors[cid] + (255,), special_flags=pygame.BLEND_RGBA_MULT)
        if self.ink_centered:
            alpha = pygame.surfarray.pixels_alpha(s)
            alpha[:] = EDGE_TIGHTEN[alpha]
            del alpha
        if self.rotation:
            a = math.radians(self.rotation)
            s = pygame.transform.rotozoom(s, self.rotation, 1.0)  # same direction as Renderer._rot
            ox, oy = voff * math.sin(a), voff * math.cos(a)
        else:
            ox, oy = 0.0, voff
        sprite = (s, round(ox - s.get_width() / 2), round(oy - s.get_height() / 2))
        if self._sprite_n >= self.MAX_SPRITES:  # forget the oldest half rather than stutter on one big rebuild
            for table in self._sprites.values():
                for old in list(table)[:len(table) // 2 + 1]:
                    del table[old]
            self._sprite_n = sum(len(t) for t in self._sprites.values())
        self._sprites.setdefault(px, {})[key] = sprite
        self._sprite_n += 1
        return sprite

    # ------------------------------------------------------------------ the grid
    def _grid(self, density: int) -> tuple:
        g = self._grids.get(density)
        if g is None:
            W, H = self.size
            sx, sy = W / (density + 1), H / (density + 1)
            # i is the outer loop in the sketch, so later columns overlap earlier ones in the same order
            ii, jj = np.meshgrid(np.arange(1, density + 1), np.arange(1, density + 1), indexing="ij")
            x, y = (ii * sx).ravel().astype(np.float32), (jj * sy).ravel().astype(np.float32)
            if self.clip:
                cx, cy, r = self.clip
                keep = np.hypot(x - cx, y - cy) <= r + 4 * max(sx, sy)
                x, y = x[keep], y[keep]
            r = np.hypot(x - W / 2, y - H / 2) / (min(W, H) / 2)
            g = (x, y, np.rint(x).astype(np.int32).tolist(), np.rint(y).astype(np.int32).tolist(), sx, sy, r)
            self._grids[density] = g
        return g

    def _distances(self, density: int, x, y, p: KineticParams) -> np.ndarray:
        W, H = self.size
        cx = W / 2 * (1 + p.cx)
        cy = H / 2 * (1 + p.cy)
        k = (density, round(cx, 1), round(cy, 1))
        if k != self._dist_key:
            self._dist = np.hypot(x - cx, y - cy) * self.unit
            self._dist_key = k
        return self._dist

    def _lookup(self, text: str, ring_half: np.ndarray) -> np.ndarray:
        ids = np.array([self._gid(ch) for ch in text] or [self._gid(" ")], dtype=np.int32)
        return ids[ring_half % len(ids)]

    def stretch_at(self, d, p: KineticParams):
        """The sketch's map(sin(frameCount * speed + d * freq), -1, 1, minS, maxS)."""
        return p.min_stretch + (np.sin(self.phase + d * p.frequency) + 1.0) * 0.5 * (p.max_stretch - p.min_stretch)

    def _alpha(self, p: KineticParams, d, r, reach: float):
        """Each cell's opacity from the opacity wave, the rim fade and the reveal. None when all are fully opaque."""
        a = None
        if p.op_min < 1.0 or p.op_max < 1.0:
            wave = (np.sin(self.op_phase + d * p.op_frequency) + 1.0) * 0.5
            if p.op_sharpness != 1.0:
                wave = wave ** p.op_sharpness
            a = p.op_min + (p.op_max - p.op_min) * wave
        if p.edge_end > p.edge_start:
            t = np.clip((r - p.edge_start) / (p.edge_end - p.edge_start), 0.0, 1.0)
            fade = 1.0 - t * t * (3.0 - 2.0 * t)
            a = fade if a is None else a * fade
        if p.reveal_outer < 1.0:
            fade = np.clip((p.reveal_outer * (reach + REVEAL_SOFTNESS) - d) / REVEAL_SOFTNESS, 0.0, 1.0)
            a = fade if a is None else a * fade
        if p.reveal_inner > 0.0:
            fade = np.clip((d - p.reveal_inner * (reach + REVEAL_SOFTNESS) + REVEAL_SOFTNESS) / REVEAL_SOFTNESS, 0.0, 1.0)
            a = fade if a is None else a * fade
        return a

    def blit_list(self, p: KineticParams, far: bool = False) -> list:
        """The frame's sprites and positions, for one Surface.blits call."""
        return self._cells(p, far)[0]

    def _cells(self, p: KineticParams, far: bool = False) -> tuple:
        """(sprites and positions, their alphas or None). With a split active, this is one half: `far` picks which."""
        density = max(1, int(round(p.density)))
        if self.ink_centered and density % 2 == 0:
            density += 1
        x, y, xi, yi, sx, sy, r = self._grid(density)
        px = max(4, int(round(sy * p.font_scale)))
        d = self._distances(density, x, y, p)
        rw = max(1e-3, p.ring_width)
        stretch = self.stretch_at(d, p)
        ring = np.floor(d / rw).astype(np.int32)
        ring_half = np.floor(d / (p.letter_width if p.letter_width > 0 else rw / 2)).astype(np.int32)

        shift = int(self.frames // max(1.0, p.swap_interval)) if p.color_swap else 0
        cids = np.array([self._cid(c) for c in p.colors], dtype=np.int32)
        cid = cids[(ring + shift) % len(cids)]
        gid = self._lookup(p.chars, ring_half)

        reach = float(d.max()) if d.size else 1.0
        if p.wipe > 0 and p.chars_next:
            edge = p.wipe * (reach + rw)
            gid = np.where(d < edge, self._lookup(p.chars_next, ring_half), gid)
            band = np.abs(d - edge) < rw * 0.5  # brand marks ride the front of the wipe
            if band.any():
                marks = np.array([self._gid(m) for m in BRAND_MARKS], dtype=np.int32)
                gid = np.where(band, marks[(ring_half + np.arange(ring.size)) % len(marks)], gid)
        split = p.split > 0 and p.side_colors
        if split and far:
            cids_b = np.array([self._cid(c) for c in p.side_colors], dtype=np.int32)
            cid = cids_b[ring % len(cids_b)]
            if p.side_chars:
                gid = self._lookup(p.side_chars, ring_half)
            # the wave keeps a quarter of its swing here: calm, but still alive
            stretch = stretch + (p.side_stretch - stretch) * p.split * 0.75

        widths = np.rint(self._width_table(px)[gid] * stretch).astype(np.int32)
        limit = int(sx * p.max_overlap) if p.max_overlap > 0 else 0xFFF
        widths = np.clip(widths, 0, min(limit, 0xFFF))
        if self.budget is not None:  # 1 px steps up to 32 px wide, then about 3%: the eye can't follow it faded
            step = (widths >> 5) + 1
            widths = np.maximum(widths // step * step, np.minimum(widths, 1))
        keep = widths > 0
        keep &= self._width_table(px)[gid] > 0
        if split:  # a cell exactly on the seam belongs to both halves
            W, H = self.size
            seam = (x - W / 2) * p.split_dir[0] + (y - H / 2) * p.split_dir[1]
            keep &= seam <= 0.5 if far else seam >= -0.5
        alpha = self._alpha(p, d, r, reach)
        if alpha is not None:
            keep &= alpha > 0.012
        keys = (widths.astype(np.int64) | (cid.astype(np.int64) << 12) | (gid.astype(np.int64) << 24)).tolist()

        table = self._sprites.setdefault(px, {})
        make = self._make_sprite
        room = self.budget if self.budget is not None else len(keys)
        alphas = (alpha * 255.0 + 0.5).astype(np.int32).tolist() if alpha is not None else [255] * len(keys)
        seq = []
        out = []
        for k, ok, cx, cy, a in zip(keys, keep.tolist(), xi, yi, alphas):
            if ok:
                e = table.get(k)
                if e is None:
                    if room <= 0:
                        continue
                    room -= 1
                    e = make(k, px)
                seq.append((e[0], (cx + e[1], cy + e[2])))
                out.append(a)
        return seq, (out if alpha is not None else None)

    def paint(self, target: pygame.Surface, p: KineticParams, far: bool = False, offset=(0, 0)) -> None:
        """Draw the frame. Alpha is set per blit on the shared sprites, so opacity adds nothing to the cache."""
        seq, alphas = self._cells(p, far)
        ox, oy = offset
        if alphas is None and not self._alpha_used:
            target.blits([(s, (x + ox, y + oy)) for s, (x, y) in seq] if offset != (0, 0) else seq, doreturn=False)
            return
        self._alpha_used = True
        blit = target.blit
        for (s, (x, y)), a in zip(seq, alphas or [255] * len(seq)):
            s.set_alpha(a)
            blit(s, (x + ox, y + oy))

    def draw(self, target: pygame.Surface, p: KineticParams, offset=(0, 0)) -> None:
        """Paint the glyphs straight onto `target`, in full color (the sketch's own look)."""
        self.paint(target, p, offset=offset)


# ====================================================================== moments
# Each track is a list of (seconds, value, easing). "base" means the current state's value for that slider and
# "start" means whatever the slider held when the moment fired, so a moment always lands back where the game is.
# `dur` is the nominal length: times scale when the moment is told to fit a game duration.
def _ease(name: str, t: float) -> float:
    if name == "out":
        return 1 - (1 - t) ** 3
    if name == "in":
        return t * t * t
    if name == "inout":
        return t * t * (3 - 2 * t)
    if name == "snap":  # overshoots slightly, for hits
        c = 1.70158
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2
    return t


MOMENTS: dict[str, dict] = {
    # Only sliders that glide smoothly are animated. Changing density or ring width moves or recolors every cell at
    # once, which reads as a jump, so a moment either leaves them alone or holds them constant from its first frame.

    # the first thing on screen after launch
    "splash": dict(dur=4.6, tracks=dict(
        opacity=[(0, 0), (1.2, 1.0, "out"), (4.6, "base", "inout")],
        reveal_outer=[(0, 0), (2.6, 1, "out")],
        speed=[(0, 0.12), (3.2, "base", "inout")],
        max_stretch=[(0, 3.5), (3.0, "base", "inout")],
        frequency=[(0, 0.015), (3.2, "base", "inout")],
    )),
    # players are ready: the waiting look brightens and speeds up
    "match_start": dict(dur=0.9, tracks=dict(
        opacity=[(0, "start"), (0.3, 0.9, "out"), (0.9, "base")],
        speed=[(0, 0.1), (0.9, "base")],
    )),
    # READY: steady, wide-spaced letters around a clear center
    "ready": dict(dur=1.2, tracks=dict(
        density=[(0, 37), (1.2, 37)],
        ring_width=[(0, 70), (1.2, 70)],
        letter_width=[(0, 34), (1.2, 34)],
        max_stretch=[(0, 1.25), (1.2, 1.7, "inout")],
        min_stretch=[(0, 1.0), (1.2, 0.85, "inout")],
        speed=[(0, 0.02), (1.2, 0.02)],
        reveal_inner=[(0, 0.3), (1.2, 0.3)],
        opacity=[(0, "start"), (0.4, 0.8, "out"), (1.2, 0.8)],
    )),
    # 3, 2, 1: the digit stays whole and legible; each beat is a gentle swell from the middle
    "beat": dict(dur=1.1, tracks=dict(
        density=[(0, 31), (1.1, 31)],
        ring_width=[(0, 80), (1.1, 80)],
        letter_width=[(0, 40), (1.1, 40)],
        max_stretch=[(0, 2.3), (0.6, 1.3, "out"), (1.1, 1.3)],
        min_stretch=[(0, 0.95), (0.6, 0.9, "out"), (1.1, 0.9)],
        frequency=[(0, 0.018), (1.1, 0.018)],
        speed=[(0, 0.035), (1.1, 0.02, "out")],
        reveal_outer=[(0, 0.3), (0.55, 1, "out")],
        reveal_inner=[(0, 0.3), (1.1, 0.3)],  # the big digit stands on clear ground
        opacity=[(0, 1.0), (0.6, 0.8), (1.1, 0.7)],
    )),
    # GO: the widest stretch of the countdown, then a hole opens from the middle for the ball
    "go": dict(dur=1.7, tracks=dict(
        density=[(0, 41), (1.7, 41)],
        ring_width=[(0, 66), (1.7, 66)],
        letter_width=[(0, 30), (1.7, 30)],
        max_stretch=[(0, 3.2), (1.7, 1.6, "out")],
        min_stretch=[(0, 0.7), (1.7, 0.7)],
        speed=[(0, 0.08), (1.7, 0.03)],
        reveal_inner=[(0, 0.28), (0.8, 0.28), (1.7, 0.75, "in")],
        opacity=[(0, 1.0), (0.8, 0.9), (1.7, "base", "in")],
    )),
    # a shock wave that spreads across the arena in the scorer's color
    "goal": dict(dur=2.3, tracks=dict(
        max_stretch=[(0, 1.6), (0.3, 3.4, "out"), (2.3, 2.4, "inout")],
        min_stretch=[(0, 0.6), (0.5, 0.35, "out"), (2.3, 0.4)],
        frequency=[(0, 0.016), (1.3, 0.032, "inout"), (2.3, 0.03)],
        speed=[(0, 0.09), (2.3, 0.04, "out")],
        reveal_outer=[(0, 0.02), (1.0, 1, "out")],
        reveal_inner=[(0, 0), (1.3, 0), (2.3, 0.65, "in")],
        opacity=[(0, 0), (0.15, 1.0, "out"), (1.4, 0.9), (2.3, "base", "in")],
    )),
    # the market closes: every slider winds down until the type stands still
    "final": dict(dur=1.6, tracks=dict(
        speed=[(0, 0.08), (1.6, 0.004, "out")],
        max_stretch=[(0, 3.4), (1.5, 1.15, "out")],
        min_stretch=[(0, 0.25), (1.5, 0.92, "out")],
        frequency=[(0, 0.015), (1.6, 0.06, "out")],
        reveal_outer=[(0, 0.1), (0.7, 1, "out")],
        opacity=[(0, 0.2), (0.3, 1.0, "out"), (1.6, 0.8)],
    )),
    # the winner's half lights up; the other half stays calm
    "result": dict(dur=3.2, tracks=dict(
        split=[(0, 0), (1.2, 1, "inout")],
        max_stretch=[(0, 3.4), (2.6, "base", "inout")],
        speed=[(0, 0.08), (3.2, "base")],
        reveal_outer=[(0, 0.05), (1.5, 1, "out")],
        opacity=[(0, 0.3), (0.4, 1.0, "out"), (3.2, "base")],
    )),
}


@dataclass
class _Playing:
    name: str
    tracks: dict
    dur: float
    k: float  # time scale: nominal seconds per real second
    gain: float
    start: dict = field(default_factory=dict)
    t: float = 0.0


class KineticBackdrop:
    """Chooses what the field shows: a base look per game state, plus one-shot moments on top."""

    SETTLE = 5.0  # how quickly sliders glide to a new base look, per second
    WIPE_S = 0.55
    SPRITE_BUDGET = 110

    def __init__(self, cfg):
        self.cfg = cfg
        self.p = KineticParams()
        self.field: KineticField | None = None
        self.layer: pygame.Surface | None = None
        self.moment: _Playing | None = None
        self.time = 0.0
        self.state = None
        self._field_key = None
        self._rect = None
        self._text_i = 0
        self._text_t = 0.0
        self._wipe_v = 0.0
        self._palette = None
        self._palette_goal = None
        self._text_override: str | None = None
        self._vals: dict[str, float] = {}
        self._booted = False
        self.winner = None
        self.names = ("", "")
        self.goal_dirs = ((-1.0, 0.0), (1.0, 0.0))
        self._goal_center = (0.0, 0.0)

    # ------------------------------------------------------------------ canvas
    def attach(self, size, clip, rotation: float, unit: float) -> None:
        """(Re)build the field for a canvas: clip = (cx, cy, r) of the arena."""
        cfg = self.cfg
        key = (tuple(size), tuple(clip), rotation, round(unit, 4), cfg["kinetic.font_latin"], cfg["kinetic.font_persian"])
        if key == self._field_key:
            return
        self._field_key = key
        cx, cy, r = clip
        side = int(2 * r)
        # the field is a square around the arena; a canvas-sized grid would put its center off the circle
        self.field = KineticField((side, side), unit, rotation, (r, r, r), cfg["kinetic.font_latin"],
                                  cfg["kinetic.font_persian"], budget=self.SPRITE_BUDGET, ink_centered=True)
        self.layer = pygame.Surface((side, side))
        self._rect = pygame.Rect(int(cx - r), int(cy - r), side, side)

    # ------------------------------------------------------------------ settings
    def _base_colors(self) -> tuple:
        cfg = self.cfg
        return tuple(hex_rgb(cfg[f"kinetic.color{i}"]) for i in (1, 2, 3))

    def _team_colors(self, team: int) -> tuple:
        t = boost(hex_rgb(self.cfg[f"colors.p{team + 1}"]), self.cfg["colors.projection_boost"])
        return (t, boost(t, 0.35), mix(t, (255, 255, 255), 0.72))

    def _attract_texts(self) -> list[str]:
        return [t for t in (s.strip() for s in str(self.cfg["kinetic.attract_text"]).split("|")) if t] or ["MOFID"]

    def _clean(self, text: str) -> str:
        return clean_chars(text, self.cfg["kinetic.space_marks"])

    def base(self, state) -> dict:
        """The slider values a game state rests on. The settings hold the calm look; states bend it."""
        cfg = self.cfg
        t = self.time
        b = dict(density=cfg["kinetic.density"], speed=cfg["kinetic.speed"], frequency=cfg["kinetic.frequency"],
                 min_stretch=cfg["kinetic.min_stretch"], max_stretch=cfg["kinetic.max_stretch"],
                 ring_width=cfg["kinetic.ring_width"], font_scale=cfg["kinetic.font_scale"], opacity=0.0,
                 cx=0.0, cy=0.0, reveal_outer=1.0, reveal_inner=0.0, split=0.0, letter_width=cfg["kinetic.letter_width"],
                 op_speed=cfg["kinetic.opacity_wave_speed"], op_frequency=cfg["kinetic.opacity_wave_frequency"],
                 op_min=1.0, op_max=1.0)
        if state == "ATTRACT":
            b["opacity"] = cfg["kinetic.opacity_waiting"]
            # the waiting screen is never static: the sliders themselves drift on slow, unrelated sines
            k = cfg["kinetic.drift"]
            b["max_stretch"] *= 1 + 0.35 * k * math.sin(t * 0.23)
            b["frequency"] *= 1 + 0.3 * k * math.sin(t * 0.137 + 1.1)
            b["op_min"], b["op_max"] = cfg["kinetic.opacity_wave_min"], cfg["kinetic.opacity_wave_max"]
        elif state == "INTRO":
            b["opacity"] = cfg["kinetic.opacity_countdown"]
        elif state == "COUNTDOWN":
            b.update(opacity=cfg["kinetic.opacity_countdown"], density=31, speed=0.02, ring_width=80,
                     letter_width=40, max_stretch=1.3, min_stretch=0.9, reveal_inner=0.3)
        elif state in ("SERVE", "PLAYING", "GOAL"):
            b["opacity"] = cfg["kinetic.opacity_play"]
        elif state == "FINAL":
            b["opacity"] = cfg["kinetic.opacity_result"]
            b["speed"] = 0.004
            b["max_stretch"], b["min_stretch"], b["frequency"] = 1.15, 0.92, 0.06
        elif state == "RESULT":
            b["opacity"] = cfg["kinetic.opacity_result"]
            if self.winner is not None:
                b["split"] = 1.0
        return b

    # ------------------------------------------------------------------ text
    def set_text(self, text: str, snap: bool = False) -> None:
        """Change the rings' text. Normally the new text spreads outward from the wave center."""
        text = self._clean(text)
        p = self.p
        if snap:
            p.chars, p.chars_next, p.wipe, self._wipe_v = text, "", 0.0, 0.0
        elif text != (p.chars_next or p.chars):
            if p.chars_next:  # a wipe was still running: it finishes instantly
                p.chars = p.chars_next
            p.chars_next, p.wipe, self._wipe_v = text, 0.0, 1.0 / self.WIPE_S

    def _side_dir(self, team: int) -> tuple:
        x, y = self.goal_dirs[team]
        return (x, -y)  # arena y points up, the field's points down

    # ------------------------------------------------------------------ moments
    def play(self, name: str, fit: float | None = None, gain: float = 1.0) -> None:
        """Start a moment; `fit` stretches it to a game duration in seconds."""
        spec = MOMENTS[name]
        k = spec["dur"] / max(0.05, fit) if fit else self.cfg["kinetic.moment_pace"]
        self.moment = _Playing(name, spec["tracks"], spec["dur"], k, gain, dict(self._vals))

    @staticmethod
    def _value(track, t: float, base: float, start: float, gain: float = 1.0) -> float:
        def v(x):
            return base if x == "base" else start if x == "start" else float(x) * gain

        if t <= track[0][0]:
            return v(track[0][1])
        for a, b in zip(track, track[1:]):
            if t <= b[0]:
                f = (t - a[0]) / max(1e-6, b[0] - a[0])
                return v(a[1]) + (v(b[1]) - v(a[1])) * _ease(b[2] if len(b) > 2 else "linear", f)
        return v(track[-1][1])

    # ------------------------------------------------------------------ game events
    def on_state(self, state: str, prev=None) -> None:
        cfg = self.cfg
        self.state = state
        if state == "ATTRACT":
            self._palette_goal = self._base_colors()
            self.p.split = 0.0
            self._text_override = None
            if prev is not None:
                self._text_t = 0.0
                self.set_text(self._attract_texts()[self._text_i % len(self._attract_texts())])
        elif state == "INTRO":
            self._palette_goal = self._base_colors()
            self.set_text(cfg["kinetic.text_start"])
            self.play("match_start", fit=cfg["match.intro_s"], gain=cfg["kinetic.opacity_moment"])
        elif state == "FINAL":
            self._palette_goal = self._base_colors()
            self.set_text(cfg["kinetic.text_final"], snap=True)
            self.play("final", fit=cfg["match.final_freeze_s"], gain=cfg["kinetic.opacity_moment"])
        elif state == "RESULT":
            self._begin_result()

    def _begin_result(self) -> None:
        cfg = self.cfg
        p = self.p
        w = self.winner
        p.side_colors = ()
        if w is None:
            self._palette_goal = self._base_colors()
            self.set_text(cfg["kinetic.text_draw"])
        else:
            self._palette_goal = self._team_colors(w)
            self.set_text(cfg["kinetic.text_winner"], snap=True)
            d = self._side_dir(w)
            p.split_dir = d
            red = hex_rgb(cfg["kinetic.loser_color"])
            p.side_colors = (red, scale(red, 0.8), mix(red, (255, 255, 255), 0.4))
            p.side_chars = self._clean(cfg["kinetic.loser_text"])
            p.side_stretch = 0.8
        self.play("result", gain=cfg["kinetic.opacity_moment"])

    def on_beat(self, label: str, length: float) -> None:
        cfg = self.cfg
        gain = cfg["kinetic.opacity_moment"]
        if label == "ready":
            self.set_text(cfg["kinetic.text_ready"], snap=True)
            self.play("ready", fit=length, gain=gain)
        elif label == "go":
            self.set_text(cfg["kinetic.text_go"], snap=True)
            self.play("go", gain=gain)  # runs past the "go" label on purpose: it fades over the serve
        else:
            self.set_text(f"{label}•", snap=True)
            self.play("beat", fit=length, gain=gain)

    def on_goal(self, scorer: int, cx: float, cy: float) -> None:
        cfg = self.cfg
        self._palette_goal = self._team_colors(scorer)
        self.p.split = 0.0
        self.set_text(cfg["kinetic.text_goal"], snap=True)
        self.play("goal", gain=cfg["kinetic.opacity_moment"])
        self._goal_center = (cx, cy) if cfg["kinetic.goal_at_impact"] else (0.0, 0.0)

    def handle_events(self, events, engine) -> None:
        if not self.cfg["kinetic.enabled"]:
            return
        for e in events:
            et = e["type"]
            if et == "state":
                self.winner = getattr(engine, "winner", None)
                self.names = tuple(getattr(engine, "names", ("", "")))
                self.goal_dirs = engine.geom.goal_dir
                self.on_state(e["state"], e.get("prev"))
            elif et == "countdown_beat":
                _, _, length, _ = engine.countdown_info()
                self.on_beat(e["label"], length)
            elif et == "goal" and not e.get("demo") and self.cfg["kinetic.on_goal"]:
                R = max(1.0, engine.geom.R)
                sx, sy = self._to_field(e["x"], e["y"], R)
                self.on_goal(e["scorer"], sx, sy)
            elif et == "match_end":
                self.winner = e.get("winner")
                self.names = tuple(getattr(engine, "names", ("", "")))

    @staticmethod
    def _to_field(x: float, y: float, R: float) -> tuple:
        """Arena coordinates (y up) to the field's center fractions (y down)."""
        return x / R, -y / R

    # ------------------------------------------------------------------ per frame
    def update(self, dt: float, state: str | None = None) -> None:
        cfg = self.cfg
        if state is not None and state != self.state:
            self.state = state
        self.time += dt
        if not self._booted:
            self._booted = True
            self._vals = self.base(self.state)
            self._palette = self._base_colors()
            self._palette_goal = self._palette
            self.set_text(self._attract_texts()[0], snap=True)
            if self.state == "ATTRACT" and cfg["kinetic.splash"]:
                self.play("splash", gain=cfg["kinetic.opacity_moment"])

        if self.state == "ATTRACT" and self.moment is None:
            self._palette_goal = self._base_colors()
            self._text_t += dt
            if self._text_t >= cfg["kinetic.text_interval_s"]:
                self._text_t = 0.0
                texts = self._attract_texts()
                self._text_i = (self._text_i + 1) % len(texts)
                self.set_text(texts[self._text_i])

        base = self.base(self.state)
        settle = 1 - math.exp(-self.SETTLE * dt)
        m = self.moment
        if m:
            m.t += dt * m.k
            if m.t >= m.dur:
                self.moment = m = None
        for k, bv in base.items():
            track = m.tracks.get(k) if m else None
            if track:
                self._vals[k] = self._value(track, m.t, bv, m.start.get(k, bv), m.gain if k == "opacity" else 1.0)
            elif k in SNAP_PARAMS:
                self._vals[k] = bv
            else:
                self._vals[k] = self._vals.get(k, bv) + (bv - self._vals.get(k, bv)) * settle
        if m and m.name == "goal":
            self._vals["cx"], self._vals["cy"] = self._goal_center

        p = self.p
        for k in FLOAT_PARAMS:
            setattr(p, k, self._vals[k])
        reduce = cfg["fx.reduce_flashing"]
        p.color_swap = cfg["kinetic.color_swap"] and not reduce
        p.swap_interval = cfg["kinetic.swap_interval"]
        p.max_overlap = cfg["kinetic.max_overlap"]
        p.op_sharpness = cfg["kinetic.opacity_wave_sharpness"]
        p.edge_start, p.edge_end = cfg["kinetic.edge_fade_start"], cfg["kinetic.edge_fade_end"]
        if reduce:
            p.opacity *= 0.6
        self._step_palette(dt)
        if self._wipe_v:
            p.wipe += self._wipe_v * dt
            if p.wipe >= 1.0:
                p.chars, p.chars_next, p.wipe, self._wipe_v = p.chars_next, "", 0.0, 0.0
        if self.field:
            self.field.advance(dt, p)

    def _step_palette(self, dt: float) -> None:
        cur, goal = self._palette, self._palette_goal
        if cur != goal:
            k = min(1.0, dt * 7)
            # steps of 8 levels keep a color glide from filling the sprite cache with near-duplicates
            step = tuple(tuple(int(round((c + (g - c) * k) / 8.0)) * 8 for c, g in zip(a, b)) for a, b in zip(cur, goal))
            near = all(abs(c - g) <= 8 for a, b in zip(step, goal) for c, g in zip(a, b))
            self._palette = goal if near or step == cur else tuple(tuple(min(255, c) for c in a) for a in step)
        self.p.colors = self._palette

    def draw(self, canvas: pygame.Surface, dim: float = 1.0) -> None:
        """Composite additively under the game, so the arena's own colors stay readable through it.

        `dim` lets the moving objects quiet the letters while they have the floor."""
        p = self.p
        k = min(1.0, p.opacity * dim)
        if not self.cfg["kinetic.enabled"] or self.field is None or k <= 0.003:
            return
        layer = self.layer
        area = self._visible_area()
        layer.fill((0, 0, 0), area)
        layer.set_clip(area)
        if p.split > 0 and p.side_colors:
            # the far half first, cut on the seam; the near half clipped to its side: the divide is exactly the middle
            self.field.paint(layer, p, True)
            pygame.draw.polygon(layer, (0, 0, 0), self._half_plane(1))
            layer.set_clip(area.clip(self._near_half()))
            self.field.paint(layer, p, False)
        else:
            self.field.paint(layer, p, False)
        layer.set_clip(None)
        k = int(k * 255)
        if k < 255:
            layer.fill((k, k, k), area, special_flags=pygame.BLEND_MULT)
        canvas.blit(layer, (self._rect.x + area.x, self._rect.y + area.y), area, special_flags=pygame.BLEND_ADD)

    def _visible_area(self) -> pygame.Rect:
        """Letters are gone past the rim fade, so the layer work can stop there."""
        W, H = self.field.size
        p = self.p
        k = min(1.0, p.edge_end + 0.08) if p.edge_end > p.edge_start else 1.0
        w, h = int(W * k), int(H * k)
        return pygame.Rect((W - w) // 2, (H - h) // 2, w, h)

    def _near_half(self) -> pygame.Rect:
        """The winner's half as a clip rectangle. A diagonal seam (a rotated display) only gets the polygon cut."""
        W, H = self.field.size
        nx, ny = self.p.split_dir
        if abs(nx) > 0.999:
            return pygame.Rect(0 if nx < 0 else W // 2, 0, W // 2, H)
        if abs(ny) > 0.999:
            return pygame.Rect(0, 0 if ny < 0 else H // 2, W, H // 2)
        return pygame.Rect(0, 0, W, H)

    def _half_plane(self, sign: int) -> list:
        """The polygon covering one half of the field, on the winner's side of the seam if sign is 1."""
        W, H = self.field.size
        cx, cy = W / 2, H / 2
        nx, ny = self.p.split_dir
        far = 2 * max(W, H)
        tx, ty = -ny * far, nx * far
        ox, oy = nx * far * sign, ny * far * sign
        return [(cx + tx, cy + ty), (cx - tx, cy - ty), (cx - tx + ox, cy - ty + oy), (cx + tx + ox, cy + ty + oy)]
