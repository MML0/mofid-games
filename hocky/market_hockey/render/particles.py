"""A bounded particle pool drawn on the additive layer."""

from __future__ import annotations

import math
import random

import pygame


class Particles:
    def __init__(self, rng: random.Random | None = None):
        self.items: list[list] = []  # x, y, vx, vy, life, max_life, color, size, drag, gravity_to_center
        self.rng = rng or random.Random()

    def burst(self, x, y, color, n=20, speed=(80, 320), life=(0.3, 0.8), size=(1.5, 3.5), cap=600, drag=2.5,
              direction=None, spread=math.pi):
        rnd = self.rng
        for _ in range(int(n)):
            if len(self.items) >= cap:
                self.items.pop(0)
            if direction is None:
                a = rnd.uniform(0, math.tau)
            else:
                a = direction + rnd.uniform(-spread, spread)
            sp = rnd.uniform(*speed)
            lf = rnd.uniform(*life)
            self.items.append([x, y, math.cos(a) * sp, math.sin(a) * sp, lf, lf, color, rnd.uniform(*size), drag, 0.0])

    def converge(self, R, color, n=30, cap=600, life=0.7):
        rnd = self.rng
        for _ in range(int(n)):
            if len(self.items) >= cap:
                self.items.pop(0)
            a = rnd.uniform(0, math.tau)
            r = R * rnd.uniform(0.75, 0.98)
            x, y = math.cos(a) * r, math.sin(a) * r
            sp = r / life
            self.items.append([x, y, -math.cos(a) * sp, -math.sin(a) * sp, life, life, color, rnd.uniform(1.5, 3.5),
                               0.0, 0.0])

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

    def draw(self, layer, to_canvas):
        surf = layer.surf
        for x, y, vx, vy, life, mx, color, size, *_ in self.items:
            f = life / mx
            c = (int(color[0] * f), int(color[1] * f), int(color[2] * f))
            sx, sy = to_canvas(x, y)
            layer.mark(pygame.draw.circle(surf, c, (int(sx), int(sy)), max(1, int(size * (0.5 + 0.5 * f)))))

    def clear(self):
        self.items.clear()
