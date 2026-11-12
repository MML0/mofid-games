"""Rendering building blocks, and the visual promises the exhibition depends on."""

import math
import random

import numpy as np
import pygame
import pytest

from conftest import add_ball, advance_to_playing, playing
from land_hockey.config import Config
from land_hockey.core.engine import Engine
from land_hockey.powerups import registry
from land_hockey.render import colors, glow, icons, overlays, text
from land_hockey.render.particles import Particles
from land_hockey.render.renderer import Renderer, ease_out_back, ease_out_cubic, ease_out_elastic


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def world(values=None, seed=2):
    cfg = Config(values or {})
    return cfg, Engine(cfg, random.Random(seed)), Renderer(cfg, random.Random(seed + 1))


# ---------------------------------------------------------------- colors
def test_hex_rgb():
    assert colors.hex_rgb("#FF0080") == (255, 0, 128) and colors.hex_rgb("00ff00") == (0, 255, 0)
    assert colors.hex_rgb("nonsense") == (255, 255, 255)


def test_scale_and_mix_stay_in_range():
    assert colors.scale((200, 100, 0), 2) == (255, 200, 0) and colors.scale((10, 10, 10), -1) == (0, 0, 0)
    assert colors.mix((0, 0, 0), (100, 200, 50), 0.5) == (50, 100, 25)


def test_boost_brightens_but_keeps_the_hue():
    r, g, b = colors.boost((120, 20, 20), 0.5)
    assert r > 120 and r > g and r > b


def test_boost_leaves_white_and_gray_without_a_tint():
    assert colors.boost((255, 255, 255), 1.0) == (255, 255, 255)
    r, g, b = colors.boost((100, 100, 100), 0.5)
    assert r == g == b > 100


def test_delta_e_ranks_similar_colors_close():
    assert colors.delta_e((255, 0, 0), (255, 0, 0)) == 0
    assert colors.delta_e((255, 0, 0), (250, 5, 5)) < colors.delta_e((255, 0, 0), (0, 255, 0))


def test_default_team_colors_are_distinct_for_visitors():
    c = Config()
    rgb = {k: colors.hex_rgb(c[f"colors.{k}"]) for k in ("p1", "p2", "good", "bad")}
    assert colors.delta_e(rgb["p1"], rgb["p2"]) > 25
    assert colors.delta_e(rgb["good"], rgb["bad"]) > 25


# ---------------------------------------------------------------- easing
@pytest.mark.parametrize("fn", [ease_out_back, ease_out_cubic, ease_out_elastic])
def test_easing_starts_at_zero_and_settles_at_one(fn):
    assert fn(0.0) == pytest.approx(0.0, abs=1e-6)
    assert fn(1.0) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------- particles
def test_particle_pool_is_bounded_and_empties():
    ps = Particles(random.Random(1))
    ps.burst(0, 0, (255, 0, 0), n=500, cap=100)
    assert len(ps.items) == 100
    ps.converge(400, (0, 255, 0), n=500, cap=100)
    assert len(ps.items) == 100
    for _ in range(300):
        ps.update(1 / 60)
    assert ps.items == []


@pytest.mark.parametrize("fn", ["burst", "converge"])
def test_particles_off_means_none(fn):
    ps = Particles(random.Random(1))
    (ps.burst(0, 0, (1, 2, 3), n=10, cap=0) if fn == "burst" else ps.converge(100, (1, 2, 3), n=10, cap=0))
    assert ps.items == []


def test_particles_draw_with_and_without_glow():
    ps = Particles(random.Random(1))
    ps.burst(0, 0, (255, 0, 0), n=5, twinkle=True)
    layer = glow.AddLayer((64, 64))
    layer.begin()
    ps.draw(layer, lambda x, y: (x + 32, y + 32), glow.GlowCache(), 0.0)
    ps.draw(layer, lambda x, y: (x + 32, y + 32), None, 0.0)
    ps.clear()
    assert ps.items == []


# ---------------------------------------------------------------- glow
def test_glow_sprites_are_cached_and_bounded():
    cache = glow.GlowCache(max_items=5, dither=0.0)
    a = cache.sprite((255, 0, 0), 10)
    assert cache.sprite((255, 0, 0), 10) is a
    for r in range(3, 20):
        cache.sprite((0, 255, 0), r)
    assert len(cache.cache) <= 6


def test_glow_is_brightest_in_the_middle():
    s = glow.GlowCache(dither=0.0).sprite((255, 255, 255), 20)
    w, h = s.get_size()
    assert s.get_at((w // 2, h // 2))[0] > s.get_at((0, h // 2))[0]


def test_additive_layer_adds_light():
    layer = glow.AddLayer((32, 32))
    layer.begin()
    layer.blit(glow.GlowCache(dither=0.0).sprite((255, 255, 255), 8), (16, 16))
    canvas = pygame.Surface((32, 32))
    canvas.fill((10, 10, 10))
    layer.composite(canvas)
    assert canvas.get_at((16, 16))[0] > 10
    assert canvas.get_at((0, 0))[0] == 10


def test_background_gradient_has_no_visible_banding():
    """The brief's first complaint: dithering must break up the 8-bit steps of the gradient."""
    plain = glow.radial_background(200, 200, 100, 100, 100, (6, 40, 56), (5, 36, 52), dither=0.0)
    dithered = glow.radial_background(200, 200, 100, 100, 100, (6, 40, 56), (5, 36, 52), dither=1.0)
    row_p = pygame.surfarray.array3d(plain)[:, 100, 1].astype(int)
    row_d = pygame.surfarray.array3d(dithered)[:, 100, 1].astype(int)
    assert np.abs(np.diff(row_p)).max() <= 1
    # long flat runs (the visible bands) are gone
    def longest_run(a):
        best = cur = 1
        for x, y in zip(a, a[1:]):
            cur = cur + 1 if x == y else 1
            best = max(best, cur)
        return best
    assert longest_run(row_d) < longest_run(row_p)


def test_dither_noise_is_bounded():
    n = glow.dither_noise((50, 50), 1.5)
    assert abs(n).max() <= 1.5 and n.std() > 0
    assert not glow.dither_noise((5, 5), 0).any()


# ---------------------------------------------------------------- icons
ICON_NAMES = sorted({t.icon for t in registry.all_types().values()})


@pytest.mark.parametrize("name", ICON_NAMES + ["unknown_icon"])
def test_every_icon_draws_something(name):
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    icons.draw_icon(s, name)
    assert pygame.mask.from_surface(s).count() > 50


def test_icons_are_all_different():
    seen = {}
    for name in ICON_NAMES:
        s = pygame.Surface((48, 48), pygame.SRCALPHA)
        icons.draw_icon(s, name)
        seen[pygame.image.tobytes(s, "RGBA")] = name
    assert len(seen) == len(ICON_NAMES)


@pytest.mark.parametrize("tid,t", sorted(registry.all_types().items()))
@pytest.mark.parametrize("bad", [False, True])
def test_every_power_up_badge_renders(tid, t, bad):
    ic = icons.IconCache()
    s = ic.badge(t.icon, tid, 40, (0, 255, 0), bad)
    assert s.get_width() >= 80
    assert ic.badge(t.icon, tid, 40, (0, 255, 0), bad) is s


def test_a_custom_icon_file_replaces_the_drawn_one(tmp_path, monkeypatch):
    img = pygame.Surface((16, 16), pygame.SRCALPHA)
    img.fill((1, 2, 3, 255))
    pygame.image.save(img, str(tmp_path / "expand.png"))
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    monkeypatch.setattr(icons, "ORBS_DIR", tmp_path / "no_faces")  # a branded coin face would take priority
    s = icons.IconCache().icon("expand", "expand", 32)
    assert s.get_at((16, 16))[:3] == (1, 2, 3)


def test_a_broken_custom_icon_falls_back(tmp_path, monkeypatch):
    (tmp_path / "expand.png").write_bytes(b"not an image")
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    s = icons.IconCache().icon("expand", "expand", 32)
    assert pygame.mask.from_surface(s).count() > 20


# ---------------------------------------------------------------- text
def test_text_cache_is_bounded_and_clears():
    cfg = Config()
    tr = text.TextRenderer(cfg, max_cache=10)
    for k in range(40):
        tr.render(f"متن {k}", 20, (255, 255, 255))
    assert len(tr.cache) <= 11
    tr.clear()
    assert not tr.cache


def test_empty_text_and_only_spaces_render():
    tr = text.TextRenderer(Config())
    assert tr.render("", 20, (255, 255, 255)).get_width() >= 0
    assert tr.render("   ", 20, (255, 255, 255)).get_height() > 0


def test_a_missing_font_falls_back():
    cfg = Config()
    cfg.set("fonts.persian", "no-such-font.ttf")
    tr = text.TextRenderer(cfg)
    assert tr.render("گل!", 30, (255, 255, 255)).get_width() > 5


def test_text_effects_grow_the_surface():
    cfg = Config()
    tr = text.TextRenderer(cfg)
    plain = tr.render("گل!", 40, (255, 255, 255))
    fancy = tr.render("گل!", 40, (255, 255, 255), outline=3)
    assert fancy.get_width() >= plain.get_width()


def test_persian_is_not_rendered_as_empty_boxes():
    """Shaped text and reversed text must differ, or the joining stopped working."""
    tr = text.TextRenderer(Config())
    joined = tr.render("سلام", 48, (255, 255, 255))
    apart = tr.render("س ل ا م", 48, (255, 255, 255))
    assert joined.get_width() < apart.get_width()


def test_digits_are_latin_in_every_mix():
    assert text.latin_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert text.has_rtl("گل 1") and not text.has_rtl("GOAL 1")


# ---------------------------------------------------------------- overlays and render edge cases
def test_debug_overlay_lists_the_state():
    cfg, eng, rend = world()
    advance_to_playing(eng)
    eng.force_spawn("expand")
    surf = rend.render(eng, 0.5, 1 / 60).copy()
    overlays.draw_debug(rend, eng, surf, 60.0, extra=["line"])
    overlays.draw_calibration(rend, eng, surf)


def test_events_before_the_first_frame_are_handled():
    cfg, eng, rend = world()
    rend.handle_events([{"type": "countdown_beat", "label": "3", "index": 0, "t": 0.0}], eng)
    rend.render(eng, 0.0, 1 / 60)


def test_slider_drags_stay_throttled():
    """The static art is slow to rebuild: a config change must not rebuild it within the same frame."""
    cfg, eng, rend = world()
    rend.render(eng, 0.0, 1 / 60)
    built = []
    rend._build_static = lambda e: built.append(1)
    cfg.set("walls.top_percent", cfg["walls.top_percent"] + 1)
    eng.step(1 / 240, {}, [True, True])
    rend.handle_events([], eng)
    rend.render(eng, 0.0, 1 / 60)
    assert built == []


def every_state_frames(values=None):
    cfg, eng, rend = world(values)
    frames = [rend.render(eng, 0.0, 1 / 60).copy()]
    eng.start_match()
    for _ in range(int(14 * 60)):
        for _ in range(4):
            eng.step(1 / 240, {}, [True, True])
        rend.handle_events(eng.drain_events(), eng)
        f = rend.render(eng, 0.5, 1 / 60)
        if _ % 60 == 0:
            frames.append(f.copy())
    return eng, frames


@pytest.mark.parametrize("values", [{}, {"arena.center_offset_x": 60, "arena.center_offset_y": -40},
                                    {"arena.mask_radius": 300}, {"fx.dither": False}, {"display.supersample": 1}])
def test_nothing_is_ever_drawn_outside_the_circle(values):
    """Light outside the floor circle would spill onto the walls and the audience."""
    eng, frames = every_state_frames(values)
    g = eng.geom
    lim = g.mask_r + eng.cfg["arena.mask_feather"] + 2
    xs, ys = np.meshgrid(np.arange(g.W), np.arange(g.H), indexing="ij")
    outside = np.hypot(xs - g.cx, ys - g.cy) > lim
    for f in frames:
        assert pygame.surfarray.array3d(f)[outside].max() == 0


def test_the_arena_is_actually_lit():
    _eng, frames = every_state_frames()
    assert all(pygame.surfarray.array3d(f).max() > 100 for f in frames)


def test_trails_show_who_touched_the_ball_last():
    cfg, eng, rend = world({"trails.style": "ribbon"})
    playing(eng)
    b = add_ball(eng, -100, 0, 400, 0, owner=0)
    for _ in range(30):
        for _ in range(4):
            eng.step(1 / 240, {}, [True, True])
        rend.render(eng, 0.5, 1 / 60)
    f1 = rend.render(eng, 0.5, 1 / 60).copy()
    b.owner = 1
    for _ in range(30):
        for _ in range(4):
            eng.step(1 / 240, {}, [True, True])
        rend.render(eng, 0.5, 1 / 60)
    assert pygame.image.tobytes(f1, "RGB") != pygame.image.tobytes(rend.render(eng, 0.5, 1 / 60), "RGB")


def test_score_digits_on_screen_are_latin():
    cfg, eng, rend = world()
    eng.time_left = 83.0
    assert not any("۰" <= ch <= "۹" for ch in rend.timer_text(eng))
    for fmt in ("seconds", "mm:ss", "auto"):
        cfg.set("hud.timer_format", fmt)
        assert rend.timer_text(eng)


@pytest.mark.parametrize("left,fmt,want", [(83.0, "mm:ss", "1:23"), (83.0, "seconds", "83"), (9.2, "auto", "10")])
def test_timer_formats(left, fmt, want):
    cfg, eng, rend = world({"hud.timer_format": fmt})
    eng.time_left = left
    assert rend.timer_text(eng) == want
