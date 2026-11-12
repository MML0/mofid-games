"""No value the control panel can produce may crash the game or break physics, live, in any state of a match."""

import math
import random

import pygame
import pytest

from land_hockey.config import Config, get_schema
from land_hockey.core.engine import ATTRACT, RESULT, Engine
from land_hockey.inputs.ai import AIAdapter
from land_hockey.render.renderer import Renderer

# Allocating 8K canvases hundreds of times only tests the machine's memory: these get their own test below.
DISPLAY_SIZE = ("display.canvas_width", "display.canvas_height", "display.supersample")


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


class World:
    """A running game: engine, AI players, renderer, all live on one config, like the real app."""

    def __init__(self, cfg, seed=1):
        self.cfg = cfg
        self.eng = Engine(cfg, random.Random(seed))
        self.ai = AIAdapter(cfg, random.Random(seed + 1))
        self.rend = Renderer(cfg, random.Random(seed + 2))
        self.t = 0.0

    def frames(self, n=2, sim_s=1 / 60):
        eng = self.eng
        hz = max(30, self.cfg["physics.hz"])
        for _ in range(n):
            samples = {i: self.ai.sample(i, self.t, sim_s, eng) for i in (0, 1)}
            for _ in range(max(1, int(sim_s * hz))):
                eng.step(1 / hz, samples, [True, True])
            self.t += sim_s
            self.rend.handle_events(eng.drain_events(), eng)
            frame = self.rend.render(eng, 0.5, sim_s)
            assert frame.get_size() == (eng.geom.W, eng.geom.H)
        self.check()

    def check(self):
        eng = self.eng
        for b in eng.balls:
            assert math.isfinite(b.x) and math.isfinite(b.y) and math.isfinite(b.vx) and math.isfinite(b.vy)
        for p in eng.paddles:
            assert math.isfinite(p.theta) and math.isfinite(p.u)
        assert len(eng.balls) < 100 and len(eng.orbs) < 100

    def liven(self, rng):
        """Keep something happening: restart finished matches, keep orbs and effects coming."""
        eng = self.eng
        if eng.state in (ATTRACT, RESULT):
            eng.start_match()
        elif rng.random() < 0.25:
            ids = list(eng.types)
            tid = rng.choice(ids)
            eng.force_spawn(tid)
            live = eng.live_balls()
            if live and live[0].owner is not None:
                eng.types[tid].collect(eng, live[0], live[0].owner)


def extremes(p):
    if p.kind in ("float", "int"):
        return [p.min, p.max]
    if p.kind == "bool":
        return [not p.default]
    if p.kind == "enum":
        return [o for o in p.options if o != p.default]
    if p.kind == "color":
        return ["#000000", "#FFFFFF"]
    if p.kind == "str":
        return ["", "متن آزمایشی 123 " * 8]
    if p.kind == "font":
        return ["no-such-font.ttf"]
    if p.kind == "key":
        return ["not-a-key"]
    return []


def test_every_value_of_every_setting_can_be_applied_live():
    """Drag every slider to both ends and pick every dropdown option, one at a time, while the game runs."""
    cfg = Config()
    world = World(cfg)
    rng = random.Random(3)
    cfg.set("input.record", False)
    world.frames(2)
    tried = 0
    for path, p in get_schema().items():
        if path in DISPLAY_SIZE or path.startswith(("input.p1.source", "input.p2.source")):
            continue
        for value in extremes(p):
            cfg.set(path, value)
            world.liven(rng)
            try:
                world.frames(2)
            except Exception as exc:
                raise AssertionError(f"{path} = {value!r} broke the game: {exc!r}") from exc
            tried += 1
        cfg.set(path, p.default)
    world.frames(3)
    assert tried > 700


@pytest.mark.parametrize("seed", range(25))
def test_random_settings_survive_a_whole_match(seed):
    """Everything changed at once, within the allowed ranges: the combinations nobody would think of trying."""
    rng = random.Random(seed)
    values = {}
    for path, p in get_schema().items():
        if path in DISPLAY_SIZE or path.startswith(("input.", "web.", "live_link.", "debug.")) or rng.random() < 0.3:
            continue
        options = extremes(p) + [p.default]
        if p.kind in ("float", "int"):
            options.append(rng.uniform(p.min, p.max))
        values[path] = rng.choice(options)
    for t in ("match.timer_enabled", "powerups.enabled"):
        values[t] = True
    values["match.duration_s"] = 10
    values["physics.hz"] = rng.choice([120, 240])
    world = World(Config(values), seed)
    world.eng.start_match()
    for _ in range(12):
        world.liven(rng)
        world.frames(6, sim_s=1 / 10)


@pytest.mark.parametrize("w,h", [(320, 320), (640, 360), (360, 640), (1920, 1080)])
@pytest.mark.parametrize("ss", [1, 3])
def test_canvas_sizes_and_supersampling(w, h, ss):
    cfg = Config({"display.canvas_width": w, "display.canvas_height": h, "display.supersample": ss})
    world = World(cfg)
    world.eng.start_match()
    world.frames(4, sim_s=1 / 4)
    assert world.rend.canvas.get_size() == (w, h)


def test_the_canvas_can_be_resized_while_running():
    cfg = Config()
    world = World(cfg)
    world.frames(2)
    for size in (640, 1280, 480):
        cfg.set("display.canvas_width", size)
        cfg.set("display.canvas_height", size)
        world.frames(2)
        assert world.rend.canvas.get_size() == (size, size)


@pytest.mark.parametrize("deg", [0, 37, 90, 180, -90])
def test_arena_rotation_keeps_play_valid(deg):
    cfg = Config({"arena.layout_rotation_deg": deg})
    world = World(cfg)
    world.eng.start_match()
    for _ in range(20):
        samples = {i: world.ai.sample(i, world.t, 0.25, world.eng) for i in (0, 1)}
        for _ in range(60):
            world.eng.step(1 / 240, samples, [True, True])
        world.t += 0.25
        world.rend.handle_events(world.eng.drain_events(), world.eng)
        world.rend.render(world.eng, 0.5, 0.25)
    world.check()
