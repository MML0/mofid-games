"""Chooses an input source per player, filters it, and feeds the engine."""

from __future__ import annotations

import logging

from .base import InputAdapter, PlayerSample
from .filters import PlayerFilter
from .registry import load

log = logging.getLogger(__name__)


class InputManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.adapters: dict = {}
        self.filters = [PlayerFilter(), PlayerFilter()]
        self.recorder = None
        self.record_failed = False
        self.last: dict[int, PlayerSample] = {}
        self.failed: set[str] = set()  # sources whose crash was already logged

    def adapter(self, name: str):
        a = self.adapters.get(name)
        if a is None:
            try:
                a = load(name)(self.cfg)
            except Exception:  # a missing driver or a broken sensor module must never stop the show
                log.exception("input source %r unavailable; that player reads as absent", name)
                a = InputAdapter(self.cfg)
                a.name = name
            self.adapters[name] = a
        return a

    def handle_event(self, event) -> None:
        for a in self.adapters.values():
            a.handle_event(event)

    def _guarded(self, a, fn, *args, default=None):
        """Sensor code is the least trusted code in the game: if it raises, that player reads as absent."""
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001
            if a.name not in self.failed:
                self.failed.add(a.name)
                log.exception("input source %r failed", a.name)
            return default

    def _sample(self, a, idx: int, now: float, dt: float, engine) -> PlayerSample:
        absent = PlayerSample(False, None, 0.0, now, None, a.name)
        return self._guarded(a, a.sample, idx, now, dt, engine, default=absent)

    def _record(self, now: float, samples: dict) -> None:
        if not self.cfg["input.record"]:
            self.record_failed = False
            self._close_recorder()
            return
        if self.record_failed:
            return
        try:
            if self.recorder is None:
                from .replay import Recorder
                self.recorder = Recorder(self.cfg["input.replay_file"])
            self.recorder.write(now, samples)
        except OSError as exc:
            log.error("input recording stopped: %s", exc)
            self.record_failed = True
            self._close_recorder()

    def _close_recorder(self) -> None:
        if self.recorder is not None:
            try:
                self.recorder.close()
            except OSError as exc:
                log.error("could not finish the input recording: %s", exc)
            self.recorder = None

    def poll(self, now: float, dt: float, engine, demo: bool = False):
        """Returns (samples for the engine, [real presence p1, p2])."""
        cfg = self.cfg
        sources = [cfg["input.p1.source"], cfg["input.p2.source"]]
        used = {self.adapter(s) for s in sources}
        if demo:
            used.add(self.adapter("ai"))
        for a in used:
            self._guarded(a, a.update, now, dt, engine)
        real = {}
        for i in (0, 1):
            a = self.adapter(sources[i])
            raw = self._sample(a, i, now, dt, engine)
            absent = PlayerSample(False, None, 0.0, now, None, a.name)
            real[i] = self._guarded(a, self.filters[i].apply, raw, now, dt, cfg, a.smooth, default=absent)
        samples = real
        if demo:
            ai = self.adapter("ai")
            samples = {i: self._sample(ai, i, now, dt, engine) for i in (0, 1)}
        self.last = real
        self._record(now, real)
        return samples, [real[0].present, real[1].present]

    def close(self) -> None:
        for a in self.adapters.values():
            a.stop()
        self._close_recorder()
