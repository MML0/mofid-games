"""A bounded particle pool drawn as soft glow sprites on the additive layer."""

from __future__ import annotations

import math
import random


class Particles:
    def __init__(self, rng: random.Random | None = None):
        # x, y, vx, vy, life, max_life, color, size, drag, twinkle_phase (None = steady)
        self.items: list[list] = []
        self.rng = rng or random.Random()

    def burst(self, x, y, color, n=20, speed=(80, 320), life=(0.3, 0.8), size=(1.5, 3.5), cap=600, drag=2.5,
              direction=None, spread=math.pi, twinkle=False):
        rnd = self.rng
        if cap <= 0:
            return
        for _ in range(int(n)):
            if len(self.items) >= cap:
                self.items.pop(0)
            a = rnd.uniform(0, math.tau) if direction is None else direction + rnd.uniform(-spread, spread)
            sp = rnd.uniform(*speed)
            lf = rnd.uniform(*life)
            self.items.append([x, y, math.cos(a) * sp, math.sin(a) * sp, lf, lf, color, rnd.uniform(*size), drag,
                               rnd.uniform(0, math.tau) if twinkle else None])

    def converge(self, R, color, n=30, cap=600, life=0.7):
        rnd = self.rng
        if cap <= 0:
            return
        for _ in range(int(n)):
            if len(self.items) >= cap:
                self.items.pop(0)
            a = rnd.uniform(0, math.tau)
            r = R * rnd.uniform(0.75, 0.98)
            sp = r / life
            self.items.append([math.cos(a) * r, math.sin(a) * r, -math.cos(a) * sp, -math.sin(a) * sp, life, life,
                               color, rnd.uniform(1.5, 3.5), 0.0, None])

    def update(self, dt):
        keep = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0:
                continue
            k = math.exp(-p[8] * dt)
            p[2] *= k
            p[3] *= k
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            keep.append(p)
        self.items = keep

    def draw(self, layer, to_canvas, glow=None, time_s: float = 0.0):
        import pygame

        surf = layer.surf
        for x, y, vx, vy, life, mx, color, size, drag, tw in self.items:
            f = life / mx
            if tw is not None:
                f *= 0.55 + 0.45 * math.sin(tw + life * 28.0)
            sx, sy = to_canvas(x, y)
            if glow is not None:
                layer.blit(glow.sprite(color, size * 3.2, round(min(1.4, f * 1.2) * 10) / 10), (sx, sy))
            else:
                c = (int(color[0] * f), int(color[1] * f), int(color[2] * f))
                layer.mark(pygame.draw.circle(surf, c, (int(sx), int(sy)), max(1, int(size))))

    def clear(self):
        self.items.clear()
