"""Brand motion: crisp moving objects from the brand book, under the game and over the kinetic type.

Everything here is drawn from the book's own shapes: its icons and bull (assets/brand, baked by
tools/make_brand_icons.py), its paper plane, its five identity marks, its dot grid and its colors. Rendering stays
sharp at floor scale: radial effects are evaluated as an exact one-dimensional function of the radius, polygons
are antialiased per frame instead of rotating a bitmap, and coins are built large and then reduced.

BrandMotion is the director: game events and a loop on the waiting screen start short-lived actors. All of it sits
in the background: objects are drawn together on one layer that fades near the rim and is laid over the floor at a
set opacity, and radial effects share the same rim fade.
"""

from __future__ import annotations

import itertools
import math
import random

import numpy as np
import pygame
from pygame import gfxdraw

from ..paths import ASSETS_DIR
from .colors import hex_rgb, mix, scale
from .kinetic import _ease

BRAND_DIR = ASSETS_DIR / "brand"
WHITE = (255, 255, 255)
SUB = 2  # radial table entries per pixel of radius
FLIP_STEPS = 10
SPRITE_LIMIT = 2600
WARM_PER_FRAME = 5  # coins built ahead per frame, so the wall's first wave finds them ready
LOGO_FILE = "group_stacked"  # the group's logo, the bull over «گروه مالی مفید», white on transparent
LOGO_ASPECT = 0.414  # its height / width
LOGO_EDGE = np.clip((np.arange(256, dtype=np.float32) - 22.0) * 255.0 / 200.0, 0, 255).astype(np.uint8)  # crisper small text
LOGO_ROW_WAITING, LOGO_ROW_RESULT = -0.62, 0.68  # height on the arena, as a share of the radius (up is positive)
CHEER_EVERY_S = 3.2  # the winner's bursts repeat this often, so a long result screen stays alive
# The start logo, as shares of its time: how long it takes to brighten, the spring's settling time,
# when its growth starts to build, and when the fade begins.
ZOOM_GAIN, ZOOM_SPRING, ZOOM_GROW, ZOOM_FADE = 0.3, 0.55, 0.28, 0.55
ZOOM_NEAR = 1.55  # its size once the spring has carried it to the center
ZOOM_END = 9.0  # its size as it fades away
SPRING_DAMPING = 0.68  # below 1 a spring overshoots: this gives one soft overshoot, no wobble
MARKS = ("dot", "plus", "minus", "times", "slash")
GAME_ICONS = ("chart", "money", "financial", "star", "risk", "stairs", "pie", "badge", "dataviz", "low_risk", "assets",
              "donut", "check", "game", "return", "market_map", "academy", "binoculars")
WIN_ICONS = ("star", "badge", "bull", "financial", "check", "stairs")
# the group's sub-brands (tools/make_brand_icons.py): they show on pale coins in their own colors
BRANDS = tuple("brand_" + n for n in ("easytrader", "mofid_app", "jet", "boursview2", "boursview", "life_insurance",
                                      "academy_mofid", "ayar", "hami", "tavan", "hamnang", "atieh", "gold"))
COINS = BRANDS * 2 + GAME_ICONS  # what the coins show: the sub-brands about three times in five
WIN_COINS = BRANDS + WIN_ICONS
FACES = ("pale", "teal", "dark", "pale", "teal", "accent", "pale", "dark")


def smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def smoother(t: float) -> float:
    """Like smooth, with no sudden change in acceleration at either end."""
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


def spring_step(t: float) -> float:
    """A damped spring released from rest toward 1, with t = 1 about where it has settled. It starts with no speed."""
    if t <= 0:
        return 0.0
    w = 6.5 * t
    d = math.sqrt(1 - SPRING_DAMPING * SPRING_DAMPING)
    return 1 - math.exp(-SPRING_DAMPING * w) * (math.cos(d * w) + SPRING_DAMPING / d * math.sin(d * w))


def envelope(t: float, dur: float, fade_in: float, fade_out: float) -> float:
    return smooth(t / max(1e-3, fade_in)) * smooth((dur - t) / max(1e-3, fade_out))


def aa_poly(target: pygame.Surface, pts, color, alpha: int = 255) -> None:
    """An antialiased filled polygon. Partial alpha goes through a small surface so edges aren't drawn twice."""
    if alpha <= 0:
        return
    if alpha >= 250:
        gfxdraw.filled_polygon(target, pts, color)
        gfxdraw.aapolygon(target, pts, color)
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2
    s = pygame.Surface((int(max(xs)) - x0 + 3, int(max(ys)) - y0 + 3), pygame.SRCALPHA)
    moved = [(p[0] - x0, p[1] - y0) for p in pts]
    gfxdraw.filled_polygon(s, moved, color)
    gfxdraw.aapolygon(s, moved, color)
    s.set_alpha(alpha)
    target.blit(s, (x0, y0))


def thick_line(target, a, b, width: float, color) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = max(1e-6, math.hypot(dx, dy))
    ox, oy = -dy / n * width / 2, dx / n * width / 2
    aa_poly(target, [(a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy), (b[0] - ox, b[1] - oy), (a[0] - ox, a[1] - oy)], color)


def disc(target, x, y, r, color) -> None:
    gfxdraw.filled_circle(target, int(x), int(y), int(r), color)
    gfxdraw.aacircle(target, int(x), int(y), int(r), color)


class RadialLayer:
    """Concentric effects as a table over the radius. One quadrant is looked up and mirrored, so a full-screen
    ring system costs about a millisecond and has edges exact to the pixel at any size."""

    def __init__(self, radius: int):
        self.n = n = int(radius) + 1
        axis = np.arange(n, dtype=np.float32) + 0.5
        r = np.hypot(axis[:, None], axis[None, :])
        self.length = int(radius * SUB) + 2
        self.idx = np.minimum((r * SUB).astype(np.int32), self.length - 1)
        self.r = np.arange(self.length, dtype=np.float32) / SUB
        self.lut = np.zeros((self.length, 3), dtype=np.float32)
        self.surf = pygame.Surface((n, n), depth=32)
        self.shifts = self.surf.get_shifts()
        self.used = False

    def begin(self) -> None:
        self.lut[:] = 0.0
        self.used = False

    def add(self, coverage, color, alpha: float = 1.0) -> None:
        """Add `color` where `coverage` (an array over self.r, or None for everywhere) is 1."""
        if alpha <= 0.002:
            return
        c = np.array(color[:3], dtype=np.float32) * alpha
        self.lut += (coverage[:, None] * c) if coverage is not None else c
        self.used = True

    def band(self, r0: float, r1: float):
        return np.clip(self.r - r0 + 0.5, 0, 1) * np.clip(r1 - self.r + 0.5, 0, 1)

    def fade_edge(self, start: float, end: float) -> None:
        """Everything added so far fades out between these two radii."""
        if self.used and end > start:
            t = np.clip((self.r - start) / (end - start), 0, 1)
            self.lut *= (1 - t * t * (3 - 2 * t))[:, None]

    def composite(self, target: pygame.Surface, cx: int, cy: int) -> None:
        if not self.used:
            return
        self.lut[-1] = 0.0  # beyond the radius
        v = np.clip(self.lut, 0, 255).astype(np.uint32)
        sr, sg, sb = self.shifts[:3]
        packed = (v[:, 0] << sr) | (v[:, 1] << sg) | (v[:, 2] << sb)
        pygame.surfarray.blit_array(self.surf, packed[self.idx])
        n = self.n
        flip = pygame.transform.flip
        add = pygame.BLEND_RGB_ADD
        target.blit(self.surf, (cx, cy), special_flags=add)
        target.blit(flip(self.surf, True, False), (cx - n, cy), special_flags=add)
        target.blit(flip(self.surf, False, True), (cx, cy - n), special_flags=add)
        target.blit(flip(self.surf, True, True), (cx - n, cy - n), special_flags=add)


class Art:
    """Coins and marks, built large from the brand files and reduced, then cached by exact size and flip step."""

    def __init__(self, cfg, rot: float):
        self.rot = rot
        pale, teal, dark, accent = (hex_rgb(cfg[f"motion.color_{k}"]) for k in ("pale", "teal", "dark", "accent"))
        self.palette = dict(pale=pale, teal=teal, dark=dark, accent=accent)
        # face: (disc, rim, the icon's dark tone, the icon's light tone)
        self.faces = dict(pale=(pale, teal, dark, teal), teal=(teal, pale, dark, WHITE),
                          dark=(dark, teal, hex_rgb(cfg["motion.color_tint"]), WHITE),
                          accent=(accent, pale, pale, WHITE))
        self._icons: dict = {}
        self._tinted: dict = {}
        self._coins: dict = {}
        self._marks: dict = {}
        self._n = 0
        self._mips: list | None = None

    def _icon(self, name: str) -> pygame.Surface | None:
        if name not in self._icons:
            try:
                self._icons[name] = pygame.image.load(str(BRAND_DIR / f"{name}.png"))
            except (FileNotFoundError, pygame.error):
                self._icons[name] = None
        return self._icons[name]

    def _tint(self, name: str, face: str) -> pygame.Surface | None:
        """The icon with the book's two tones mapped onto a coin face, by the green channel that separates them."""
        k = (name, face)
        if k not in self._tinted:
            src = self._icon(name)
            if src is None:
                self._tinted[k] = None
            else:
                s = src.copy()
                _, _, deep, light = self.faces[face]
                t = np.clip((np.arange(256, dtype=np.float32) - 76.0) / 120.0, 0, 1)[:, None]
                lut = (np.array(deep, dtype=np.float32) * (1 - t) + np.array(light, dtype=np.float32) * t).astype(np.uint8)
                rgb = pygame.surfarray.pixels3d(s)
                rgb[:] = lut[rgb[:, :, 1]]
                del rgb
                self._tinted[k] = s
        return self._tinted[k]

    def _face(self, name: str, face: str, size: int) -> pygame.Surface:
        k = (name, face, size)
        s = self._coins.get(k)
        if s is None:
            n = size * (3 if size < 150 else 2)
            big = pygame.Surface((n, n), pygame.SRCALPHA)
            base, rim, _, _ = self.faces[face]
            pygame.draw.circle(big, rim, (n // 2, n // 2), n // 2)
            pygame.draw.circle(big, base, (n // 2, n // 2), int(n * 0.455))
            icon = None if name.startswith("brand_") else self._tint(name, face)
            logo = self._icon(name) if name.startswith("brand_") else None
            if logo is not None:
                # the logo keeps its own colors, and its white page becomes exactly the face's color: no square shows.
                # Its box is small enough that even its corners fall inside the face.
                lw, lh = logo.get_size()
                k2 = min(n * 0.7 / lw, n * 0.5 / lh)
                lg = pygame.transform.smoothscale(logo, (max(1, int(lw * k2)), max(1, int(lh * k2))))
                rgb = pygame.surfarray.pixels3d(lg)
                paper = max(1, int(rgb.max()))  # reduction leaves the white page a shade under 255
                rgb[:] = np.clip(rgb * (np.array(base, dtype=np.float32) / paper) + 0.5, 0, 255).astype(np.uint8)
                del rgb
                big.blit(lg, lg.get_rect(center=(n // 2, n // 2)))
            if icon is not None:
                w = int(n * 0.62)
                ic = pygame.transform.smoothscale(icon, (w, w))
                big.blit(ic, ((n - w) // 2, (n - w) // 2))
            if self.rot:
                big = pygame.transform.rotozoom(big, self.rot, 1.0)
            s = pygame.transform.smoothscale(big, (size, size))
            self._store(self._coins, k, s)
        return s

    def _store(self, table: dict, k, s) -> None:
        if self._n >= SPRITE_LIMIT:
            self._coins.clear()
            self._n = 0
        table[k] = s
        self._n += 1

    def coin(self, name: str, face: str, size: int, theta: float) -> pygame.Surface:
        """A coin turned by theta around its horizontal axis: squashed, and darker as it goes edge-on."""
        size = max(4, int(size) & ~1)
        if name.startswith("brand_"):
            face = "pale"  # a sub-brand always sits on the pale face, the closest to its own white page
        c = abs(math.cos(theta))
        step = int(c * FLIP_STEPS + 0.5)
        if step >= FLIP_STEPS:
            return self._face(name, face, size)
        k = (name, face, size, step)
        s = self._coins.get(k)
        if s is None:
            q = step / FLIP_STEPS
            s = pygame.transform.smoothscale(self._face(name, face, size), (size, max(2, int(size * q))))
            v = int(150 + 105 * q)
            s.fill((v, v, v, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self._store(self._coins, k, s)
        return s

    def white(self, name: str) -> pygame.Surface | None:
        """A brand file in white, the book's version for dark and turquoise grounds, upright for the layout."""
        k = ("white", name)
        if k not in self._tinted:
            src = self._icon(name)
            if src is None:
                self._tinted[k] = None
            else:
                # a surface of the display's own pixel layout: a PNG's layout blits several times slower
                s = pygame.Surface(src.get_size(), pygame.SRCALPHA)
                s.fill((255, 255, 255, 0))
                alpha = pygame.surfarray.pixels_alpha(s)
                alpha[:] = pygame.surfarray.array_alpha(src)
                del alpha
                self._tinted[k] = pygame.transform.rotozoom(s, self.rot, 1.0) if self.rot else s
        return self._tinted[k]

    def logo_frame(self, width: int, center: tuple, screen: pygame.Rect) -> tuple:
        """The white logo at a width and a center: (surface, position), cropped to the screen.

        It scales from the smallest ready-made reduction that is still large enough, so each frame costs about the same
        at any size. Width and height stay even around the center, which keeps it from wobbling by a pixel as it grows."""
        mips = self._logo_mips()
        if not mips:
            return None, (0, 0)
        src = next((m for m in mips if m.get_width() >= width), mips[-1])
        iw, ih = src.get_size()
        w = max(2, int(width / 2 + 0.5) * 2)
        h = max(2, int(w * ih / iw / 2 + 0.5) * 2)
        rect = pygame.Rect(int(center[0] - w / 2 + 0.5), int(center[1] - h / 2 + 0.5), w, h)
        clip = rect.clip(screen)
        if clip.w <= 0 or clip.h <= 0:
            return None, (0, 0)
        f = iw / w
        crop = pygame.Rect(int((clip.x - rect.x) * f), int((clip.y - rect.y) * f), max(1, int(clip.w * f)), max(1, int(clip.h * f)))
        frame = pygame.transform.smoothscale(src.subsurface(crop.clip(src.get_rect())), clip.size)
        if clip.w * clip.h < 600_000:  # past this it is big enough to be sharp, and fading anyway
            alpha = pygame.surfarray.pixels_alpha(frame)
            alpha[:] = LOGO_EDGE[alpha]
            del alpha
        return frame, clip.topleft

    def _logo_mips(self) -> list:
        """The logo at full size and at each half down to a small one, smallest first."""
        if self._mips is None:
            s = self.white(LOGO_FILE)
            self._mips = []
            while s is not None:
                self._mips.insert(0, s)
                if s.get_width() < 300:
                    break
                s = pygame.transform.smoothscale(s, (s.get_width() // 2, s.get_height() // 2))
        return self._mips

    def warm_list(self, size: int):
        """Every coin a wall can show, for building ahead a few per frame."""
        for name in dict.fromkeys(WIN_COINS + COINS):
            for face in ("pale",) if name.startswith("brand_") else self.faces:
                for step in range(FLIP_STEPS + 1):
                    yield (name, face, size, math.acos(step / FLIP_STEPS))

    def mark(self, name: str, size: int, color) -> pygame.Surface:
        """A brand mark at an exact size, on the book's 3x3 grid."""
        k = (name, size, color)
        s = self._marks.get(k)
        if s is None:
            n = max(2, size) * 4
            big = pygame.Surface((n, n), pygame.SRCALPHA)
            if name == "dot":
                pygame.draw.circle(big, color, (n / 2, n / 2), n / 2)
            else:
                pygame.draw.polygon(big, color, mark_points(name, n / 2, n / 2, n / 2, 0.0))
                if name == "plus":
                    pygame.draw.polygon(big, color, mark_points("plus", n / 2, n / 2, n / 2, math.pi / 2))
                elif name == "times":
                    pygame.draw.polygon(big, color, mark_points("slash", n / 2, n / 2, n / 2, 0.0))
            s = pygame.transform.smoothscale(big, (max(2, size), max(2, size)))
            self._marks[k] = s
        return s


def mark_points(name: str, x: float, y: float, r: float, spin: float) -> list:
    """One bar of a mark as a polygon. `plus` and `times` need a second bar: see draw_mark."""
    half = r
    t = r / 3
    if name == "plus":
        pts = ((-half, -t), (half, -t), (half, t), (-half, t))
    elif name == "minus":
        pts = ((-half, -t), (half, -t), (half, t), (-half, t))
    elif name == "slash":
        pts = ((-half * 0.99, -t * 0.72), (half * 0.99, -t * 0.72), (half * 0.99, t * 0.72), (-half * 0.99, t * 0.72))
        spin -= math.pi / 4
    else:  # times: the first bar
        pts = ((-half * 0.99, -t * 0.72), (half * 0.99, -t * 0.72), (half * 0.99, t * 0.72), (-half * 0.99, t * 0.72))
        spin += math.pi / 4
    c, s = math.cos(spin), math.sin(spin)
    return [(x + px * c - py * s, y + px * s + py * c) for px, py in pts]


def draw_mark(target, name: str, x: float, y: float, r: float, spin: float, color, alpha: int) -> None:
    if name == "dot":
        if alpha >= 250:
            disc(target, x, y, r * 0.8, color)
        else:
            k = int(r * 2) + 4
            s = pygame.Surface((k, k), pygame.SRCALPHA)
            disc(s, k // 2, k // 2, r * 0.8, color)
            s.set_alpha(alpha)
            target.blit(s, (int(x) - k // 2, int(y) - k // 2))
        return
    aa_poly(target, mark_points(name, x, y, r, spin), color, alpha)
    if name == "plus":
        aa_poly(target, mark_points("plus", x, y, r, spin + math.pi / 2), color, alpha)
    elif name == "times":
        aa_poly(target, mark_points("slash", x, y, r, spin), color, alpha)


# ====================================================================== actors
class Actor:
    dur = 1.0
    fade_out = 0.3
    type_level = 1.0  # how much of the kinetic type may show while this actor runs
    paints = True  # draws objects (False: only radial effects, which don't need the object layer)

    def __init__(self, stage, delay: float = 0.0):
        self.st = stage
        self.t = -delay
        self.exit_t: float | None = None

    @property
    def started(self) -> bool:
        return self.t >= 0

    def step(self, dt: float) -> bool:
        self.t += dt
        if self.exit_t is not None and self.t - self.exit_t >= self.fade_out:
            return False
        return self.t < self.dur

    def leave(self) -> None:
        """The state changed: fade out where it is, still moving, instead of cutting. A few that never started just go."""
        if self.t < 0:
            self.dur = self.t
        elif self.exit_t is None:
            self.exit_t = self.t

    def presence(self) -> float:
        """1 until it is told to leave, then falling smoothly to 0."""
        return 1.0 if self.exit_t is None else smooth(1.0 - (self.t - self.exit_t) / self.fade_out)

    def type_limit(self) -> float:
        return self.type_level if self.started else 1.0

    def radial(self, layer: RadialLayer, level: float) -> None:
        pass

    def area(self) -> pygame.Rect | None:
        """Where this frame's drawing can land, so small objects don't pay for a full-screen layer. None: anywhere."""
        return None

    def draw(self, target: pygame.Surface, level: float) -> None:
        pass


class Flood(Actor):
    """The disc floods from the middle, grooved with pulsing rings, then an iris opens from the center."""

    type_level = 0.0
    paints = False

    def __init__(self, stage, color, dur=2.0, strength=1.0, delay=0.0, min_groove=0.05):
        super().__init__(stage, delay)
        # the layer is additive: taking the floor's color out first lands on the true brand color, not a brighter one
        self.color = tuple(max(0, c - f) for c, f in zip(color, stage.floor))
        self.dur, self.strength, self.min_groove = dur, strength, min_groove
        self.spacing = stage.R / 8.5

    def type_limit(self) -> float:
        if not self.started:
            return 1.0
        return smooth((self.t / self.dur - 0.55) / 0.4)

    def radial(self, layer, level) -> None:
        if not self.started:
            return
        st, t, u = self.st, self.t, self.t / self.dur
        outer = st.R * _ease("out", min(1.0, u / 0.26))
        inner = st.R * 1.02 * _ease("in", max(0.0, (u - 0.42) / 0.58))
        cover = layer.band(inner, outer)
        s = self.spacing
        ph = t * s * 0.9
        pos = (layer.r - ph) % s - s / 2
        # the grooves start as hairlines and widen until they swallow the bands
        w = s * (self.min_groove + (0.55 - self.min_groove * 0.5) * smooth((u - 0.12) / 0.7)) + 2 * math.sin(t * 9) * (1 - u)
        groove = np.clip(w / 2 - np.abs(pos) + 0.5, 0, 1)
        layer.add(cover * (1 - groove), self.color, self.strength * self.st.flood_strength * level)


class Shock(Actor):
    """Thin rings racing outward. `reverse` closes them on the center instead."""

    fade_out = 0.2
    paints = False

    def __init__(self, stage, color, rings=3, dur=1.1, width=14.0, gap=0.13, delay=0.0, reverse=False, start=0.0, strength=1.0):
        super().__init__(stage, delay)
        self.color, self.rings, self.span, self.width, self.gap = color, rings, dur, width, gap
        self.dur, self.reverse, self.start, self.strength = dur + gap * rings, reverse, start, strength

    def radial(self, layer, level) -> None:
        if not self.started:
            return
        R = self.st.R
        for i in range(self.rings):
            u = (self.t - i * self.gap) / self.span
            if not 0 <= u < 1:
                continue
            e = _ease("in" if self.reverse else "out", u)
            k = 1 - e if self.reverse else e
            r = R * (self.start + (1 - self.start) * k)
            w = max(2.5, self.width * ((1 - u) ** 1.5))
            layer.add(layer.band(r - w / 2, r + w / 2), self.color, self.strength * level * (1 - u) ** 0.7)


class PulseBed(Actor):
    """Fine fixed rings lit by two sines beating against each other, with a heartbeat. The mesmerizing one."""

    type_level = 0.3
    fade_out = 0.7
    paints = False

    def __init__(self, stage, color, color2, dur=7.0, delay=0.0, strength=1.0):
        super().__init__(stage, delay)
        self.color, self.color2, self.dur, self.strength = color, color2, dur, strength
        self.pitch = stage.R / 15.0

    def radial(self, layer, level) -> None:
        if not self.started:
            return
        env = envelope(self.t, self.dur, 0.7, self.fade_out) * level * self.strength
        r = layer.r
        k1, k2 = 2 * math.pi / (self.st.R * 0.42), 2 * math.pi / (self.st.R * 0.67)
        t = self.t
        beat = 0.72 + 0.28 * max(math.sin(t * 4.4), 0.0) ** 8 + 0.2 * max(math.sin(t * 4.4 - 0.9), 0.0) ** 8
        wave = (0.5 + 0.5 * np.sin(r * k1 - t * 3.1)) * (0.45 + 0.55 * (0.5 + 0.5 * np.sin(r * k2 + t * 1.7)))
        pos = (r - t * 7.0) % self.pitch - self.pitch / 2
        ring = np.clip((1.8 + wave * 5.0) - np.abs(pos) + 0.5, 0, 1)
        fade = np.clip((self.st.R - r) / 30.0, 0, 1)
        a = ring * fade * (0.18 + 0.82 * wave ** 1.6) * beat * env
        hot = (wave ** 2)[:, None]
        c1, c2 = np.array(self.color, dtype=np.float32), np.array(self.color2, dtype=np.float32)
        layer.lut += a[:, None] * (c1 * (1 - hot) + c2 * hot)
        layer.used = True


class CountRing(Actor):
    """The reference's game ring: a bold circle around the digit, with one dot running round it."""

    fade_out = 0.25

    def __init__(self, stage, length: float, turns=1.0):
        super().__init__(stage)
        self.dur = max(0.2, length)
        self.turns = turns

    def radial(self, layer, level) -> None:
        R = self.st.R * 0.46
        grow = _ease("out", min(1.0, self.t / 0.3))
        a = level * envelope(self.t, self.dur, 0.12, self.fade_out)
        layer.add(layer.band(R * grow - 3.5, R * grow + 3.5), self.st.art.palette["pale"], a)

    def _dot(self) -> tuple:
        st = self.st
        a = -math.pi / 2 + 2 * math.pi * self.turns * self.t / self.dur
        r = st.R * 0.46 * _ease("out", min(1.0, self.t / 0.3))
        return st.cx + r * math.cos(a), st.cy + r * math.sin(a)

    def area(self) -> pygame.Rect:
        k = int(self.st.R * 0.1)
        return pygame.Rect(0, 0, k, k).move(int(self._dot()[0] - k / 2), int(self._dot()[1] - k / 2))

    def draw(self, target, level) -> None:
        st = self.st
        alpha = int(255 * level * envelope(self.t, self.dur, 0.12, self.fade_out))
        x, y = self._dot()
        draw_mark(target, "dot", x, y, st.R * 0.03, 0, st.art.palette["pale"], alpha)


class HeroCoin(Actor):
    """A big coin at one spot, turning over from face to face."""

    fade_out = 0.3

    def __init__(self, stage, sides, size, x=0.0, y=0.0, turn_s=0.85, delay=0.0, loops=1):
        super().__init__(stage, delay)
        self.sides, self.size, self.x, self.y, self.turn_s = sides, size, x, y, turn_s
        self.dur = 0.3 + turn_s * max(1, len(sides) * loops - 1) + 0.55

    def area(self) -> pygame.Rect:
        k = int(self.size * 1.2)
        return pygame.Rect(int(self.st.cx + self.x - k / 2), int(self.st.cy + self.y - k / 2), k, k)

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        t = self.t
        pop = _ease("snap", min(1.0, t / 0.3)) if t < 0.3 else 1.0
        out = smooth((self.dur - t) / 0.3)
        size = self.size * max(0.0, pop) * out
        if size < 6:
            return
        i = max(0.0, t - 0.3) / self.turn_s
        whole = int(i)
        turn = min(1.0, (i - whole) / 0.55)
        theta = math.pi * _ease("inout", turn)
        side = self.sides[(whole + (1 if theta > math.pi / 2 else 0)) % len(self.sides)]
        s = st.art.coin(side[0], side[1], int(size), theta)
        s.set_alpha(int(255 * level))
        target.blit(s, s.get_rect(center=(st.cx + self.x, st.cy + self.y)))
        s.set_alpha(255)


class FlyingCoin(Actor):
    """Comes out of the middle turning over, spirals outward, and is gone before the rim."""

    def __init__(self, stage, delay=0.0):
        super().__init__(stage, delay)
        rng = stage.rng
        self.a0 = rng.uniform(0, math.tau)
        self.spin = rng.choice((-1, 1)) * rng.uniform(0.25, 0.75)
        self.dur = rng.uniform(2.6, 4.2)
        self.size = stage.coin_px * rng.uniform(0.9, 1.5)
        self.turns = rng.uniform(2.0, 4.0)
        self.front = (rng.choice(COINS), rng.choice(FACES))
        self.back = (rng.choice(COINS), rng.choice(FACES))
        self.r1 = stage.R * rng.uniform(0.62, 0.84)

    def _center(self) -> tuple:
        st = self.st
        r = st.R * 0.1 + (self.r1 - st.R * 0.1) * _ease("out", min(1.0, self.t / self.dur))
        a = self.a0 + self.spin * self.t
        return st.cx + r * math.cos(a), st.cy + r * math.sin(a)

    def area(self) -> pygame.Rect:
        x, y = self._center()
        k = int(self.size * 1.2)
        return pygame.Rect(int(x - k / 2), int(y - k / 2), k, k)

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        u = self.t / self.dur
        size = self.size * _ease("out", min(1.0, u / 0.18)) * smooth((1 - u) / 0.2)
        if size < 6:
            return
        theta = math.pi * self.turns * u
        side = self.front if int(theta / math.pi + 0.5) % 2 == 0 else self.back
        s = st.art.coin(side[0], side[1], int(size) & ~7 or 8, theta)
        s.set_alpha(int(255 * level))
        target.blit(s, s.get_rect(center=self._center()))
        s.set_alpha(255)


class CoinWall(Actor):
    """The disc fills with flipping coins in a wave, and more waves keep turning them over."""

    type_level = 0.25
    fade_out = 0.45

    def __init__(self, stage, dur=7.0, half=None, icons=COINS, every=2.3, hold_alpha=1.0, delay=0.0, inner=0.0,
                 keep_clear=()):
        super().__init__(stage, delay)
        self.dur, self.half, self.icons, self.every, self.hold_alpha = dur, half, icons, every, hold_alpha
        px = stage.coin_px
        pitch = px * 1.08
        lim = stage.R * 0.9 - px / 2
        rows = int(lim / (pitch * 0.866)) + 1
        org = (0.0, 0.0) if half is None else (half[0] * stage.R, half[1] * stage.R)
        self.cells = []
        for row in range(-rows, rows + 1):
            y = row * pitch * 0.866
            off = pitch / 2 if row % 2 else 0.0
            for col in range(-int(lim / pitch) - 2, int(lim / pitch) + 3):
                x = col * pitch + off
                r = math.hypot(x, y)
                if not stage.R * inner <= r <= lim:
                    continue
                if half is not None and x * half[0] + y * half[1] < px * 0.6:
                    continue
                if any(abs(x - bx) < hw + px * 0.4 and abs(y - by) < hh + px * 0.4 for bx, by, hw, hh in keep_clear):
                    continue
                seed = (row * 7919 + col * 104729) & 0xFFFF
                self.cells.append((x, y, math.hypot(x - org[0], y - org[1]), seed))
        self.speed = stage.R * 1.25
        k = int(px * 0.6) + 2
        xs, ys = [c[0] for c in self.cells] or [0.0], [c[1] for c in self.cells] or [0.0]
        self.box = pygame.Rect(stage.cx + int(min(xs)) - k, stage.cy + int(min(ys)) - k,
                               int(max(xs) - min(xs)) + 2 * k, int(max(ys) - min(ys)) + 2 * k)

    def area(self) -> pygame.Rect:
        return self.box

    def _side(self, seed: int, wave: int) -> tuple:
        v = (seed * 31 + wave * 17) & 0xFFFF
        return self.icons[v % len(self.icons)], FACES[(seed // 3 + wave) % len(FACES)]

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        art = st.art
        px = st.coin_px & ~1
        t = self.t
        left = self.dur - t
        settle = 1.0 - (1.0 - self.hold_alpha) * smooth((t - 1.4) / 1.2)
        alpha = int(255 * level * settle)
        every = self.every
        speed = self.speed
        cx, cy = st.cx, st.cy
        blit = target.blit
        used = []
        for x, y, d, seed in self.cells:
            local = t - d / speed
            if local <= 0:
                continue
            wave = int(local // every)
            turn = (local % every) / 0.55
            theta = math.pi * _ease("inout", turn) if turn < 1 else 0.0
            side = self._side(seed, wave + (1 if theta > math.pi / 2 else 0))
            # coins arrive and leave by turning, at the one prebuilt size: a wave of new sizes would hitch
            edge = min(local / 0.32, (left - 0.9 * d / (st.R * 2.0)) / 0.3 if left < 0.9 else 1.0)
            if edge <= 0.05:
                continue
            if edge < 1:
                theta = math.pi / 2 * (1 - edge)
            s = art.coin(side[0], side[1], px, theta)
            if s.get_alpha() != alpha:
                s.set_alpha(alpha)
                used.append(s)
            blit(s, (int(cx + x - s.get_width() / 2), int(cy + y - s.get_height() / 2)))
        for s in used:
            s.set_alpha(255)


class Plane(Actor):
    """The book's paper plane as a folded 3D shape: it banks along a curved path, with a shadow and a dotted trail."""

    fade_out = 0.25
    # nose, left wing tip, keel, right wing tip (x forward, y across, z up); the top view is the book's silhouette
    NOSE, WING_L, KEEL, WING_R, FOLD = (1.0, 0, 0), (-0.78, 0.66, 0.16), (-0.5, 0, -0.26), (-0.78, -0.66, 0.16), (-0.42, 0, 0.0)

    def __init__(self, stage, a0=None, delay=0.0, dur=None, size=None, target_side=None):
        super().__init__(stage, delay)
        rng = stage.rng
        R = stage.R * 1.25
        a0 = rng.uniform(0, math.tau) if a0 is None else a0
        a1 = a0 + math.pi + rng.uniform(-0.8, 0.8)
        if target_side is not None:
            a1 = math.atan2(target_side[1], target_side[0]) + rng.uniform(-0.5, 0.5)
        self.p0 = (R * math.cos(a0), R * math.sin(a0))
        self.p3 = (R * math.cos(a1), R * math.sin(a1))
        bend = rng.choice((-1, 1)) * R * rng.uniform(0.45, 0.95)
        nx, ny = -(self.p3[1] - self.p0[1]), self.p3[0] - self.p0[0]
        n = max(1.0, math.hypot(nx, ny))
        self.p1 = (self.p0[0] * 0.4 + nx / n * bend, self.p0[1] * 0.4 + ny / n * bend)
        self.p2 = (self.p3[0] * 0.4 + nx / n * bend, self.p3[1] * 0.4 + ny / n * bend)
        self.dur = dur or rng.uniform(2.6, 3.6)
        self.size = size or stage.plane_px
        self.roll_phase = rng.uniform(0, 6.28)
        self.trail: list = []
        self._next_dot = 0.0
        side = int(self.size * 3)
        self.buf = pygame.Surface((side, side), pygame.SRCALPHA)

    def _at(self, u: float) -> tuple:
        a, b, c, d = self.p0, self.p1, self.p2, self.p3
        v = 1 - u
        return (v * v * v * a[0] + 3 * v * v * u * b[0] + 3 * v * u * u * c[0] + u * u * u * d[0],
                v * v * v * a[1] + 3 * v * v * u * b[1] + 3 * v * u * u * c[1] + u * u * u * d[1])

    def _project(self, p, heading: float, roll: float, k: float, ox: float, oy: float) -> tuple:
        x, y, z = p
        cr, sr = math.cos(roll), math.sin(roll)
        y2, z2 = y * cr - z * sr, y * sr + z * cr
        ch, sh = math.cos(heading), math.sin(heading)
        return (ox + (x * ch - y2 * sh) * k, oy + (x * sh + y2 * ch) * k, z2)

    def step(self, dt: float) -> bool:
        alive = super().step(dt)
        if self.started:
            self._next_dot -= dt
            if self._next_dot <= 0:
                self._next_dot = 0.075
                self.trail.append((*self._at(min(1.0, self.t / self.dur)), self.t))
                self.trail = self.trail[-16:]
        return alive

    def area(self) -> pygame.Rect:
        st = self.st
        x, y = self._at(min(1.0, max(0.0, self.t / self.dur)))
        o = self.buf.get_width() // 2
        xs, ys = [x - o, x + o], [y - o, y + o]
        for tx, ty, _ in self.trail:  # the dots behind it
            xs.append(tx)
            ys.append(ty)
        pad = int(st.R * 0.03)
        x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
        return pygame.Rect(st.cx + x0, st.cy + y0, int(max(xs)) + pad - x0, int(max(ys)) + pad - y0)

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        u = min(1.0, self.t / self.dur)
        x, y = self._at(u)
        x2, y2 = self._at(min(1.0, u + 0.01))
        x0, y0 = self._at(max(0.0, u - 0.01))
        heading = math.atan2(y2 - y0, x2 - x0)
        roll = 0.75 * math.sin(self.t * 2.3 + self.roll_phase)
        art = st.art
        for tx, ty, born in self.trail:
            age = (self.t - born) / 1.1
            if age < 1:
                dot = art.mark("dot", max(3, int(st.R * 0.012 * (1 - age * 0.5))), art.palette["pale"])
                dot.set_alpha(int(190 * level * (1 - age)))
                target.blit(dot, (int(st.cx + tx), int(st.cy + ty)))
                dot.set_alpha(255)
        buf = self.buf
        buf.fill((0, 0, 0, 0))
        k = self.size * 0.55
        o = buf.get_width() / 2
        pts = {i: self._project(p, heading, roll, k, o, o) for i, p in enumerate((self.NOSE, self.WING_L, self.KEEL, self.WING_R, self.FOLD))}
        tint = art.palette["teal"]
        shade = lambda a, b: mix(tint, WHITE, max(0.0, min(1.0, a + b * math.sin(roll))))  # noqa: E731
        d = self.size * 0.09
        for tri in ((0, 1, 4), (0, 3, 4), (0, 2, 4)):  # the shadow, on the floor below the plane
            gfxdraw.filled_polygon(buf, [(pts[i][0] + d, pts[i][1] + d * 1.4) for i in tri], (0, 18, 28, 150))
        for tri, col in (((0, 2, 4), scale(tint, 0.62)), ((0, 1, 4), shade(0.85, 0.3)), ((0, 3, 4), shade(0.55, -0.3))):
            poly = [pts[i][:2] for i in tri]
            gfxdraw.filled_polygon(buf, poly, col)
            gfxdraw.aapolygon(buf, poly, col)
        buf.set_alpha(int(255 * level))
        target.blit(buf, (int(st.cx + x - o), int(st.cy + y - o)))


class MarkBurst(Actor):
    """The five identity marks thrown outward, tumbling."""

    def __init__(self, stage, colors, count=34, dur=1.5, delay=0.0, sector=None, speed=1.0):
        super().__init__(stage, delay)
        self.dur = dur
        rng = stage.rng
        self.items = []
        for i in range(count):
            a = rng.uniform(0, math.tau) if sector is None else math.atan2(sector[1], sector[0]) + rng.uniform(-1.2, 1.2)
            self.items.append((a, rng.uniform(0.25, 0.86) * stage.R * speed, rng.uniform(0.012, 0.042) * stage.R,
                               rng.choice(MARKS), rng.uniform(-6, 6), rng.choice(colors), rng.uniform(0, 0.25)))

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        for a, dist, size, name, spin, color, late in self.items:
            u = (self.t - late) / (self.dur - late)
            if not 0 <= u < 1:
                continue
            e = _ease("out", u)
            r = st.R * 0.08 + dist * e
            alpha = int(255 * level * smooth((1 - u) / 0.35))
            draw_mark(target, name, st.cx + r * math.cos(a), st.cy + r * math.sin(a), size * min(1.0, u * 6), spin * e + a,
                      color, alpha)


class DotWave(Actor):
    """The book's dot grid with a heartbeat: pulses run through it, dots swell and open into the identity marks."""

    type_level = 0.15
    fade_out = 0.5

    def __init__(self, stage, dur=7.0, period=1.5, delay=0.0, palette=None, strength=1.0):
        super().__init__(stage, delay)
        self.dur, self.period, self.strength = dur, period, strength
        p = stage.R * 2 / 27
        self.pitch = p
        n = int(stage.R / p) + 1
        ax = np.arange(-n, n + 1, dtype=np.float32) * p
        x, y = np.meshgrid(ax, ax)
        r = np.hypot(x, y)
        keep = r < stage.R * 0.9
        self.x, self.y, self.r = x[keep], y[keep], r[keep]
        self.xi = (self.x + stage.cx).astype(np.int32).tolist()
        self.yi = (self.y + stage.cy).astype(np.int32).tolist()
        seeds = (np.round(self.x / p) * 13 + np.round(self.y / p) * 7).astype(np.int32)
        self.marks = np.abs(seeds) % len(MARKS)
        art = stage.art
        self.colors = palette or (art.palette["dark"], art.palette["teal"], art.palette["pale"])

    def draw(self, target, level) -> None:
        if not self.started:
            return
        st = self.st
        R = st.R
        env = envelope(self.t, self.dur, 0.5, self.fade_out) * self.strength
        alpha = int(255 * level * env)
        if alpha <= 2:
            return
        t = self.t
        swell = np.zeros_like(self.r)
        speed = R * 0.8
        width = R * 0.13
        for beat in range(int(t / self.period) + 1):
            for off, gain in ((0.0, 1.0), (0.24, 0.65)):  # lub, dub
                w = (t - beat * self.period - off) * speed
                if 0 < w < R * 1.2:
                    swell = np.maximum(swell, gain * np.exp(-(((self.r - w) / width) ** 2)))
        p = self.pitch
        rim = np.clip((R * 0.9 - self.r) / (R * 0.2), 0, 1)
        sizes = (p * (0.2 + 0.72 * swell) * rim).astype(np.int32) // 2 * 2
        col = np.where(swell > 0.62, 2, np.where(swell > 0.12, 1, 1))
        marks = np.where(swell > 0.3, self.marks, 0)
        art = st.art
        names = MARKS
        colors = self.colors
        seq = []
        used = set()
        for sz, c, m, x, y in zip(sizes.tolist(), col.tolist(), marks.tolist(), self.xi, self.yi):
            if sz < 2:
                continue
            s = art.mark(names[m], sz, colors[c])
            used.add(s)
            seq.append((s, (x - sz // 2, y - sz // 2)))
        for s in used:
            s.set_alpha(alpha)
        target.blits(seq, doreturn=False)
        for s in used:
            s.set_alpha(255)


class MarketLine(Actor):
    """A market chart drawn straight across the board in the shapes of the book's chart icons."""

    type_level = 0.2
    fade_out = 0.3

    def __init__(self, stage, dur=5.5, delay=0.0):
        super().__init__(stage, delay)
        self.dur = dur
        rng = stage.rng
        R = stage.R
        n = 15
        a = math.radians(stage.rot)
        self.ux, self.uy = math.cos(a), math.sin(a)  # along the row: "up" is perpendicular, screen coordinates
        self.vx, self.vy = math.sin(a), -math.cos(a)
        self.pts = []
        level = -0.26
        for i in range(n):
            f = i / (n - 1)
            level += rng.uniform(-0.1, 0.17)
            level = max(-0.42, min(0.46, level))
            self.pts.append((-0.82 + 1.64 * f, level, rng.random()))
        self.width = max(5.0, R * 0.016)
        self.base = -0.56

    def _xy(self, s: float, h: float) -> tuple:
        R = self.st.R
        return (self.st.cx + (self.ux * s + self.vx * h) * R, self.st.cy + (self.uy * s + self.vy * h) * R)

    def draw(self, target, level) -> None:
        if not self.started or level < 0.02:
            return
        st = self.st
        art = st.art
        n = len(self.pts)
        head = _ease("inout", min(1.0, self.t / (self.dur * 0.55))) * (n - 1)
        tail = _ease("in", max(0.0, (self.t - self.dur * 0.72) / (self.dur * 0.28))) * (n - 1)
        k = 1 - st.cfg["motion.chart_strength"] * level  # the chart is a backdrop: its colors lean toward the floor
        pale, teal = mix(art.palette["pale"], st.floor, k), mix(art.palette["teal"], st.floor, k)
        red = mix(st.loss, st.floor, k)
        line = mix(art.palette["teal"], WHITE, 0.45)
        line = mix(line, st.floor, k)
        # candles first, under the line
        for i, (s, h, v) in enumerate(self.pts):
            if i > head or i < tail:
                continue
            grow = _ease("snap", min(1.0, (head - i) / 1.6)) if head < n - 1 else 1.0
            prev = self.pts[max(0, i - 1)][1]
            col = teal if h >= prev else red
            hw = 0.022
            top, bot = self.base + (h - self.base) * 0.62 * grow, self.base
            a, b = self._xy(s - hw, bot), self._xy(s + hw, bot)
            c, d = self._xy(s + hw, top), self._xy(s - hw, top)
            aa_poly(target, [a, b, c, d], col)
            w0, w1 = self._xy(s, top), self._xy(s, min(top + 0.05 + v * 0.05, h - 0.02))
            thick_line(target, w0, w1, 3, col)
        whole = int(head)
        first = int(tail)
        pts = [self._xy(p[0], p[1]) for p in self.pts]
        last = None
        for i in range(first, min(whole + 1, n)):
            q = pts[i]
            if last is not None:
                thick_line(target, last, q, self.width, line)
            last = q
        if last is not None and whole < n - 1:
            f = head - whole
            q = (pts[whole][0] + (pts[whole + 1][0] - pts[whole][0]) * f, pts[whole][1] + (pts[whole + 1][1] - pts[whole][1]) * f)
            thick_line(target, last, q, self.width, line)
            last = q
        r = self.width * 1.0
        for i in range(first, min(whole + 1, n)):
            disc(target, pts[i][0], pts[i][1], r, pale)
        if last is not None:
            disc(target, last[0], last[1], self.width * 2.0, pale)


# ====================================================================== the director
class BrandMotion:
    """Chooses what moves. Each game state has a level (how strong it may be) and its own cues."""

    LOOP = ((0.0, "flood"), (9.0, "flyers"), (17.0, "dots"), (24.0, "market"), (30.0, "pulse"), (38.0, "wall"))
    LOOP_S = 46.0

    def __init__(self, cfg, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.actors: list[Actor] = []
        self.art: Art | None = None
        self.layer: RadialLayer | None = None
        self.state = None
        self.type_dim = 1.0
        self.time = 0.0
        self.cx = self.cy = 0
        self.R = 1.0
        self.rot = 0.0
        self.coin_px = self.plane_px = self.hero_px = 1
        self.loss = (243, 113, 109)
        self.floor = (0, 0, 0)
        self.flood_strength = 1.0
        self.zoom_t: float | None = None
        self._zoom_from = 0.0
        self._logo_alpha = 0.0
        self._ad_alpha = 0.0
        self._next_cheer = 0.0
        self.objects: pygame.Surface | None = None
        self.edge_mask: pygame.Surface | None = None
        self._edge = None
        self._warm = iter(())
        self._key = None
        self._loop_t = 0.0
        self._loop_i = 0
        self._next_plane = 0.0
        self._flyer_until = 0.0
        self._flyer_next = 0.0
        self._booted = False
        self._level = 1.0
        self.goal_dirs = ((-1.0, 0.0), (1.0, 0.0))
        self.winner = None
        self.teams = ((0, 167, 150), (131, 44, 115))

    # ------------------------------------------------------------------ canvas
    def attach(self, center, mask_r: float, rim: float, rot: float) -> None:
        cfg = self.cfg
        d = 2 * rim
        key = (tuple(center), rim, rot, cfg["motion.coin_size"], cfg["motion.plane_size"], cfg["motion.hero_size"],
               *(cfg[f"motion.color_{k}"] for k in ("pale", "teal", "dark", "accent", "tint")))
        if key == self._key:
            return
        first = self._key is None
        self._key = key
        self.cx, self.cy = int(center[0]), int(center[1])
        self.R = float(rim)
        self.rot = rot
        self.coin_px = max(16, int(d * cfg["motion.coin_size"]))
        self.plane_px = max(24, int(d * cfg["motion.plane_size"]))
        self.hero_px = max(32, int(d * cfg["motion.hero_size"]))
        self.art = Art(cfg, rot)
        self.floor = hex_rgb(cfg["colors.arena_inner"])
        self._warm = iter(self.art.warm_list(self.coin_px & ~1))
        self.loss = hex_rgb(cfg["kinetic.loser_color"])
        self.art._logo_mips()  # built now, so pressing Start doesn't hitch
        self._logo_alpha = cfg["motion.logo_rest"] if cfg["motion.logo_waiting"] else 0.0  # it's simply there, from the first frame
        if first or self.layer is None or self.layer.n != int(mask_r) + 1:
            self.layer = RadialLayer(int(mask_r))
        self.actors = []

    # ------------------------------------------------------------------ cues
    def add(self, *actors) -> None:
        if not self.cfg["motion.planes"]:
            actors = [a for a in actors if not isinstance(a, Plane)]
        self.actors.extend(actors)

    def clear(self) -> None:
        for a in self.actors:
            a.leave()
        self._flyer_until = 0.0

    def _hero_sides(self, count=4) -> list:
        """The big coin's faces: the group's sub-brands, each readable at that size."""
        return [(i, "pale") for i in self.rng.sample(BRANDS, count)]

    def cue_flood(self, color=None, hero=True, dur=2.2) -> None:
        pal = self.art.palette
        color = color or pal["pale"]
        reduce = self.cfg["fx.reduce_flashing"]
        self.add(Flood(self, color, dur=dur, strength=0.45 if reduce else 1.0))
        if hero:
            self.add(HeroCoin(self, [("bull", "teal")] + self._hero_sides(3), int(self.hero_px * 0.75), delay=0.55))
        self.add(Plane(self, delay=0.5), Plane(self, delay=1.2), Plane(self, delay=2.0),
                 Shock(self, pal["teal"], rings=5, dur=1.2, width=9, gap=0.17, delay=3.0))

    def cue_flyers(self) -> None:
        self._flyer_until = self.time + 7.0
        self._flyer_next = self.time

    def cue_dots(self) -> None:
        self.add(DotWave(self, dur=6.8))

    def cue_market(self) -> None:
        self.add(MarketLine(self, dur=5.8), Plane(self, delay=2.2))

    def cue_pulse(self) -> None:
        pal = self.art.palette
        self.add(PulseBed(self, pal["teal"], pal["pale"], dur=7.8))
        # small enough to sit between the title and the prompt
        self.add(HeroCoin(self, self._hero_sides(6), int(self.hero_px * 0.62), turn_s=1.1, delay=0.4))
        self.add(Plane(self, delay=1.5), Plane(self, delay=4.5))

    def cue_wall(self) -> None:
        # the title and the prompt keep the middle; the names, the title's ends and the logo keep their places
        self.add(CoinWall(self, dur=7.5, inner=0.42, keep_clear=self._waiting_clear()))

    def _waiting_clear(self) -> tuple:
        """Where the waiting screen writes, for the coin walls to stay out of: the title, prompt, names and logo."""
        R = self.R
        a = math.radians(90 + self.rot)
        ux, uy = math.cos(a), -math.sin(a)  # "up" on the canvas
        turned = abs(math.sin(math.radians(self.rot))) > 0.7

        def box(x, y, hw, hh):
            return (x, y, hh, hw) if turned else (x, y, hw, hh)

        boxes = [box(ux * R * 0.34, uy * R * 0.34, R * 0.5, R * 0.12), box(-ux * R * 0.27, -uy * R * 0.27, R * 0.4, R * 0.06),
                 self._logo_clear(LOGO_ROW_WAITING)]
        for team in (0, 1):
            dx, dy = self._dir(team)
            boxes.append(box(dx * R * 0.5 + ux * R * 0.05, dy * R * 0.5 + uy * R * 0.05, R * 0.25, R * 0.14))
        return tuple(boxes)

    def cue_goal(self, scorer: int) -> None:
        pal = self.art.palette
        team = self.teams[scorer]
        bright = mix(team, WHITE, 0.45)
        reduce = self.cfg["fx.reduce_flashing"]
        self.clear()
        # the book limits purple and red as backgrounds, so any team but turquoise floods in fine bands from the first frame
        limited = team != pal["teal"]
        self.add(Flood(self, team, dur=1.25, strength=0.5 if reduce else 0.95, min_groove=0.72 if limited else 0.05))
        self.add(Shock(self, bright, rings=4, dur=1.2, width=20, gap=0.16))
        self.add(MarkBurst(self, (bright, pal["pale"], WHITE), count=46, dur=1.6))
        self.add(Plane(self, target_side=self._dir(scorer), delay=0.2, dur=1.8))

    def cue_beat(self, label: str, length: float) -> None:
        pal = self.art.palette
        for a in self.actors:
            if isinstance(a, (CountRing, DotWave)):
                a.leave()
        if label == "go":
            self.add(Flood(self, pal["teal"], dur=0.9, strength=0.4 if self.cfg["fx.reduce_flashing"] else 0.9))
            self.add(MarkBurst(self, (pal["pale"], WHITE, pal["teal"]), count=40, dur=1.1))
            self.add(Plane(self, delay=0.1, dur=2.0), Plane(self, delay=0.35, dur=2.2))
            return
        self.add(CountRing(self, length))
        self.add(Shock(self, pal["pale"], rings=2, dur=max(0.5, length * 0.75), width=8, gap=0.14, start=0.46))
        if label == "ready":
            beat = self.cfg["countdown.beat_s"]
            self.add(DotWave(self, dur=length + self.cfg["countdown.start"] * beat, period=beat, strength=0.8))

    def cue_final(self, length: float) -> None:
        pal = self.art.palette
        self.clear()
        self.add(Shock(self, pal["pale"], rings=4, dur=max(0.6, length * 0.7), width=11, gap=0.14, reverse=True))

    def cue_result(self) -> None:
        pal = self.art.palette
        self.clear()
        w = self.winner
        R = self.R
        slogan = (0.0, R * 0.55, R * 0.46, R * 0.03)  # keep clear of what the result screen writes
        logo = self._logo_clear(LOGO_ROW_RESULT)
        self._next_cheer = self.time + CHEER_EVERY_S
        if w is None:
            self.add(CoinWall(self, dur=3600, every=2.8, hold_alpha=self.cfg["motion.result_wall"], inner=0.66,
                              keep_clear=(slogan, logo)))
            self._cheer()
            return
        side = self._dir(w)
        bright = mix(self.teams[w], WHITE, 0.45)
        label = (side[0] * R * 0.5, side[1] * R * 0.5 - R * 0.16, R * 0.17, R * 0.42)  # trophy, winner, score, name
        # the coins keep to the rim: the winner's trophy, name and score stand in calm space
        self.add(CoinWall(self, dur=3600, half=side, icons=WIN_COINS, every=2.6, hold_alpha=self.cfg["motion.result_wall"],
                          inner=0.6, keep_clear=(label, slogan, logo)))
        self._cheer()

    def _cheer(self) -> None:
        """The result screen's fireworks. Repeats for as long as the screen stays up."""
        pal = self.art.palette
        w = self.winner
        if w is None:
            self.add(Shock(self, pal["pale"], rings=3, dur=1.6, width=10, gap=0.24))
            self.add(MarkBurst(self, (pal["pale"], pal["teal"]), count=30, dur=2.0))
            return
        side = self._dir(w)
        bright = mix(self.teams[w], WHITE, 0.45)
        self.add(Shock(self, bright, rings=4, dur=1.4, width=16, gap=0.2))
        self.add(MarkBurst(self, (bright, pal["pale"], WHITE), count=52, dur=2.0, sector=side))
        self.add(Plane(self, target_side=side, delay=0.4), Plane(self, target_side=side, delay=1.2))

    def _logo_clear(self, row: float) -> tuple:
        """The logo's rectangle on screen, for the coin walls to stay out of."""
        size = self.cfg["motion.logo_size" if row == LOGO_ROW_WAITING else "motion.logo_result_size"]
        return (0.0, -row * self.R, self.R * size * 1.12, self.R * size * LOGO_ASPECT * 1.2)  # with a little air

    def _dir(self, team: int) -> tuple:
        x, y = self.goal_dirs[team]
        return (x, -y)  # arena y points up, the canvas's points down

    # ------------------------------------------------------------------ events
    def handle_events(self, events, engine) -> None:
        cfg = self.cfg
        if not cfg["motion.enabled"] or self.art is None:
            return
        for e in events:
            et = e["type"]
            if et == "state":
                self.goal_dirs = engine.geom.goal_dir
                self.winner = getattr(engine, "winner", None)
                self.on_state(e["state"], e.get("prev"))
            elif et == "countdown_beat":
                _, _, length, _ = engine.countdown_info()
                self.cue_beat(e["label"], length)
            elif et == "goal" and not e.get("demo") and cfg["motion.on_goal"]:
                self.goal_dirs = engine.geom.goal_dir
                self.cue_goal(e["scorer"])
            elif et == "match_end":
                self.winner = e.get("winner")

    def on_state(self, state: str, prev=None) -> None:
        cfg = self.cfg
        self.state = state
        self.teams = (hex_rgb(cfg["colors.p1"]), hex_rgb(cfg["colors.p2"]))
        if state == "ATTRACT":
            self.clear()
            self._loop_t, self._loop_i = 0.0, 0
        elif state == "INTRO":
            self.clear()
            if cfg["motion.logo_zoom"] and cfg["match.intro_s"] > 0.05:
                self.zoom_t = 0.0
                self._zoom_from = self._logo_alpha
                self._logo_alpha = 0.0
            else:
                self.cue_flood(self.art.palette["teal"], hero=False, dur=max(0.6, cfg["match.intro_s"] + 0.15))
        elif state in ("PLAYING", "SERVE"):
            if not self._next_plane:
                self._next_plane = self.time + cfg["motion.plane_every_s"] * 0.5
        elif state == "FINAL":
            self.cue_final(cfg["match.final_freeze_s"])
        elif state == "RESULT":
            self.cue_result()

    # ------------------------------------------------------------------ per frame
    def level(self) -> float:
        cfg = self.cfg
        return {"ATTRACT": cfg["motion.level_waiting"], "INTRO": cfg["motion.level_moment"],
                "COUNTDOWN": cfg["motion.level_countdown"], "SERVE": cfg["motion.level_play"],
                "PLAYING": cfg["motion.level_play"], "GOAL": cfg["motion.level_moment"],
                "FINAL": cfg["motion.level_moment"], "RESULT": cfg["motion.level_result"]}.get(self.state, 0.0)

    def update(self, dt: float, state: str | None = None) -> None:
        cfg = self.cfg
        if not cfg["motion.enabled"] or self.art is None:
            self.type_dim = 1.0
            return
        if state is not None and state != self.state:
            self.state = state
        self.time += dt
        for args in itertools.islice(self._warm, WARM_PER_FRAME):
            self.art.coin(*args)
        self._level += (self.level() - self._level) * (1 - math.exp(-6 * dt))
        self.flood_strength = cfg["motion.flood_strength"]
        rest = cfg["motion.logo_rest"] if self.state == "ATTRACT" and cfg["motion.logo_waiting"] else 0.0
        self._logo_alpha += (rest - self._logo_alpha) * (1 - math.exp(-2.5 * dt))  # back from a match, it fades in gently
        ad = cfg["motion.logo_play_opacity"] if self.state in ("SERVE", "PLAYING", "GOAL") and cfg["motion.logo_play"] else 0.0
        self._ad_alpha += (ad - self._ad_alpha) * (1 - math.exp(-(1.2 if ad else 3.0) * dt))  # in slowly, out quickly
        if self.zoom_t is not None:
            self.zoom_t += dt
            if self.zoom_t >= cfg["match.intro_s"] or self.state != "INTRO":
                self.zoom_t = None
        if self.state == "ATTRACT" and cfg["motion.waiting_loop"]:
            if not self._booted and not cfg["motion.splash"]:
                self._loop_t, self._loop_i = 9.0, 1  # no opening flood
            self._booted = True
            self._loop_t += dt
            while self._loop_i < len(self.LOOP) and self.LOOP[self._loop_i][0] <= self._loop_t:
                getattr(self, "cue_" + self.LOOP[self._loop_i][1])()
                self._loop_i += 1
            if self._loop_t >= self.LOOP_S:
                self._loop_t, self._loop_i = 0.0, 0
            if self.time < self._flyer_until and self.time >= self._flyer_next:
                self._flyer_next = self.time + self.rng.uniform(0.18, 0.42)
                self.add(FlyingCoin(self))
        elif self.state in ("PLAYING", "SERVE") and cfg["motion.in_play"]:
            if self.time >= self._next_plane:
                self._next_plane = self.time + cfg["motion.plane_every_s"] * self.rng.uniform(0.8, 1.2)
                self.add(Plane(self))
        elif self.state == "RESULT" and self.time >= self._next_cheer:
            self._next_cheer = self.time + CHEER_EVERY_S
            self._cheer()
        if not cfg["motion.planes"]:  # unticked while the game runs: those already in the air fade out
            for a in self.actors:
                if isinstance(a, Plane):
                    a.leave()
        self.actors = [a for a in self.actors if a.step(dt)]
        target = min((a.type_limit() for a in self.actors), default=1.0)
        self.type_dim += (target - self.type_dim) * (1 - math.exp(-5 * dt))

    def draw(self, canvas: pygame.Surface) -> None:
        if not self.cfg["motion.enabled"] or self.art is None:
            return
        level = max(0.0, min(1.0, self._level))
        cfg = self.cfg
        start, end = cfg["motion.edge_fade_start"] * self.R, cfg["motion.edge_fade_end"] * self.R
        layer = self.layer
        layer.begin()
        for a in self.actors:
            a.radial(layer, level * a.presence())
        layer.fade_edge(start, end)
        layer.composite(canvas, self.cx, self.cy)
        self.draw_rest_logo(canvas)
        self.draw_play_logo(canvas)
        opacity = level * cfg["motion.object_opacity"]
        if opacity < 0.01 or not any(a.paints and a.started for a in self.actors):
            return
        # together on one layer: overlapping objects don't show through each other, and the rim fade is per pixel
        self._prepare_objects(canvas.get_size(), start, end)
        objects = self.objects
        area = self._paint_area(end, objects.get_rect())
        objects.set_clip(area)
        objects.fill((0, 0, 0, 0))
        for a in self.actors:
            a.draw(objects, a.presence())
        objects.set_clip(None)
        objects.blit(self.edge_mask, area.topleft, area, special_flags=pygame.BLEND_RGBA_MULT)
        objects.set_alpha(int(255 * min(1.0, opacity)))
        canvas.blit(objects, area.topleft, area)

    def _paint_area(self, end: float, bounds: pygame.Rect) -> pygame.Rect:
        """The part of the layer this frame can touch: nothing shows past the rim fade, and most objects are small."""
        k = int(end) + 2
        whole = pygame.Rect(self.cx - k, self.cy - k, k * 2, k * 2).clip(bounds)
        rects = [a.area() for a in self.actors if a.paints and a.started]
        if not rects or None in rects:
            return whole
        return rects[0].unionall(rects[1:]).clip(whole)

    def zoom_frame(self, u: float, rest: float) -> tuple:
        """The start logo at `u` (0..1) of its time: (size as a multiple of its resting size, opacity, share of the way
        from its resting place to the center). All three are smooth curves that run the whole time, with no phases to
        switch between: a spring carries it to the center with one soft overshoot and a little growth, the growth then
        builds, and the fade comes in while it is still growing and lands gently on zero."""
        spring = spring_step(u / ZOOM_SPRING)
        growth = max(0.0, (u - ZOOM_GROW) / (1 - ZOOM_GROW)) ** 2
        size = math.exp(math.log(ZOOM_NEAR) * spring + math.log(ZOOM_END / ZOOM_NEAR) * growth)
        opacity = (rest + (1.0 - rest) * smoother(u / ZOOM_GAIN)) * (1.0 - smoother((u - ZOOM_FADE) / (1 - ZOOM_FADE)))
        return size, opacity, spring

    def _logo_place(self, row: float) -> tuple:
        a = math.radians(90 + self.rot)
        return self.cx + math.cos(a) * self.R * row, self.cy - math.sin(a) * self.R * row

    def _rest_width(self) -> int:
        return int(self.R * 2 * self.cfg["motion.logo_size"])

    def draw_rest_logo(self, canvas: pygame.Surface) -> None:
        """The logo, always there behind everything on the waiting screen."""
        if self._logo_alpha <= 0.01 or self.zoom_t is not None:
            return
        self._blit_logo(canvas, self._rest_width(), self._logo_place(LOGO_ROW_WAITING), self._logo_alpha)

    def draw_play_logo(self, canvas: pygame.Surface) -> None:
        """During the match: the logo faint in the middle of the floor, under the game, like a sponsor's mark on ice."""
        if self._ad_alpha > 0.004:
            self._blit_logo(canvas, int(self.R * 2 * self.cfg["motion.logo_play_size"]), (self.cx, self.cy), self._ad_alpha)

    def draw_result_logo(self, canvas: pygame.Surface, alpha: float) -> None:
        """The logo at the head of the result screen, with nothing around it."""
        if self.art:
            self._blit_logo(canvas, int(self.R * 2 * self.cfg["motion.logo_result_size"]), self._logo_place(LOGO_ROW_RESULT), alpha)

    def _blit_logo(self, canvas, width: int, center: tuple, alpha: float) -> None:
        """Every frame of the logo goes through here, so the resting logo and the first frame of the zoom are identical."""
        frame, pos = self.art.logo_frame(width, center, canvas.get_rect())
        if frame is not None:
            frame.set_alpha(int(255 * alpha + 0.5))
            canvas.blit(frame, pos)

    def draw_logo_zoom(self, canvas: pygame.Surface) -> None:
        """After Start: the waiting screen's logo brightens, springs to the center, grows, and fades out as it grows."""
        cfg = self.cfg
        if self.zoom_t is None or self.art is None or not cfg["motion.enabled"]:
            return
        k, opacity, travel = self.zoom_frame(self.zoom_t / max(0.05, cfg["match.intro_s"]), self._zoom_from)
        if opacity <= 0.004:
            return
        rx, ry = self._logo_place(LOGO_ROW_WAITING)
        center = (rx + (self.cx - rx) * travel, ry + (self.cy - ry) * travel)
        self._blit_logo(canvas, int(self._rest_width() * k), center, opacity)

    def _prepare_objects(self, size, start: float, end: float) -> None:
        key = (size, self.cx, self.cy, round(start, 1), round(end, 1))
        if key == self._edge:
            return
        self._edge = key
        self.objects = pygame.Surface(size, pygame.SRCALPHA)
        W, H = size
        x = np.arange(W, dtype=np.float32)[:, None] + 0.5 - self.cx
        y = np.arange(H, dtype=np.float32)[None, :] + 0.5 - self.cy
        t = np.clip((np.hypot(x, y) - start) / max(1.0, end - start), 0, 1)
        self.edge_mask = pygame.Surface(size, pygame.SRCALPHA)
        self.edge_mask.fill((255, 255, 255, 255))
        alpha = pygame.surfarray.pixels_alpha(self.edge_mask)
        alpha[:] = ((1 - t * t * (3 - 2 * t)) * 255).astype(np.uint8)
        del alpha
