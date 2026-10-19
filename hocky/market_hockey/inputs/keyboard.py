"""Keyboard adapter: A/D for Player 1, Left/Right for Player 2 (from each player's own point of view).

The keys drive a virtual position with acceleration and braking, so the keyboard behaves like a sensor.
Optional alternates (W/S, Up/Down) move a paddle up/down on screen.
"""

from __future__ import annotations

import pygame

from .base import InputAdapter, PlayerSample


def key_code(name: str) -> int | None:
    try:
        return pygame.key.key_code(name)
    except (ValueError, pygame.error):
        return None


class KeyboardAdapter(InputAdapter):
    name = "keyboard"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.u = [0.5, 0.5]
        self.v = [0.0, 0.0]
        self._codes = None
        self._ver = -1

    def _keys(self):
        if self._codes is None or self._ver != self.cfg.version:
            c = self.cfg
            self._codes = {
                0: [key_code(c["input.keyboard.p1_left"]), key_code(c["input.keyboard.p1_right"]),
                    key_code(c["input.keyboard.p1_up"]), key_code(c["input.keyboard.p1_down"])],
                1: [key_code(c["input.keyboard.p2_left"]), key_code(c["input.keyboard.p2_right"]),
                    key_code(c["input.keyboard.p2_up"]), key_code(c["input.keyboard.p2_down"])],
            }
            self._ver = c.version
        return self._codes

    @staticmethod
    def _down(pressed, code):
        return code is not None and 0 <= code < len(pressed) and pressed[code] if not isinstance(pressed, dict) \
            else bool(pressed.get(code))

    def direction(self, idx: int, pressed) -> int:
        left, right, up, down = self._keys()[idx]
        d = (1 if self._is(pressed, right) else 0) - (1 if self._is(pressed, left) else 0)
        if self.cfg["input.keyboard.alt_keys_enabled"]:
            # u grows counter-clockwise: for P1 that is screen-down, for P2 screen-up
            alt = (1 if self._is(pressed, down) else 0) - (1 if self._is(pressed, up) else 0)
            d += alt if idx == 0 else -alt
        d = max(-1, min(1, d))
        if self.cfg["input.keyboard.invert_p1" if idx == 0 else "input.keyboard.invert_p2"]:
            d = -d
        return d

    @staticmethod
    def _is(pressed, code) -> bool:
        if code is None:
            return False
        try:
            return bool(pressed[code])
        except (IndexError, KeyError):
            return False

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        try:
            pressed = pygame.key.get_pressed()
        except pygame.error:
            pressed = {}
        return self.integrate(idx, self.direction(idx, pressed), dt)

    def integrate(self, idx: int, d: int, dt: float) -> PlayerSample:
        c = self.cfg
        vmax, acc, fr = c["input.keyboard.max_speed"], c["input.keyboard.accel"], c["input.keyboard.friction"]
        v = self.v[idx]
        if d:
            if v * d < 0:
                v = 0.0
            v = max(-vmax, min(vmax, v + d * acc * dt))
        else:
            v = max(0.0, abs(v) - fr * dt) * (1 if v > 0 else -1)
        u = self.u[idx] + v * dt
        if u <= 0.0 or u >= 1.0:
            u = min(1.0, max(0.0, u))
            v = 0.0
        self.u[idx], self.v[idx] = u, v
        return PlayerSample(True, u, 1.0, 0.0, None, self.name)
