import math

from conftest import add_ball, playing, run

from market_hockey.core.entities import Orb
from market_hockey.powerups import registry
from market_hockey.powerups.base import PowerUpType


def _collect(engine, tid, owner=0, ball=None):
    b = ball or add_ball(engine, 0, 0, 500, 40, owner=owner)
    engine.types[tid].collect(engine, b, owner)
    return b


def test_all_ten_types_registered():
    ids = set(registry.all_types())
    assert {"expand", "shrink", "speed_up", "chaos", "double_ball", "trajectory_reveal", "slow_down", "dim_ball",
            "shield", "bull_market"} <= ids


def test_default_colors_follow_collector_rule(cfg):
    good = [t for t in registry.all_types() if cfg[f"powerups.types.{t}.class"] == "good"]
    assert "shrink" in good and "expand" in good and "speed_up" in good
    assert cfg["powerups.types.trajectory_reveal.class"] == "good"  # it now helps the collector
    on = [t for t in registry.all_types() if cfg[f"powerups.types.{t}.enabled"]]
    assert sorted(on) == sorted(["expand", "shrink", "speed_up", "chaos", "double_ball", "trajectory_reveal"])


def test_expand_mine_shrink_opponent(engine):
    playing(engine)
    _collect(engine, "expand", owner=0)
    _collect(engine, "shrink", owner=0)
    assert math.isclose(engine.effects.paddle_mult(0), engine.cfg["powerups.types.expand.multiplier"])
    assert math.isclose(engine.effects.paddle_mult(1), engine.cfg["powerups.types.shrink.multiplier"])
    run(engine, 1.0)
    assert engine.paddles[0].size_mult > 1.3 and engine.paddles[1].size_mult < 0.75


def test_effects_expire_and_restore(engine):
    playing(engine)
    engine.cfg.set("powerups.types.expand.duration_s", 0.5)
    _collect(engine, "expand", owner=1)
    run(engine, 1.5)
    assert engine.effects.paddle_mult(1) == 1.0
    assert abs(engine.paddles[1].size_mult - 1.0) < 0.02


def test_trajectory_reveal_helps_collector_by_default(engine):
    playing(engine)
    _collect(engine, "trajectory_reveal", owner=0)
    assert engine.effects.reveal_beneficiaries() == {0}
    engine.effects.clear()
    engine.cfg.set("powerups.types.trajectory_reveal.beneficiary", "opponent")
    _collect(engine, "trajectory_reveal", owner=0)
    assert engine.effects.reveal_beneficiaries() == {1}


def test_orb_hitbox_is_larger_than_the_drawn_orb(engine):
    playing(engine)
    r = engine.cfg["powerups.orb_radius"]
    o = Orb(95, "expand", "good", 0, 0, r + engine.cfg["ball.radius"] + 6, 9)  # just outside the drawn orb
    o.state = "idle"
    engine.orbs.append(o)
    engine.cfg.set("powerups.magnet.enabled", False)
    add_ball(engine, -60, 0, 500, 0, owner=0)
    ev = run(engine, 0.3)
    assert any(e["type"] == "powerup_collected" for e in ev)


def test_speed_effects_respect_limits_and_exclusivity(engine):
    playing(engine)
    engine.cfg.set("powerups.types.slow_down.enabled", True)
    b = _collect(engine, "speed_up", owner=0)
    assert engine.effects.ball_speed_mult(b.id) > 1.0
    engine.types["slow_down"].collect(engine, b, 0)  # opposite event replaces the active one
    assert engine.effects.ball_speed_mult(b.id) < 1.0
    assert len([e for e in engine.effects.effects if e.group == "ball_speed"]) == 1
    b.rally = 10000
    assert engine.ball_target_speed(b) <= engine.cfg["ball.max_speed"]


def test_double_ball_is_delayed_smaller_and_slower(engine):
    playing(engine)
    cfg = engine.cfg
    b = _collect(engine, "double_ball", owner=1)
    x0, y0 = b.x, b.y
    assert len(engine.live_balls()) == 1 and engine.pending_spawns  # not yet
    run(engine, cfg["powerups.types.double_ball.spawn_delay_s"] + 0.02)
    live = engine.live_balls()
    assert len(live) == 2
    first, second = live
    assert second.owner == 1 and second.id != first.id
    assert math.isclose(second.r, first.r * cfg["powerups.types.double_ball.radius_scale"], rel_tol=1e-6)
    assert math.hypot(second.vx, second.vy) < 0.7 * math.hypot(first.vx, first.vy)  # slow start
    assert math.hypot(second.x - x0, second.y - y0) < 30  # appears where the orb was collected
    assert math.hypot(first.x - second.x, first.y - second.y) > 150  # big gap between the two balls
    second.owner = 0
    assert first.owner == 1
    run(engine, cfg["powerups.types.double_ball.slow_s"] + 1.0)
    if not second.scored:
        assert engine.effects.ball_speed_mult(second.id) == 1.0  # slow start wore off


def test_double_ball_instant_mode(engine):
    playing(engine)
    engine.cfg.set("powerups.types.double_ball.mode", "instant")
    _collect(engine, "double_ball", owner=1)
    assert len(engine.live_balls()) == 2


def test_max_balls_respected(engine):
    playing(engine)
    b = add_ball(engine, 0, 0, 500, 0, owner=0)
    for _ in range(5):
        engine.split_ball(b, 3, 20, 10)
    assert len(engine.live_balls()) <= engine.cfg["physics.max_balls"]


def test_chaos_instant_keeps_heading_to_opponent(engine):
    playing(engine)
    for _ in range(30):
        b = add_ball(engine, 0, 0, 600, 0, owner=0)
        engine.chaos_deflect(b, 0, 20, 55)
        assert b.vx > 0  # still toward P2's side
        engine.balls.clear()


def test_chaos_sequence_pauses_announces_and_fires_twice(engine):
    playing(engine)
    cfg = engine.cfg
    p = "powerups.types.chaos"
    b = add_ball(engine, -200, 0, 500, 30, owner=0)
    engine.types["chaos"].collect(engine, b, 0)
    assert engine.chaos_paused(b) and b.vx == 0 and b.vy == 0
    t_before = engine.time_left
    ev = run(engine, cfg[f"{p}.intro_s"] * 0.5)
    assert (b.x, b.y) == (-200, 0) and engine.time_left == t_before  # hovering; match timer paused
    ev += run(engine, cfg[f"{p}.intro_s"] * 0.5 + cfg[f"{p}.select_s"] + 0.02)
    kinds = [e["type"] for e in ev]
    assert kinds.index("chaos_select") < kinds.index("chaos_fire")
    assert b.vx > 0  # fired toward the opponent (P2)
    ev = run(engine, cfg[f"{p}.reroll_delay_s"] + cfg[f"{p}.reroll_select_s"] + 0.1)
    rerolls = [e for e in ev if e["type"] == "chaos_select" and e["reroll"]]
    fires = [e for e in ev if e["type"] == "chaos_fire"]
    assert rerolls and fires and fires[-1]["roll"] == 2
    run(engine, 0.3)
    assert b.chaos is None and b.vx > 0


def test_chaos_no_second_change_near_the_player(engine):
    playing(engine)
    cfg = engine.cfg
    p = "powerups.types.chaos"
    ax, ay = engine.paddle_shape(1).apex()
    b = add_ball(engine, ax - 220, ay, 500, 0, owner=0)  # already close to P2
    engine.types["chaos"].collect(engine, b, 0)
    ev = run(engine, cfg[f"{p}.intro_s"] + cfg[f"{p}.select_s"] + cfg[f"{p}.reroll_delay_s"] + 0.2)
    assert not [e for e in ev if e["type"] == "chaos_select" and e["reroll"]]
    assert b.chaos is None


def test_unowned_ball_does_not_collect(engine):
    playing(engine)
    o = Orb(99, "expand", "good", 0, 60, 0, 9)
    o.state = "idle"
    engine.orbs.append(o)
    add_ball(engine, 0, 0, 500, 0, owner=None)
    ev = run(engine, 0.3)
    assert not any(e["type"] == "powerup_collected" for e in ev)
    assert any(e["type"] == "orb_touch_unowned" for e in ev)


def test_owned_ball_collects_and_last_toucher_gets_it(engine):
    playing(engine)
    o = Orb(98, "expand", "good", 0, 60, 0, 9)
    o.state = "idle"
    engine.orbs.append(o)
    add_ball(engine, 0, 0, 500, 0, owner=1)
    ev = run(engine, 0.3)
    got = [e for e in ev if e["type"] == "powerup_collected"]
    assert got and got[0]["collector"] == 1
    assert engine.effects.paddle_mult(1) > 1.0


def test_magnet_pulls_orb_toward_owned_ball(engine):
    playing(engine)
    engine.cfg.set("powerups.magnet.strength", 3000)
    o = Orb(97, "expand", "good", 0, 0, 0, 9)
    o.state = "idle"
    engine.orbs.append(o)
    b = add_ball(engine, 150, 0, 0.0, 0.0, owner=0)
    b.held = True  # keep still
    b.held = False
    b.vx = b.vy = 0.0
    for _ in range(60):
        engine._update_orbs(1 / 240)
    assert o.x > 2.0  # moved toward the ball
    assert math.hypot(o.x - o.hx, o.y - o.hy) <= engine.cfg["powerups.magnet.max_offset"] + 1e-6
    # a ball nobody has touched does not attract (default)
    o2 = Orb(96, "expand", "good", 1, 0, 100, 9)
    o2.state = "idle"
    engine.orbs = [o2]
    b.owner = None
    b.x, b.y = 120, 100
    for _ in range(60):
        engine._update_orbs(1 / 240)
    assert abs(o2.x) < 0.5


def test_disabled_types_never_spawn(engine):
    playing(engine)
    for tid in engine.types:
        engine.cfg.set(f"powerups.types.{tid}.enabled", tid == "shrink")
    engine.cfg.set("powerups.no_repeat", False)
    seen = set()
    for _ in range(40):
        o = engine._spawn_orb(phase=3)
        if o:
            seen.add(o.type_id)
        engine.orbs.clear()
        engine.type_cd.clear()
    assert seen == {"shrink"}


def test_spawn_positions_valid(engine):
    playing(engine)
    for layout in ("pentagon", "cross", "ring", "random"):
        engine.cfg.set("center_zone.layout", layout)
        engine._refresh_geometry()
        for _ in range(10):
            engine.orbs.clear()
            engine.type_cd.clear()
            o = engine._spawn_orb(phase=3)
            assert o is not None
            assert math.hypot(o.x, o.y) < engine.geom.wall_face - engine.cfg["powerups.orb_radius"]


def test_registry_accepts_new_type():
    @registry.register
    class Temp(PowerUpType):
        id = "_temp_test"
        name = "Temp"

        def collect(self, engine, ball, collector):
            return {}

    try:
        assert "_temp_test" in registry.all_types()
    finally:
        registry._TYPES.pop("_temp_test", None)


def test_shield_blocks_one_ball(engine):
    playing(engine)
    engine.cfg.set("powerups.types.shield.enabled", True)
    b0 = add_ball(engine, 0, 0, 0, 0, owner=0)
    engine.types["shield"].collect(engine, b0, 0)
    engine.balls.clear()
    g = engine.geom
    a = math.radians(g.goals[0].center + 40)
    engine.paddles[0].u = 0.0
    add_ball(engine, (g.R - 30) * math.cos(a), (g.R - 30) * math.sin(a), 600 * math.cos(a), 600 * math.sin(a), owner=1)
    ev = run(engine, 0.3)
    assert any(e["type"] == "shield_block" for e in ev)
    assert engine.scores == [0, 0]


def test_bull_market_doubles_next_goal(engine):
    playing(engine)
    engine.cfg.set("powerups.types.bull_market.enabled", True)
    b0 = add_ball(engine, 0, 0, 0, 0, owner=1)
    engine.types["bull_market"].collect(engine, b0, 1)
    engine.balls.clear()
    g = engine.geom
    a = math.radians(g.goals[0].center + 40)
    engine.paddles[0].u = 0.0
    add_ball(engine, (g.R - 12) * math.cos(a), (g.R - 12) * math.sin(a), 600 * math.cos(a), 600 * math.sin(a), owner=1)
    run(engine, 0.2)
    assert engine.scores == [0, 2]


def test_random_path_shot_cannot_be_sped_up(engine):
    playing(engine)
    cfg = engine.cfg
    p = "powerups.types.chaos"
    b = add_ball(engine, -200, 0, 500, 30, owner=0)
    engine.types["speed_up"].collect(engine, b, 0)  # already sped up before the random path
    assert engine.speed_mult(b) > 1.0
    engine.types["chaos"].collect(engine, b, 0)
    run(engine, cfg[f"{p}.intro_s"] + cfg[f"{p}.select_s"] + 0.02)
    assert b.calm and engine.speed_mult(b) == 1.0  # speed-up cancelled once the path is chosen
    engine.types["speed_up"].collect(engine, b, 0)
    assert engine.speed_mult(b) == 1.0  # and ignored until a player hits it
    sh = engine.paddle_shape(1)
    b.x, b.y = sh.apex()[0] + sh.fx * 40, sh.apex()[1] + sh.fy * 40
    b.vx, b.vy = -sh.fx * 500, -sh.fy * 500
    b.chaos = None
    run(engine, 0.3)
    assert not b.calm  # the paddle hit clears it
