import math

from conftest import add_ball, playing, run

from market_hockey.prediction.trajectory import predict


def test_prediction_does_not_mutate(engine):
    playing(engine)
    b = add_ball(engine, -100, 50, 700, 120, owner=0)
    before = (b.x, b.y, b.vx, b.vy, b.owner, b.hits)
    p_before = [(p.theta, p.size_mult) for p in engine.paddles]
    pr = predict(engine, b, 1)
    assert (b.x, b.y, b.vx, b.vy, b.owner, b.hits) == before
    assert [(p.theta, p.size_mult) for p in engine.paddles] == p_before
    assert pr.contact is not None and pr.out_dir is not None


def test_prediction_matches_real_contact(engine):
    playing(engine)
    sh = engine.paddle_shape(1)
    ax, ay = sh.apex()
    b = add_ball(engine, 0, 0, ax * 1.2, ay * 1.2 + 30, owner=0)
    pr = predict(engine, b, 1)
    assert pr.intercept
    ev = run(engine, 2.0)
    hits = [e for e in ev if e["type"] == "paddle_hit"]
    assert hits
    assert math.hypot(hits[0]["x"] - pr.contact[0], hits[0]["y"] - pr.contact[1]) < 3 * b.r


def test_hypothetical_bounce_when_paddle_elsewhere(engine):
    playing(engine)
    engine.paddles[1].u = 0.0
    engine._refresh_geometry()
    engine.paddles[1].theta = engine.geom.u_to_theta(1, 0.0, engine.paddle_width(1))
    b = add_ball(engine, 0, 0, 700, 200, owner=0)
    pr = predict(engine, b, 1)
    assert pr.contact is not None and not pr.intercept and pr.out_dir is not None
    assert pr.out_dir[0] < 0  # would bounce back toward P1
