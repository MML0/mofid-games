import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from market_hockey.config import Config  # noqa: E402
from market_hockey.core.engine import Engine  # noqa: E402


@pytest.fixture
def cfg():
    return Config()


@pytest.fixture
def engine(cfg):
    e = Engine(cfg, random.Random(3))
    return e


def playing(engine):
    """Put the engine straight into PLAYING with no balls (tests add their own)."""
    engine.start_match()
    engine.balls.clear()
    engine.orbs.clear()
    engine.state = "PLAYING"
    engine.state_t = 0.0
    engine.play_elapsed = 20.0
    engine.drain_events()
    return engine


def add_ball(engine, x, y, vx, vy, owner=None):
    from market_hockey.core.entities import Ball

    b = Ball(engine._next_ball_id, x, y, engine.cfg["ball.radius"], engine.time)
    engine._next_ball_id += 1
    b.held = False
    b.vx, b.vy = vx, vy
    b.rally = (vx * vx + vy * vy) ** 0.5
    b.owner = owner
    engine.balls.append(b)
    return b


def run(engine, seconds, dt=1 / 240):
    events = []
    for _ in range(int(seconds / dt)):
        engine.step(dt, {}, [True, True])
        events += engine.drain_events()
    return events
