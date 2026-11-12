"""The client's branding on the orbs: their artwork, their colors, and the text an orb leaves when collected."""

import random

import pygame
import pytest

from conftest import add_ball, playing
from land_hockey.config import Config
from land_hockey.core.engine import Engine
from land_hockey.paths import ORBS_DIR
from land_hockey.render.colors import hex_rgb
from land_hockey.render.icons import IconCache
from land_hockey.render.renderer import Renderer

BRANDED = {"expand": "بالکر بزرگ", "speed_up": "زیاد شدن سرعت", "double_ball": "دو توپ", "shrink": "بالکر حریف کوچک",
           "trajectory_reveal": "تحلیل مسیر"}
OWN_COLOR = {"expand": "#3CAA5C", "speed_up": "#D4B96F", "double_ball": "#3D9BFF", "shrink": "#FF3B45",
             "trajectory_reveal": "#A35BFF"}


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def world(values=None):
    cfg = Config(values or {})
    engine = Engine(cfg, random.Random(5))
    playing(engine)
    return cfg, engine, Renderer(cfg, random.Random(6))


def collect(engine, rend, tid):
    engine.drain_events()
    orb = engine._spawn_orb(forced_type=tid)
    engine._collect(orb, add_ball(engine, 0, 0, 100, 0, owner=0), 0)
    rend.handle_events(engine.drain_events(), engine)
    return orb


@pytest.mark.parametrize("tid", BRANDED)
def test_every_branded_orb_ships_a_round_face(tid):
    face = pygame.image.load(str(ORBS_DIR / f"{tid}.png"))
    w, h = face.get_size()
    assert w == h == 512 and face.get_bitsize() == 32
    assert face.get_at((0, 0)).a == 0 and face.get_at((w // 2, h // 2)).a == 255


@pytest.mark.parametrize("tid", BRANDED)
def test_the_face_fills_the_orb_instead_of_the_white_icon(tid):
    cache = IconCache()
    body = cache.badge(tid, tid, 30, (255, 0, 0), False)
    plain = cache.badge(tid, "no_such_face", 30, (255, 0, 0), False)
    assert pygame.image.tobytes(body, "RGBA") != pygame.image.tobytes(plain, "RGBA")


def test_a_power_up_without_a_face_keeps_its_drawn_icon():
    assert IconCache().face("shield") is None


@pytest.mark.parametrize("tid,text", BRANDED.items())
def test_defaults_carry_the_clients_text(tid, text):
    assert Config()[f"powerups.types.{tid}.float_text"] == text


@pytest.mark.parametrize("tid,color", OWN_COLOR.items())
def test_own_color_is_used_for_glow_and_splash(tid, color):
    _, engine, rend = world()
    rend._colors()
    assert rend._orb_color(tid, "good") == hex_rgb(color)


def test_without_an_own_color_it_glows_in_its_class():
    _, engine, rend = world()
    rend._colors()
    assert rend._orb_color("shield", "good") == rend.c["good"]


def test_the_shrink_orb_only_looks_red_it_still_helps_its_collector():
    assert Config()["powerups.types.shrink.class"] == "good"


def test_the_glow_does_not_wash_out_the_artwork():
    _, engine, rend = world()
    orb = engine._spawn_orb(forced_type="expand")
    orb.state, orb.state_t = "idle", 0.0
    orb.x, orb.y, orb.hx, orb.hy = 0.0, -40.0, 0.0, -40.0
    frame = rend.render(engine, 0.0, 1 / 60)
    x, y = rend.to_c(orb.x, orb.y)
    samples = [frame.get_at((int(x), int(y) + dy))[:3] for dy in (-14, 14)]  # above and below the name on the coin
    art = pygame.image.load(str(ORBS_DIR / "expand.png")).get_at((256, 60))[:3]  # the artwork's plain background
    assert any(all(abs(a - b) < 16 for a, b in zip(px, art)) for px in samples)


def test_collecting_pops_the_text_at_the_orb():
    _, engine, rend = world()
    orb = collect(engine, rend, "double_ball")
    assert [(f["text"], f["x"], f["y"]) for f in rend.floats] == [("دو توپ", orb.x, orb.y)]


def test_the_text_is_gone_after_its_set_duration():
    _, engine, rend = world({"powerups.float_text.duration_s": 0.3})
    collect(engine, rend, "expand")
    rend.render(engine, 0.0, 0.25)
    assert len(rend.floats) == 1
    rend.render(engine, 0.0, 0.1)
    assert rend.floats == []


def test_an_orb_with_no_text_of_its_own_uses_its_message():
    _, engine, rend = world({"powerups.types.expand.float_text": ""})
    collect(engine, rend, "expand")
    assert rend.floats[0]["text"] == Config()["powerups.types.expand.toast_collector"]


def test_the_text_can_be_switched_off():
    _, engine, rend = world({"powerups.float_text.enabled": False})
    collect(engine, rend, "expand")
    assert rend.floats == []
