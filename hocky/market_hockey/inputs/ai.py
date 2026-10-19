"""AI player: used for the attract-mode demo, single-player vs CPU, and soak tests. Pure Python."""

from __future__ import annotations

import random

from ..prediction.trajectory import predict
from .base import InputAdapter, PlayerSample


class AIAdapter(InputAdapter):
    name = "ai"

    def __init__(self, cfg, rng: random.Random | None = None):
        super().__init__(cfg)
        self.rng = rng or random.Random()
        self.u = [0.5, 0.5]
        self.target = [0.5, 0.5]
        self.next_think = [0.0, 0.0]
        self.clock = 0.0

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        c = self.cfg
        if idx == 0:
            self.clock += dt
        t = self.clock
        if engine is not None and t >= self.next_think[idx]:
            self.next_think[idx] = t + c["input.ai.reaction_s"] * self.rng.uniform(0.7, 1.3)
            self.target[idx] = self._think(idx, engine)
        diff = c["input.ai.difficulty"]
        vmax = c["input.ai.max_speed"] * (0.55 + 0.6 * diff)
        d = self.target[idx] - self.u[idx]
        step = vmax * dt
        self.u[idx] += max(-step, min(step, d))
        return PlayerSample(True, self.u[idx], 1.0, now, None, self.name)

    def _think(self, idx, engine) -> float:
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
                best = (pr.contact_time or 9, pr.contact_angle)
        if best is None:
            return 0.5 + self.rng.uniform(-0.08, 0.08)
        u = engine.geom.angle_to_u(idx, best[1], engine.paddle_width(idx))
        noise = c["input.ai.noise"] * (1.25 - diff)
        aim = self.rng.uniform(-0.05, 0.05) * diff  # hit off-center on purpose to steer the return
        return min(1.0, max(0.0, u + self.rng.gauss(0, noise) + aim))
