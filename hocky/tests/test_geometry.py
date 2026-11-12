import math

from land_hockey.core.geometry import Arc, Geometry


def test_rim_segmentation_from_percentages(cfg):
    cfg.set("walls.top_percent", 10)
    g = Geometry(cfg)
    assert math.isclose(g.walls[0].span, 36.0)
    assert math.isclose(g.walls[1].span, 36.0)  # linked
    assert math.isclose(g.goals[0].span + g.goals[1].span + 72.0, 360.0)
    cfg.set("walls.link_sizes", False)
    cfg.set("walls.bottom_percent", 20)
    g = Geometry(cfg)
    assert math.isclose(g.walls[1].span, 72.0)


def test_wall_and_goal_membership(cfg):
    g = Geometry(cfg)
    assert g.in_wall(90) and g.in_wall(270)
    assert g.goal_of(180) == 0  # left = Player 1's goal
    assert g.goal_of(0) == 1 and g.goal_of(359.5) == 1 and g.goal_of(0.5) == 1  # wraparound
    assert g.goal_of(90) is None


def test_arc_wraparound():
    a = Arc(300, 120)
    assert a.contains(10) and a.contains(300) and a.contains(59.9) and not a.contains(200)
    assert math.isclose(a.unwrap(10), 370)


def test_u_mapping_player_view(cfg):
    g = Geometry(cfg)
    w = 130
    # P1 stands on the left facing the center: their left (u=0) is the TOP
    t0 = math.radians(g.u_to_theta(0, 0.0, w))
    t1 = math.radians(g.u_to_theta(0, 1.0, w))
    assert math.sin(t0) > 0.5 and math.sin(t1) < -0.5
    # P2 stands on the right facing the center: their left (u=0) is the BOTTOM
    t0 = math.radians(g.u_to_theta(1, 0.0, w))
    t1 = math.radians(g.u_to_theta(1, 1.0, w))
    assert math.sin(t0) < -0.5 and math.sin(t1) > 0.5
    for i in (0, 1):
        for u in (0.0, 0.3, 1.0):
            th = g.u_to_theta(i, u, w)
            assert math.isclose(g.angle_to_u(i, th % 360, w), u, abs_tol=1e-6)


def test_paddle_range_respects_walls_and_size(cfg):
    g = Geometry(cfg)
    lo, hi = g.paddle_range(0, 130)
    lo2, hi2 = g.paddle_range(0, 250)
    assert lo2 > lo and hi2 < hi  # a bigger paddle has less room
    assert g.goals[0].start < lo and hi < g.goals[0].end


def test_layout_rotation_moves_everything(cfg):
    cfg.set("arena.layout_rotation_deg", 90)
    g = Geometry(cfg)
    assert g.goal_of(270) == 0 and g.goal_of(90) == 1
    assert g.in_wall(180)
