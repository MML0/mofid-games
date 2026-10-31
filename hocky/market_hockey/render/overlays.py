"""Debug (F3) and calibration (F2) overlays."""

from __future__ import annotations

import math

import pygame

_font = None


def _f(size=16):
    global _font
    try:
        if _font is not None and _font.get_height() == size:
            return _font
    except pygame.error:  # the font module was restarted since this font was made
        pass
    _font = pygame.font.Font(None, size + 4)
    return _font


def draw_debug(renderer, engine, surf, fps: float = 0.0, extra: list[str] | None = None) -> None:
    cfg = engine.cfg
    g = engine.geom
    to_c = renderer.to_c
    lines = [
        f"FPS {fps:5.1f}   physics {cfg['physics.hz']} Hz   state {engine.state}{' (paused)' if engine.paused else ''}",
        f"time {engine.time_left:5.1f}  phase {engine.phase_index()}  scores {engine.scores}  balls {len(engine.live_balls())}"
        f"  orbs {len(engine.orbs)}  particles {len(renderer.particles.items)}",
        "effects: " + (", ".join(f"{e.type_id}->{e.target[0]}{e.target[1] if len(e.target) > 1 else ''} {e.remaining:.1f}s"
                                for e in engine.effects.effects) or "-"),
        f"paddles: P1 u={engine.paddles[0].u:.2f} {'present' if engine.paddles[0].present else 'ABSENT'}   "
        f"P2 u={engine.paddles[1].u:.2f} {'present' if engine.paddles[1].present else 'ABSENT'}   text: {renderer.text.backend}",
    ]
    lines += extra or []
    f = _f(16)
    y = int(g.cy - g.R * 0.62)
    for ln in lines:
        s = f.render(ln, True, (230, 240, 240))
        bg = pygame.Surface((s.get_width() + 8, s.get_height() + 2), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        x = int(g.cx - s.get_width() / 2)
        surf.blit(bg, (x - 4, y - 1))
        surf.blit(s, (x, y))
        y += s.get_height() + 2
    if cfg["debug.colliders"]:
        for i in (0, 1):
            sh = engine.paddle_shape(i)
            qx, qy = to_c(sh.qx, sh.qy)
            pygame.draw.circle(surf, (255, 255, 0), (int(qx), int(qy)), int(sh.rho), 1)
            ax, ay = to_c(*sh.apex())
            pygame.draw.line(surf, (255, 255, 0), (ax, ay), (ax + sh.fx * 40, ay - sh.fy * 40), 1)
            pygame.draw.line(surf, (255, 80, 80), (ax, ay), (ax + sh.rx * 30, ay - sh.ry * 30), 1)
        for b in engine.live_balls():
            bx, by = to_c(b.x, b.y)
            pygame.draw.circle(surf, (0, 255, 0), (int(bx), int(by)), int(b.r), 1)
            pygame.draw.line(surf, (0, 255, 0), (bx, by), (bx + b.vx * 0.08, by - b.vy * 0.08), 1)
        for cx, cy in g.caps:
            px, py = to_c(cx, cy)
            pygame.draw.circle(surf, (255, 0, 255), (int(px), int(py)), int(g.cap_r), 1)
        pygame.draw.circle(surf, (0, 200, 255), (int(g.cx), int(g.cy)), int(g.wall_face), 1)


def draw_calibration(renderer, engine, surf) -> None:
    g = engine.geom
    c = renderer.c
    cx, cy = int(g.cx), int(g.cy)
    white = (255, 255, 255)
    pygame.draw.circle(surf, white, (cx, cy), int(g.mask_r) - 1, 1)
    for k in range(1, 10):
        pygame.draw.circle(surf, (70, 90, 100), (cx, cy), int(g.mask_r * k / 10), 1)
    pygame.draw.line(surf, white, (cx - 30, cy), (cx + 30, cy), 1)
    pygame.draw.line(surf, white, (cx, cy - 30), (cx, cy + 30), 1)
    f = _f(15)
    for a in range(0, 360, 15):
        ar = math.radians(a)
        r0, r1 = g.mask_r - 18, g.mask_r - 2
        p0 = (cx + r0 * math.cos(ar), cy - r0 * math.sin(ar))
        p1 = (cx + r1 * math.cos(ar), cy - r1 * math.sin(ar))
        pygame.draw.line(surf, white, p0, p1, 2 if a % 90 == 0 else 1)
        t = f.render(str(a), True, (180, 200, 210))
        tp = (cx + (g.mask_r - 34) * math.cos(ar) - t.get_width() / 2, cy - (g.mask_r - 34) * math.sin(ar) - t.get_height() / 2)
        surf.blit(t, tp)
    for arc, col in ((g.walls[0], c["wall"]), (g.walls[1], c["wall"]), (g.goals[0], c["goal"]), (g.goals[1], c["goal"])):
        for a in (arc.start, arc.end):
            ar = math.radians(a)
            pygame.draw.line(surf, col, (cx + g.R * 0.75 * math.cos(ar), cy - g.R * 0.75 * math.sin(ar)),
                             (cx + g.R * math.cos(ar), cy - g.R * math.sin(ar)), 1)
    sw = [c["p1"], c["p1b"], c["p2"], c["p2b"], c["good"], c["bad"], c["neutral"], c["goal"], c["wall"], c["smart"]]
    w = 34
    x0 = cx - len(sw) * w // 2
    for k, col in enumerate(sw):
        pygame.draw.rect(surf, col, (x0 + k * w, cy + 60, w - 4, 24))
    t = f.render(f"mask r={g.mask_r:.0f}  rim R={g.R:.0f}  center=({g.cx:.0f},{g.cy:.0f})  rot={g.rot:.1f}", True, white)
    surf.blit(t, (cx - t.get_width() // 2, cy + 96))
