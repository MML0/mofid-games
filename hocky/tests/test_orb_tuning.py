"""Bigger orbs, more of them, and less text around them."""

import json
import math
import random

import pygame
import pytest

from conftest import add_ball, playing
from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.render.renderer import Renderer


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def _collect(values, tid="shrink"):
    cfg = Config({"powerups.types.shrink.toast_collector": "mine", "powerups.types.shrink.toast_opponent": "theirs",
                  **values})
    engine = Engine(cfg, random.Random(5))
    playing(engine)
    rend = Renderer(cfg, random.Random(6))
    engine.drain_events()
    orb = engine._spawn_orb(forced_type=tid)
    engine._collect(orb, add_ball(engine, 0, 0, 100, 0, owner=0), 0)
    rend.handle_events(engine.drain_events(), engine)
    return rend


def test_floating_text_replaces_only_the_collectors_message():
    assert [t["text"] for t in _collect({}).toasts] == ["theirs"]


@pytest.mark.parametrize("values", ({"powerups.float_text.hide_collector_message": False},
                                    {"powerups.float_text.enabled": False}))
def test_collectors_message_returns_when_the_floating_text_does_not_cover_it(values):
    assert [t["text"] for t in _collect(values).toasts] == ["mine", "theirs"]


def test_saved_old_defaults_move_up_but_operator_values_stay(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"_meta": {"schema_version": 13},
                                "powerups": {"orb_radius": 30, "spawn_interval_max_s": 9.0},
                                "text": {"toast_size": 34}}), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg["powerups.orb_radius"] == 60 and cfg["text.toast_size"] == 26
    assert cfg["powerups.spawn_interval_max_s"] == 9.0  # the operator chose this one


def test_a_random_orb_never_lands_on_the_ball():
    cfg = Config({"center_zone.layout": "random", "powerups.max_active_orbs": 8})
    engine = Engine(cfg, random.Random(9))
    playing(engine)
    engine.balls.clear()
    ball = add_ball(engine, 40, 20, 0, 0, owner=0)
    placed = 0
    for _ in range(300):
        engine.orbs.clear()
        orb = engine._spawn_orb(phase=2)
        if orb is not None:
            placed += 1
            assert math.hypot(orb.x - ball.x, orb.y - ball.y) >= cfg["powerups.min_distance_from_ball"]
    assert placed > 100


def test_random_orbs_never_land_on_each_other():
    cfg = Config({"center_zone.layout": "random", "powerups.max_active_orbs": 8, "powerups.max_bad_orbs": 8,
                  "powerups.no_repeat": False, "powerups.avoid_conflicting_spawns": False})
    engine = Engine(cfg, random.Random(4))
    playing(engine)
    engine.balls.clear()
    for _ in range(100):
        engine.orbs.clear()
        for _ in range(8):
            engine._spawn_orb(phase=3)
        for i, a in enumerate(engine.orbs):
            for b in engine.orbs[i + 1:]:
                assert math.hypot(a.x - b.x, a.y - b.y) > 2 * cfg["powerups.orb_radius"]
