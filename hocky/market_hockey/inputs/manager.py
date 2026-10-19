"""Chooses an input source per player, filters it, and feeds the engine."""

from __future__ import annotations

import logging

from .base import PlayerSample
from .filters import PlayerFilter

log = logging.getLogger(__name__)


class InputManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.adapters: dict = {}
        self.filters = [PlayerFilter(), PlayerFilter()]
        self.recorder = None
        self.last: dict[int, PlayerSample] = {}

    def adapter(self, name: str):
        a = self.adapters.get(name)
        if a is None:
            if name == "keyboard":
                from .keyboard import KeyboardAdapter as cls
            elif name == "ai":
                from .ai import AIAdapter as cls
            elif name == "mouse":
                from .mouse import MouseAdapter as cls
            elif name == "network":
                from .network import NetworkAdapter as cls
            elif name == "replay":
                from .replay import ReplayAdapter as cls
            else:
                from .ai import AIAdapter as cls
            a = cls(self.cfg)
            self.adapters[name] = a
        return a

    def handle_event(self, event) -> None:
        for a in self.adapters.values():
            a.handle_event(event)

    def poll(self, now: float, dt: float, engine, demo: bool = False):
        """Returns (samples for the engine, [real presence p1, p2])."""
        cfg = self.cfg
        sources = [cfg["input.p1.source"], cfg["input.p2.source"]]
        used = {self.adapter(s) for s in sources}
        if demo:
            used.add(self.adapter("ai"))
        for a in used:
            a.update(now, dt, engine)
        real = {}
        for i in (0, 1):
            a = self.adapter(sources[i])
            raw = a.sample(i, now, dt, engine)
            real[i] = self.filters[i].apply(raw, now, dt, cfg, a.smooth)
        samples = real
        if demo:
            ai = self.adapter("ai")
            samples = {i: ai.sample(i, now, dt, engine) for i in (0, 1)}
        self.last = real
        if cfg["input.record"]:
            if self.recorder is None:
                from .replay import Recorder
                self.recorder = Recorder(cfg["input.replay_file"])
            self.recorder.write(now, real)
        elif self.recorder is not None:
            self.recorder.close()
            self.recorder = None
        return samples, [real[0].present, real[1].present]

    def close(self) -> None:
        for a in self.adapters.values():
            a.stop()
        if self.recorder:
            self.recorder.close()
