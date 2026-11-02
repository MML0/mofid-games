import math

from conftest import add_ball, playing, run


def _shoot_at_goal(engine, goal_idx, angle_offset=40.0):
    g = engine.geom
    arc = g.goals[goal_idx]
    a = math.radians(arc.center + angle_offset)
    # keep the paddle out of the way (far end of its range)
    engine.paddles[goal_idx].u = 0.0
    r = g.R - 12
    return add_ball(engine, r * math.cos(a), r * math.sin(a), 600 * math.cos(a), 600 * math.sin(a), owner=1 - goal_idx)


def test_left_goal_scores_for_p2(engine):
    playing(engine)
    _shoot_at_goal(engine, 0)
    ev = run(engine, 0.2)
    goals = [e for e in ev if e["type"] == "goal"]
    assert len(goals) == 1 and goals[0]["scorer"] == 1
    assert engine.scores == [0, 1]


def test_right_goal_scores_for_p1(engine):
    playing(engine)
    _shoot_at_goal(engine, 1)
    ev = run(engine, 0.2)
    assert [e["scorer"] for e in ev if e["type"] == "goal"] == [0]
    assert engine.scores == [1, 0]


def test_own_goal_counts_for_opponent(engine):
    playing(engine)
    b = _shoot_at_goal(engine, 0)
    b.owner = 0  # P1 touched it last and it goes into P1's own goal
    run(engine, 0.2)
    assert engine.scores == [0, 1]


def test_untouched_ball_still_scores(engine):
    playing(engine)
    b = _shoot_at_goal(engine, 1)
    b.owner = None
    run(engine, 0.2)
    assert engine.scores == [1, 0]


def test_serve_goes_toward_conceder(engine):
    for conceded in (0, 1):
        playing(engine)
        _shoot_at_goal(engine, conceded)
        ev = run(engine, engine.cfg["match.goal_pause_s"] + engine.cfg["serve.delay_s"] + 0.3)
        serves = [e for e in ev if e["type"] == "serve"]
        assert serves and serves[0]["receiver"] == conceded
        dx = serves[0]["dx"]
        assert (dx < 0) if conceded == 0 else (dx > 0)


def test_no_points_after_match_end(engine):
    playing(engine)
    engine._finish()
    _shoot_at_goal(engine, 0)
    run(engine, 0.3)
    assert engine.scores == [0, 0]


def test_score_limit_ends_match(engine):
    engine.cfg.set("match.score_limit", 2)
    playing(engine)
    for _ in range(2):
        _shoot_at_goal(engine, 0)
        run(engine, engine.cfg["match.goal_pause_s"] + 0.2)
        engine.balls = [b for b in engine.balls if b.held]
        if engine.state == "SERVE":
            engine.state = "PLAYING"
    assert engine.state in ("FINAL", "RESULT") and engine.winner == 1


def test_timer_ends_match_and_golden_goal(engine):
    playing(engine)
    engine.time_left = 0.05
    run(engine, 0.2)
    assert engine.state == "FINAL" and engine.winner is None
    engine.cfg.set("match.tie_rule", "golden_goal")
    playing(engine)
    engine.time_left = 0.05
    run(engine, 0.2)
    assert engine.golden and engine.state == "PLAYING"


def test_full_match_flow_reaches_result(engine):
    engine.cfg.set("match.duration_s", 10)
    engine.start_match()
    ev = run(engine, 45.0)
    states = [e["state"] for e in ev if e["type"] == "state"]
    for st in ("COUNTDOWN", "PLAYING", "FINAL", "RESULT"):
        assert st in states
    beats = [e["label"] for e in ev if e["type"] == "countdown_beat"]
    assert beats[:7] == ["ready", "5", "4", "3", "2", "1", "go"]


def test_names_clear_after_each_game(engine):
    engine.set_names("سارا", "Reza")
    playing(engine)
    engine._finish()
    assert engine.names == ["سارا", "Reza"]  # still shown on the result screen
    engine.reset_to_attract()
    assert engine.names == ["", ""]  # waiting for the next players
    # names typed during the result screen are kept for the next game
    playing(engine)
    engine._finish()
    engine.set_names("نگار", "Ali")
    engine.start_match()
    assert engine.names == ["نگار", "Ali"]
    # a game reset mid-match keeps the names
    engine.reset_to_attract()
    assert engine.names == ["نگار", "Ali"]
