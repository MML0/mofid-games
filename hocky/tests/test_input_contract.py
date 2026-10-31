"""The rules every input source must follow. Parametrized over the registry, so a new sensor (LiDAR, ...) added to
market_hockey/inputs/registry.py is held to all of them with no new test code."""

import ast
import math
from pathlib import Path

import pygame
import pytest

from conftest import free_udp_port, playing
from market_hockey.config import get_schema
from market_hockey.inputs.base import InputAdapter, PlayerSample
from market_hockey.inputs.manager import InputManager
from market_hockey.inputs.registry import ADAPTERS, load

SOURCES = sorted(ADAPTERS)


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


@pytest.fixture
def make(cfg):
    made = []
    cfg.set("input.network.port", free_udp_port())

    def build(name):
        a = load(name)(cfg)
        made.append(a)
        return a

    yield build
    for a in made:
        a.stop()


def valid_sample(s, name):
    assert isinstance(s, PlayerSample)
    assert s.source == name
    assert isinstance(s.present, bool)
    assert s.u is None or (math.isfinite(s.u) and 0.0 <= s.u <= 1.0)
    assert 0.0 <= s.confidence <= 1.0


def test_the_registry_and_the_settings_list_the_same_sources():
    schema = get_schema()
    assert set(schema["input.p1.source"].options) == set(ADAPTERS)
    assert set(schema["input.p2.source"].options) == set(ADAPTERS)


@pytest.mark.parametrize("name", SOURCES)
def test_is_a_named_input_adapter(name):
    cls = load(name)
    assert issubclass(cls, InputAdapter)
    assert cls.name == name


@pytest.mark.parametrize("name", SOURCES)
def test_samples_are_always_valid(make, engine, name):
    a = make(name)
    assert isinstance(a.smooth, bool), "`smooth` tells the manager whether to filter this source; it must stay a bool"
    playing(engine)
    for k in range(30):
        now = k / 60
        a.update(now, 1 / 60, engine)
        for idx in (0, 1):
            valid_sample(a.sample(idx, now, 1 / 60, engine), name)
        engine.step(1 / 60, {}, [True, True])


@pytest.mark.parametrize("name", SOURCES)
def test_survives_events_and_repeated_stop(make, engine, name):
    a = make(name)
    a.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=0, unicode="a"))
    a.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1), rel=(0, 0), buttons=(0, 0, 0)))
    a.update(0.0, 1 / 60, engine)
    a.stop()
    a.stop()


@pytest.mark.parametrize("name", SOURCES)
def test_samples_drive_the_engine(make, engine, name):
    a = make(name)
    playing(engine)
    for k in range(60):
        now = k / 60
        a.update(now, 1 / 60, engine)
        engine.step(1 / 60, {i: a.sample(i, now, 1 / 60, engine) for i in (0, 1)}, [True, True])
    for p in engine.paddles:
        assert math.isfinite(p.theta) and 0.0 <= p.u <= 1.0


@pytest.mark.parametrize("name", SOURCES)
def test_runs_through_the_manager_for_both_players(cfg, engine, name):
    cfg.set("input.network.port", free_udp_port())
    cfg.set("input.p1.source", name)
    cfg.set("input.p2.source", name)
    m = InputManager(cfg)
    try:
        for k in range(10):
            samples, presence = m.poll(k / 60, 1 / 60, engine)
            assert set(samples) == {0, 1} and len(presence) == 2
            assert all(isinstance(x, bool) for x in presence)
    finally:
        m.close()


@pytest.mark.parametrize("name", SOURCES)
def test_is_loaded_lazily_so_a_missing_driver_only_affects_that_source(name):
    """No adapter module may be imported by the engine, the renderer or the schema."""
    root = Path(__file__).resolve().parent.parent / "market_hockey"
    module = ADAPTERS[name].split(":")[0]
    for sub in ("core", "render", "powerups", "prediction"):
        for f in (root / sub).rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").endswith(f"inputs.{module}"), f"{f} imports the {name} adapter"
