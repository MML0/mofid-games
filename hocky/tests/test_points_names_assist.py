"""Win 4 / lose 1 / draw 2 points on the result screen, default player names, no golden goal in the shipped
settings, a stronger center logo, and the catch assist that only helps a paddle that is already close."""

import json
import math
import random

import pygame
import pytest

from conftest import add_ball, playing
from market_hockey.config import Config
from market_hockey.core.engine import Engine
from market_hockey.inputs.base import PlayerSample
from market_hockey.paths import ORBS_DIR
from market_hockey.render.renderer import result_sentence

ROOT = ORBS_DIR.parent.parent


def _finished(scores, names=("", ""), **values):
    engine = Engine(Config(values), random.Random(1))
    playing(engine)
    engine.set_names(*names)
    engine.scores = list(scores)
    engine._finish()
    return engine


# ---------------------------------------------------------------- points and the result sentence
def test_points_win_lose_draw():
    assert _finished([5, 3]).match_points() == [4, 1]
    assert _finished([0, 2]).match_points() == [1, 4]
    assert _finished([2, 2]).match_points() == [2, 2]


def test_match_end_event_carries_the_points():
    engine = _finished([1, 3])
    end = [e for e in engine.drain_events() if e["type"] == "match_end"][0]
    assert end["points"] == [1, 4] and end["winner"] == 1


def test_the_points_follow_the_settings():
    engine = _finished([4, 4], **{"match.points_draw": 3})
    assert engine.match_points() == [3, 3]
    assert "سه" in result_sentence(engine.cfg, engine)


def test_result_sentence_for_a_win_uses_names_or_the_default_names():
    engine = _finished([1, 3])
    assert result_sentence(engine.cfg, engine) == "بازیکن قرمز برنده شد و 4 امتیاز کسب کرد - بازیکن آبی 1 امتیاز کسب کرد"
    engine = _finished([6, 2], names=("سارا", "علی"))
    assert result_sentence(engine.cfg, engine) == "سارا برنده شد و 4 امتیاز کسب کرد - علی 1 امتیاز کسب کرد"


def test_result_sentence_for_a_draw():
    engine = _finished([2, 2])
    assert result_sentence(engine.cfg, engine) == "مساوی شدید و هر کدام دو امتیاز کسب کردید"


def test_default_names_are_blue_and_red_player():
    engine = Engine(Config(), random.Random(1))
    assert [engine.display_name(i) for i in (0, 1)] == ["بازیکن آبی", "بازیکن قرمز"]
    engine.set_names("سارا", "")
    assert [engine.display_name(i) for i in (0, 1)] == ["سارا", "بازیکن قرمز"]


# ---------------------------------------------------------------- golden goal off, draw back
def test_a_tie_at_the_buzzer_is_a_draw_with_the_shipped_settings():
    shipped = Config.load(ROOT / "config" / "settings.json")
    assert shipped["match.tie_rule"] == "draw"
    engine = Engine(shipped, random.Random(1))
    playing(engine)
    engine.scores = [2, 2]
    engine.time_left = 0.01
    engine._run_timer(0.05)
    assert engine.state == "FINAL" and engine.winner is None and not engine.golden


def test_shipped_settings_have_the_new_values():
    shipped = Config.load(ROOT / "config" / "settings.json")
    assert (shipped["match.points_win"], shipped["match.points_loss"], shipped["match.points_draw"]) == (4, 1, 2)
    assert shipped["text.player_1"] == "بازیکن آبی" and shipped["text.player_2"] == "بازیکن قرمز"
    assert shipped["motion.logo_play_opacity"] >= 0.35
    assert shipped["paddles.assist.enabled"]


def test_v15_settings_move_to_the_draw_and_the_new_defaults(tmp_path):
    path = tmp_path / "v15.json"
    path.write_text(json.dumps({"_meta": {"schema_version": 15},
                                "match": {"tie_rule": "golden_goal"},
                                "powerups": {"min_active_orbs": 2, "spawn_interval_min_s": 1.5,
                                             "spawn_interval_max_s": 3.0},
                                "motion": {"logo_play_opacity": 0.14},
                                "text": {"player_1": "بازیکن 1", "player_2": "تیم دوم"}}), encoding="utf-8")
    cfg = Config.load(path)
    assert cfg["match.tie_rule"] == "draw"
    assert cfg["powerups.min_active_orbs"] == 1
    assert (cfg["powerups.spawn_interval_min_s"], cfg["powerups.spawn_interval_max_s"]) == (3.5, 6.0)
    assert cfg["motion.logo_play_opacity"] == 0.4
    assert cfg["text.player_1"] == "بازیکن آبی"
    assert cfg["text.player_2"] == "تیم دوم"  # the operator's own label stays


# ---------------------------------------------------------------- catch assist
def _assist_case(offset_px, **values):
    """A ball 200 px before paddle 0's line, heading for the middle of its goal; the player stands offset_px away
    along the track. Returns how far (px along the arc) the paddle ends up from where the player stands."""
    engine = Engine(Config({"paddles.p1.width": 130, "paddles.p2.width": 130, **values}), random.Random(1))
    playing(engine)
    g = engine.geom
    p = engine.paddles[0]
    w = engine.paddle_width(0)
    rb = g.paddle_back_radius(0)
    lo, hi = g.paddle_range(0, w)
    mid = (lo + hi) / 2
    stand = mid + math.degrees(offset_px / rb)
    u = (stand - lo) / (hi - lo)
    gx, gy = g.goal_dir[0]
    line = rb - w * 0.25 - engine.cfg["ball.radius"]
    a = math.radians(mid)
    ax, ay = math.cos(a), math.sin(a)
    add_ball(engine, ax * (line - 200), ay * (line - 200), ax * 700, ay * 700)
    for _ in range(60):
        engine._update_paddles(1 / 60, {0: PlayerSample(u=u, instant=True), 1: PlayerSample(u=0.5)})
    return math.radians(p.theta - stand) * rb


def test_the_assist_pulls_a_close_paddle_toward_the_ball():
    moved = _assist_case(60)
    assert -60 < moved < -20  # toward the ball, but not all the way


def test_a_far_paddle_gets_no_help():
    assert abs(_assist_case(220)) < 0.5


def test_the_assist_can_be_switched_off_and_scaled():
    assert abs(_assist_case(60, **{"paddles.assist.enabled": False})) < 0.5
    assert abs(_assist_case(60, **{"paddles.assist.strength": 0.0})) < 0.5
    assert _assist_case(60, **{"paddles.assist.strength": 1.0}) < _assist_case(60)
    assert abs(_assist_case(60, **{"paddles.assist.reach_px": 40})) < 0.5


def test_no_assist_for_a_ball_going_away_or_on_the_waiting_screen():
    engine = Engine(Config(), random.Random(1))
    playing(engine)
    g = engine.geom
    lo, hi = g.paddle_range(0, engine.paddle_width(0))
    a = math.radians((lo + hi) / 2)
    add_ball(engine, math.cos(a) * 200, math.sin(a) * 200, -math.cos(a) * 700, -math.sin(a) * 700)
    assert engine._catch_assist(0, engine.paddles[0], engine.paddle_width(0)) == 0.0
    engine.state = "ATTRACT"
    engine.balls[0].vx, engine.balls[0].vy = -engine.balls[0].vx, -engine.balls[0].vy
    before = engine.paddles[0].theta
    engine._update_paddles(1 / 60, {0: PlayerSample(u=0.5, instant=True)})
    assert abs(engine.paddles[0].theta - before) < 1e-6


def _rally(offset_px, enabled=True):
    """Full physics: a ball from the middle straight at paddle 0's goal, the player standing still offset_px away.
    Returns (caught, the largest step the paddle took away from the ball's line while the ball was coming)."""
    engine = Engine(Config({"paddles.assist.enabled": enabled}), random.Random(1))
    playing(engine)
    g = engine.geom
    w = engine.paddle_width(0)
    rb = g.paddle_back_radius(0)
    lo, hi = g.paddle_range(0, w)
    mid = (lo + hi) / 2
    u = (mid + math.degrees(offset_px / rb) - lo) / (hi - lo)
    a = math.radians(mid)
    b = add_ball(engine, 0, 0, math.cos(a) * 650, math.sin(a) * 650, owner=1)
    away, prev = 0.0, None
    for k in range(240):
        engine.step(1 / 120, {0: PlayerSample(u=u, instant=True), 1: PlayerSample(u=0.5, instant=True)}, [True, True])
        dist = abs(math.radians(engine.paddles[0].theta - mid)) * rb
        coming = b.x * b.vx + b.y * b.vy > 0 and not b.scored
        if prev is not None and coming:
            away = max(away, dist - prev)
        prev = dist
        if b.scored or not coming:
            break
    return not b.scored, away


def test_a_close_still_player_catches_a_ball_they_would_miss():
    assert not _rally(100, enabled=False)[0]
    caught, away = _rally(100)
    assert caught and away <= 1e-6


def test_the_paddle_never_moves_away_from_the_coming_ball():
    for off in (20, 60, 100, 130, 160, 250):
        assert _rally(off)[1] <= 1e-6, off


def test_a_far_player_still_concedes():
    assert not _rally(200)[0]


def test_the_drift_is_slow():
    engine = Engine(Config(), random.Random(1))
    playing(engine)
    g = engine.geom
    w = engine.paddle_width(0)
    rb = g.paddle_back_radius(0)
    lo, hi = g.paddle_range(0, w)
    mid = (lo + hi) / 2
    u = (mid + math.degrees(110 / rb) - lo) / (hi - lo)
    a = math.radians(mid)
    line = rb - 60
    add_ball(engine, math.cos(a) * line, math.sin(a) * line, math.cos(a) * 300, math.sin(a) * 300)
    start = None
    for _ in range(6):  # 0.1 s
        engine._update_paddles(1 / 60, {0: PlayerSample(u=u, instant=True)})
        start = start if start is not None else engine.paddles[0].theta
    moved = abs(math.radians(engine.paddles[0].theta - start)) * rb
    assert 0 < moved <= engine.cfg["paddles.assist.speed_px_s"] * 0.1 + 1


def test_no_help_when_the_paddle_already_covers_the_ball():
    assert abs(_assist_case(10)) < 0.5


# ---------------------------------------------------------------- the result screen draws
@pytest.fixture
def _pg():
    pygame.init()
    pygame.display.set_mode((64, 64))
    yield


def test_the_result_screen_draws_points_and_the_sentence(_pg):
    from market_hockey.render.renderer import Renderer

    for scores in ([3, 1], [2, 2]):
        engine = _finished(scores)
        rend = Renderer(engine.cfg, random.Random(2))
        engine.state = "RESULT"
        engine.state_t = 2.0
        rend.handle_events(engine.drain_events(), engine)
        frame = rend.render(engine, 0.5, 1 / 60)
        assert frame.get_width() > 0


def test_a_number_inside_persian_text_gets_room(_pg):
    from market_hockey.render.text import TextRenderer

    t = TextRenderer(Config())
    joined = t.render("علی1امتیاز", 40, (255, 255, 255)).get_width()
    spaced = t.render("علی 1 امتیاز", 40, (255, 255, 255)).get_width()
    assert spaced >= joined + 8
