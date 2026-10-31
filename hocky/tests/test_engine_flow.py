"""The match as a state machine: pause, reset, start modes, phases, names, serves, stalls, multi-ball."""

import math
import random

import pytest

from conftest import add_ball, advance_to_playing, playing, run
from market_hockey.config import Config
from market_hockey.core.engine import ATTRACT, COUNTDOWN, FINAL, GOAL, INTRO, PLAYING, RESULT, SERVE, Engine
from market_hockey.inputs.base import PlayerSample


def make(values=None, seed=3):
    return Engine(Config(values or {}), random.Random(seed))


def step(engine, seconds, inputs=None, presence=(True, True), dt=1 / 240):
    out = []
    for _ in range(int(seconds / dt)):
        engine.step(dt, inputs or {}, list(presence))
        out += engine.drain_events()
    return out


def test_states_run_in_order_for_a_real_match():
    e = make({"match.duration_s": 10, "match.score_limit_enabled": False, "match.attract_demo": False})
    seen = []
    e.start_match()
    for _ in range(int(40 / (1 / 240))):
        e.step(1 / 240, {}, [True, True])
        if not seen or seen[-1] != e.state:
            seen.append(e.state)
        if e.state == RESULT:
            break
    assert seen[0] == INTRO and COUNTDOWN in seen and PLAYING in seen and seen[-1] == RESULT and FINAL in seen
    assert seen.index(INTRO) < seen.index(COUNTDOWN) < seen.index(PLAYING) < seen.index(FINAL)


def test_pause_freezes_everything():
    e = make()
    advance_to_playing(e)
    snap = (e.time, e.time_left, e.balls[0].x, e.balls[0].y)
    e.toggle_pause()
    assert e.drain_events()[-1] == {"type": "pause", "paused": True, "t": e.time}
    step(e, 1.0)
    assert (e.time, e.time_left, e.balls[0].x, e.balls[0].y) == snap
    e.toggle_pause()
    step(e, 0.1)
    assert e.time > snap[0]


def test_reset_clears_the_match():
    e = make()
    advance_to_playing(e)
    e.scores = [3, 2]
    e.force_spawn("expand")
    e.reset_to_attract()
    assert e.state == ATTRACT and e.scores == [0, 0] and not e.orbs and not e.effects.effects


def test_a_new_match_starts_clean():
    e = make()
    advance_to_playing(e)
    e.scores = [3, 2]
    e.golden = True
    e.winner = 1
    e.start_match()
    assert e.scores == [0, 0] and not e.golden and e.winner is None and e.time_left == e.match_duration
    assert e.match_count == 2


def test_auto_start_needs_both_players_for_a_moment():
    e = make({"match.start_mode": "auto_when_both_present", "match.attract_demo": False})
    step(e, 3.0, presence=(True, False))
    assert e.state == ATTRACT
    step(e, 1.0, presence=(True, True))
    assert e.state == ATTRACT  # not yet: someone just walking past must not start a game
    step(e, 0.7, presence=(True, True))
    assert e.state != ATTRACT


def test_someone_leaving_resets_the_auto_start_wait():
    e = make({"match.start_mode": "auto_when_both_present", "match.attract_demo": False})
    step(e, 1.2)
    step(e, 0.1, presence=(False, True))
    step(e, 1.2)
    assert e.state == ATTRACT


def test_auto_loop_restarts_by_itself():
    e = make({"match.start_mode": "auto_loop", "match.auto_loop_delay_s": 1.0, "match.attract_demo": False})
    step(e, 1.1)
    assert e.state != ATTRACT


def test_operator_mode_waits_forever():
    e = make({"match.attract_demo": False})
    step(e, 30.0)
    assert e.state == ATTRACT and not e.balls


def test_attract_demo_plays_by_itself_without_scoring():
    e = make()
    events = step(e, 15.0)
    assert any(ev["type"] == "serve" or ev["type"] == "paddle_hit" for ev in events)
    assert e.scores == [0, 0] and e.state == ATTRACT


def test_result_screen_returns_to_attract_unless_it_waits_for_the_operator():
    e = make({"match.result_wait_for_operator": False, "match.result_s": 1.0})
    e.state, e.state_t = RESULT, 0.0
    step(e, 1.5)
    assert e.state == ATTRACT
    e = make({"match.result_wait_for_operator": True, "match.result_s": 1.0})
    e.state, e.state_t = RESULT, 0.0
    step(e, 5.0)
    assert e.state == RESULT


# ---------------------------------------------------------------- phases
def test_phases_advance_with_the_clock_and_the_last_one_has_no_spawns():
    e = make()
    e.match_duration = 100.0
    marks = [(e.cfg["phases.warmup_end"], 0), (e.cfg["phases.early_end"], 1), (e.cfg["phases.mid_end"], 2),
             (e.cfg["phases.peak_end"], 3)]
    for end, phase in marks:
        e.play_elapsed = end * 100 - 0.01
        assert e.phase_index() == phase
    e.play_elapsed = 99.9
    assert e.phase_index() == 4


def test_phases_off_means_steady_mid_game():
    assert make({"phases.enabled": False}).phase_index() == 2


def test_no_timer_never_reaches_the_final_phase():
    e = make({"match.timer_enabled": False})
    e.play_elapsed = 1e6
    assert e.phase_index() == 3


# ---------------------------------------------------------------- names
def test_names_are_cleaned_and_limited():
    e = make()
    e.set_names("  سارا\n", "x" * 100)
    assert e.names == ["سارا", "x" * 24]
    e.set_name(1, "Ali")
    assert e.names == ["سارا", "Ali"]
    e.set_names(None, 5)
    assert e.names == ["", "5"]


def test_zero_width_joiner_in_names_is_kept():
    e = make()
    e.set_names("علی‌رضا", "")
    assert "‌" in e.names[0]


def test_display_name_falls_back_to_the_label():
    e = make()
    assert e.display_name(0) == e.cfg["text.player_1"]
    e.set_name(0, "سارا")
    assert e.display_name(0) == "سارا"


# ---------------------------------------------------------------- serves
@pytest.mark.parametrize("first,receiver", [("p1", 0), ("p2", 1)])
def test_first_serve_setting(first, receiver):
    e = make({"serve.first": first})
    advance_to_playing(e)
    b = e.live_balls()[0]
    assert e.heading_to(b) == receiver


def test_alternate_first_serve_switches_each_match():
    e = make({"serve.first": "alternate"})
    got = []
    for _ in range(4):
        e.start_match()
        advance_to_playing(e)
        got.append(e.heading_to(e.live_balls()[0]))
    assert got[0] != got[1] and got[1] != got[2] and got[2] != got[3]


def score_on(e, side):
    b = e.live_balls()[0]
    a = math.radians(e.geom.goals[side].center)
    b.x, b.y = (e.geom.R - 3) * math.cos(a), (e.geom.R - 3) * math.sin(a)
    b.vx, b.vy = 900 * math.cos(a), 900 * math.sin(a)


@pytest.mark.parametrize("mode", ["toward_conceder", "toward_scorer", "random", "alternate"])
def test_every_serve_after_goal_mode_restarts_play(mode):
    e = make({"serve.after_goal": mode, "match.score_limit": 99})
    advance_to_playing(e)
    score_on(e, 0)
    step(e, 0.2)
    assert e.scores == [0, 1] and e.state in (GOAL, SERVE)
    for _ in range(int(10 / (1 / 240))):
        e.step(1 / 240, {}, [True, True])
        if e.state == PLAYING:
            break
    assert e.state == PLAYING and e.live_balls()
    b = e.live_balls()[0]
    if mode == "toward_conceder":
        assert e.heading_to(b) == 0
    elif mode == "toward_scorer":
        assert e.heading_to(b) == 1


def test_multiball_continue_keeps_playing_after_a_goal():
    e = make({"scoring.multiball_policy": "continue", "match.score_limit": 99})
    playing(e)
    add_ball(e, 0, 0, -e.geom.R * 4, 0, owner=1)
    add_ball(e, 50, 0, 10, 300, owner=1)
    a = math.radians(e.geom.goals[0].center)
    e.balls[0].x, e.balls[0].y = (e.geom.R - 3) * math.cos(a), (e.geom.R - 3) * math.sin(a)
    e.balls[0].vx, e.balls[0].vy = 900 * math.cos(a), 900 * math.sin(a)
    step(e, 0.05)
    assert e.scores[1] == 1 and e.state == PLAYING and e.live_balls()


def test_multiball_end_rally_stops_at_the_first_goal():
    e = make({"scoring.multiball_policy": "end_rally", "match.score_limit": 99})
    playing(e)
    add_ball(e, 0, 0, -e.geom.R * 4, 0, owner=1)
    add_ball(e, 50, 0, 10, 300, owner=1)
    a = math.radians(e.geom.goals[0].center)
    e.balls[0].x, e.balls[0].y = (e.geom.R - 3) * math.cos(a), (e.geom.R - 3) * math.sin(a)
    e.balls[0].vx, e.balls[0].vy = 900 * math.cos(a), 900 * math.sin(a)
    step(e, 0.05)
    assert e.scores[1] == 1 and e.state == GOAL


# ---------------------------------------------------------------- stalls and overlaps
def test_a_stalled_ball_is_steered_toward_a_goal():
    e = make({"physics.stall_action": "steer", "physics.stall_timeout_s": 1.0, "physics.stall_steer_deg_s": 180})
    playing(e)
    ax, ay = e.geom.axis
    b = add_ball(e, 0, 0, -ay * 300, ax * 300, owner=0)  # bouncing between the walls, never reaching a goal
    b.rally = 300
    step(e, 1.2)
    assert b.scored or abs(b.vx * ax + b.vy * ay) / math.hypot(b.vx, b.vy) > 0.3


def test_a_stalled_ball_can_be_reserved_instead():
    e = make({"physics.stall_action": "reserve", "physics.stall_timeout_s": 1.0})
    playing(e)
    ax, ay = e.geom.axis
    add_ball(e, 0, 0, -ay * 300, ax * 300, owner=0)
    events = step(e, 1.2)
    assert any(ev["type"] == "stall_reserve" for ev in events)


def test_balls_bounce_off_each_other():
    e = make({"physics.balls_collide": True})
    playing(e)
    a = add_ball(e, -60, 0, 300, 0, owner=0)
    b = add_ball(e, 60, 0, -300, 0, owner=1)
    events = step(e, 0.4)
    assert any(ev["type"] == "ball_ball" for ev in events)
    assert a.vx < 0 < b.vx


def test_balls_can_pass_through_each_other():
    e = make({"physics.balls_collide": False})
    playing(e)
    a = add_ball(e, -60, 0, 300, 0, owner=0)
    b = add_ball(e, 60, 0, -300, 0, owner=1)
    events = step(e, 0.4)
    assert not any(ev["type"] == "ball_ball" for ev in events)
    assert a.vx > 0 > b.vx


def test_debug_ball_needs_a_ball_to_split():
    e = make()
    playing(e)
    e.debug_spawn_ball()
    assert not e.balls
    add_ball(e, 0, 0, 300, 0)
    e.debug_spawn_ball()
    assert len(e.balls) == 2


def test_unknown_power_up_cannot_be_spawned():
    e = make()
    playing(e)
    assert e.force_spawn("no_such_type") is False
    assert not e.orbs


def test_no_input_keeps_paddles_where_they_are():
    e = make()
    playing(e)
    before = [p.theta for p in e.paddles]
    step(e, 0.5)
    assert [p.theta for p in e.paddles] == pytest.approx(before)


def test_holding_a_position_when_u_is_none():
    e = make()
    playing(e)
    step(e, 0.2, inputs={0: PlayerSample(True, 0.9), 1: PlayerSample(True, 0.1)})
    held = [p.u for p in e.paddles]
    step(e, 0.2, inputs={0: PlayerSample(True, None), 1: PlayerSample(True, None)})
    assert [p.u for p in e.paddles] == pytest.approx(held)


def test_events_are_serializable_for_logging():
    import json

    e = make({"match.duration_s": 10})
    e.start_match()
    for ev in step(e, 20.0):
        json.dumps(ev, default=str)
        assert "type" in ev and "t" in ev


def test_engine_is_deterministic_for_a_seed():
    def play(seed):
        e = make(seed=seed)
        e.start_match()
        out = []
        for _ in range(int(10 / (1 / 240))):
            e.step(1 / 240, {}, [True, True])
        for b in e.balls:
            out.append((round(b.x, 6), round(b.y, 6)))
        return out, e.scores

    assert play(5) == play(5)
