"""Input contract. The engine only ever sees a PlayerSample per player: a position 0..1 along that
player's own arc (0 = the player's LEFT end, 1 = their RIGHT end). Any sensor can produce this."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlayerSample:
    present: bool = True  # someone is there / tracking is valid
    u: float | None = None  # 0..1 along the player's arc; None = hold the current position
    confidence: float = 1.0
    timestamp: float = 0.0
    xy: tuple | None = None  # optional normalized arena point (-1..1, rim = 1) for future 2D control
    source: str = ""


class InputAdapter:
    """Adapters implement update() once per frame and sample() per player."""

    name = "base"
    smooth = False  # apply sensor smoothing / spike rejection in the manager

    def __init__(self, cfg):
        self.cfg = cfg

    def start(self) -> None:
        pass

    def handle_event(self, event) -> None:
        pass

    def update(self, now: float, dt: float, engine) -> None:
        pass

    def sample(self, idx: int, now: float, dt: float, engine) -> PlayerSample:
        return PlayerSample(present=False, timestamp=now, source=self.name)

    def stop(self) -> None:
        pass
