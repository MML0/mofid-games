import math

import pygame
import pytest

from market_hockey.render.text import TextRenderer, latin_digits, split_runs


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield
    pygame.quit()


def test_latin_digits():
    assert latin_digits("۱۲۳ و ٤٥") == "123 و 45"
    assert latin_digits("طرح حامي \u0643") == "طرح حامی \u06a9"  # Arabic yeh / kaf typed in the panel: Persian on screen


def test_bidi_runs():
    assert split_runs("بازیکن 1") == [(True, "بازیکن "), (False, "1")]
    assert split_runs("0:42") == [(False, "0:42")]


@pytest.mark.parametrize("backend", ["harfbuzz", "reshaper"])
def test_persian_renders(cfg, backend):
    cfg.set("text.shaping_backend", backend)
    tr = TextRenderer(cfg)
    s = tr.render("واکنش به‌موقع!", 40, (255, 255, 255))
    assert s.get_width() > 100 and s.get_height() > 20
    mixed = tr.render("بازیکن 1", 40, (255, 255, 255))
    assert mixed.get_width() > 60


def test_mask_has_no_leaks(tmp_path):
    from market_hockey.app import capture_states
    from market_hockey.config import Config
    from market_hockey.core.geometry import Geometry

    shots = capture_states(tmp_path, seed=11)
    assert len(shots) >= 9
    g = Geometry(Config())
    lim = g.mask_r + Config()["arena.mask_feather"] + 2
    for p in shots:
        img = pygame.image.load(str(p))
        w, h = img.get_size()
        for y in range(0, h, 5):
            for x in range(0, w, 5):
                if math.hypot(x - g.cx, y - g.cy) > lim:
                    assert img.get_at((x, y))[:3] == (0, 0, 0), f"leak in {p.name} at {(x, y)}"
