"""Additive glow layer and cached radial-gradient sprites."""

from __future__ import annotations

import pygame


class GlowCache:
    def __init__(self, max_items: int = 800):
        self.cache: dict = {}
        self.max_items = max_items

    def sprite(self, color, radius: float, intensity: float = 1.0) -> pygame.Surface:
        r = max(2, int(radius))
        q = max(0, min(40, int(intensity * 20 + 0.5)))
        key = (tuple(color[:3]), r, q)
        s = self.cache.get(key)
        if s is None:
            if len(self.cache) > self.max_items:
                self.cache.clear()
            s = pygame.Surface((2 * r, 2 * r))
            s.fill((0, 0, 0))
            steps = max(6, min(28, r // 2))
            k = q / 20.0
            for i in range(steps):
                t = (i + 1) / steps  # 0 outer -> 1 inner
                rr = max(1, int(r * (1 - i / steps)))
                a = (t ** 2.2) * k
                col = tuple(min(255, int(c * a)) for c in color[:3])
                pygame.draw.circle(s, col, (r, r), rr)
            self.cache[key] = s
        return s


class AddLayer:
    """An RGB surface composited onto the canvas with BLEND_ADD. Tracks a dirty rect so that clearing and
    compositing only touch the area actually drawn this frame."""

    def __init__(self, size):
        self.surf = pygame.Surface(size)
        self.surf.fill((0, 0, 0))
        self.dirty: pygame.Rect | None = None
        self.prev: pygame.Rect | None = None

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
