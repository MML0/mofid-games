"""Collision primitives (pure math). Used by the engine and by the trajectory predictor."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import clamp, wrap_pi


class PaddleShape:
    """A paddle is a circular cap: chord of width w (flat back toward the rim), dome of depth d toward the center.

    d = (w/2) * shape_ratio; shape_ratio = 1 is a true semicircle.
    """

    __slots__ = ("theta", "rb", "w", "hw", "d", "rho", "mx", "my", "fx", "fy", "rx", "ry", "qx", "qy",
                 "alpha", "cos_alpha", "af")

    def __init__(self, theta_deg: float, rb: float, w: float, ratio: float):
        t = math.radians(theta_deg)
        c, s = math.cos(t), math.sin(t)
        self.theta = theta_deg
        self.rb = rb
        self.w = w
        self.hw = hw = w / 2
        self.d = d = max(1.0, hw * clamp(ratio, 0.05, 1.0))
        self.rho = rho = (hw * hw + d * d) / (2 * d)
        self.mx, self.my = rb * c, rb * s
        self.fx, self.fy = -c, -s  # facing: toward the arena center
        self.rx, self.ry = self.fy, -self.fx  # the player's right hand
        self.qx = self.mx - self.fx * (rho - d)
        self.qy = self.my - self.fy * (rho - d)
        self.alpha = math.asin(clamp(hw / rho, 0.0, 1.0))
        self.cos_alpha = (rho - d) / rho
        self.af = math.atan2(self.fy, self.fx)

    def outline(self, n: int = 28, inset: float = 0.0) -> list[tuple[float, float]]:
        """Dome outline from the left chord end around to the right chord end (arena coords).

        inset > 0 returns the same arc pulled `inset` px toward the inside (for highlights)."""
        pts = []
        a0 = self.af + self.alpha  # left end (counter-clockwise side of facing = player's left)
        rr = max(1.0, self.rho - inset)
        for k in range(n + 1):
            a = a0 - 2 * self.alpha * k / n
            pts.append((self.qx + rr * math.cos(a), self.qy + rr * math.sin(a)))
        return pts

    def apex(self) -> tuple[float, float]:
        return (self.mx + self.fx * self.d, self.my + self.fy * self.d)


def paddle_contact(bx: float, by: float, r: float, sh: PaddleShape):
    """Return None or (nx, ny, resolved_x, resolved_y, front) for a ball of radius r centered at (bx, by)."""
    dx, dy = bx - sh.mx, by - sh.my
    a = dx * sh.fx + dy * sh.fy
    b = dx * sh.rx + dy * sh.ry
    if a > sh.d + r or a < -r or abs(b) > sh.hw + r:
        return None
    qx, qy = bx - sh.qx, by - sh.qy
    qd = math.hypot(qx, qy)
    inside = qd < sh.rho and a > 0
    arc = None
    if qd > 1e-9:
        ux, uy = qx / qd, qy / qd
        if ux * sh.fx + uy * sh.fy >= sh.cos_alpha:
            arc = (abs(qd - sh.rho), sh.qx + ux * sh.rho, sh.qy + uy * sh.rho, ux, uy)
    bc = clamp(b, -sh.hw, sh.hw)
    cx, cy = sh.mx + sh.rx * bc, sh.my + sh.ry * bc
    cdist = math.hypot(bx - cx, by - cy)
    if arc is not None and arc[0] <= cdist:
        dist, px, py, nx, ny = arc
        if not inside and dist >= r:
            return None
        front = True
    else:
        px, py = cx, cy
        if inside:
            nx, ny = -sh.fx, -sh.fy
        else:
            if cdist >= r:
                return None
            if cdist > 1e-9:
                nx, ny = (bx - cx) / cdist, (by - cy) / cdist
            else:
                nx, ny = -sh.fx, -sh.fy
        front = (nx * sh.fx + ny * sh.fy) > -0.2
    return nx, ny, px + nx * (r + 0.25), py + ny * (r + 0.25), front


@dataclass
class HitParams:
    restitution: float = 1.0
    transfer: float = 0.35
    blend: float = 0.4
    max_aim: float = math.radians(60)
    max_out: float = math.radians(72)
    allow_backward: bool = False
    hit_gain: float = 1.0
    to_ball: float = 0.25
    min_forward: float = 0.15
    fwd_x: float = 1.0
    fwd_y: float = 0.0
    vmin: float = 300.0
    vmax: float = 1500.0
    tip_limit: float | None = None  # rounded tips: extra radians allowed beyond the dome's edge angle (None = off)


def contact_offset(nx: float, ny: float, sh: PaddleShape) -> float:
    """Signed hit position on the dome: -1 = player's left tip, 0 = center, +1 = player's right tip."""
    return clamp(math.atan2(nx * sh.rx + ny * sh.ry, nx * sh.fx + ny * sh.fy) / max(1e-6, sh.alpha), -1.0, 1.0)


def paddle_response(vx, vy, nx, ny, sh: PaddleShape, vpx, vpy, hp: HitParams, front: bool, target_speed: float):
    """Velocity after hitting a (kinematic) paddle. Returns None when the ball is already separating."""
    vn = (vx - vpx) * nx + (vy - vpy) * ny  # normal speed relative to the (moving) paddle surface
    if vn >= 0:
        return None
    if front and hp.tip_limit is not None:
        # a corner hit would otherwise use a sideways normal; treat the tip as the continuation of the dome
        beta = math.atan2(nx * sh.rx + ny * sh.ry, nx * sh.fx + ny * sh.fy)
        lim = sh.alpha + hp.tip_limit
        if abs(beta) > lim:
            b2 = math.copysign(lim, beta)
            cnx = sh.fx * math.cos(b2) + sh.rx * math.sin(b2)
            cny = sh.fy * math.cos(b2) + sh.ry * math.sin(b2)
            cvn = (vx - vpx) * cnx + (vy - vpy) * cny
            if cvn < 0:
                nx, ny, vn = cnx, cny, cvn
    e = hp.restitution
    ox = vx - (1 + e) * vn * nx
    oy = vy - (1 + e) * vn * ny
    # tangential drag: a sliding paddle pulls the ball along its motion (0 = frictionless, 1 = full grip)
    tx, ty = -ny, nx
    dvt = (vpx * tx + vpy * ty) - (ox * tx + oy * ty)
    ox += hp.transfer * dvt * tx
    oy += hp.transfer * dvt * ty
    ang = math.atan2(oy, ox) if (abs(ox) + abs(oy)) > 1e-9 else sh.af
    s = 0.0
    if front:
        s = contact_offset(nx, ny, sh)
        aim = sh.af - s * hp.max_aim  # rotate toward the player's right for positive s
        ang += hp.blend * wrap_pi(aim - ang)
        if not hp.allow_backward:
            rel = clamp(wrap_pi(ang - sh.af), -hp.max_out, hp.max_out)
            ang = sh.af + rel
        if hp.min_forward > -1.0:
            fwd = math.cos(ang) * hp.fwd_x + math.sin(ang) * hp.fwd_y
            if fwd < hp.min_forward:
                fa = math.atan2(hp.fwd_y, hp.fwd_x)
                lat = wrap_pi(ang - fa)
                off = math.acos(clamp(hp.min_forward, -1.0, 1.0))
                ang = fa + (off if lat >= 0 else -off)
    speed = clamp(target_speed * hp.hit_gain + math.hypot(vpx, vpy) * hp.to_ball, hp.vmin, hp.vmax)
    return math.cos(ang) * speed, math.sin(ang) * speed, s


def reflect_static_circle(ball, cx: float, cy: float, cr: float, e: float = 1.0) -> bool:
    """Bounce a ball off a fixed circle. Returns True if the velocity changed."""
    dx, dy = ball.x - cx, ball.y - cy
    dist = math.hypot(dx, dy)
    lim = ball.r + cr
    if dist >= lim or dist < 1e-9:
        return False
    nx, ny = dx / dist, dy / dist
    ball.x, ball.y = cx + nx * (lim + 0.1), cy + ny * (lim + 0.1)
    vn = ball.vx * nx + ball.vy * ny
    if vn < 0:
        ball.vx -= (1 + e) * vn * nx
        ball.vy -= (1 + e) * vn * ny
        return True
    return False


def segment_exit_point(ox, oy, x, y, R):
    """Point where the segment (o -> p) leaves the circle of radius R (o inside, p outside)."""
    dx, dy = x - ox, y - oy
    a = dx * dx + dy * dy
    if a < 1e-12:
        return x, y
    b = 2 * (ox * dx + oy * dy)
    c = ox * ox + oy * oy - R * R
    disc = max(0.0, b * b - 4 * a * c)
    t = clamp((-b + math.sqrt(disc)) / (2 * a), 0.0, 1.0)
    return ox + dx * t, oy + dy * t


def seg_point_dist(ax, ay, bx, by, px, py) -> float:
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / L, 0.0, 1.0)
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def enforce_axis_ratio(ball, axis, min_ratio: float, rng=None) -> bool:
    """Make sure the ball keeps moving sideways (toward a goal) at least `min_ratio` of its speed."""
    if min_ratio <= 0:
        return False
    sp = math.hypot(ball.vx, ball.vy)
    if sp < 1e-6:
        return False
    ax, ay = axis
    va = (ball.vx * ax + ball.vy * ay) / sp
    if abs(va) >= min_ratio:
        return False
    sign = 1.0 if va > 0 else -1.0 if va < 0 else (rng.choice((-1.0, 1.0)) if rng else 1.0)
    px, py = -ay, ax
    vp = (ball.vx * px + ball.vy * py) / sp
    psign = 1.0 if vp >= 0 else -1.0
    na = sign * min_ratio
    npp = psign * math.sqrt(max(0.0, 1 - min_ratio * min_ratio))
    ball.vx = (ax * na + px * npp) * sp
    ball.vy = (ay * na + py * npp) * sp
    return True
