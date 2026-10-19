import math

import pygame
import pytest

from market_hockey.inputs.base import PlayerSample
from market_hockey.inputs.filters import PlayerFilter
from market_hockey.inputs.network import NetworkAdapter


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    yield


def test_keyboard_player_view_directions(cfg):
    from market_hockey.inputs.keyboard import KeyboardAdapter

    kb = KeyboardAdapter(cfg)
    assert kb.direction(0, {pygame.K_d: 1}) == 1 and kb.direction(0, {pygame.K_a: 1}) == -1
    assert kb.direction(1, {pygame.K_RIGHT: 1}) == 1 and kb.direction(1, {pygame.K_LEFT: 1}) == -1
    # alternates: screen-up moves P1 toward its top end (u down) and P2 toward its top end (u up)
    assert kb.direction(0, {pygame.K_w: 1}) == -1 and kb.direction(1, {pygame.K_UP: 1}) == 1
    cfg.set("input.keyboard.invert_p1", True)
    assert kb.direction(0, {pygame.K_d: 1}) == -1


def test_keyboard_both_players_simultaneously(cfg):
    from market_hockey.inputs.keyboard import KeyboardAdapter

    kb = KeyboardAdapter(cfg)
    for _ in range(60):
        a = kb.integrate(0, 1, 1 / 60)
        b = kb.integrate(1, -1, 1 / 60)
    assert a.u > 0.7 and b.u < 0.3


def test_network_tracking_maps_to_u(cfg, engine):
    na = NetworkAdapter.__new__(NetworkAdapter)
    na.cfg, na.sock, na.latest, na.blobs, na.messages = cfg, None, {}, None, 0
    na.feed({"type": "tracking", "players": [{"id": "p1", "x": -0.9, "y": 0.35, "conf": 0.9},
                                             {"id": "p2", "x": 0.9, "y": -0.35, "conf": 0.9}]}, now=1.0)
    s1 = na.sample(0, 1.0, 1 / 60, engine)
    s2 = na.sample(1, 1.0, 1 / 60, engine)
    assert s1.present and s2.present
    assert s1.u < 0.5  # upper-left = P1's left side
    assert s2.u < 0.5  # lower-right = P2's left side
    assert not na.sample(0, 5.0, 1 / 60, engine).present  # timed out


def test_network_blobs_assigned_by_region(cfg, engine):
    na = NetworkAdapter.__new__(NetworkAdapter)
    na.cfg, na.sock, na.latest, na.blobs, na.messages = cfg, None, {}, None, 0
    na.feed({"type": "blobs", "blobs": [{"x": 0.95, "y": 0.0}, {"x": -0.95, "y": 0.0}, {"x": 0.1, "y": 0.1}]}, now=1.0)
    na.update(1.0, 1 / 60, engine)
    assert math.isclose(na.sample(0, 1.0, 0, engine).u, 0.5, abs_tol=0.05)
    assert math.isclose(na.sample(1, 1.0, 0, engine).u, 0.5, abs_tol=0.05)


def test_calibration_flip(cfg):
    na = NetworkAdapter.__new__(NetworkAdapter)
    na.cfg = cfg
    cfg.set("input.network.flip_x", True)
    assert na.calibrate(0.5, 0.2) == (-0.5, 0.2)


def test_filter_hold_then_absent(cfg):
    f = PlayerFilter()
    out = f.apply(PlayerSample(True, 0.4), 0.0, 1 / 60, cfg, smooth=True)
    assert out.present and out.u == pytest.approx(0.4)
    held = f.apply(PlayerSample(False, None), 1.0, 1 / 60, cfg, smooth=True)
    assert held.present and held.u is None  # briefly lost: hold position
    gone = f.apply(PlayerSample(False, None), 10.0, 1 / 60, cfg, smooth=True)
    assert not gone.present


def test_filter_rejects_spikes(cfg):
    f = PlayerFilter()
    for k in range(10):
        f.apply(PlayerSample(True, 0.2), k / 60, 1 / 60, cfg, smooth=True)
    spike = f.apply(PlayerSample(True, 0.95), 10 / 60, 1 / 60, cfg, smooth=True)
    assert spike.u < 0.3


def test_engine_has_no_keyboard_code():
    import market_hockey.core.engine as eng

    src = open(eng.__file__, encoding="utf-8").read()
    assert "import pygame" not in src and "K_" not in src


def test_ai_motion_is_smooth(cfg, engine):
    """The demo robots must not jitter: no sudden reversals or jumps in velocity."""
    import random
    from conftest import add_ball, playing

    from market_hockey.inputs.ai import AIAdapter

    playing(engine)
    add_ball(engine, 0, 0, -500, 60, owner=1)
    ai = AIAdapter(cfg, random.Random(4))
    us = []
    for k in range(240):
        us.append(ai.sample(0, k / 60, 1 / 60, engine).u)
        engine.step(1 / 60, {}, [True, True])
    vel = [(b - a) * 60 for a, b in zip(us, us[1:])]
    acc = [abs(b - a) * 60 for a, b in zip(vel, vel[1:])]
    assert max(acc) < 40  # range/s^2: bounded acceleration, no twitching
    reversals = sum(1 for a, b in zip(vel, vel[1:]) if a * b < 0 and abs(a) > 0.05 and abs(b) > 0.05)
    assert reversals <= 3
