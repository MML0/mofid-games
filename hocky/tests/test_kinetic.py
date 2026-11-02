"""The kinetic backdrop: fidelity to the reference sketch, and the promises the game depends on."""

import math
import random

import numpy as np
import pygame
import pytest

from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.render.kinetic import (BRAND_MARKS, MOMENTS, SITE_CANVAS, KineticBackdrop, KineticField, KineticParams,
                                          clean_chars)
from market_hockey.render.renderer import Renderer


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def backdrop(values=None, state="ATTRACT"):
    b = KineticBackdrop(Config(values or {}))
    b.attach((400, 400), (200, 200, 200), 0.0, 3.0)
    b.update(0.0, state)
    return b


def run(b, seconds, state=None, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        b.update(dt, state)


# ---------------------------------------------------------------- the sketch's formulas
@pytest.mark.parametrize("frame,speed,freq,lo,hi", [(0, 0.06, 0.03, 0.25, 2.6), (137, 0.2, 0.1, 0.05, 8), (999, 0.01, 0.005, 1, 1)])
def test_stretch_is_the_sketch_formula(frame, speed, freq, lo, hi):
    f = KineticField(SITE_CANVAS)
    p = KineticParams(speed=speed, frequency=freq, min_stretch=lo, max_stretch=hi)
    f.phase = frame * speed
    for d in (0.0, 13.0, 200.0, 777.0):
        wave = math.sin(frame * speed + d * freq)
        assert f.stretch_at(np.array([d]), p)[0] == pytest.approx(lo + (wave + 1) / 2 * (hi - lo), abs=1e-5)


def test_ring_colors_and_letters_follow_the_sketch():
    """The cell at the center takes the first letter and first color; further out the rings advance."""
    f = KineticField((400, 400))
    colors = ((10, 0, 0), (0, 20, 0), (0, 0, 30))
    p = KineticParams(density=9, chars="AB", ring_width=40, colors=colors)
    seq = f.blit_list(p)
    assert len(seq) == 81
    d = np.hypot(*np.meshgrid((np.arange(1, 10) * 40.0 - 200), (np.arange(1, 10) * 40.0 - 200), indexing="ij")).ravel()
    for i, (sprite, _) in enumerate(seq):
        rgb = sprite.get_at(sprite.get_bounding_rect().center)[:3]
        expected = colors[int(d[i] // 40) % 3]
        assert rgb == pytest.approx(expected, abs=2), (i, d[i])


def test_grid_density_sets_the_font_size():
    f = KineticField(SITE_CANVAS)
    big = f.blit_list(KineticParams(density=10, chars="H", min_stretch=1, max_stretch=1))
    small = f.blit_list(KineticParams(density=60, chars="H", min_stretch=1, max_stretch=1))
    assert big[0][0].get_height() > 4 * small[0][0].get_height()


def test_changing_speed_does_not_jump_the_wave():
    """frameCount * speed would leap when a moment animates the speed; the accumulated phase must not."""
    f = KineticField((200, 200))
    p = KineticParams(speed=0.2)
    f.advance(10.0, p)
    before = f.phase
    p.speed = 0.01
    f.advance(1 / 60, p)
    assert f.phase - before == pytest.approx(0.01, abs=1e-6)


def test_spaces_stay_empty_in_the_sketch_and_become_dots_for_the_brand():
    assert clean_chars("گل!") == "گل" and clean_chars("MOFID NOW") == "MOFID•NOW"
    assert clean_chars("a b", space_marks=False) == "A B" and clean_chars("") == "•"
    f = KineticField((300, 300))
    assert f.blit_list(KineticParams(density=10, chars=" ")) == []


@pytest.mark.parametrize("text", ["MOFID", "کارگزاری مفید", "12 34", BRAND_MARKS, "ژ۱a•"])
def test_any_text_renders(text):
    f = KineticField((300, 300))
    assert f.blit_list(KineticParams(density=12, chars=clean_chars(text)))


def test_a_cold_cache_never_builds_more_than_the_budget_in_one_frame():
    f = KineticField((800, 800), budget=50)
    first = f.blit_list(KineticParams(density=40, chars="MOFID", max_stretch=8))
    assert f._sprite_n == 50 and len(first) >= 50
    for _ in range(40):
        last = f.blit_list(KineticParams(density=40, chars="MOFID", max_stretch=8))
    assert len(last) > len(first)  # the skipped cells arrive over the next frames


def test_the_site_field_draws_exact_widths_without_a_budget():
    f = KineticField((800, 800))
    assert len(f.blit_list(KineticParams(density=40, chars="H"))) == 1600


def test_sprite_cache_is_bounded():
    f = KineticField((600, 600))
    f.MAX_SPRITES = 200
    for i in range(40):
        f.phase = i * 0.37
        f.blit_list(KineticParams(density=30, chars="MOFID", max_stretch=8, colors=(((i * 6) % 255, 9, 9),) * 3))
    assert f._sprite_n <= 200 + 900


# ---------------------------------------------------------------- moments
@pytest.mark.parametrize("name", list(MOMENTS))
def test_every_moment_lands_on_the_resting_look(name):
    b = backdrop(state="PLAYING")
    b.play(name, gain=0.4)
    run(b, MOMENTS[name]["dur"] + 2.0, "PLAYING")
    rest = b.base("PLAYING")
    assert b.moment is None
    for k in ("density", "speed", "max_stretch", "ring_width", "opacity", "reveal_outer", "reveal_inner"):
        assert getattr(b.p, k) == pytest.approx(rest[k], abs=0.02), k


@pytest.mark.parametrize("name", list(MOMENTS))
def test_moments_stay_inside_the_sliders_ranges(name):
    b = backdrop()
    b.play(name, gain=0.4)
    for _ in range(int(MOMENTS[name]["dur"] * 60)):
        b.update(1 / 60, "ATTRACT")
        p = b.p
        assert 0.0 <= p.opacity <= 1.0 and 9 <= p.density <= 120 and 0 < p.min_stretch <= p.max_stretch + 1e-6
        assert p.max_stretch <= 8 + 1e-6 and 0.001 < p.speed <= 0.2 + 1e-6 and 20 <= p.ring_width <= 200


def test_moments_animate_the_sliders():
    b = backdrop(state="PLAYING")
    run(b, 0.2, "PLAYING")
    b.on_goal(0, 0.9, 0.0)
    peak = 0.0
    for _ in range(40):
        b.update(1 / 60, "GOAL")
        peak = max(peak, b.p.max_stretch)
    assert peak > 3 and b.p.opacity > 0.1


def test_goal_uses_the_scorer_color_and_the_goal_text():
    b = backdrop(state="PLAYING")
    b.on_goal(1, 0.0, 0.9)
    run(b, 1.2, "GOAL")
    assert b.p.chars == "GOAL"
    assert b.p.colors[0] == b._team_colors(1)[0] or b.p.colors != b._base_colors()


def test_text_wipes_outward_then_commits():
    b = backdrop()
    b.set_text("NEXT")
    assert b.p.chars_next == "NEXT"
    b.update(0.2, "ATTRACT")
    assert 0 < b.p.wipe < 1
    run(b, 1.0, "ATTRACT")
    assert b.p.chars == "NEXT" and b.p.chars_next == "" and b.p.wipe == 0


def test_waiting_screen_cycles_the_brand_texts():
    b = backdrop({"kinetic.attract_text": "AAA|BBB", "kinetic.text_interval_s": 2.0, "kinetic.splash": False})
    assert b.p.chars == "AAA"
    run(b, 3.0, "ATTRACT")
    assert b.p.chars == "BBB"


# ---------------------------------------------------------------- faintness and brand
def test_nothing_is_drawn_during_play_by_default():
    b = backdrop({"kinetic.splash": False}, state="PLAYING")
    run(b, 2.0, "PLAYING")
    canvas = pygame.Surface((400, 400))
    canvas.fill((9, 8, 7))
    before = pygame.image.tobytes(canvas, "RGB")
    b.draw(canvas)
    assert pygame.image.tobytes(canvas, "RGB") == before


@pytest.mark.parametrize("state,key", [("ATTRACT", "kinetic.opacity_waiting"), ("RESULT", "kinetic.opacity_result"),
                                       ("COUNTDOWN", "kinetic.opacity_countdown")])
def test_opacity_settings_control_the_brightness(state, key):
    b = backdrop({"kinetic.splash": False, key: 0.3}, state=state)
    run(b, 2.0, state)
    canvas = pygame.Surface((400, 400))
    b.draw(canvas)
    arr = pygame.surfarray.array3d(canvas)
    assert 0 < arr.max() <= 0.3 * 255 + 4


def test_disabled_draws_nothing():
    cfg = Config({"kinetic.enabled": False})
    e = Engine(cfg, random.Random(1))
    r = Renderer(cfg, random.Random(1))
    r.render(e, 0.0, 1 / 60)
    canvas = pygame.Surface((64, 64))
    r.kinetic.draw(canvas)
    assert pygame.surfarray.array3d(canvas).max() == 0


def test_default_palette_leads_with_the_brand_color():
    b = backdrop()
    assert b._base_colors()[0] == (0, 167, 150)  # brand turquoise leads; the blues are the reference's picks


def test_reduce_flashing_softens_and_disables_the_flicker():
    b = backdrop({"fx.reduce_flashing": True, "kinetic.color_swap": True}, state="PLAYING")
    b.on_goal(0, 0.5, 0.5)
    run(b, 0.3, "GOAL")
    assert not b.p.color_swap and b.p.opacity <= 0.75 * 0.6 + 0.01


# ---------------------------------------------------------------- playtest promises
def game_field(side=1080, **kw):
    return KineticField((side, side), 1207 / side, 0.0, (side / 2, side / 2, side / 2), budget=None, ink_centered=True, **kw)


@pytest.mark.parametrize("density", [12, 13, 28, 29])
def test_the_pattern_is_dead_center(density):
    """A symmetric letter on any grid leaves the field symmetric about the exact middle, in both axes."""
    p = KineticParams(density=density, chars="H", colors=((255, 255, 255),) * 3, min_stretch=1, max_stretch=1)
    s = pygame.Surface((1080, 1080))
    game_field().draw(s, p)
    a = pygame.surfarray.array3d(s)[:, :, 0] > 128
    ys = np.nonzero(a.any(axis=0))[0]
    xs = np.nonzero(a.any(axis=1))[0]
    assert abs((xs[0] + xs[-1]) / 2 - 539.5) <= 1 and abs((ys[0] + ys[-1]) / 2 - 539.5) <= 1


def test_game_grid_always_has_a_cell_on_the_center():
    p = KineticParams(density=28, chars="H", colors=((255, 255, 255),) * 3, min_stretch=1, max_stretch=1)
    s = pygame.Surface((1080, 1080))
    game_field().draw(s, p)
    assert s.get_at((540, 540))[0] > 0 or s.get_at((530, 540))[0] > 0


def test_nothing_drifts_off_center_by_default():
    b = backdrop(state="ATTRACT")
    for _ in range(60 * 20):
        b.update(1 / 60, "ATTRACT")
        assert b.p.cx == 0 and b.p.cy == 0
    b = backdrop(state="PLAYING")
    b.on_goal(0, 0.95, 0.2)
    for _ in range(60):
        b.update(1 / 60, "GOAL")
        assert b.p.cx == 0 and b.p.cy == 0
    b = backdrop({"kinetic.goal_at_impact": True}, state="PLAYING")
    b.on_goal(0, 0.95, 0.2)
    b.update(1 / 60, "GOAL")
    assert b.p.cx == 0.95


def test_the_result_divide_is_on_the_exact_center_line():
    b = backdrop({"kinetic.splash": False, "kinetic.opacity_result": 1.0}, state="RESULT")
    b.goal_dirs, b.winner = ((-1.0, 0.0), (1.0, 0.0)), 0
    b.on_state("RESULT", "FINAL")
    run(b, 4.0, "RESULT")
    canvas = pygame.Surface((400, 400))
    b.draw(canvas)
    a = pygame.surfarray.array3d(canvas).astype(int)
    red_on_winner_side = (a[:198, :, 0] > a[:198, :, 1] + 40).sum()
    green_on_other_side = (a[202:, :, 1] > a[202:, :, 0] + 40).sum()
    assert red_on_winner_side == 0 and green_on_other_side == 0
    assert a[:198].max() > 0 and a[202:].max() > 0


def test_effect_text_defaults_are_all_english():
    cfg = Config({})
    for key in ("attract_text", "text_start", "text_ready", "text_go", "text_goal", "text_final", "text_winner",
                "text_draw", "loser_text"):
        assert cfg[f"kinetic.{key}"].isascii(), key
    b = backdrop(state="COUNTDOWN")
    seen = []
    for label in ("ready", "3", "go"):
        b.on_beat(label, 1.0)
        seen.append(b.p.chars)
    b.on_goal(1, 0, 0)
    seen.append(b.p.chars)
    b.winner, b.names = 0, ("سارا", "علی")
    b._begin_result()
    seen += [b.p.chars, b.p.side_chars]
    assert all(s.replace("•", "x").isascii() for s in seen), seen


def test_letters_cannot_spread_past_the_overlap_limit():
    f = game_field()
    p = KineticParams(density=21, chars="M", min_stretch=8, max_stretch=8, max_overlap=1.5)
    cell = 1080 / 22
    assert max(s.get_width() for s, _ in f.blit_list(p)) <= cell * 1.5 + 1


@pytest.mark.parametrize("name", list(MOMENTS))
def test_no_moment_is_a_stack_of_letters(name):
    """Default moments keep every letter within the limit, even on their peak frames."""
    b = backdrop()
    b.play(name, gain=0.3)
    for _ in range(int(MOMENTS[name]["dur"] * 60)):
        b.update(1 / 60, "ATTRACT")
        assert b.p.max_stretch <= 4


def test_countdown_digit_stays_readable():
    """The digit keeps its shape (little stretch, whole grid) and leaves the middle clear for the big number."""
    b = backdrop(state="COUNTDOWN")
    b.on_beat("3", 1.1)
    density = set()
    for _ in range(66):
        b.update(1 / 60, "COUNTDOWN")
        density.add(round(b.p.density))
        assert b.p.max_stretch <= 2.4 and b.p.min_stretch >= 0.85 and b.p.reveal_inner > 0.25 and b.p.speed <= 0.04
    assert density == {31}


def test_big_countdown_number_is_centered_on_the_arena():
    cfg = Config({})
    e = Engine(cfg, random.Random(1))
    r = Renderer(cfg, random.Random(1))
    r.render(e, 0.0, 1 / 60)
    g = e.geom
    r.canvas.fill((0, 0, 0))
    r._text_at("1", 300, (255, 255, 255), 0, 0, key="digits", outline=3, glow=0.8, ink_center=True)
    box = pygame.mask.from_threshold(r.canvas, (255, 255, 255), (6, 6, 6)).get_bounding_rects()
    box = box[0].unionall(box[1:])
    assert abs(box.centerx - g.cx) <= 3 and abs(box.centery - g.cy) <= 3


def test_title_divider_is_flanked_evenly():
    fa, en = (150, 40, 260), (90, 30, 150)  # (surface center, ink left, ink right)
    fx, ex = Renderer._title_offsets(fa, en, 40)
    assert fx - (fa[0] - fa[1]) == 40  # Persian ink starts 40 from the divider
    assert ex + (en[2] - en[0]) == -40  # English ink ends 40 from the divider


def lit(canvas, r0, r1, side=400):
    a = pygame.surfarray.array3d(canvas).sum(axis=2).astype(float)
    xx, yy = np.meshgrid(np.arange(side) - side / 2 + 0.5, np.arange(side) - side / 2 + 0.5, indexing="ij")
    rr = np.hypot(xx, yy) / (side / 2)
    return a[(rr >= r0) & (rr < r1)]


def test_letters_fade_to_nothing_before_the_game_elements():
    b = backdrop({"kinetic.splash": False, "kinetic.opacity_waiting": 1.0, "kinetic.opacity_wave_min": 1.0,
                  "kinetic.max_overlap": 1.0}, state="ATTRACT")
    run(b, 1.0, "ATTRACT")
    canvas = pygame.Surface((400, 400))
    b.draw(canvas)
    assert lit(canvas, 0.1, 0.4).mean() > 3 * lit(canvas, 0.7, 0.8).mean()  # fading across the range
    assert lit(canvas, 0.86, 1.0).max() == 0  # nothing reaches the paddles, walls or goal lines


def test_opacity_wave_rises_and_falls_on_its_own_sine():
    b = backdrop({"kinetic.splash": False, "kinetic.opacity_waiting": 1.0, "kinetic.opacity_wave_frequency": 0.0,
                  "kinetic.opacity_wave_min": 0.0, "kinetic.opacity_wave_sharpness": 1.0,
                  "kinetic.opacity_wave_speed": 0.05}, state="ATTRACT")
    run(b, 2.0, "ATTRACT")
    levels = []
    for _ in range(int(2 * math.pi / (0.05 * 60) * 60) + 2):
        b.update(1 / 60, "ATTRACT")
        canvas = pygame.Surface((400, 400))
        b.draw(canvas)
        levels.append(float(pygame.surfarray.array3d(canvas).sum()))
    assert min(levels) < 0.05 * max(levels)  # with a valley of 0 the whole visual really disappears
    jumps = np.abs(np.diff(levels)) / max(levels)
    assert jumps.max() < 0.12  # and it glides there


def test_opacity_wave_is_off_outside_the_waiting_screen():
    b = backdrop(state="COUNTDOWN")
    run(b, 2.0, "COUNTDOWN")
    assert b.p.op_min > 0.98 and b.p.op_max > 0.98


def test_opacity_does_not_grow_the_sprite_cache():
    f = KineticField((400, 400), budget=None)
    p = KineticParams(density=20, chars="MOFID", min_stretch=1, max_stretch=1)
    f.blit_list(p)
    n = f._sprite_n
    p.op_min, p.edge_start, p.edge_end = 0.1, 0.4, 0.8
    canvas = pygame.Surface((400, 400))
    for i in range(30):
        f.op_phase = i * 0.3
        f.paint(canvas, p)
    assert f._sprite_n == n


def test_alpha_then_plain_frames_do_not_keep_a_stale_fade():
    f = KineticField((200, 200))
    p = KineticParams(density=9, chars="H", colors=((255, 255, 255),) * 3, min_stretch=1, max_stretch=1, op_min=0.1, op_max=0.1)
    c = pygame.Surface((200, 200))
    f.paint(c, p)
    dim = pygame.surfarray.array3d(c).max()
    p.op_min = p.op_max = 1.0
    c.fill((0, 0, 0))
    f.paint(c, p)
    assert dim <= 40 and pygame.surfarray.array3d(c).max() >= 240


@pytest.mark.parametrize("name", list(MOMENTS))
def test_moments_never_slide_the_grid(name):
    """Stepping density or ring width mid-moment shifted every cell at once, which was the visible jumping."""
    b = backdrop()
    b.play(name, gain=0.3)
    for k in ("density", "ring_width", "letter_width"):
        track = MOMENTS[name]["tracks"].get(k)
        assert track is None or len({v[1] for v in track}) == 1, k
    seen = set()
    for _ in range(int(MOMENTS[name]["dur"] * 60) - 1):
        b.update(1 / 60, "ATTRACT")
        seen.add((b.p.density, b.p.ring_width, b.p.letter_width))
    assert len(seen) == 1


def test_letter_rings_can_differ_from_color_rings():
    f = KineticField((400, 400))
    p = KineticParams(density=9, chars="AB", ring_width=20, letter_width=1000, min_stretch=1, max_stretch=1)
    assert {s.get_size() for s, _ in f.blit_list(p)} == {f.blit_list(p)[0][0].get_size()}  # a single letter everywhere


def test_brand_fonts_are_the_defaults_and_exist():
    from market_hockey.paths import FONTS_DIR
    cfg = Config({})
    assert cfg["fonts.persian_title"] == "Pinar-Black.ttf" and cfg["fonts.latin"].startswith("SF-Compact")
    for key in ("fonts.persian", "fonts.persian_title", "fonts.digits", "fonts.latin", "kinetic.font_latin", "kinetic.font_persian"):
        assert (FONTS_DIR / cfg[key]).exists(), key


# ---------------------------------------------------------------- in the game
def test_a_whole_match_drives_the_backdrop_through_every_moment():
    cfg = Config({"match.duration_s": 2, "match.result_s": 2.0})
    e = Engine(cfg, random.Random(5))
    r = Renderer(cfg, random.Random(6))
    seen = set()
    states = set()
    e.start_match()
    for _ in range(60 * 30):
        for _ in range(4):
            e.step(1 / 240)
        r.handle_events(e.drain_events(), e)
        r.render(e, 0.0, 1 / 60)
        states.add(e.state)
        if r.kinetic.moment:
            seen.add(r.kinetic.moment.name)
        if e.state == "ATTRACT" and "RESULT" in states:
            break
    assert {"match_start", "ready", "beat", "go", "final", "result"} <= seen, seen
