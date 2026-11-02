"""Moving brand objects: they come from the brand files, stay sharp and centered, and never stall a frame."""

import random

import numpy as np
import pygame
import pytest

from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.render.brand_motion import (BRAND_DIR, GAME_ICONS, MARKS, WIN_ICONS, ZOOM_END, ZOOM_FADE, spring_step, Actor, BrandMotion,
                                               CoinWall, Flood, HeroCoin, Plane, RadialLayer)
from market_hockey.render.renderer import Renderer


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def motion(values=None, state="ATTRACT"):
    m = BrandMotion(Config(values or {}), random.Random(3))
    m.attach((200, 200), 200, 190, 0.0)
    m.state = state
    return m


def run(m, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        m.update(dt)


def test_every_icon_in_use_is_a_baked_brand_file():
    for name in set(GAME_ICONS + WIN_ICONS) | {"bull", "plane", "logo_stacked"}:
        assert (BRAND_DIR / f"{name}.png").exists(), name


def test_rings_are_dead_center_and_their_edges_are_one_pixel():
    layer = RadialLayer(200)
    layer.begin()
    layer.add(layer.band(50, 80), (255, 255, 255))
    c = pygame.Surface((400, 400))
    layer.composite(c, 200, 200)
    a = pygame.surfarray.array3d(c)[:, :, 0].astype(int)
    assert (a == a[::-1, :]).all() and (a == a[:, ::-1]).all()  # mirror-symmetric around the middle
    assert a[200 + 65, 200] == 255 and a[200 + 30, 200] == 0 and a[200 + 100, 200] == 0
    row = a[200:, 200]
    assert (row[(row > 0) & (row < 255)]).size <= 4  # two edges, a pixel or two each: no soft glow


def test_a_flood_lands_on_the_true_color_rather_than_adding_to_the_floor():
    cfg = Config({"colors.arena_inner": "#102030"})
    m = BrandMotion(cfg, random.Random(1))
    m.attach((200, 200), 200, 190, 0.0)
    assert Flood(m, (100, 100, 100)).color == (84, 68, 52)


def test_a_purple_goal_stays_under_the_brands_30_percent():
    m = motion(state="GOAL")
    m.teams = ((0, 167, 150), m.art.palette["accent"])
    m.cue_goal(1)
    flood = next(a for a in m.actors if isinstance(a, Flood))
    run(m, 0.0)
    for u in (0.27, 0.4, 0.6):  # from fully grown onward
        flood.t = flood.dur * u
        m.layer.begin()
        flood.radial(m.layer, 1.0)
        r = m.layer.r
        lit = m.layer.lut[:, 0] > 1
        area = (r[lit] * 2).sum() / (r[r < m.R] * 2).sum()  # weighted by circumference
        assert area < 0.33, u


def test_the_waiting_loop_runs_every_object_and_loops():
    m = motion()
    seen = set()
    for _ in range(60 * 50):
        m.update(1 / 60)
        seen |= {type(a).__name__ for a in m.actors}
    assert {"Flood", "HeroCoin", "Plane", "FlyingCoin", "DotWave", "MarketLine", "PulseBed", "CoinWall"} <= seen
    assert m._loop_t < 46


def test_the_wall_leaves_the_prompt_and_title_clear_on_the_waiting_screen():
    m = motion()
    m.cue_wall()
    wall = next(a for a in m.actors if isinstance(a, CoinWall))
    assert min(np.hypot(c[0], c[1]) for c in wall.cells) >= m.R * 0.42 - 1


def test_the_winners_wall_is_on_the_winners_side_and_off_their_score():
    m = motion(state="RESULT")
    m.goal_dirs = ((-1.0, 0.0), (1.0, 0.0))
    m.winner = 1
    m.cue_result()
    wall = next(a for a in m.actors if isinstance(a, CoinWall))
    assert wall.cells and all(c[0] > 0 for c in wall.cells)
    score_at = m.R * 0.5
    assert all(abs(c[0] - score_at) > m.R * 0.17 or abs(c[1]) > m.R * 0.2 for c in wall.cells)


def test_planes_cross_during_play_only_when_allowed():
    m = motion({"motion.plane_every_s": 4.0}, state="PLAYING")
    run(m, 6)
    assert any(isinstance(a, Plane) for a in m.actors)
    m = motion({"motion.plane_every_s": 4.0, "motion.in_play": False}, state="PLAYING")
    run(m, 6)
    assert not m.actors


def test_all_marks_draw():
    m = motion()
    for name in MARKS:
        s = m.art.mark(name, 40, (255, 255, 255))
        assert pygame.surfarray.array_alpha(s).max() == 255


def test_coins_turn_edge_on():
    m = motion()
    flat = m.art.coin("star", "pale", 80, 0.0)
    side = m.art.coin("star", "pale", 80, 1.45)
    assert flat.get_height() == 80 and side.get_height() < 20 and side.get_width() == 80


def test_a_missing_icon_file_only_loses_the_picture():
    m = motion()
    assert m.art.coin("no_such_icon", "teal", 40, 0.0).get_width() == 40


def test_disabled_draws_nothing_and_leaves_the_letters_alone():
    m = motion({"motion.enabled": False})
    run(m, 1)
    assert not m.actors and m.type_dim == 1.0
    c = pygame.Surface((400, 400))
    m.draw(c)
    assert pygame.surfarray.array3d(c).max() == 0


def test_leaving_a_state_ends_its_objects_quickly():
    m = motion()
    run(m, 1)
    old = list(m.actors)
    assert old
    m.on_state("INTRO", "ATTRACT")
    run(m, 0.6)
    assert not set(old) & set(m.actors)


@pytest.mark.parametrize("reduce", [False, True])
def test_a_whole_match_runs_with_the_objects_on(reduce):
    cfg = Config({"match.duration_s": 10, "match.result_s": 2.0, "fx.reduce_flashing": reduce})
    e = Engine(cfg, random.Random(5))
    r = Renderer(cfg, random.Random(6))
    e.start_match()
    states = set()
    for _ in range(60 * 30):
        for _ in range(4):
            e.step(1 / 240)
        r.handle_events(e.drain_events(), e)
        r.render(e, 0.0, 1 / 60)
        states.add(e.state)
        if e.state == "ATTRACT" and "RESULT" in states:
            break
    assert "RESULT" in states


def test_old_settings_move_to_the_smaller_letters_and_stronger_look():
    from market_hockey.config.store import MIGRATIONS
    flat = {"kinetic.density": 35, "kinetic.opacity_moment": 0.22, "kinetic.opacity_waiting": 0.5}
    out = MIGRATIONS[8](dict(flat))
    assert out["kinetic.density"] == 55 and out["kinetic.opacity_moment"] == 0.75
    assert out["kinetic.opacity_waiting"] == 0.5  # someone's own value stays


def test_objects_fade_near_the_rim_over_a_shorter_range_than_the_letters():
    cfg = Config({})
    assert cfg["motion.edge_fade_end"] - cfg["motion.edge_fade_start"] < cfg["kinetic.edge_fade_end"] - cfg["kinetic.edge_fade_start"]
    m = motion({"motion.object_opacity": 1.0})
    m._prepare_objects((400, 400), 0.72 * m.R, 0.92 * m.R)
    a = pygame.surfarray.array_alpha(m.edge_mask)
    assert a[200, 200] == 255 and a[int(200 + 0.6 * m.R), 200] == 255
    assert 0 < a[int(200 + 0.82 * m.R), 200] < 255
    assert a[int(200 + 0.95 * m.R), 200] == 0


def test_a_candle_at_the_rim_disappears_and_one_at_the_middle_stays_behind_the_game():
    class Block(Actor):
        dur = 9.0

        def draw(self, target, level):
            target.fill((255, 255, 255, 255))

    m = motion({"motion.object_opacity": 0.5})
    m.add(Block(m))
    m._level = 1.0
    c = pygame.Surface((400, 400))
    m.draw(c)
    a = pygame.surfarray.array3d(c)[:, :, 0]
    assert 120 <= a[200, 200] <= 135  # half strength: a background, not a foreground
    assert a[200 + int(0.95 * m.R), 200] == 0


def test_floods_are_softened_and_fade_at_the_rim():
    m = motion({"motion.flood_strength": 0.5, "colors.arena_inner": "#000000"})
    run(m, 0.0)
    m.update(1 / 60)
    flood = Flood(m, (200, 200, 200), dur=4.0)
    flood.t = 1.2
    m.layer.begin()
    flood.radial(m.layer, 1.0)
    assert m.layer.lut[:, 0].max() <= 101
    m.layer.fade_edge(0.72 * m.R, 0.92 * m.R)
    assert m.layer.lut[int(0.95 * m.R * 2), 0] == 0


def test_the_countdown_counts_five_seconds_and_follows_its_setting():
    e = Engine(Config({}), random.Random(1))
    assert e.cfg["countdown.start"] == 5 and e.cfg["countdown.beat_s"] == 1.0
    assert e.countdown_total() == pytest.approx(e.cfg["countdown.ready_s"] + 5.0 + e.cfg["countdown.go_s"])
    e = Engine(Config({"countdown.start": 3}), random.Random(1))
    assert e.countdown_total() == pytest.approx(e.cfg["countdown.ready_s"] + 3 * e.cfg["countdown.beat_s"] + e.cfg["countdown.go_s"])


def _waiting_contrast(backing):
    """The bright pixels left around the title while a pale flood covers the floor."""
    cfg = Config({"match.title_backing": backing, "motion.flood_strength": 1.0})
    e = Engine(cfg, random.Random(1))
    r = Renderer(cfg, random.Random(1))
    r.render(e, 0.0, 1 / 60)
    r.handle_events(e.drain_events(), e)
    for _ in range(40):  # the opening flood is fully grown by now
        s = r.render(e, 0.0, 1 / 60)
    g = e.geom
    x, y = int(g.cx), int(g.cy - g.R * 0.34 + cfg["text.banner_size"] * 0.9)
    return pygame.surfarray.array3d(s)[x - 200:x + 200, y - 6:y + 6].mean()


def test_the_title_stands_on_a_dark_backing_even_during_a_flood():
    assert _waiting_contrast(0.82) < 0.6 * _waiting_contrast(0.0)


@pytest.mark.parametrize("start", [1, 3, 5, 9])
def test_every_count_runs_and_colors_alternate(start):
    cfg = Config({"countdown.start": start, "match.duration_s": 10, "match.attract_demo": False})
    e = Engine(cfg, random.Random(2))
    r = Renderer(cfg, random.Random(2))
    e.start_match()
    beats = []
    for _ in range(60 * 18):
        for _ in range(4):
            e.step(1 / 240)
        ev = e.drain_events()
        beats += [x["label"] for x in ev if x["type"] == "countdown_beat"]
        r.handle_events(ev, e)
        r.render(e, 0.0, 1 / 60)
        if "go" in beats:
            break
    assert beats == ["ready", *[str(n) for n in range(start, 0, -1)], "go"]


def test_small_objects_only_composite_their_own_area_and_nothing_is_cut_or_left_behind():
    m = motion({"motion.object_opacity": 1.0, "motion.edge_fade_start": 1.1, "motion.edge_fade_end": 1.2})
    m.add(Plane(m, a0=0.5, dur=2.0))
    c = pygame.Surface((400, 400))
    frames = []
    for _ in range(70):
        m.update(1 / 60)
        c.fill((0, 0, 0))
        m.draw(c)
        frames.append(pygame.surfarray.array3d(c).copy())
        plane = next((a for a in m.actors if isinstance(a, Plane)), None)
        if plane and plane.started:
            area = m._paint_area(1.2 * m.R, c.get_rect())
            assert area.w < 400 and area.h < 400  # a plane alone needs less than the whole screen
    # a later frame in which the plane has moved on shows nothing where the plane used to be
    lit = [(f.max(axis=2) > 40) for f in frames[20:]]
    assert lit[0].any() and lit[-1].any()
    assert (lit[0] & ~lit[-1]).any() and (lit[-1] & ~lit[0]).any()


def test_the_center_coin_is_not_cut_by_its_area():
    m = motion({"motion.object_opacity": 1.0})
    m.add(HeroCoin(m, [("star", "pale")], 120))
    c = pygame.Surface((400, 400))
    for _ in range(30):
        m.update(1 / 60)
    m.draw(c)
    a = pygame.surfarray.array3d(c)[:, :, 1]
    lit = np.argwhere(a > 60)
    assert lit[:, 0].max() - lit[:, 0].min() >= 110 and lit[:, 1].max() - lit[:, 1].min() >= 110


def test_the_result_screen_lasts_ten_seconds_and_keeps_moving():
    assert Config({})["match.result_s"] == 10.0
    m = motion(state="RESULT")
    m.goal_dirs = ((-1.0, 0.0), (1.0, 0.0))
    m.winner = 0
    m.cue_result()
    bursts = 0
    for _ in range(int(10 * 60)):
        before = m._next_cheer
        m.update(1 / 60)
        bursts += m._next_cheer != before
    assert bursts >= 2  # the fireworks keep coming, not only in the first seconds


def _curve(rest=0.55, n=600):
    m = motion()
    return [m.zoom_frame(i / n, rest) for i in range(n + 1)]


def test_the_start_logo_begins_exactly_as_the_waiting_screen_shows_it_and_ends_at_nothing():
    k, op, travel = _curve()[0]
    assert k == 1.0 and op == pytest.approx(0.55) and travel == 0.0
    k, op, travel = _curve()[-1]
    assert k == pytest.approx(ZOOM_END, rel=0.02) and op == pytest.approx(0.0, abs=1e-6) and travel == pytest.approx(1.0, abs=0.03)


def test_the_start_logo_has_no_clicks_every_curve_changes_smoothly():
    for curve in zip(*_curve()):
        steps = np.diff(curve)
        assert np.abs(np.diff(steps)).max() < np.abs(steps).max() * 0.1, "a sudden change of speed"


def test_the_spring_starts_slowly_and_overshoots_the_center_softly_once():
    assert spring_step(0.0) == 0.0 and spring_step(0.02) < 0.02  # no jolt on leaving
    values = [spring_step(i / 200) for i in range(201)]
    assert 1.02 < max(values) < 1.12  # past the center a little
    assert abs(values[-1] - 1) < 0.03  # and settled
    peaks = np.sum((np.diff(np.sign(np.diff(values))) < 0))
    assert peaks == 1  # one soft overshoot, no wobble


def test_the_start_logo_grows_all_the_way_and_only_fades_after_it_has_grown():
    frames = _curve()
    sizes = [f[0] for f in frames]
    assert sizes[-1] > 8 and all(b >= a - 0.03 for a, b in zip(sizes, sizes[1:]))
    n = len(frames) - 1
    assert frames[int(ZOOM_FADE * n)][1] > 0.99  # fully visible when the fade begins
    assert frames[int(ZOOM_FADE * n)][0] > 1.4  # and it has already zoomed a bit
    mid = frames[int(0.8 * n)]
    assert 0.1 < mid[1] < 0.9 and mid[0] > frames[int(ZOOM_FADE * n)][0] * 1.3  # fading and growing at the same time


def _logo_frame(values=None, seconds=None):
    m = BrandMotion(Config({"match.intro_s": 2.8, "motion.waiting_loop": False, **(values or {})}), random.Random(1))
    m.attach((200, 200), 200, 190, 0.0)
    m.state = "ATTRACT"
    m.update(1 / 60)
    c = pygame.Surface((400, 400))
    if seconds is not None:
        m.state = "INTRO"
        m.on_state("INTRO", "ATTRACT")
        if seconds:
            run(m, seconds)
    return m, c


def test_the_same_logo_is_on_the_waiting_screen_with_no_jump_when_start_is_pressed():
    m, c = _logo_frame()
    m.draw(c)
    rest = pygame.surfarray.array3d(c).copy()
    assert 100 < rest.max() < 170 and rest[:, :200].max() == 0  # soft, and low on the arena
    m, c = _logo_frame(seconds=0.0)
    m.draw_logo_zoom(c)
    first = pygame.surfarray.array3d(c)
    assert np.abs(first.astype(int) - rest.astype(int)).max() < 8  # pressing Start changes nothing you could see


def test_the_logo_is_white_on_transparent_with_no_box_or_disc():
    m = motion()
    img = pygame.image.load(str(BRAND_DIR / "logo_stacked.png"))
    alpha = pygame.surfarray.array_alpha(img)
    assert img.get_width() >= 3000 and alpha[0, 0] == 0 and alpha[-1, -1] == 0 and alpha.max() == 255
    assert (alpha == 0).mean() > 0.5  # most of the image is see-through
    assert ((alpha > 0) & (alpha < 255)).mean() < 0.02  # hard vector edges, not a soft raster
    m._logo_alpha = 1.0
    m.state = "ATTRACT"
    c = pygame.Surface((400, 400))
    m.draw_rest_logo(c)
    a = pygame.surfarray.array3d(c)
    assert a.max() >= 250 and (a[:, :, 0] == a[:, :, 1]).all() and (a[:, :, 1] == a[:, :, 2]).all()


def test_the_logo_stays_centered_and_does_not_wobble_as_it_grows():
    m = motion()
    screen = pygame.Rect(0, 0, 400, 400)
    for width in range(60, 380, 7):
        frame, pos = m.art.logo_frame(width, (200, 200), screen)
        assert frame.get_width() % 2 == 0 and frame.get_height() % 2 == 0
        assert pos[0] + frame.get_width() / 2 == 200 and pos[1] + frame.get_height() / 2 == 200


def test_a_frame_of_the_zoom_costs_about_the_same_at_any_size():
    import time
    m = motion()
    screen = pygame.Rect(0, 0, 1080, 1080)
    costs = []
    for width in (280, 700, 1500, 2600):
        t = time.perf_counter()
        for _ in range(5):
            m.art.logo_frame(width, (540, 540), screen)
        costs.append((time.perf_counter() - t) / 5)
    assert max(costs) < 0.03  # a giant image rescaled from scratch every frame took far longer, and stuttered


def test_the_logo_leaves_with_the_zoom_and_returns_softly_after_a_match():
    m, c = _logo_frame(seconds=0.2)
    assert m._logo_alpha < 0.02
    m.zoom_t = None
    m.on_state("ATTRACT", "RESULT")
    m.state = "ATTRACT"
    m.update(1 / 60)
    assert m._logo_alpha < 0.05
    run(m, 3)
    assert m._logo_alpha == pytest.approx(0.55, abs=0.05)


def test_objects_fade_where_they_are_instead_of_jumping_when_a_state_ends():
    m = motion()
    plane = Plane(m, a0=0.5, dur=3.0)
    m.add(plane)
    run(m, 1.0)
    before = plane._at(plane.t / plane.dur)
    plane.leave()
    assert plane.presence() == 1.0
    m.update(1 / 60)
    after = plane._at(plane.t / plane.dur)
    assert np.hypot(after[0] - before[0], after[1] - before[1]) < m.R * 0.05  # still on its way, not teleported
    p1 = plane.presence()
    run(m, plane.fade_out * 0.5)
    assert 0 < plane.presence() < p1
    run(m, plane.fade_out)
    assert plane not in m.actors


def test_the_waiting_text_fades_out_after_start_and_the_score_waits():
    cfg = Config({"motion.waiting_loop": False})
    e = Engine(cfg, random.Random(1))
    r = Renderer(cfg, random.Random(1))
    e.names = ["علی", "سارا"]
    r.render(e, 0.0, 1 / 60)
    r.handle_events(e.drain_events(), e)
    g = e.geom
    box = int(g.cx + g.R * 0.25), int(g.cy - g.R * 0.45), int(g.R * 0.5), int(g.R * 0.25)  # the title

    def bright():
        for _ in range(4):
            e.step(1 / 240)
        r.handle_events(e.drain_events(), e)
        s = r.render(e, 0.0, 1 / 60)
        a = pygame.surfarray.array3d(s)[box[0]:box[0] + box[2], box[1]:box[1] + box[3]]
        return (a.min(axis=2) > 120).mean()

    waiting = bright()
    e.start_match()
    levels = [bright() for _ in range(40)]
    assert waiting > 0.02
    assert levels[0] > waiting * 0.5  # no vanishing on the frame after Start
    assert levels[-1] < waiting * 0.1


def test_no_logo_zoom_keeps_the_old_flood():
    m = motion({"motion.logo_zoom": False}, state="INTRO")
    m.on_state("INTRO", "ATTRACT")
    assert m.zoom_t is None and any(isinstance(a, Flood) for a in m.actors)


def _waiting(values, names=("", "")):
    cfg = Config(values)
    e = Engine(cfg, random.Random(1))
    r = Renderer(cfg, random.Random(1))
    e.names = list(names)
    s = None
    for _ in range(420):  # past the opening flood
        r.handle_events(e.drain_events(), e)
        s = r.render(e, 0.0, 1 / 60)
    return e, pygame.surfarray.array3d(s).astype(int)


def test_the_logo_is_on_the_waiting_screen_and_can_be_turned_off():
    e, on = _waiting({})
    _, off = _waiting({"motion.logo_waiting": False})
    g = e.geom
    y = int(g.cy + g.R * 0.62)
    x0, x1 = int(g.cx - g.R * 0.3), int(g.cx + g.R * 0.3)
    assert on[x0:x1, y - 50:y + 50].mean() > off[x0:x1, y - 50:y + 50].mean() + 3


def test_the_result_logo_is_white_with_nothing_around_it():
    m = motion()
    c = pygame.Surface((400, 400))
    m.draw_result_logo(c, 1.0)
    a = pygame.surfarray.array3d(c)
    assert a.max() >= 250 and (a[:, :, 0] == a[:, :, 2]).all()
    lit = np.argwhere(a[:, :, 0] > 0)
    assert 200 - 80 <= lit[:, 0].min() and lit[:, 0].max() <= 200 + 80 and lit[:, 1].max() < 130  # at the top, and small


def test_player_names_stand_on_a_backing_on_the_waiting_screen():
    names = ("علی", "سارا")
    e, s = _waiting({}, names)
    _, bare = _waiting({"match.title_backing": 0.0}, names)
    g = e.geom
    x, y = int(g.cx + g.goal_dir[0][0] * g.R * 0.5), int(g.cy)
    # just outside the letters, where the visuals would otherwise show
    assert s[x - 70:x + 70, y + 26:y + 40].mean() < bare[x - 70:x + 70, y + 26:y + 40].mean()


def test_old_settings_get_the_longer_result_and_someones_own_values_stay():
    from market_hockey.config.store import MIGRATIONS
    out = MIGRATIONS[10]({"match.result_s": 6.0, "match.intro_s": 0.9})
    assert out["match.result_s"] == 10.0 and MIGRATIONS[11](out)["match.intro_s"] == 2.8
    out = MIGRATIONS[10]({"match.result_s": 20.0, "match.intro_s": 0.5})
    assert out["match.result_s"] == 20.0 and out["match.intro_s"] == 0.5


def test_a_team_in_a_limited_brand_color_floods_in_bands():
    m = motion(state="GOAL")
    m.teams = ((0, 167, 150), (226, 0, 47))
    m.cue_goal(1)
    assert next(a for a in m.actors if isinstance(a, Flood)).min_groove > 0.5
    m.cue_goal(0)
    assert [a for a in m.actors if isinstance(a, Flood)][-1].min_groove < 0.1
