"""Additive glow layer, smooth dithered radial-gradient sprites, and gradient helpers (numpy)."""

from __future__ import annotations

import numpy as np
import pygame

_rng = np.random.default_rng(12345)


def dither_noise(shape, strength: float = 1.0) -> np.ndarray:
    """Triangular-PDF noise in [-strength, strength] LSB: breaks 8-bit banding without visible grain."""
    if strength <= 0:
        return np.zeros(shape, dtype=np.float32)
    return ((_rng.random(shape, dtype=np.float32) + _rng.random(shape, dtype=np.float32)) - 1.0) * strength


def to_surface(rgb: np.ndarray) -> pygame.Surface:
    """rgb: float array (W, H, 3) in 0..255 (x-major, like pygame.surfarray)."""
    return pygame.surfarray.make_surface(np.clip(rgb + 0.5, 0, 255).astype(np.uint8))


class GlowCache:
    def __init__(self, max_items: int = 2500, dither: float = 1.0):
        self.cache: dict = {}
        self.max_items = max_items
        self.dither = dither

    def sprite(self, color, radius: float, intensity: float = 1.0) -> pygame.Surface:
        """Soft radial glow (black background, use with BLEND_ADD). `radius` is the visible extent."""
        r = max(2, int(radius + 0.5))
        if r > 24:
            r = int(round(r / 2.0) * 2)  # quantize large sprites to keep the cache small
        q = max(0, min(60, int(intensity * 20 + 0.5)))
        key = (tuple(int(v) for v in color[:3]), r, q)
        s = self.cache.get(key)
        if s is None:
            if len(self.cache) > self.max_items:
                self.cache.clear()
            n = 2 * r
            ax = (np.arange(n, dtype=np.float32) + 0.5 - r) / r
            d2 = ax[:, None] ** 2 + ax[None, :] ** 2
            # smooth core + long soft tail, exactly zero at the edge
            f = np.exp(-d2 * 3.2) * np.clip(1.0 - d2, 0.0, 1.0) ** 1.5
            k = q / 20.0
            col = np.array(color[:3], dtype=np.float32) * k
            img = f[:, :, None] * col[None, None, :]
            if self.dither > 0:
                img += dither_noise(img.shape[:2], self.dither * 0.6)[:, :, None] * (f[:, :, None] > 0.002)
            s = to_surface(img)
            self.cache[key] = s
        return s


class AddLayer:
    """An RGB surface composited onto the canvas with BLEND_ADD. Tracks a dirty rect so that clearing and
    compositing only touch the area actually drawn this frame."""

    def __init__(self, size):
        self.surf = pygame.Surface(size)
        self.surf.fill((0, 0, 0))
        self.dirty: pygame.Rect | None = None

    def mark(self, rect) -> None:
        if rect is None:
            return
        r = pygame.Rect(rect)
        if r.w <= 0 or r.h <= 0:
            return
        self.dirty = r if self.dirty is None else self.dirty.union(r)

    def blit(self, sprite: pygame.Surface, center) -> None:
        w, h = sprite.get_size()
        pos = (int(center[0] - w / 2), int(center[1] - h / 2))
        self.mark(self.surf.blit(sprite, pos, special_flags=pygame.BLEND_ADD))

    def begin(self) -> None:
        if self.dirty is not None:
            self.surf.fill((0, 0, 0), self.dirty)
        self.dirty = None

    def composite(self, canvas: pygame.Surface) -> None:
        if self.dirty is not None:
            r = self.dirty.clip(self.surf.get_rect())
            canvas.blit(self.surf, r.topleft, r, special_flags=pygame.BLEND_ADD)


def radial_background(W, H, cx, cy, radius, inner, outer, dither=1.0, gamma=0.8) -> pygame.Surface:
    """Smooth radial gradient inside `radius` (black outside), dithered so no banding steps are visible."""
    xs = np.arange(W, dtype=np.float32) + 0.5 - cx
    ys = np.arange(H, dtype=np.float32) + 0.5 - cy
    d = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2) / max(1.0, radius)
    t = np.clip(d, 0.0, 1.0) ** gamma
    inner = np.array(inner[:3], dtype=np.float32)
    outer = np.array(outer[:3], dtype=np.float32)
    img = inner[None, None, :] + (outer - inner)[None, None, :] * t[:, :, None]
    # a gentle vignette toward the rim for depth
    img *= (1.0 - 0.18 * np.clip((d - 0.75) / 0.25, 0.0, 1.0) ** 2)[:, :, None]
    img[d > 1.0] = 0.0
    if dither > 0:
        img += dither_noise((W, H), dither)[:, :, None]
    return to_surface(img)
