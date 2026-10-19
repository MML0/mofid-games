"""Record inputs to JSONL and play them back (for reproducing sessions and testing without sensors)."""

from __future__ import annotations

import json
import logging

from ..paths import ROOT
from .base import InputAdapter, PlayerSample

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self, path):
        self.path = ROOT / path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "w", encoding="utf-8")
        self.t0 = None

    def write(self, now, samples):
        if self.t0 is None:
            self.t0 = now
        rec = {"t": round(now - self.t0, 4),
               "p": [[s.present, s.u] for s in (samples.get(0), samples.get(1)) if s is not None]}
        self.fh.write(json.dumps(rec) + "\n")

    def close(self):
        self.fh.close()


class ReplayAdapter(InputAdapter):
    name = "replay"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.frames = []
        self.clock = 0.0
        self.i = 0
        try:
            with open(ROOT / cfg["input.replay_file"], encoding="utf-8") as fh:
                self.frames = [json.loads(line) for line in fh if line.strip()]
        except (OSError, ValueError) as exc:
            log.warning("replay file unavailable: %s", exc)

    def update(self, now, dt, engine):
        if not self.frames:
            return
        self.clock += dt
        end = self.frames[-1]["t"]
        if end > 0 and self.clock > end:
            self.clock = 0.0
            self.i = 0
        while self.i + 1 < len(self.frames) and self.frames[self.i + 1]["t"] <= self.clock:
            self.i += 1

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        if not self.frames:
            return PlayerSample(False, None, 0.0, now, None, self.name)
        p = self.frames[self.i]["p"]
        if idx >= len(p):
            return PlayerSample(False, None, 0.0, now, None, self.name)
        present, u = p[idx]
        return PlayerSample(bool(present), u, 1.0, now, None, self.name)
