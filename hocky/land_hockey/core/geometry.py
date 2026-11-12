"""Arena geometry (pure math, no pygame).

Arena frame: origin at the circle center, +x right, +y up, angles in degrees counter-clockwise from +x
(0° = right / P2 side, 90° = top, 180° = left / P1 side, 270° = bottom).
Canvas frame: screen = (cx + x, cy - y).

The rim is split into four arcs: P1 goal (left), P2 goal (right), top bumper wall, bottom bumper wall.
Each goal arc is traversed counter-clockwise from its *start*, which is the owning player's LEFT end
(P1 stands on the left facing the center, so their left is the top; P2's left is the bottom).
"""

from __future__ import annotations

import math

TAU = math.tau


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def wrap_pi(a: float) -> float:
    """Wrap radians to (-pi, pi]."""
    a = (a + math.pi) % TAU - math.pi
    return math.pi if a == -math.pi else a


def norm_deg(a: float) -> float:
    return a % 360.0


def pp(cfg, idx: int, key: str):
    """Per-player paddle setting, honoring paddles.link_players."""
    pid = "p1" if (idx == 0 or cfg["paddles.link_players"]) else "p2"
    return cfg[f"paddles.{pid}.{key}"]


class Arc:
    __slots__ = ("start", "span")

    def __init__(self, start: float, span: float):
        self.start = start
        self.span = span

    @property
    def end(self) -> float:
        return self.start + self.span

    @property
    def center(self) -> float:
        return self.start + self.span / 2

    def contains(self, ang: float, margin: float = 0.0) -> bool:
        return ((ang - self.start + margin) % 360.0) <= self.span + 2 * margin

    def unwrap(self, ang: float) -> float:
        """Angle expressed in [start, start+360)."""
        return self.start + ((ang - self.start) % 360.0)

    def __repr__(self):
        return f"Arc({self.start:.1f}, {self.span:.1f})"


class Geometry:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W = int(cfg["display.canvas_width"])
        self.H = int(cfg["display.canvas_height"])
        self.cx = self.W / 2 + cfg["arena.center_offset_x"]
        self.cy = self.H / 2 + cfg["arena.center_offset_y"]
        self.mask_r = float(cfg["arena.mask_radius"])
        self.R = float(min(cfg["arena.rim_radius"], self.mask_r))
        self.t = float(min(cfg["walls.thickness"], self.R * 0.2))
        self.wall_face = self.R - self.t
        self.rot = float(cfg["arena.layout_rotation_deg"])

        tp = float(cfg["walls.top_percent"])
        bp = tp if cfg["walls.link_sizes"] else float(cfg["walls.bottom_percent"])
        if tp + bp > 60.0:  # keep each goal arc at least 20% of the circle
            k = 60.0 / (tp + bp)
            tp, bp = tp * k, bp * k
        self.top_percent, self.bottom_percent = tp, bp
        tw, bw = tp * 3.6, bp * 3.6
        rot = self.rot
        self.walls = [Arc(90 + rot - tw / 2, tw), Arc(270 + rot - bw / 2, bw)]
        gspan = 180.0 - (tw + bw) / 2
        self.goals = [Arc(90 + rot + tw / 2, gspan), Arc(270 + rot + bw / 2, gspan)]

        self.cap_r = self.t / 2
        rc = self.R - self.t / 2
        self.caps = []
        for w in self.walls:
            for a in (w.start, w.end):
                ar = math.radians(a)
                self.caps.append((rc * math.cos(ar), rc * math.sin(ar)))

        ar = math.radians(rot)
        self.axis = (math.cos(ar), math.sin(ar))  # P1 -> P2
        self.goal_dir = [(-self.axis[0], -self.axis[1]), self.axis]  # direction toward each player's goal

        self.slots = self._slots()

        # HUD anchors (arena coords)
        def at(deg, r):
            a = math.radians(deg)
            return (r * math.cos(a), r * math.sin(a))

        self.timer_pos = at(90 + rot, self.wall_face - cfg["hud.timer_offset"])
        bx, by = at(270 + rot, self.wall_face - cfg["hud.score_offset"])
        spread = cfg["hud.score_spread"]
        ax, ay = self.axis
        self.score_pos = [(bx - ax * spread, by - ay * spread), (bx + ax * spread, by + ay * spread)]
        self.serve_pos = (float(cfg["serve.position_x"]), float(cfg["serve.position_y"]))

    # ---- coordinate helpers ----------------------------------------------------
    def to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return (self.cx + x, self.cy - y)

    def to_arena(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.cx, self.cy - sy)

    # ---- arcs ----------------------------------------------------------------
    def in_wall(self, ang: float) -> bool:
        return self.walls[0].contains(ang) or self.walls[1].contains(ang)

    def goal_of(self, ang: float) -> int | None:
        for i, g in enumerate(self.goals):
            if g.contains(ang):
                return i
        return None

    # ---- paddles ---------------------------------------------------------------
    def paddle_back_radius(self, idx: int) -> float:
        return max(self.R * 0.3, self.R - pp(self.cfg, idx, "rim_padding"))

    def paddle_range(self, idx: int, width: float) -> tuple[float, float]:
        rb = self.paddle_back_radius(idx)
        half = math.degrees(math.asin(clamp((width / 2) / rb, 0.0, 1.0)))
        margin = pp(self.cfg, idx, "end_margin_deg")
        g = self.goals[idx]
        lo, hi = g.start + margin + half, g.end - margin - half
        if lo > hi:
            lo = hi = g.center
        return lo, hi

    def u_to_theta(self, idx: int, u: float, width: float) -> float:
        lo, hi = self.paddle_range(idx, width)
        return lo + (hi - lo) * clamp(u, 0.0, 1.0)

    def angle_to_u(self, idx: int, ang: float, width: float) -> float:
        """Map any arena angle to this player's 0..1 range (clamped to the nearest end)."""
        lo, hi = self.paddle_range(idx, width)
        g = self.goals[idx]
        a = g.unwrap(ang)
        if a > g.start + 360.0 - (360.0 - g.span) / 2:  # closer to the start going backwards
            a -= 360.0
        if hi - lo < 1e-6:
            return 0.5
        return clamp((a - lo) / (hi - lo), 0.0, 1.0)

    # ---- center zone -------------------------------------------------------------
    def _slots(self) -> list[tuple[float, float]]:
        cfg = self.cfg
        layout = cfg["center_zone.layout"]
        r = float(cfg["center_zone.slot_radius"])
        base = float(cfg["center_zone.rotation_deg"]) + self.rot
        n = int(cfg["center_zone.slot_count"])
        pts = []
        if layout == "pentagon":
            pts = [self._polar(base + k * 72, r) for k in range(5)]
        elif layout == "cross":
            pts = [(0.0, 0.0)] + [self._polar(base + 45 + k * 90, r) for k in range(4)]
        elif layout == "ring":
            pts = [self._polar(base + k * 360 / n, r) for k in range(n)]
        else:  # random: deterministic golden-angle scatter inside the zone (positions jittered at spawn)
            zr = float(cfg["center_zone.zone_radius"])
            golden = 137.50776
            for k in range(n):
                rr = zr * math.sqrt((k + 0.5) / n)
                pts.append(self._polar(base + k * golden, rr))
        lim = self.wall_face - cfg["powerups.orb_radius"] - 4
        out = []
        for x, y in pts:
            d = math.hypot(x, y)
            if d > lim > 0:
                x, y = x * lim / d, y * lim / d
            out.append((x, y))
        return out

    @staticmethod
    def _polar(deg: float, r: float) -> tuple[float, float]:
        a = math.radians(deg)
        return (r * math.cos(a), r * math.sin(a))
