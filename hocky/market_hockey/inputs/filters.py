"""Sensor filters: confidence gate, spike rejection, One Euro smoothing, dead zone, presence timeout."""

from __future__ import annotations

import math

from .base import PlayerSample


class OneEuro:
    """One Euro filter (Casiez et al. 2012): smooth when slow, responsive when fast."""

    def __init__(self):
        self.x = None
        self.dx = 0.0
        self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t, min_cutoff, beta, d_cutoff=1.0):
        if self.x is None or self.t is None or t <= self.t:
            self.x, self.t = x, t
            return x
        dt = t - self.t
        dx = (x - self.x) / dt
        a_d = self._alpha(d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = min_cutoff + beta * abs(self.dx)
        a = self._alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        self.t = t
        return self.x

    def reset(self):
        self.x = None
        self.t = None
        self.dx = 0.0


class PlayerFilter:
    def __init__(self):
        self.euro = OneEuro()
        self.last_u = None
        self.last_seen = -1e9
        self.jump_start = None

    def apply(self, s: PlayerSample, now: float, dt: float, cfg, smooth: bool) -> PlayerSample:
        valid = (s.present and s.u is not None and math.isfinite(s.u)
                 and s.confidence >= cfg["input.filters.min_confidence"])
        if valid:
            u = min(1.0, max(0.0, s.u))
            if smooth:
                if self.last_u is not None and dt > 0:
                    rate = abs(u - self.last_u) / dt
                    if rate > cfg["input.filters.max_jump_per_s"]:
                        if self.jump_start is None:
                            self.jump_start = now
                        if (now - self.jump_start) * 1000 < cfg["input.filters.jump_confirm_ms"]:
                            u = self.last_u
                        else:
                            self.jump_start = None
                            self.euro.reset()
                    else:
                        self.jump_start = None
                u = self.euro(u, now, cfg["input.filters.one_euro_min_cutoff"], cfg["input.filters.one_euro_beta"])
            if self.last_u is not None and abs(u - self.last_u) < cfg["input.filters.dead_zone"]:
                u = self.last_u
            self.last_u = u
            self.last_seen = now
            return PlayerSample(True, u, s.confidence, now, s.xy, s.source, s.instant)
        if now - self.last_seen <= cfg["input.filters.absent_timeout_s"]:
            return PlayerSample(True, None, 0.0, now, None, s.source)  # briefly lost: hold
        self.euro.reset()
        return PlayerSample(False, None, 0.0, now, None, s.source)
