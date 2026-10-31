"""Record inputs to JSONL and play them back (for reproducing sessions and testing without sensors)."""

from __future__ import annotations

import json
import logging
import math

from ..paths import ROOT
from .base import InputAdapter, PlayerSample

log = logging.getLogger(__name__)


def _parse_frame(line: str) -> dict | None:
    """One replay line as {"t": seconds, "p": [[present, u], ...]}, or None if it is not one."""
    try:
        rec = json.loads(line)
        t, players = rec["t"], rec["p"]
        frame = {"t": float(t), "p": []}
        for present, u in players:
            if u is not None:
                u = float(u)
                u = min(1.0, max(0.0, u)) if math.isfinite(u) else None
            frame["p"].append([bool(present), u])
        return frame if math.isfinite(frame["t"]) else None
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        return None


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
                parsed = [_parse_frame(line) for line in fh if line.strip()]
            self.frames = [f for f in parsed if f is not None]
            if len(self.frames) < len(parsed):
                log.warning("replay file: skipped %d damaged lines", len(parsed) - len(self.frames))
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
