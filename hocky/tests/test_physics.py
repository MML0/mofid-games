import math

from conftest import add_ball, playing, run

from market_hockey.core.collisions import HitParams, PaddleShape, paddle_contact, paddle_response


def _hit(theta, offset, ratio=1.0, blend=0.0, speed=500.0):
    sh = PaddleShape(theta, 484, 130, ratio)
    ax, ay = sh.apex()
    # start a ball in front of the dome, displaced toward the player's right by `offset` px, moving straight at it
    bx = ax + sh.fx * 40 + sh.rx * offset
    by = ay + sh.fy * 40 + sh.ry * offset
    vx, vy = -sh.fx * speed, -sh.fy * speed
    hp = HitParams(blend=blend, min_forward=-2, fwd_x=sh.fx, fwd_y=sh.fy)
    for _ in range(400):
        bx += vx / 600
        by += vy / 600
        c = paddle_contact(bx, by, 14, sh)
        if c:
            nx, ny, rx, ry, front = c
            res = paddle_response(vx, vy, nx, ny, sh, 0, 0, hp, front, speed)
            assert res is not None
            ox, oy, s = res
            return ox * sh.rx + oy * sh.ry, ox * sh.fx + oy * sh.fy, s
    raise AssertionError("no contact")


def test_hit_position_controls_direction_for_both_players():
    for theta in (180.0, 0.0):  # P1 and P2
        lat_c, fwd_c, _ = _hit(theta, 0)
        assert abs(lat_c) < 1e-6 * 500 + 1 and fwd_c > 0  # center hit returns straight
        lat_r, _, s_r = _hit(theta, 30)
        lat_l, _, s_l = _hit(theta, -30)
        assert lat_r > 50 and s_r > 0  # right side of the dome -> to the player's right
        assert lat_l < -50 and s_l < 0  # left side -> to the player's left


def test_deflection_grows_with_offset():
    lats = [_hit(180.0, off, blend=0.4)[0] for off in (0, 10, 20, 30, 40)]
    assert all(b > a for a, b in zip(lats, lats[1:]))


def test_outgoing_angle_is_clamped():
    sh = PaddleShape(180.0, 484, 130, 1.0)
    hp = HitParams(blend=0.0, max_out=math.radians(60), min_forward=-2, fwd_x=1, fwd_y=0)
    # a glancing hit near the tip
    nx, ny = math.cos(math.radians(-80)), math.sin(math.radians(-80))
    ox, oy, _ = paddle_response(-500, 0, nx, ny, sh, 0, 0, hp, True, 500)
    ang = math.degrees(math.atan2(oy, ox))
    assert abs(ang) <= 60.0 + 1e-6


def test_moving_paddle_adds_sideways_motion():
    sh = PaddleShape(180.0, 484, 130, 1.0)
    hp = HitParams(blend=0.0, transfer=0.5, min_forward=-2)
    still = paddle_response(-500, 0, 1, 0, sh, 0, 0, hp, True, 500)
    moving = paddle_response(-500, 0, 1, 0, sh, 0, -400, hp, True, 500)
    assert moving[1] < still[1] - 50


def test_wall_bounce_never_scores(engine):
    playing(engine)
    b = add_ball(engine, 0, 300, 0.0, 700.0, owner=0)
    ev = run(engine, 0.6)
    assert any(e["type"] == "wall_bounce" for e in ev)
    assert engine.scores == [0, 0]
    assert b.vy < 0  # came back down


def test_vertical_ping_pong_is_broken(engine):
    playing(engine)
    b = add_ball(engine, 0, 0, 0.0, 800.0)
    run(engine, 4.0)
    sp = math.hypot(b.vx, b.vy)
    assert b.scored or abs(b.vx) / sp >= engine.cfg["physics.min_axis_ratio"] - 1e-6


def test_no_tunnelling_at_max_speed(engine):
    playing(engine)
    cfg = engine.cfg
    p = engine.paddles[1]
    sh = engine.paddle_shape(1)
    ax, ay = sh.apex()
    vmax = cfg["ball.max_speed"]
    b = add_ball(engine, ax + sh.fx * 300, ay + sh.fy * 300, -sh.fx * vmax, -sh.fy * vmax, owner=0)
    b.rally = vmax
    ev = run(engine, 0.5)
    assert any(e["type"] == "paddle_hit" and e["player"] == 1 for e in ev)
    assert engine.scores == [0, 0]


def test_ball_never_left_inside_paddle(engine):
    playing(engine)
    for k in range(30):
        sh = engine.paddle_shape(0)
        b = add_ball(engine, sh.mx + sh.fx * 20, sh.my + sh.fy * 20, -600, (k - 15) * 30, owner=1)
        run(engine, 1 / 60)
        from market_hockey.core.collisions import paddle_contact
        c = paddle_contact(b.x, b.y, b.r - 1.0, engine.paddle_shape(0))
        assert c is None
        engine.balls.clear()


def test_speed_stays_bounded_after_many_hits(engine):
    playing(engine)
    cfg = engine.cfg
    b = add_ball(engine, 0, 0, 500, 0, owner=0)
    for _ in range(1000):
        engine._collide_paddle(b, 1, engine.paddle_shape(1), (0.0, 0.0))
        b.last_hit.clear()
        b.vx, b.vy = abs(b.vx) + 1, b.vy
        sh = engine.paddle_shape(1)
        b.x, b.y = sh.apex()[0] + sh.fx * 10, sh.apex()[1] + sh.fy * 10
    assert math.hypot(b.vx, b.vy) <= cfg["ball.max_speed"] + 1e-6
