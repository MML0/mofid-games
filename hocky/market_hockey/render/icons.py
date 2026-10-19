"""Procedural vector icons for power-ups, drawn with pygame primitives (crisp at any size).

assets/icons/<type_id>.png overrides the procedural icon for that power-up.
"""

from __future__ import annotations

import math

import pygame

from ..paths import ICONS_DIR


def _aa_poly(s, color, pts):
    pygame.draw.polygon(s, color, pts)
    pygame.draw.aalines(s, color, True, pts)


def _line(s, color, a, b, w):
    pygame.draw.line(s, color, a, b, w)
    r = max(1, w // 2)
    pygame.draw.circle(s, color, (int(a[0]), int(a[1])), r)
    pygame.draw.circle(s, color, (int(b[0]), int(b[1])), r)


def _arrow_head(s, color, tip, ang, size):
    l = (tip[0] - size * math.cos(ang - 0.55), tip[1] - size * math.sin(ang - 0.55))
    r = (tip[0] - size * math.cos(ang + 0.55), tip[1] - size * math.sin(ang + 0.55))
    _aa_poly(s, color, [tip, l, r])


def _bar(s, color, cx, cy, w, h):
    rect = pygame.Rect(0, 0, int(w), int(h))
    rect.center = (int(cx), int(cy))
    pygame.draw.rect(s, color, rect, border_radius=int(h / 2))


def draw_icon(s: pygame.Surface, name: str, color=(255, 255, 255)) -> None:
    S = s.get_width()
    c = S / 2
    lw = max(2, int(S * 0.075))
    if name == "expand":
        _bar(s, color, c, c, S * 0.36, S * 0.16)
        for d in (-1, 1):
            tip = (c + d * S * 0.46, c)
            _line(s, color, (c + d * S * 0.22, c), tip, lw)
            _arrow_head(s, color, tip, 0 if d > 0 else math.pi, S * 0.16)
    elif name == "shrink":
        _bar(s, color, c, c, S * 0.22, S * 0.16)
        for d in (-1, 1):
            tip = (c + d * S * 0.15, c)
            _line(s, color, (c + d * S * 0.46, c), tip, lw)
            _arrow_head(s, color, tip, math.pi if d > 0 else 0, S * 0.15)
        pygame.draw.circle(s, color, (int(c), int(c - S * 0.3)), max(2, int(S * 0.06)))  # "opponent" marker
    elif name == "speed_up":
        pts = [(c + S * 0.08, c - S * 0.44), (c - S * 0.2, c + S * 0.04), (c - S * 0.02, c + S * 0.04),
               (c - S * 0.1, c + S * 0.44), (c + S * 0.22, c - S * 0.08), (c + S * 0.03, c - S * 0.08)]
        _aa_poly(s, color, pts)
    elif name == "slow_down":
        pts = [(c - S * 0.42 + S * 0.84 * k / 30, c - S * 0.08 + S * 0.1 * math.sin(k / 30 * math.tau * 1.5))
               for k in range(31)]
        pygame.draw.lines(s, color, False, pts, lw)
        y = c + S * 0.18
        _line(s, color, (c - S * 0.16, y), (c, y + S * 0.14), lw)
        _line(s, color, (c + S * 0.16, y), (c, y + S * 0.14), lw)
    elif name == "chaos":
        for flip in (1, -1):
            pts = []
            for k in range(21):
                t = k / 20
                x = c - S * 0.4 + S * 0.72 * t
                y = c + flip * S * 0.26 * math.cos(t * math.pi)
                pts.append((x, y))
            pygame.draw.lines(s, color, False, pts, lw)
            a = math.atan2(pts[-1][1] - pts[-3][1], pts[-1][0] - pts[-3][0])
            _arrow_head(s, color, (pts[-1][0] + S * 0.06, pts[-1][1]), a, S * 0.16)
    elif name == "double_ball":
        r = int(S * 0.2)
        pygame.draw.circle(s, color, (int(c - S * 0.12), int(c + S * 0.06)), r, lw)
        pygame.draw.circle(s, color, (int(c + S * 0.14), int(c - S * 0.08)), r)
    elif name == "trajectory":
        pts = []
        for k in range(9):
            t = k / 8
            pts.append((c - S * 0.4 + S * 0.62 * t, c + S * 0.36 - S * 0.62 * t + S * 0.25 * math.sin(t * math.pi)))
        for x, y in pts[:-1]:
            pygame.draw.circle(s, color, (int(x), int(y)), max(1, int(S * 0.04)))
        tx, ty = c + S * 0.26, c - S * 0.26
        pygame.draw.circle(s, color, (int(tx), int(ty)), int(S * 0.15), max(2, lw - 1))
        pygame.draw.circle(s, color, (int(tx), int(ty)), max(2, int(S * 0.05)))
    elif name == "dim_ball":
        r = int(S * 0.34)
        pygame.draw.circle(s, color, (int(c), int(c)), r, lw)
        half = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.circle(half, color, (int(c), int(c)), r)
        s.blit(half, (0, 0), pygame.Rect(0, 0, int(c), S))
    elif name == "shield":
        pts = [(c, c - S * 0.42), (c + S * 0.34, c - S * 0.28), (c + S * 0.3, c + S * 0.12), (c, c + S * 0.42),
               (c - S * 0.3, c + S * 0.12), (c - S * 0.34, c - S * 0.28)]
        pygame.draw.polygon(s, color, pts, lw)
        _line(s, color, (c - S * 0.08, c - S * 0.14), (c - S * 0.08, c + S * 0.16), lw)
        _line(s, color, (c + S * 0.08, c - S * 0.14), (c + S * 0.08, c + S * 0.16), lw)
    elif name == "bull":
        pygame.draw.circle(s, color, (int(c), int(c + S * 0.1)), int(S * 0.2))
        for d in (-1, 1):
            pts = []
            for k in range(13):
                t = k / 12
                a = math.pi * (0.95 - 0.75 * t)
                x = c + d * (S * 0.14 + S * 0.24 * (1 - math.cos(a)) * 0.6)
                y = c - S * 0.02 - S * 0.34 * math.sin(math.pi * t * 0.6)
                pts.append((x, y))
            pygame.draw.lines(s, color, False, pts, lw + 1)
    elif name == "trophy":
        cup = [(c - S * 0.26, c - S * 0.36), (c + S * 0.26, c - S * 0.36), (c + S * 0.2, c - S * 0.02),
               (c + S * 0.08, c + S * 0.1), (c - S * 0.08, c + S * 0.1), (c - S * 0.2, c - S * 0.02)]
        _aa_poly(s, color, cup)
        for d in (-1, 1):
            rect = pygame.Rect(0, 0, int(S * 0.24), int(S * 0.26))
            rect.center = (int(c + d * S * 0.27), int(c - S * 0.2))
            pygame.draw.circle(s, color, rect.center, int(S * 0.12), lw)
        _bar(s, color, c, c + S * 0.2, S * 0.08, S * 0.2)
        _bar(s, color, c, c + S * 0.36, S * 0.4, S * 0.1)
    else:  # fallback: a star-ish diamond
        _aa_poly(s, color, [(c, c - S * 0.4), (c + S * 0.3, c), (c, c + S * 0.4), (c - S * 0.3, c)])


class IconCache:
    def __init__(self):
        self.cache: dict = {}
        self.files: dict = {}

    def icon(self, name: str, type_id: str, size: int, color=(255, 255, 255)) -> pygame.Surface:
        size = max(8, int(size))
        key = (name, type_id, size, tuple(color))
        s = self.cache.get(key)
        if s is None:
            override = ICONS_DIR / f"{type_id}.png"
            if override.exists():
                try:
                    img = self.files.get(type_id) or pygame.image.load(str(override))
                    self.files[type_id] = img
                    s = pygame.transform.smoothscale(img.convert_alpha() if pygame.display.get_surface() else img,
                                                     (size, size))
                except pygame.error:
                    s = None
            if s is None:
                big = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                draw_icon(big, name, color)
                s = pygame.transform.smoothscale(big, (size, size))
            self.cache[key] = s
        return s

    def badge(self, name, type_id, radius, ring_color, bad: bool, icon_scale: float = 0.62) -> pygame.Surface:
        """The orb body: dark disc, class-colored ring (dashed for bad), white icon."""
        r = max(6, int(radius))
        key = ("badge", name, type_id, r, tuple(ring_color), bad, round(icon_scale, 2))
        s = self.cache.get(key)
        if s is None:
            S = 2 * r + 6
            big = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)
            C = S
            R2 = r * 2
            pygame.draw.circle(big, (6, 22, 30, 235), (C, C), R2)
            lw = max(3, R2 // 9)
            if bad:
                n = 14
                for k in range(n):
                    a0 = k / n * math.tau
                    a1 = a0 + math.tau / n * 0.6
                    rect = pygame.Rect(C - R2, C - R2, 2 * R2, 2 * R2)
                    pygame.draw.arc(big, ring_color, rect, a0, a1, lw)
                pygame.draw.circle(big, (*ring_color, 90), (C, C), R2 - lw - 2, 2)
            else:
                pygame.draw.circle(big, ring_color, (C, C), R2, lw)
            isz = int(R2 * 2 * icon_scale)
            icon = pygame.Surface((isz, isz), pygame.SRCALPHA)
            override = ICONS_DIR / f"{type_id}.png"
            if override.exists():
                try:
                    icon = pygame.transform.smoothscale(pygame.image.load(str(override)), (isz, isz))
                except pygame.error:
                    draw_icon(icon, name, (255, 255, 255))
            else:
                draw_icon(icon, name, (255, 255, 255))
            big.blit(icon, (C - isz // 2, C - isz // 2))
            s = pygame.transform.smoothscale(big, (S, S))
            self.cache[key] = s
        return s
