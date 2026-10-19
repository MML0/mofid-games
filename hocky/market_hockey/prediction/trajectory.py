"""Trajectory prediction: where will a ball meet the receiver's paddle, and how will it bounce off?

Pure function on a *copy* of the ball. It reuses the engine's collision code and never mutates game state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core.collisions import PaddleShape, enforce_axis_ratio, paddle_contact, paddle_response, reflect_static_circle
from ..core.geometry import clamp


@dataclass
class Prediction:
    receiver: int
    points: list = field(default_factory=list)
    contact: tuple | None = None
    contact_angle: float | None = None
    contact_time: float | None = None
    out_dir: tuple | None = None
    intercept: bool = False  # the receiver's paddle, where it is now, would hit the ball
    goal: bool = False  # the ball reaches the goal line without meeting the paddle line
    strong: bool = True  # False = faint always-on aim assist


class _B:
    __slots__ = ("x", "y", "vx", "vy", "r")

    def __init__(self, x, y, vx, vy, r):
        self.x, self.y, self.vx, self.vy, self.r = x, y, vx, vy, r


def _unit(vx, vy):
    s = math.hypot(vx, vy)
    return (vx / s, vy / s) if s > 1e-9 else None


def predict(engine, ball, receiver: int, max_time: float | None = None, max_bounces: int | None = None,
            point_spacing: float = 6.0) -> Prediction:
    cfg = engine.cfg
    g = engine.geom
    max_time = cfg["prediction.max_time_s"] if max_time is None else max_time
    max_bounces = cfg["prediction.max_bounces"] if max_bounces is None else max_bounces
    pred = Prediction(receiver)
    b = _B(ball.x, ball.y, ball.vx, ball.vy, ball.r)
    speed = math.hypot(b.vx, b.vy)
    if speed < 1.0:
        return pred
    sh = engine.paddle_shape(receiver)
    hp = engine.hit_params(receiver)
    target = engine.ball_target_speed(ball)
    rb = sh.rb
    band = rb - sh.d - b.r
    arc = g.goals[receiver]
    lo, hi = g.paddle_range(receiver, sh.w)
    ratio = cfg["physics.min_axis_ratio"]
    step = clamp(0.4 * b.r / speed, 1 / 2000, 1 / 120)
    t = 0.0
    bounces = 0
    pts = [(b.x, b.y)]
    lastx, lasty = b.x, b.y
    band_hit = None
    while t < max_time:
        b.x += b.vx * step
        b.y += b.vy * step
        t += step
        hit = paddle_contact(b.x, b.y, b.r, sh)
        if hit:
            nx, ny, rx, ry, front = hit
            res = paddle_response(b.vx, b.vy, nx, ny, sh, 0.0, 0.0, hp, front, target)
            pts.append((b.x, b.y))
            pred.points = pts
            pred.contact = (b.x, b.y)
            pred.contact_angle = math.degrees(math.atan2(b.y, b.x))
            pred.contact_time = t
            pred.out_dir = _unit(res[0], res[1]) if res else None
            pred.intercept = True
            return pred
        d = math.hypot(b.x, b.y)
        bounced = False
        if d > g.wall_face - b.r:
            ang = math.degrees(math.atan2(b.y, b.x))
            if g.in_wall(ang):
                nx, ny = b.x / d, b.y / d
                vn = b.vx * nx + b.vy * ny
                if vn > 0:
                    b.vx -= 2 * vn * nx
                    b.vy -= 2 * vn * ny
                    enforce_axis_ratio(b, g.axis, ratio)
                    bounced = True
                lim = g.wall_face - b.r
                b.x, b.y = nx * lim, ny * lim
        for cx, cy in g.caps:
            if reflect_static_circle(b, cx, cy, g.cap_r):
                bounced = True
        if bounced:
            bounces += 1
            pts.append((b.x, b.y))
            lastx, lasty = b.x, b.y
            if bounces > max_bounces:
                break
        ang = math.degrees(math.atan2(b.y, b.x))
        if band_hit is None and d >= band and arc.contains(ang):
            band_hit = (b.x, b.y, b.vx, b.vy, t, ang)
        if band_hit is not None and d > rb + b.r:
            break  # passed the paddle line without the real paddle hitting it
        if d > g.R:
            pred.goal = True
            break
        if math.hypot(b.x - lastx, b.y - lasty) >= point_spacing:
            pts.append((b.x, b.y))
            lastx, lasty = b.x, b.y
    pred.points = pts
    if band_hit is not None:
        x, y, vx, vy, tt, ang = band_hit
        theta = clamp(arc.unwrap(ang), lo, hi)
        hsh = PaddleShape(theta, rb, sh.w, sh.d / max(1e-6, sh.hw))
        nx, ny = _unit(x - hsh.qx, y - hsh.qy) or (hsh.fx, hsh.fy)
        res = paddle_response(vx, vy, nx, ny, hsh, 0.0, 0.0, hp, True, target)
        if res is None:
            res = (-vx, -vy, 0.0)
        # trim the path to the contact point
        trimmed = []
        for px, py in pts:
            trimmed.append((px, py))
            if math.hypot(px, py) >= band:
                break
        trimmed.append((x, y))
        pred.points = trimmed
        pred.contact = (x, y)
        pred.contact_angle = ang
        pred.contact_time = tt
        pred.out_dir = _unit(res[0], res[1])
        pred.goal = False
    elif pred.goal:
        pred.contact = (b.x, b.y)
        pred.contact_angle = math.degrees(math.atan2(b.y, b.x))
        pred.contact_time = t
    return pred
