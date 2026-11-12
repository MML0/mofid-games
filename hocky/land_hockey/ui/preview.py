"""Live mini-map of the arena layout (works without the game running)."""

from __future__ import annotations

import math

from ..core.collisions import PaddleShape
from ..core.geometry import Geometry, pp


def draw_preview(cv, cfg, size: int) -> list[str]:
    """Draw the layout on a Tk canvas. Returns warnings (e.g. HUD outside the safe area)."""
    cv.delete("all")
    g = Geometry(cfg)
    warnings = []
    s = size / (2 * max(g.mask_r, g.R) * 1.04)
    ox = oy = size / 2

    def P(x, y):
        return ox + x * s, oy - y * s

    def bbox(r, cx=0.0, cy=0.0):
        x, y = P(cx, cy)
        return (x - r * s, y - r * s, x + r * s, y + r * s)

    cv.create_rectangle(0, 0, size, size, fill="#000000", outline="")
    cv.create_oval(*bbox(g.mask_r), fill="#062A3A", outline="#3a5560")
    cv.create_oval(*bbox(g.R * 0.6), fill="", outline="#0c3a4c")
    a = math.radians(90 + g.rot)
    cv.create_line(*P(math.cos(a) * g.wall_face, math.sin(a) * g.wall_face),
                   *P(-math.cos(a) * g.wall_face, -math.sin(a) * g.wall_face), fill="#1F7A99", dash=(4, 4))
    for arc in g.goals:
        cv.create_arc(*bbox(g.R), start=arc.start, extent=arc.span, style="arc", outline=cfg["colors.goal"],
                      width=max(2, cfg["goals.line_width"] * s))
    for k, arc in enumerate(g.walls):
        cv.create_arc(*bbox(g.R - g.t / 2), start=arc.start, extent=arc.span, style="arc", outline=cfg["colors.wall"],
                      width=max(3, g.t * s))
        pct = g.top_percent if k == 0 else g.bottom_percent
        x, y = P(math.cos(math.radians(arc.center)) * (g.R + 2), math.sin(math.radians(arc.center)) * (g.R + 2))
        cv.create_text(x, y + (10 if k == 0 else -10), text=f"{pct:.1f}%", fill="#0B1F2A", font=("TkDefaultFont", 9, "bold"))
    for i in (0, 1):
        col = cfg[f"colors.p{i + 1}"]
        w = pp(cfg, i, "width")
        lo, hi = g.paddle_range(i, w)
        lo0, hi0 = g.paddle_range(i, 0)
        rb = g.paddle_back_radius(i)
        cv.create_arc(*bbox(rb), start=lo0, extent=hi0 - lo0, style="arc", outline=col, dash=(3, 3))
        for th, solid in ((lo, False), ((lo + hi) / 2, True), (hi, False)):
            sh = PaddleShape(th, rb, w, pp(cfg, i, "shape_ratio"))
            pts = []
            for x, y in sh.outline(16):
                pts += list(P(x, y))
            cv.create_polygon(*pts, fill=col if solid else "", outline=col, width=2 if solid else 1,
                              dash=() if solid else (2, 2))
    orb_r = cfg["powerups.orb_radius"]
    for x, y in g.slots:
        cv.create_oval(*bbox(orb_r, x, y), outline=cfg["colors.good"], width=1)
    sx, sy = P(*g.serve_pos)
    cv.create_line(sx - 6, sy, sx + 6, sy, fill="white")
    cv.create_line(sx, sy - 6, sx, sy + 6, fill="white")
    limit = g.R - cfg["hud.safe_margin"]

    def hud_box(cx, cy, w, h, label):
        corners = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx + w / 2, cy + h / 2)]
        bad = any(math.hypot(x, y) > limit for x, y in corners)
        x0, y0 = P(cx - w / 2, cy + h / 2)
        x1, y1 = P(cx + w / 2, cy - h / 2)
        cv.create_rectangle(x0, y0, x1, y1, outline="#F3716D" if bad else "#8FB3C0", width=2 if bad else 1)
        cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label, fill="#E6F2F5", font=("TkDefaultFont", 9))
        if bad:
            warnings.append(f"{label} is outside the safe area")

    ts = cfg["hud.timer_size"]
    if cfg["match.timer_enabled"]:
        hud_box(*g.timer_pos, ts * 1.2, ts * 0.8, "timer")
    ss = cfg["hud.score_size"]
    for i in (0, 1):
        hud_box(*g.score_pos[i], ss * 0.65, ss * 0.8, f"P{i + 1}")
    return warnings
