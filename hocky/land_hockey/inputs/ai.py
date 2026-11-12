"""AI player: used for the attract-mode demo, single-player vs CPU, and soak tests. Pure Python.

Movement is deliberately human-like: the aim point is chosen once per incoming ball, the target is low-pass
filtered, and the paddle follows it with a critically damped spring (smooth ease-in / ease-out).
"""

from __future__ import annotations

import math
import random

from ..prediction.trajectory import predict
from .base import InputAdapter, PlayerSample


class AIAdapter(InputAdapter):
    name = "ai"

    def __init__(self, cfg, rng: random.Random | None = None):
        super().__init__(cfg)
        self.rng = rng or random.Random()
        self.u = [0.5, 0.5]
        self.v = [0.0, 0.0]
        self.target = [0.5, 0.5]
        self.eased = [0.5, 0.5]
        self.next_think = [0.0, 0.0]
        self.aim_key = [None, None]
        self.aim_off = [0.0, 0.0]
        self.clock = 0.0

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        c = self.cfg
        if idx == 0:
            self.clock += dt
        t = self.clock
        if engine is not None and t >= self.next_think[idx]:
            self.next_think[idx] = t + c["input.ai.reaction_s"] * self.rng.uniform(0.8, 1.2)
            self.target[idx] = self._think(idx, engine, t)
        if dt <= 0:
            return PlayerSample(True, self.u[idx], 1.0, now, None, self.name)
        k = c["input.ai.smoothing"]
        # low-pass the target, then follow it with a critically damped spring
        self.eased[idx] += (self.target[idx] - self.eased[idx]) * (1 - math.exp(-dt * k * 0.8))
        diff = c["input.ai.difficulty"]
        vmax = c["input.ai.max_speed"] * (0.55 + 0.6 * diff)
        a = k * k * (self.eased[idx] - self.u[idx]) - 2 * k * self.v[idx]
        self.v[idx] = max(-vmax, min(vmax, self.v[idx] + a * dt))
        self.u[idx] = max(0.0, min(1.0, self.u[idx] + self.v[idx] * dt))
        if self.u[idx] in (0.0, 1.0):
            self.v[idx] = 0.0
        return PlayerSample(True, self.u[idx], 1.0, now, None, self.name)

    def _think(self, idx, engine, t) -> float:
        c = self.cfg
        diff = c["input.ai.difficulty"]
        best = None
        for b in engine.live_balls():
            if b.held or engine.heading_to(b) != idx:
                continue
            pr = predict(engine, b, idx, max_time=3.0, max_bounces=6, point_spacing=1e9)
            if pr.contact_angle is None:
                continue
            if best is None or (pr.contact_time or 9) < best[0]:
                best = (pr.contact_time or 9, pr.contact_angle, (b.id, b.hits))
        if best is None:
            self.aim_key[idx] = None
            return 0.5 + 0.12 * math.sin(t * 0.45 + idx * 2.1)  # gentle idle sway
        if self.aim_key[idx] != best[2]:  # new incoming ball: decide once how to play it
            self.aim_key[idx] = best[2]
            noise = c["input.ai.noise"] * (1.25 - diff)
            self.aim_off[idx] = self.rng.gauss(0, noise) + self.rng.uniform(-0.05, 0.05) * diff
        u = engine.geom.angle_to_u(idx, best[1], engine.paddle_width(idx))
        return min(1.0, max(0.0, u + self.aim_off[idx]))
