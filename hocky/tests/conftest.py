import hashlib
import os
import random
import socket
import sys
import time
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


def free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for(fn, tries=500):
    """Loopback UDP is fast but not instant: poll until `fn` returns something truthy, and return it."""
    for _ in range(tries):
        got = fn()
        if got:
            return got
        time.sleep(0.002)
    raise AssertionError("timed out waiting for a network message")


def advance_to_playing(engine, dt=1 / 240, limit=20.0):
    """Start a match and run the real intro and countdown until the ball is in play."""
    if engine.state == "ATTRACT":
        engine.start_match()
    for _ in range(int(limit / dt)):
        engine.step(dt, {}, [True, True])
        if engine.state == "PLAYING":
            return engine
    raise AssertionError(f"never reached PLAYING (stuck in {engine.state})")


@pytest.fixture(scope="session", autouse=True)
def _shipped_files_stay_untouched():
    """No test may change the settings, presets or match history that ship with or belong to the real game."""
    root = Path(__file__).resolve().parent.parent
    watched = [root / "config" / "settings.json", root / "config" / "defaults.json", root / "logs" / "history.jsonl",
               root / "logs" / "matches.csv", *sorted((root / "config" / "presets").glob("*.json"))]

    def digest():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in watched}

    before = digest()
    yield
    assert digest() == before, "a test modified a real config or log file"
