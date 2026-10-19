"""Mouse adapter (debug): the mouse angle around the arena center drives the selected player."""

from __future__ import annotations

import math

import pygame

from .base import InputAdapter, PlayerSample


class MouseAdapter(InputAdapter):
    name = "mouse"

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        if engine is None:
            return PlayerSample(False, None, 0, now, None, self.name)
        try:
            mx, my = pygame.mouse.get_pos()
        except pygame.error:
            return PlayerSample(True, None, 1, now, None, self.name)
        x, y = engine.geom.to_arena(mx, my)
        ang = math.degrees(math.atan2(y, x))
        u = engine.geom.angle_to_u(idx, ang, engine.paddle_width(idx))
        r = engine.geom.R or 1.0
        return PlayerSample(True, u, 1.0, now, (x / r, y / r), self.name)
