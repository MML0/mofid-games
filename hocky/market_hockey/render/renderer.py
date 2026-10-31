"""Draws the engine state onto a logical canvas. Everything outside the circle is masked to pure black last.

Quality notes:
- the background is a dithered numpy gradient (no banding steps);
- static line art (goal arcs, walls, tracks) and the paddles are drawn supersampled and smoothed down;
- glows, trails and particles are soft radial sprites composited additively.
"""

from __future__ import annotations

import math
import random

import pygame

from ..core.geometry import pp
from .colors import boost, hex_rgb, mix, scale
from .glow import AddLayer, GlowCache, radial_background
from .icons import IconCache
from .particles import Particles
from .text import TextRenderer

STATIC_PREFIXES = ("display.canvas", "display.supersample", "arena.", "walls.", "goals.", "center_zone.", "colors.",
                   "paddles.", "powerups.orb_radius", "hud.", "fx.dither")
MASK_PREFIXES = ("display.canvas", "arena.mask", "arena.center")


def ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_out_elastic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


class Renderer:
    def __init__(self, cfg, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.text = TextRenderer(cfg)
        self.glow = GlowCache(4000, cfg["fx.dither_strength"] if cfg["fx.dither"] else 0.0)
        self.icons = IconCache()
        self.particles = Particles(self.rng)
        self._cfg_v = -1
        self._static_dirty_since = None
        self.size = None
        self.canvas = self.add = self.static = self.mask = self.dim = self.out = None
        self.c: dict = {}
        self.time = 0.0
        self.trails: dict[int, list] = {}
        self.trail_flash: dict[int, float] = {}
        self.dead_trails: dict[int, tuple] = {}
        self.rings: list[dict] = []
        self.toasts: list[dict] = []
        self.flights: list[dict] = []
        self.wall_hits: list[tuple] = []
        self.banners: list[dict] = []
        self.pending_marks: list[dict] = []
        self.score_pop = [-9.0, -9.0]
        self.goal_flash: tuple | None = None
        self.flash: tuple | None = None
        self.shake_until = 0.0
        self.ambient = []
        self._amb_scroll = 0.0
        self._amb_bias = (0.0, None, 0)
        self._sparkle_acc: dict[int, float] = {}
        self.debug_draw = None  # set by app: callable(renderer, engine, surface)
        self.supervisor_url = ""  # set by app: shown small on the waiting screen
        self._reserved: list[pygame.Rect] = []  # screen space already taken by text this frame

    # ====================================================================== setup
    def _colors(self) -> None:
        cfg = self.cfg
        b = cfg["colors.projection_boost"]
        g = lambda k: hex_rgb(cfg[f"colors.{k}"])  # noqa: E731
        c = {k: g(k) for k in ("p1", "p2", "neutral_ball", "ball_core", "good", "bad", "neutral", "smart",
                               "arena_inner", "arena_outer", "lines", "goal", "wall", "wall_hatch", "text",
                               "timer_final")}
        c["p1b"], c["p2b"] = boost(c["p1"], b), boost(c["p2"], b)
        c["team"] = [c["p1"], c["p2"]]
        c["teamb"] = [c["p1b"], c["p2b"]]
        c["core"] = [mix(c["p1b"], (255, 255, 255), 0.55), mix(c["p2b"], (255, 255, 255), 0.55)]
        c["class"] = {"good": c["good"], "bad": c["bad"], "neutral": c["neutral"]}
        c["wallb"] = boost(c["wall"], 0.2)
        self.c = c

    def _ensure(self, engine) -> None:
        cfg = self.cfg
        g = engine.geom
        changes = cfg.changes_since(self._cfg_v) if self._cfg_v >= 0 else {"*"}
        if not changes and self.canvas is not None and self._static_dirty_since is None:
            return
        self._cfg_v = cfg.version
        allc = "*" in changes
        size = (g.W, g.H)
        if allc or any(p.startswith("colors.") for p in changes):
            self._colors()
        if allc or any(p.startswith(("fonts.", "text.shaping")) for p in changes):
            self.text.clear()
        if allc or any(p.startswith("fx.dither") for p in changes):
            self.glow = GlowCache(4000, cfg["fx.dither_strength"] if cfg["fx.dither"] else 0.0)
        if self.canvas is None or size != self.size:
            self.size = size
            self.canvas = pygame.Surface(size)
            self.out = pygame.Surface(size)
            self.add = AddLayer(size)
            allc = True
        if allc or any(p.startswith(MASK_PREFIXES) for p in changes):
            self._build_mask(g)
        if allc or self.static is None:
            self._build_static(engine)
            self._static_dirty_since = None
        elif any(p.startswith(STATIC_PREFIXES) for p in changes) or self._static_dirty_since is not None:
            # throttle rebuilds while a slider is being dragged
            if self._static_dirty_since is None:
                self._static_dirty_since = self.time
            if self.time - self._static_dirty_since >= 0.12 or not changes:
                self._build_static(engine)
                self._static_dirty_since = None

    def to_c(self, x, y):
        g = self._g
        return (g.cx + x, g.cy - y)

    def _arc_pts(self, r, a0, a1, steps=None, k=1.0):
        g = self._g
        steps = steps or max(8, int(abs(a1 - a0) / (1.5 / k)))
        out = []
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            out.append(((g.cx + r * math.cos(a)) * k, (g.cy - r * math.sin(a)) * k))
        return out

    def _band(self, r_in, r_out, a0, a1, k=1.0):
        return self._arc_pts(r_out, a0, a1, k=k) + self._arc_pts(r_in, a1, a0, k=k)

    def _build_mask(self, g) -> None:
        W, H = g.W, g.H
        k = 2
        big = pygame.Surface((W * k, H * k), pygame.SRCALPHA)
        big.fill((0, 0, 0, 255))
        pygame.draw.circle(big, (0, 0, 0, 0), (int(g.cx * k), int(g.cy * k)), int(g.mask_r * k))
        mask = pygame.transform.smoothscale(big, (W, H))
        feather = self.cfg["arena.mask_feather"]
        if feather > 1.5:
            f = feather / 1.5
            small = pygame.transform.smoothscale(mask, (max(8, int(W / f)), max(8, int(H / f))))
            mask = pygame.transform.smoothscale(small, (W, H))
            hard = pygame.Surface((W, H), pygame.SRCALPHA)
            hard.fill((0, 0, 0, 255))
            pygame.draw.circle(hard, (0, 0, 0, 0), (int(g.cx), int(g.cy)), int(g.mask_r + feather + 1))
            mask.blit(hard, (0, 0))
        self.mask = mask.convert_alpha() if pygame.display.get_surface() else mask
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.circle(dim, (0, 0, 0, 255), (int(g.cx), int(g.cy)), int(g.mask_r))
        self.dim = dim

    # ---------------------------------------------------------------- static layer (supersampled)
    @staticmethod
    def _poly_a(dst, pts, color, alpha=1.0):
        """Alpha-blend a polygon onto a SRCALPHA surface (pygame.draw itself does not blend)."""
        if alpha <= 0 or len(pts) < 3:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2
        w, h = int(max(xs)) - x0 + 3, int(max(ys)) - y0 + 3
        tmp = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        tmp.fill((*color[:3], 0))
        pygame.draw.polygon(tmp, (*color[:3], 255), [(x - x0, y - y0) for x, y in pts])
        tmp.set_alpha(int(255 * min(1.0, alpha)))
        dst.blit(tmp, (x0, y0))

    @staticmethod
    def _circle_a(dst, color, center, r, alpha=1.0, width=0):
        if alpha <= 0 or r <= 0:
            return
        rr = int(r) + 3
        tmp = pygame.Surface((2 * rr, 2 * rr), pygame.SRCALPHA)
        tmp.fill((*color[:3], 0))
        pygame.draw.circle(tmp, (*color[:3], 255), (rr, rr), int(r), int(width))
        tmp.set_alpha(int(255 * min(1.0, alpha)))
        dst.blit(tmp, (int(center[0]) - rr, int(center[1]) - rr))

    def _build_static(self, engine) -> None:
        cfg = self.cfg
        g = engine.geom
        self._g = g
        c = self.c
        k = int(cfg["display.supersample"])
        dith = cfg["fx.dither_strength"] if cfg["fx.dither"] else 0.0
        S = radial_background(g.W, g.H, g.cx, g.cy, g.mask_r, c["arena_inner"], c["arena_outer"], dith)
        art = pygame.Surface((g.W * k, g.H * k), pygame.SRCALPHA)
        art.fill((*c["arena_outer"], 0))
        P = lambda x, y: ((g.cx + x) * k, (g.cy - y) * k)  # noqa: E731
        bg = c["arena_outer"]
        # center line (between the halves, from top wall to bottom wall)
        if cfg["arena.show_center_line"]:
            a = math.radians(90 + g.rot)
            dx, dy = math.cos(a), math.sin(a)
            L = g.wall_face - 8
            seg, gap = 16, 12
            t = -L
            while t < L:
                t2 = min(L, t + seg)
                p1, p2 = P(dx * t, dy * t), P(dx * t2, dy * t2)
                nx, ny = -dy * 1.0 * k, -dx * 1.0 * k
                self._poly_a(art, [(p1[0] + nx, p1[1] - ny), (p2[0] + nx, p2[1] - ny), (p2[0] - nx, p2[1] + ny),
                                   (p1[0] - nx, p1[1] + ny)], c["lines"], cfg["arena.center_line_alpha"])
                t = t2 + gap
        # paddle tracks: dotted arcs
        if cfg["arena.show_tracks"]:
            for i in (0, 1):
                lo, hi = g.paddle_range(i, 0)
                rb = g.paddle_back_radius(i)
                a = lo
                while a <= hi:
                    x, y = rb * math.cos(math.radians(a)), rb * math.sin(math.radians(a))
                    self._circle_a(art, c["teamb"][i], P(x, y), 1.6 * k, cfg["arena.track_alpha"] * 1.6)
                    a += 2.2
        # slot rings
        if cfg["center_zone.show_slot_rings"] and cfg["center_zone.layout"] != "random":
            rr = (cfg["powerups.orb_radius"] + 5) * k
            for x, y in g.slots:
                self._circle_a(art, c["lines"], P(x, y), rr, cfg["center_zone.slot_ring_alpha"] * 1.4, width=max(1, int(1.5 * k)))
        # rim line
        rim_w = cfg["arena.rim_line_width"]
        if rim_w > 0:
            self._poly_a(art, self._band(g.R - rim_w / 2, g.R + rim_w / 2, 0, 360, k), c["lines"], 0.75)
            if cfg["arena.rim_glow"] > 0:
                self._poly_a(art, self._band(g.R - rim_w * 2, g.R + rim_w * 2, 0, 360, k), c["lines"],
                             0.18 * cfg["arena.rim_glow"])
        # goal arcs: soft glow bands + crisp core
        lw = cfg["goals.line_width"]
        gl = cfg["goals.glow"]
        for arc in g.goals:
            if gl > 0:
                for wmul, a in ((7.0, 0.07), (4.0, 0.14), (2.2, 0.3)):
                    self._poly_a(art, self._band(g.R - lw * wmul / 2, g.R + lw * wmul / 2, arc.start, arc.end, k),
                                 c["goal"], a * gl)
            self._poly_a(art, self._band(g.R - lw / 2, g.R + lw / 2, arc.start, arc.end, k), c["goal"], 1.0)
            self._poly_a(art, self._band(g.R - lw * 0.15, g.R + lw * 0.15, arc.start, arc.end, k),
                         mix(c["goal"], (255, 255, 255), 0.5), 0.8)
        # bumper walls
        if cfg["walls.style"] == "energy":
            self._walls_energy_static(art, g, k)
        else:
            self._walls_classic_static(art, g, k)
        small = pygame.transform.smoothscale(art, (g.W, g.H)) if k > 1 else art
        S.blit(small, (0, 0))
        if cfg["walls.style"] == "energy" and cfg["walls.glow"] > 0:
            # soft static halo along each wall's inner face (glow stamps give naturally soft ends)
            for w in g.walls:
                a = w.start + 1.0
                while a <= w.end - 1.0:
                    ar = math.radians(a)
                    p = ((g.cx + g.wall_face * math.cos(ar)), (g.cy - g.wall_face * math.sin(ar)))
                    spr = self.glow.sprite(c["wall"], g.t * 2.2, 0.16 * cfg["walls.glow"])
                    S.blit(spr, (int(p[0] - spr.get_width() / 2), int(p[1] - spr.get_height() / 2)),
                           special_flags=pygame.BLEND_ADD)
                    a += 1.5
        self.static = S.convert() if pygame.display.get_surface() else S

    def _walls_energy_static(self, art, g, k) -> None:
        cfg = self.cfg
        c = self.c
        wc, base = c["wall"], mix(c["wall_hatch"], (0, 0, 0), 0.45)
        glow = cfg["walls.glow"]
        t = g.t
        face = g.wall_face
        for w in g.walls:
            a0, a1 = w.start, w.end
            # deep base
            self._poly_a(art, self._band(face, g.R, a0, a1, k), base, 0.92)
            # luminous gradient from the inner face outward
            n = 6
            for j in range(n):
                r0 = face + t * 0.7 * j / n
                self._poly_a(art, self._band(r0, face + t * 0.7, a0, a1, k), wc, 0.07 + 0.02 * j)
            # pattern: small diamonds riding inside the band
            if cfg["walls.hatch"]:
                mid = face + t * 0.55
                step = 5.0
                a = a0 + step
                while a < a1 - step * 0.6:
                    ar = math.radians(a)
                    cx, cy = mid * math.cos(ar), mid * math.sin(ar)
                    ux, uy = math.cos(ar), math.sin(ar)  # radial
                    vx, vy = -uy, ux  # tangential
                    s1, s2 = t * 0.24, t * 0.38
                    pts = [(cx + ux * s1, cy + uy * s1), (cx + vx * s2, cy + vy * s2), (cx - ux * s1, cy - uy * s1),
                           (cx - vx * s2, cy - vy * s2)]
                    self._poly_a(art, [((g.cx + x) * k, (g.cy - y) * k) for x, y in pts], wc, 0.28)
                    a += step
            # crisp inner face line + its glow, thin outer edge
            self._poly_a(art, self._band(face - 3.5, face + 3.5, a0, a1, k), wc, 0.30 * glow)
            self._poly_a(art, self._band(face - 1.4, face + 1.4, a0, a1, k), mix(wc, (255, 255, 255), 0.35), 1.0)
            self._poly_a(art, self._band(g.R - 1.0, g.R, a0, a1, k), wc, 0.45)
            # emitter nodes at both ends
            for a in (a0, a1):
                ar = math.radians(a)
                rc = g.R - t / 2
                p = ((g.cx + rc * math.cos(ar)) * k, (g.cy - rc * math.sin(ar)) * k)
                self._circle_a(art, base, p, t * 0.78 * k, 1.0)
                self._circle_a(art, wc, p, t * 0.78 * k, 0.9, width=max(1, int(1.6 * k)))
                self._circle_a(art, mix(wc, (255, 255, 255), 0.5), p, t * 0.3 * k, 1.0)

    def _walls_classic_static(self, art, g, k) -> None:
        cfg = self.cfg
        c = self.c
        for w in g.walls:
            self._poly_a(art, self._band(g.wall_face, g.R, w.start, w.end, k), c["wall"], cfg["walls.band_alpha"])
            for a in (w.start, w.end):
                ar = math.radians(a)
                rc = g.R - g.t / 2
                self._circle_a(art, c["wall"], ((g.cx + rc * math.cos(ar)) * k, (g.cy - rc * math.sin(ar)) * k),
                               g.t / 2 * k, cfg["walls.band_alpha"])
            if cfg["walls.hatch"]:
                a = w.start + 2.5
                while a < w.end - 1.2:
                    p1 = ((g.cx + (g.wall_face + 3) * math.cos(math.radians(a))) * k,
                          (g.cy - (g.wall_face + 3) * math.sin(math.radians(a))) * k)
                    a2 = math.radians(a + 2.75)
                    p2 = ((g.cx + (g.R - 3) * math.cos(a2)) * k, (g.cy - (g.R - 3) * math.sin(a2)) * k)
                    pygame.draw.line(art, (*c["wall_hatch"], 255), p1, p2, 3 * k)
                    a += 5.0

    # ====================================================================== events
    def handle_events(self, events, engine) -> None:
        if self.canvas is None:  # events can arrive before the first frame is drawn
            self._ensure(engine)
        cfg = self.cfg
        c = self.c
        g = engine.geom
        cap = cfg["fx.max_particles"]
        for e in events:
            et = e["type"]
            if et == "paddle_hit":
                col = c["teamb"][e["player"]]
                if e.get("owner_changed"):
                    self.trail_flash[e["ball_id"]] = self.time
                self.particles.burst(e["x"], e["y"], col, cfg["trails.sparks_on_hit"], (120, 380), (0.2, 0.5), cap=cap)
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.35, r0=8, r1=46, color=col, w=3))
                if e.get("smart"):
                    self.particles.burst(e["x"], e["y"], c["smart"], 40, (150, 520), (0.3, 0.8), cap=cap)
                    self.toast(cfg["text.smart_hit"], c["smart"], e["player"])
            elif et == "wall_bounce":
                if cfg["walls.hit_flash"] and e.get("wall", -1) >= 0:
                    self.wall_hits.append((e["wall"], math.degrees(math.atan2(e["y"], e["x"])), self.time))
                    self.wall_hits = self.wall_hits[-8:]
                if cfg["fx.wall_ripples"]:
                    self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.4, r0=6, r1=40,
                                           color=scale(c["wallb"], 0.8), w=2))
            elif et == "goal":
                sc = e["scorer"]
                col = c["teamb"][sc]
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.7, r0=10, r1=220, color=col, w=6))
                self.particles.burst(e["x"], e["y"], col, 26 if e.get("demo") else 70, (100, 520), (0.4, 1.1), cap=cap)
                if not e.get("demo"):
                    self.score_pop[sc] = self.time
                    self.goal_flash = (e["conceded"], self.time, e["angle"])
                    self.toast(cfg["text.goal"], col, None, size_mult=1.5)
                    self.shake_until = self.time + cfg["fx.shake_s"]
                    self._amb_bias = (1.0, col, 6)
            elif et == "countdown_beat":
                idx = e["index"]
                cols = [(255, 255, 255), c["p1b"], c["p2b"], c["p1b"], (255, 255, 255)]
                col = cols[min(idx, 4)]
                self.flash = (self.time, col, 1.0 if idx in (1, 2, 3) else 0.7)
                self.rings.append(dict(x=0, y=0, t0=self.time, dur=0.6, r0=20, r1=g.R * 0.9, color=col, w=5))
                self.particles.converge(g.R, col, cfg["countdown.particles"], cap=cap, life=cfg["countdown.beat_s"] * 0.8)
                if e["label"] == "go":
                    self.flash = (self.time, (255, 255, 255), 1.4)
                    self.particles.burst(0, 0, (255, 255, 255), 50, (200, 600), (0.3, 0.7), cap=cap)
            elif et == "serve":
                if not e.get("demo"):
                    self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.4, r0=10, r1=60,
                                           color=(255, 255, 255), w=3))
            elif et == "orb_spawned":
                col = c["class"].get(e["cls"], c["neutral"])
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.45, r0=6,
                                       r1=cfg["powerups.orb_radius"] * 2.2, color=boost(col, 0.2), w=3))
            elif et == "powerup_collected":
                self._on_collect(e, engine)
            elif et == "shield_block":
                self.particles.burst(e["x"], e["y"], c["good"], 50, (150, 450), (0.3, 0.9), cap=cap)
            elif et == "ball_split":
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.4, r0=4, r1=50,
                                       color=(255, 255, 255), w=3))
            elif et == "ball_expired":
                self.particles.burst(e["x"], e["y"], (200, 200, 200), 18, (60, 200), (0.2, 0.5), cap=cap)
            elif et == "chaos":
                self.particles.burst(e["x"], e["y"], c["neutral"], 30, (100, 300), (0.3, 0.7), cap=cap)
            elif et == "chaos_start":
                col = boost(c["neutral"], 0.35)
                dur = e["intro_s"] + e["select_s"] + 0.35
                ty, sy = self._banner_rows(g, e["x"], e["y"])
                self.banner(e["title"], col, dur, ty, 1.3)
                self.banner(e["subtitle"], mix(col, (255, 255, 255), 0.6), dur, sy, 0.72)
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.6, r0=10, r1=120, color=col, w=4))
                self.particles.burst(e["x"], e["y"], col, 40, (80, 300), (0.4, 0.9), cap=cap, twinkle=True)
                self.flash = (self.time, col, 0.5)
            elif et == "chaos_select" and e.get("reroll"):
                col = boost(c["neutral"], 0.35)
                if e.get("text"):
                    self.banner(e["text"], col, e["duration"] + 0.45, self._banner_rows(g, e["x"], e["y"])[0], 1.1)
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.4, r0=8, r1=70, color=col, w=3))
            elif et == "chaos_fire":
                col = boost(c["neutral"], 0.35)
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.35, r0=6, r1=55, color=(255, 255, 255), w=3))
                self.particles.burst(e["x"], e["y"], col, 34, (200, 620), (0.2, 0.5), cap=cap,
                                     direction=e["angle"], spread=0.22)
                self.particles.burst(e["x"], e["y"], (255, 255, 255), 12, (100, 300), (0.15, 0.35), cap=cap)
            elif et == "ball_pending":
                owner = e.get("owner")
                self.pending_marks.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=max(0.05, e["delay"]), r=e["r"],
                                               color=c["teamb"][owner] if owner is not None else c["neutral_ball"]))
            elif et == "golden_goal":
                self.toast(cfg["text.golden_goal"], c["smart"], None, size_mult=1.4)
            elif et == "match_end":
                self.flash = (self.time, (255, 255, 255), 0.8)
            elif et == "match_start":
                self.trails.clear()
                self.toasts.clear()
                self.banners.clear()
                self.pending_marks.clear()
            elif et == "state" and e["state"] in ("ATTRACT", "SERVE", "FINAL"):
                if e["state"] == "ATTRACT":
                    self.toasts.clear()
                self.banners.clear()
                self.pending_marks.clear()

    def _on_collect(self, e, engine) -> None:
        cfg = self.cfg
        c = self.c
        cap = cfg["fx.max_particles"]
        col_cls = c["class"].get(e["cls"], c["neutral"])
        col_team = c["teamb"][e["collector"]]
        self.particles.burst(e["x"], e["y"], col_cls, 30, (120, 360), (0.3, 0.8), cap=cap)
        self.particles.burst(e["x"], e["y"], col_team, 24, (80, 300), (0.3, 0.8), cap=cap)
        self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.5, r0=cfg["powerups.orb_radius"],
                               r1=cfg["powerups.orb_radius"] * 3, color=col_cls, w=4))
        t = engine.types.get(e["type_id"])
        self.flights.append(dict(t0=self.time, dur=0.5, x=e["x"], y=e["y"], affects=e.get("affects"),
                                 icon=t.icon if t else "", type_id=e["type_id"], color=col_cls))
        if engine.state == "ATTRACT" and not cfg["match.attract_toasts"]:
            return
        if e.get("toast_c"):
            self.toast(e["toast_c"], col_team, e["collector"], cls_color=col_cls)
        if e.get("toast_o"):
            self.toast(e["toast_o"], c["teamb"][1 - e["collector"]], 1 - e["collector"], cls_color=col_cls)

    @staticmethod
    def _banner_rows(g, x, y) -> tuple[float, float]:
        """Title/subtitle heights on the half of the arena away from the ball, so the text never hides it."""
        a = math.radians(90 + g.rot)
        ball_up = x * math.cos(a) + y * math.sin(a)
        return (0.34, 0.19) if ball_up < 0 else (-0.24, -0.39)

    def banner(self, text, color, dur, y_frac, size_mult=1.0) -> None:
        """A centered message at a fixed height (fraction of R above the center)."""
        if not text:
            return
        self.banners = [b for b in self.banners if abs(b["y"] - y_frac) > 0.02]  # replace what was on that line
        self.banners.append(dict(text=text, color=color, t0=self.time, dur=dur, y=y_frac,
                                 size=int(self.cfg["text.banner_size"] * size_mult)))

    def toast(self, text, color, side, size_mult=1.0, cls_color=None) -> None:
        cfg = self.cfg
        same = [t for t in self.toasts if t["side"] == side]
        if len(same) >= 2:
            self.toasts.remove(same[0])
        self.toasts.append(dict(text=text, color=color, side=side, t0=self.time, dur=cfg["text.toast_duration"],
                                size=int(cfg["text.toast_size"] * size_mult), cls_color=cls_color))

    # ====================================================================== render
    def render(self, engine, alpha: float, dt: float) -> pygame.Surface:
        self.time += dt
        self._reserved = []
        self._g = engine.geom
        self._ensure(engine)
        g = engine.geom
        self._g = g
        cfg = self.cfg
        C = self.canvas
        add = self.add
        add.begin()
        C.blit(self.static, (0, 0))
        st = engine.state
        self.particles.update(dt)

        if cfg["fx.ambient_chart"]:
            self._ambient(dt)
        self._draw_flash()
        self._walls_fx(engine)
        if st not in ("ATTRACT", "RESULT", "FINAL"):
            self._hud(engine)
        self._final_pulse(engine)
        self._goal_flash(engine)
        self._orbs(engine)
        self._predictions(engine)
        self._trails(engine, alpha, dt)
        self._shields(engine)
        self._paddles(engine, alpha)
        self._balls(engine, alpha)
        self._chaos(engine)
        self._pending_balls()
        self._rings()
        self.particles.draw(add, self.to_c, self.glow)
        add.composite(C)
        self._flights(engine)

        if st == "INTRO":
            self._intro(engine)
        if st == "ATTRACT":
            self._attract(engine)
        elif st == "COUNTDOWN":
            self._countdown(engine)
        elif st == "SERVE" and cfg["serve.show_telegraph"]:
            self._telegraph(engine)
        elif st in ("FINAL", "RESULT"):
            self._result(engine)
        self._toasts(engine)
        self._absent(engine)
        if engine.paused:
            self.dim.set_alpha(140)
            C.blit(self.dim, (0, 0))
            self._text_at(cfg["text.paused"], cfg["text.banner_size"] * 1.4, (255, 255, 255), 0, 0)
        if self.debug_draw:
            self.debug_draw(self, engine, C)

        target = C
        if self.time < self.shake_until and cfg["fx.shake_px"] > 0:
            k = (self.shake_until - self.time) / max(0.01, cfg["fx.shake_s"])
            ox = int(self.rng.uniform(-1, 1) * cfg["fx.shake_px"] * k)
            oy = int(self.rng.uniform(-1, 1) * cfg["fx.shake_px"] * k)
            self.out.fill((0, 0, 0))
            self.out.blit(C, (ox, oy))
            target = self.out
        target.blit(self.mask, (0, 0))
        return target

    # ---------------------------------------------------------------- background
    def _ambient(self, dt) -> None:
        g = self._g
        cfg = self.cfg
        R = g.R
        spacing = 30.0
        if not self.ambient:
            y = 0.0
            for _ in range(int(2 * R / spacing) + 3):
                y = max(-0.22 * R, min(0.22 * R, y + self.rng.gauss(0, 14)))
                self.ambient.append([y, None])
        self._amb_scroll += 22 * dt
        while self._amb_scroll >= spacing:
            self._amb_scroll -= spacing
            bias, col, n = self._amb_bias
            last = self.ambient[-1][0]
            step = self.rng.gauss(0, 14) + (bias * 22 if n > 0 else 0)
            self._amb_bias = (bias, col, n - 1) if n > 0 else (0.0, None, 0)
            self.ambient.pop(0)
            self.ambient.append([max(-0.25 * R, min(0.25 * R, last + step)), col if n > 0 else None])
        a = cfg["fx.ambient_alpha"]
        base = scale(self.c["lines"], a * 2.2)
        x0 = -R - spacing - self._amb_scroll
        pts = [(self.to_c(x0 + k * spacing, y), col) for k, (y, col) in enumerate(self.ambient)]
        for k in range(1, len(pts)):
            col = scale(pts[k][1], a * 2.5) if pts[k][1] else base
            self.add.mark(pygame.draw.aaline(self.add.surf, col, pts[k - 1][0], pts[k][0], 2))

    def _draw_flash(self) -> None:
        if not self.flash:
            return
        t0, col, inten = self.flash
        cfg = self.cfg
        k = 1 - (self.time - t0) / 0.35
        if k <= 0:
            self.flash = None
            return
        mx = cfg["fx.flash_max_alpha"] * (0.3 if cfg["fx.reduce_flashing"] else 1.0)
        a = min(0.6, mx * inten) * k * k
        g = self._g
        self.add.mark(pygame.draw.circle(self.add.surf, scale(col, a), (int(g.cx), int(g.cy)), int(g.mask_r)))

    def _walls_fx(self, engine) -> None:
        cfg = self.cfg
        if cfg["walls.style"] != "energy":
            return
        g = self._g
        c = self.c
        wc = c["wallb"]
        glow = cfg["walls.glow"]
        flow = cfg["walls.flow_speed"]
        n = cfg["walls.pulses"]
        face = g.wall_face
        t = g.t
        for wi, w in enumerate(g.walls):
            if flow > 0 and n > 0:
                for k in range(n):
                    ph = (self.time * flow / max(1.0, w.span) + k / n) % 1.0
                    fade = math.sin(math.pi * ph)
                    for a, inten in ((w.start + w.span * ph, 0.55), (w.end - w.span * ((ph + 0.5 / n) % 1.0), 0.28)):
                        ar = math.radians(a)
                        pos = self.to_c((face + 2) * math.cos(ar), (face + 2) * math.sin(ar))
                        self.add.blit(self.glow.sprite(wc, t * 1.7, inten * fade * glow), pos)
            for a in (w.start, w.end):
                ar = math.radians(a)
                rc = g.R - t / 2
                pulse = 0.4 + 0.25 * math.sin(self.time * 3.2 + a * 0.1)
                self.add.blit(self.glow.sprite(wc, t * 1.6, pulse * glow), self.to_c(rc * math.cos(ar), rc * math.sin(ar)))
        keep = []
        for wi, ang, t0 in self.wall_hits:
            age = self.time - t0
            if age > 0.7:
                continue
            keep.append((wi, ang, t0))
            w = g.walls[wi]
            k = 1 - age / 0.7
            if age < 0.25:
                ar = math.radians(ang)
                self.add.blit(self.glow.sprite(wc, t * 3.2, 1.3 * (1 - age / 0.25)),
                              self.to_c(face * math.cos(ar), face * math.sin(ar)))
            spread = 110 * age
            a0 = w.unwrap(ang)
            for side in (-1, 1):
                a = a0 + side * spread
                if w.start <= a <= w.end:
                    ar = math.radians(a)
                    self.add.blit(self.glow.sprite(wc, t * 2.0, 0.9 * k),
                                  self.to_c((face + 2) * math.cos(ar), (face + 2) * math.sin(ar)))
        self.wall_hits = keep

    def _final_pulse(self, engine) -> None:
        cfg = self.cfg
        if not cfg["fx.final_pulse"] or engine.state not in ("PLAYING", "SERVE") or not cfg["match.timer_enabled"]:
            return
        if engine.time_left > cfg["hud.final_seconds"] or engine.golden:
            return
        frac = engine.time_left - math.floor(engine.time_left)
        k = 0.25 * frac ** 2
        g = self._g
        self.add.mark(pygame.draw.aacircle(self.add.surf, scale(self.c["timer_final"], k), (int(g.cx), int(g.cy)),
                                           int(g.wall_face - 4), 10))

    def _goal_flash(self, engine) -> None:
        if not self.goal_flash:
            return
        idx, t0, ang = self.goal_flash
        t = self.time - t0
        dur = 1.0
        if t > dur:
            self.goal_flash = None
            return
        g = self._g
        arc = g.goals[idx]
        k = 1 - t / dur
        lw = self.cfg["goals.line_width"]
        col = self.c["goal"]
        a = arc.start
        while a <= arc.end:
            ar = math.radians(a)
            self.add.blit(self.glow.sprite(col, lw * 3.0, 0.45 * k), self.to_c(g.R * math.cos(ar), g.R * math.sin(ar)))
            a += 2.5
        a0 = arc.unwrap(ang)
        spread = arc.span * min(1.0, t / 0.5)
        for side in (-1, 1):
            a = a0 + side * spread
            if arc.start <= a <= arc.end:
                ar = math.radians(a)
                self.add.blit(self.glow.sprite(col, 44, 1.3 * k), self.to_c(g.R * math.cos(ar), g.R * math.sin(ar)))

    # ---------------------------------------------------------------- HUD
    def _rot(self, surf, extra=0.0):
        ang = self._g.rot + extra
        return pygame.transform.rotate(surf, ang) if abs(ang) > 0.01 else surf

    def _text_surface(self, text, size, color, key="persian", scale_k=1.0, extra_rot=0.0, outline=2, glow=0.0):
        s = self.text.render(text, size, color, key, outline=outline, outline_color=(0, 6, 10), glow=glow)
        if abs(scale_k - 1.0) > 0.01:
            s = pygame.transform.smoothscale(s, (max(1, int(s.get_width() * scale_k)),
                                                 max(1, int(s.get_height() * scale_k))))
        return self._rot(s, extra_rot)

    def _text_at(self, text, size, color, x, y, key="persian", alpha=1.0, scale_k=1.0, extra_rot=0.0, outline=2,
                 glow=0.0, reserve=False, avoid=False, axis=None, at=None):
        """Draw centered text. reserve=True marks its box as taken; avoid=True moves it to the nearest free spot.
        `at` = explicit screen position (skips the arena->screen conversion)."""
        s = self._text_surface(text, size, color, key, scale_k, extra_rot, outline, glow)
        cx, cy = at if at is not None else self.to_c(x, y)
        if avoid:
            cx, cy = self._free_spot(s.get_width(), s.get_height(), cx, cy, axis)
        if alpha < 0.999:
            s = s.copy()
            s.set_alpha(int(255 * max(0.0, alpha)))
        rect = s.get_rect(center=(int(cx), int(cy)))
        self.canvas.blit(s, rect.topleft)
        if reserve:
            self._reserve(rect)
        return rect

    def _reserve(self, rect) -> None:
        # the soft shadow/glow padding is generous; keep only the visible core of the text box
        r = pygame.Rect(rect)
        self._reserved.append(r.inflate(-int(r.w * 0.12), -int(r.h * 0.3)))

    def _fits(self, r: pygame.Rect, ignore=None) -> bool:
        g = self._g
        lim = g.R - self.cfg["hud.safe_margin"]
        core = r.inflate(-int(r.w * 0.12), -int(r.h * 0.3))
        for px, py in (core.topleft, core.topright, core.bottomleft, core.bottomright):
            if math.hypot(px - g.cx, py - g.cy) > lim:
                return False
        pad = core.inflate(10, 6)
        return not any(pad.colliderect(o) for o in self._reserved if o is not ignore)

    def _free_spot(self, w, h, cx, cy, axis=None):
        """Nearest position to (cx, cy) whose box fits inside the circle and overlaps no reserved text."""
        ax, ay = axis or (0.0, 1.0)
        px, py = -ay, ax
        step = max(12.0, h * 0.42)
        cands = [(0.0, 0.0)]
        for k in range(1, 10):
            for sgn in (1, -1):
                cands.append((ax * step * k * sgn, ay * step * k * sgn))
        for k in range(1, 6):
            for sgn in (1, -1):
                cands.append((px * step * 2 * k * sgn, py * step * 2 * k * sgn))
        for dx, dy in cands:
            r = pygame.Rect(0, 0, w, h)
            r.center = (int(cx + dx), int(cy + dy))
            if self._fits(r):
                return r.center
        return (cx, cy)

    def timer_text(self, engine) -> str:
        cfg = self.cfg
        if engine.golden:
            return "+"
        tl = engine.time_left
        if engine.state in ("INTRO", "COUNTDOWN"):
            tl = float(cfg["match.duration_s"])
        secs = int(math.ceil(max(0.0, tl) - 1e-6))
        fmt = cfg["hud.timer_format"]
        if fmt == "mm:ss" or (fmt == "auto" and secs >= 60):
            return f"{secs // 60}:{secs % 60:02d}"
        return str(secs)

    def _hud(self, engine) -> None:
        cfg = self.cfg
        g = self._g
        c = self.c
        ha = cfg["hud.alpha"]
        hg = cfg["hud.glow"]
        if cfg["match.timer_enabled"]:
            txt = self.timer_text(engine)
            col = c["text"]
            k = 1.0
            final = (engine.time_left <= cfg["hud.final_seconds"] and engine.state in ("PLAYING", "SERVE", "GOAL")
                     and not engine.golden)
            if final:
                col = c["timer_final"]
                frac = engine.time_left - math.floor(engine.time_left)
                k = 1.0 + 0.14 * frac ** 3 + (0.15 if engine.time_left <= 5 else 0)
            if engine.golden:
                col = c["smart"]
            self._text_at(txt, cfg["hud.timer_size"], col, *g.timer_pos, key="digits", alpha=ha, scale_k=k,
                          glow=hg * 0.6, reserve=True)
        for i in (0, 1):
            t = self.time - self.score_pop[i]
            k = 1.0 + (0.5 * math.sin(math.pi * t / 0.6) if 0 <= t < 0.6 else 0)
            self._text_at(str(engine.scores[i]), cfg["hud.score_size"], c["teamb"][i], *g.score_pos[i],
                          key="digits", alpha=ha, scale_k=k, glow=hg, reserve=True)
            name = engine.names[i] if cfg["hud.show_names"] else ""
            if name or cfg["hud.show_player_labels"]:
                x, y = g.score_pos[i]
                ux, uy = math.cos(math.radians(90 + g.rot)), math.sin(math.radians(90 + g.rot))
                off = cfg["hud.score_size"] * 0.56 + cfg["hud.name_size"] * 0.55
                self._text_at(name or cfg[f"text.player_{i + 1}"], cfg["hud.name_size"] if name else cfg["hud.label_size"],
                              c["teamb"][i], x + ux * off, y + uy * off, alpha=ha * 0.95, glow=0.3, reserve=True)

    # ---------------------------------------------------------------- orbs
    def _orbs(self, engine) -> None:
        cfg = self.cfg
        c = self.c
        orb_r = cfg["powerups.orb_radius"]
        for o in engine.orbs:
            t = engine.types.get(o.type_id)
            icon = t.icon if t else ""
            cls_col = c["class"].get(o.cls, c["neutral"])
            if o.state == "spawning":
                k = ease_out_back(o.state_t / max(0.01, cfg["powerups.spawn_anim_s"]))
                a = 1.0
            elif o.state == "despawning":
                k = 1 - o.state_t / 0.3
                a = k
            elif o.state == "collected":
                k = 1 + o.state_t * 2.2
                a = max(0.0, 1 - o.state_t / 0.45)
            else:
                k = 1.0
                a = 1.0
            if k <= 0.02 or a <= 0.02:
                continue
            bob = math.sin(self.time * 2.2 + o.id) * cfg["powerups.bob_px"]
            jit = math.sin(self.time * 60) * o.wobble * 10
            x, y = o.x + jit, o.y + bob
            if cfg["powerups.magnet.show_tether"]:
                off = math.hypot(o.x - o.hx, o.y - o.hy)
                if off > 5:
                    p1, p2 = self.to_c(o.hx, o.hy), self.to_c(x, y)
                    n = max(2, int(off / 9))
                    for s in range(n):
                        f = s / n
                        px, py = p1[0] + (p2[0] - p1[0]) * f, p1[1] + (p2[1] - p1[1]) * f
                        self.add.mark(pygame.draw.aacircle(self.add.surf, scale(cls_col, 0.35), (int(px), int(py)), 2))
            blink = 1.0
            if o.cls == "bad":
                blink = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.time * math.tau * 1.5))
            gi = (0.5 + 0.7 * o.pulled) * blink * a
            self.add.blit(self.glow.sprite(cls_col, orb_r * 2.4 * max(0.3, k), gi), self.to_c(x, y))
            body = self.icons.badge(icon, o.type_id, orb_r, cls_col, o.cls == "bad", cfg["powerups.icon_scale"])
            if abs(k - 1) > 0.01:
                sz = max(2, int(body.get_width() * k))
                body = pygame.transform.smoothscale(body, (sz, sz))
            if a < 0.999:
                body = body.copy()
                body.set_alpha(int(255 * a))
            cx, cy = self.to_c(x, y)
            self.canvas.blit(body, (int(cx - body.get_width() / 2), int(cy - body.get_height() / 2)))
            if o.state in ("spawning", "idle"):
                rem = max(0.0, 1 - o.age / max(0.01, o.life))
                rr = orb_r + 7
                rect = pygame.Rect(0, 0, 2 * rr, 2 * rr)
                rect.center = (int(cx), int(cy))
                if rem > 0.01:
                    self.add.mark(pygame.draw.arc(self.add.surf, (110, 110, 110), rect, math.pi / 2,
                                                  math.pi / 2 + math.tau * rem, 2))

    # ---------------------------------------------------------------- predictions
    def _predictions(self, engine) -> None:
        if not engine.predictions:
            return
        cfg = self.cfg
        c = self.c
        spacing = cfg["prediction.dot_spacing"]
        phase = (self.time * cfg["prediction.march_speed"]) % spacing
        for bid, pr in engine.predictions.items():
            pts = pr.points
            if len(pts) < 2:
                continue
            strong = getattr(pr, "strong", True)
            ka = 1.0 if strong else cfg["prediction.assist_alpha"]
            dr = cfg["prediction.dot_radius"] * (1.0 if strong else cfg["prediction.assist_dot_scale"])
            col = c["teamb"][pr.receiver] if cfg["prediction.color_mode"] == "receiver" else (255, 255, 255)
            dotc = mix(col, (255, 255, 255), 0.35)
            seglens = []
            total = 0.0
            for k in range(1, len(pts)):
                L = math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
                seglens.append(L)
                total += L
            if total < 1:
                continue
            d, k, acc = phase, 0, 0.0
            if not strong:
                d += total * (1.0 - cfg["prediction.assist_path_fraction"])  # only the stretch near the paddle
            while d < total:
                while k < len(seglens) and acc + seglens[k] < d:
                    acc += seglens[k]
                    k += 1
                if k >= len(seglens):
                    break
                f = (d - acc) / max(1e-6, seglens[k])
                x = pts[k][0] + (pts[k + 1][0] - pts[k][0]) * f
                y = pts[k][1] + (pts[k + 1][1] - pts[k][1]) * f
                fade = (0.35 + 0.65 * (d / total)) if strong else (0.25 + 0.75 * (d / total))
                sx, sy = self.to_c(x, y)
                self.add.blit(self.glow.sprite(dotc, dr * 2.6, fade * ka * 1.4), (sx, sy))
                d += spacing
            if not pr.contact:
                continue
            gx, gy = pr.contact
            sx, sy = self.to_c(gx, gy)
            if strong or cfg["prediction.assist_ghost"]:
                r = max(3, int(cfg["ball.radius"] * (1.0 if strong else cfg["prediction.assist_ghost_scale"])))
                pulse = 0.75 + 0.25 * math.sin(self.time * 8)
                ga = cfg["prediction.ghost_alpha"] * pulse * (1.0 if strong else ka * 2.0)
                ghost = pygame.Surface((4 * r, 4 * r), pygame.SRCALPHA)
                pygame.draw.aacircle(ghost, (*dotc, int(255 * min(1, ga))), (2 * r, 2 * r), r, 2)
                pygame.draw.aacircle(ghost, (*dotc, int(110 * min(1, ga))), (2 * r, 2 * r), max(1, r - 3))
                self.canvas.blit(ghost, (int(sx - 2 * r), int(sy - 2 * r)))
            if pr.out_dir and not pr.goal and (strong or cfg["prediction.assist_arrow"]):
                L = cfg["prediction.arrow_length"] if strong else cfg["prediction.assist_arrow_length"]
                ex, ey = gx + pr.out_dir[0] * L, gy + pr.out_dir[1] * L
                p1, p2 = (sx, sy), self.to_c(ex, ey)
                ac = scale(dotc, ka if strong else min(1.0, ka * 2.2))
                if not strong:  # tiny and faint: a thin stroke with a small chevron
                    self.add.mark(pygame.draw.aaline(self.add.surf, ac, p1, p2, 1))
                    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                    for sgn in (-0.6, 0.6):
                        q = (p2[0] - 6 * math.cos(ang + sgn), p2[1] - 6 * math.sin(ang + sgn))
                        self.add.mark(pygame.draw.aaline(self.add.surf, ac, p2, q, 1))
                    continue
                if pr.intercept:
                    self.add.mark(pygame.draw.aaline(self.add.surf, ac, p1, p2, 3))
                else:
                    n = 6
                    for s in range(0, n, 2):
                        a0, a1 = s / n, (s + 1) / n
                        q1 = (p1[0] + (p2[0] - p1[0]) * a0, p1[1] + (p2[1] - p1[1]) * a0)
                        q2 = (p1[0] + (p2[0] - p1[0]) * a1, p1[1] + (p2[1] - p1[1]) * a1)
                        self.add.mark(pygame.draw.aaline(self.add.surf, ac, q1, q2, 3))
                ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                for s in (-0.6, 0.6):
                    q = (p2[0] - 11 * math.cos(ang + s), p2[1] - 11 * math.sin(ang + s))
                    self.add.mark(pygame.draw.aaline(self.add.surf, ac, p2, q, 3))

    # ---------------------------------------------------------------- trails
    def _trails(self, engine, alpha, dt) -> None:
        cfg = self.cfg
        c = self.c
        base_dur = cfg["trails.duration_s"]
        live_ids = set()
        cap = cfg["fx.max_particles"]
        for b in engine.balls:
            if b.removed:
                continue
            live_ids.add(b.id)
            x = b.px + (b.x - b.px) * alpha
            y = b.py + (b.y - b.py) * alpha
            tr = self.trails.setdefault(b.id, [])
            if b.held:
                tr.clear()
                continue
            tr.append((self.time, x, y, b.owner))
            # star sparkles shed by the moving ball
            rate = cfg["trails.sparkles"]
            if rate > 0 and not b.scored and dt > 0:
                sp = math.hypot(b.vx, b.vy)
                acc = self._sparkle_acc.get(b.id, 0.0) + rate * dt * min(2.0, sp / 600.0)
                col = c["core"][b.owner] if b.owner is not None else c["neutral_ball"]
                while acc >= 1.0:
                    acc -= 1.0
                    back = math.atan2(-b.vy, -b.vx)
                    self.particles.burst(x + self.rng.uniform(-b.r, b.r) * 0.6, y + self.rng.uniform(-b.r, b.r) * 0.6,
                                         col, 1, (10, 70), (0.35, 0.8), (0.8, 1.8), cap=cap, drag=1.5,
                                         direction=back, spread=1.2, twinkle=True)
                self._sparkle_acc[b.id] = acc
        for bid in list(self.trails):
            if bid not in live_ids:
                if bid not in self.dead_trails:
                    self.dead_trails[bid] = (self.time, self.trails[bid])
                del self.trails[bid]
                self._sparkle_acc.pop(bid, None)
        for bid, (t0, tr) in list(self.dead_trails.items()):
            if self.time - t0 > base_dur * 2:
                del self.dead_trails[bid]
        balls = {b.id: b for b in engine.balls}
        items = [(bid, tr, balls.get(bid)) for bid, tr in self.trails.items()]
        items += [(bid, tr, None) for bid, (t0, tr) in self.dead_trails.items()]
        comet = cfg["trails.style"] == "comet"
        for bid, tr, b in items:
            dur = base_dur
            if b is not None and engine.speed_mult(b) > 1.01:
                dur *= cfg["trails.speedup_length_mult"]
            while tr and self.time - tr[0][0] > dur:
                tr.pop(0)
            if len(tr) < 2:
                continue
            if comet:
                self._comet(engine, bid, tr, b, dur)
            else:
                self._ribbon(engine, bid, tr, b, dur)

    def _comet(self, engine, bid, tr, b, dur) -> None:
        """Soft glowing star trail: dense additive stamps whose size and brightness fall off with age."""
        cfg = self.cfg
        c = self.c
        mode = cfg["trails.color_mode"]
        r = b.r if b is not None else cfg["ball.radius"]
        owner_now = b.owner if b is not None else tr[-1][3]
        ball_a = engine.effects.ball_alpha(bid) if b is not None else 0.6
        ta, tg = cfg["trails.alpha"], cfg["trails.glow"]
        head = cfg["trails.head_size"]
        falloff = cfg["trails.falloff"]
        flash = self.time - self.trail_flash.get(bid, -9)
        smart = b is not None and engine.time < b.smart_until
        step = max(2.5, r * 0.3)
        # walk from the head (newest) to the tail
        seq = tr[::-1]
        dist_to_next = 0.0
        for i in range(len(seq) - 1):
            t1, x1, y1, o1 = seq[i]
            t2, x2, y2, o2 = seq[i + 1]
            seg = math.hypot(x2 - x1, y2 - y1)
            if seg < 1e-6:
                continue
            pos = dist_to_next
            while pos < seg:
                f = pos / seg
                tt = t1 + (t2 - t1) * f
                age = (self.time - tt) / dur
                if age >= 1.0:
                    return
                k = (1.0 - age) ** falloff
                x, y = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
                own = owner_now if mode == "current_owner" else o1
                col = c["teamb"][own] if own is not None else c["neutral_ball"]
                core = c["core"][own] if own is not None else (255, 255, 255)
                rad = r * head * (0.22 + 0.78 * k)
                sx, sy = self.to_c(x, y)
                inten = round(k * ta * ball_a * 10) / 10
                if inten > 0:
                    self.add.blit(self.glow.sprite(col, rad * 2.8, inten * 0.42 * tg), (sx, sy))
                    if k > 0.25:
                        self.add.blit(self.glow.sprite(core, rad * 1.15, inten * 0.85), (sx, sy))
                if flash < 0.18 and age < 0.5:
                    self.add.blit(self.glow.sprite((255, 255, 255), rad * 1.6, 0.9 * (1 - flash / 0.18) * k), (sx, sy))
                if smart and age < 0.7:
                    self.add.blit(self.glow.sprite(c["smart"], rad * 1.4, 0.5 * k), (sx, sy))
                pos += step
            dist_to_next = pos - seg

    def _ribbon(self, engine, bid, tr, b, dur) -> None:
        cfg = self.cfg
        c = self.c
        r = b.r if b is not None else cfg["ball.radius"]
        owner_now = b.owner if b is not None else tr[-1][3]
        ball_a = engine.effects.ball_alpha(bid) if b is not None else 0.6
        ta, tg, ws = cfg["trails.alpha"], cfg["trails.glow"], cfg["trails.width_scale"]
        pts = []
        for (t, x, y, own) in tr:
            own_c = owner_now if cfg["trails.color_mode"] == "current_owner" else own
            col = c["teamb"][own_c] if own_c is not None else c["neutral_ball"]
            pts.append((self.to_c(x, y), col, max(0.0, 1 - (self.time - t) / dur)))
        surf = self.add.surf
        for k in range(1, len(pts)):
            (p0, _, _), (p1, col, f) = pts[k - 1], pts[k]
            if f <= 0:
                continue
            w = max(1, int(2 * r * ws * f))
            if tg > 0:
                self.add.mark(pygame.draw.line(surf, scale(col, 0.32 * tg * f * ta * ball_a), p0, p1, int(w * 2.4) + 2))
            self.add.mark(pygame.draw.aaline(surf, scale(col, f * ta * ball_a), p0, p1, w))

    # ---------------------------------------------------------------- shields
    def _shields(self, engine) -> None:
        g = self._g
        for eff in engine.effects.of_kind("shield"):
            arc = g.goals[eff.target[1]]
            span = arc.span * eff.data.get("coverage", 100) / 100
            a0 = arc.center - span / 2
            pulse = 0.6 + 0.4 * math.sin(self.time * 6)
            a = a0
            while a <= a0 + span:
                ar = math.radians(a)
                self.add.blit(self.glow.sprite(self.c["good"], 14, 0.55 * pulse),
                              self.to_c((g.R - 6) * math.cos(ar), (g.R - 6) * math.sin(ar)))
                a += 2.0

    # ---------------------------------------------------------------- paddles (supersampled)
    def _paddles(self, engine, alpha) -> None:
        cfg = self.cfg
        c = self.c
        k = int(cfg["display.supersample"])
        stacking = cfg["paddles.size_stacking"]
        for p in engine.paddles:
            i = p.idx
            th = p.prev_theta + (p.theta - p.prev_theta) * alpha
            sh = engine.paddle_shape(i, th)
            outline = [self.to_c(x, y) for x, y in sh.outline(40)]
            team, teamb = c["team"][i], c["teamb"][i]
            present = p.present or engine.state == "ATTRACT"
            dimk = 1.0 if present else 0.35
            mult = engine.effects.paddle_mult(i, stacking)
            # soft neon glow along the dome
            for j in range(0, len(outline), 3):
                self.add.blit(self.glow.sprite(teamb, 16, 0.42 * dimk), outline[j])
            # body on a supersampled sprite
            xs = [q[0] for q in outline]
            ys = [q[1] for q in outline]
            pad = 8
            x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
            w, h = int(max(xs)) - x0 + pad, int(max(ys)) - y0 + pad
            spr = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
            spr.fill((*team, 0))
            pts = [((qx - x0) * k, (qy - y0) * k) for qx, qy in outline]
            fill = scale(mix(team, (0, 0, 0), 0.38), dimk)
            pygame.draw.polygon(spr, (*fill, 255), pts)
            # inner highlight band just inside the dome edge
            inner = [((qx - x0) * k, (qy - y0) * k) for qx, qy in
                     (self.to_c(ax, ay) for ax, ay in sh.outline(40, inset=6.0))][3:-3]
            if len(inner) > 1:
                pygame.draw.lines(spr, (*scale(mix(team, (255, 255, 255), 0.12), dimk), 255), False, inner, max(1, int(5 * k)))
            edge = scale(teamb, dimk)
            if mult > 1.02:
                pulse = 0.6 + 0.4 * math.sin(self.time * 7)
                edge = mix(edge, c["good"], 0.55 * pulse + 0.2)
            elif mult < 0.98 and int(self.time * 12) % 3 != 0:
                edge = mix(edge, c["bad"], 0.6)
            pygame.draw.lines(spr, (*edge, 255), True, pts, max(2, int(3.5 * k)))
            pygame.draw.lines(spr, (*scale(mix(teamb, (255, 255, 255), 0.55), dimk), 255), False, pts, max(1, int(1.2 * k)))
            if k > 1:
                spr = pygame.transform.smoothscale(spr, (w, h))
            self.canvas.blit(spr, (x0, y0))
            # active effects for this player: icon + countdown ring behind the paddle
            effs = engine.effects.player_effects(i)
            if effs:
                n = len(effs)
                rb = sh.rb + min(22.0, max(14.0, (engine.geom.R - sh.rb) * 0.55))
                for kk, eff in enumerate(effs):
                    t = engine.types.get(eff.type_id)
                    cls = cfg.get(f"powerups.types.{eff.type_id}.class", "neutral")
                    ccol = c["class"].get(cls, c["neutral"])
                    if eff.collector is not None and eff.collector != i and cls == "good":
                        ccol = c["bad"]  # good for the collector = bad for this player
                    a = math.radians(th + (kk - (n - 1) / 2) * 7.5)
                    sx, sy = self.to_c(rb * math.cos(a), rb * math.sin(a))
                    ic = self.icons.icon(t.icon if t else "", eff.type_id, 18)
                    self.canvas.blit(ic, (int(sx - 9), int(sy - 9)))
                    rect = pygame.Rect(0, 0, 28, 28)
                    rect.center = (int(sx), int(sy))
                    self.add.mark(pygame.draw.arc(self.add.surf, ccol, rect, math.pi / 2, math.pi / 2 + math.tau * eff.frac, 3))

    # ---------------------------------------------------------------- balls
    def _ball_sprite(self, ring, core, tint, r, a) -> pygame.Surface:
        key = ("ball", ring, core, tint, int(r), int(a * 20))
        s = self.icons.cache.get(key)
        if s is None:
            k = 3
            R = int((2 * r + 8) * k)
            big = pygame.Surface((R, R), pygame.SRCALPHA)
            big.fill((*ring, 0))
            C = R // 2
            pygame.draw.circle(big, (*ring, int(255 * max(a, 0.6))), (C, C), int((r + 3) * k), int(3 * k))
            pygame.draw.circle(big, (*core, int(255 * a)), (C, C), int(r * k))
            pygame.draw.circle(big, (*mix(core, tint, 0.35), int(200 * a)), (C + int(r * 0.25 * k), C + int(r * 0.25 * k)),
                               max(1, int(r * 0.45 * k)))
            s = pygame.transform.smoothscale(big, (R // k, R // k))
            self.icons.cache[key] = s
        return s

    def _balls(self, engine, alpha) -> None:
        cfg = self.cfg
        c = self.c
        cap = cfg["fx.max_particles"]
        for b in engine.balls:
            if b.removed:
                continue
            x = b.px + (b.x - b.px) * alpha
            y = b.py + (b.y - b.py) * alpha
            col = c["teamb"][b.owner] if b.owner is not None else c["neutral_ball"]
            a = engine.effects.ball_alpha(b.id)
            if b.scored:
                a *= max(0.0, 1 - (engine.time - b.scored_t) / 0.5)
                if a <= 0:
                    continue
            r = b.r
            gsize = cfg["ball.glow_size"]
            gint = cfg["ball.glow_intensity"]
            if b.held:
                if engine.state == "COUNTDOWN":
                    prog = min(1.0, engine.state_t / max(0.1, engine.countdown_total()))
                    gsize *= 0.6 + 1.6 * prog
                    gint *= 0.6 + 0.9 * prog
                else:
                    gsize *= 1 + 0.25 * math.sin(self.time * 9)
            sx, sy = self.to_c(x, y)
            self.add.blit(self.glow.sprite(col, r * gsize, gint * a), (sx, sy))
            if engine.speed_mult(b) > 1.01 and not b.held and self.rng.random() < 0.7:
                ang = math.atan2(b.vy, b.vx) + math.pi
                self.particles.burst(x, y, (255, 150, 60), 2, (60, 200), (0.15, 0.35), (1.5, 3.0), cap=cap,
                                     direction=ang, spread=0.5)
            if engine.time < b.smart_until and self.rng.random() < 0.6:
                self.particles.burst(x, y, c["smart"], 1, (20, 90), (0.2, 0.5), cap=cap, twinkle=True)
            if engine.effects.ball_has(b.id, "wobble") is not None and self.rng.random() < 0.5:
                self.particles.burst(x, y, c["neutral"], 1, (20, 80), (0.2, 0.5), cap=cap)
            ring = c["smart"] if engine.time < b.smart_until else col
            body = self._ball_sprite(ring, c["ball_core"], col, r, a)
            self.canvas.blit(body, (int(sx - body.get_width() / 2), int(sy - body.get_height() / 2)))
            if b.owner is not None and engine.effects.for_player(b.owner, "bull") is not None:
                self.add.mark(pygame.draw.aacircle(self.add.surf, scale(c["smart"], 0.8), (int(sx), int(sy)), int(r + 7), 2))

    def _chaos(self, engine) -> None:
        """Random-path sequence: charging aura, then a roulette of candidate paths that locks on the chosen one."""
        c = self.c
        col = c["neutral"]
        colb = boost(col, 0.35)
        for b in engine.balls:
            ch = b.chaos
            if not ch or b.removed:
                continue
            sx, sy = self.to_c(b.x, b.y)
            p = ch["p"]
            if ch["stage"] == "intro":
                self.add.blit(self.glow.sprite(colb, b.r * (4.2 + 1.4 * math.sin(self.time * 10)), 0.9), (sx, sy))
                for j in range(6):
                    a = self.time * 4.0 + j * math.tau / 6
                    rr = b.r * 2.7 + 4 * math.sin(self.time * 6 + j)
                    self.add.blit(self.glow.sprite(colb, 8, 1.0), (sx + math.cos(a) * rr, sy + math.sin(a) * rr))
                rr = int(b.r * 3.4)
                rect = pygame.Rect(0, 0, 2 * rr, 2 * rr)
                rect.center = (int(sx), int(sy))
                for j in range(8):
                    a0 = -self.time * 3.0 + j * math.tau / 8
                    self.add.mark(pygame.draw.arc(self.add.surf, colb, rect, a0, a0 + 0.38, 2))
            elif ch["stage"] == "select":
                cands = ch["candidates"]
                n = len(cands)
                if not n:
                    continue
                t = ch["t"] / max(0.01, ch.get("select_len", p["select_s"]))
                cycles = 2 if ch["rolls_done"] == 0 else 1
                total = cycles * n + ch["chosen"]
                locked = t >= 0.82
                hi = ch["chosen"] if locked else int(ease_out_cubic(t / 0.82) * total) % n
                self.add.blit(self.glow.sprite(colb, b.r * 3.6, 0.75), (sx, sy))
                for j, a in enumerate(cands):
                    dx, dy = math.cos(a), -math.sin(a)
                    bright = j == hi
                    L = p.get("ray_length", 70) * (1.3 if bright and locked else 1.0)
                    d = b.r * 1.5
                    while d < L:
                        f = 1 - d / L * 0.65
                        if bright:
                            inten = (1.25 if locked else 0.95) * f
                            if locked:
                                inten *= 0.75 + 0.25 * math.sin(self.time * 40)
                            self.add.blit(self.glow.sprite(colb if not locked else (255, 255, 255), 6, inten),
                                          (sx + dx * d, sy + dy * d))
                        else:
                            self.add.blit(self.glow.sprite(col, 4, 0.34 * f), (sx + dx * d, sy + dy * d))
                        d += 7
                    if bright:
                        tip = (sx + dx * L, sy + dy * L)
                        ang = math.atan2(dy, dx)
                        for sgn in (-0.55, 0.55):
                            q = (tip[0] - 8 * math.cos(ang + sgn), tip[1] - 8 * math.sin(ang + sgn))
                            self.add.mark(pygame.draw.aaline(self.add.surf, colb, tip, q, 2))

    def _pending_balls(self) -> None:
        """Telegraph where (and when) the delayed second ball will appear."""
        keep = []
        for pm in self.pending_marks:
            age = self.time - pm["t0"]
            if age > pm["dur"]:
                continue
            keep.append(pm)
            k = age / pm["dur"]
            sx, sy = self.to_c(pm["x"], pm["y"])
            rr = pm["r"] * (4.0 - 2.8 * ease_out_cubic(k))
            col = scale(pm["color"], 0.35 + 0.65 * k)
            self.add.mark(pygame.draw.aacircle(self.add.surf, col, (int(sx), int(sy)), max(2, int(rr)), 2))
            self.add.blit(self.glow.sprite(pm["color"], pm["r"] * (1.5 + 2.5 * k), 0.25 + 0.6 * k), (sx, sy))
        self.pending_marks = keep

    def _rings(self) -> None:
        keep = []
        for rg in self.rings:
            t = (self.time - rg["t0"]) / rg["dur"]
            if t >= 1:
                continue
            keep.append(rg)
            r = rg["r0"] + (rg["r1"] - rg["r0"]) * (1 - (1 - t) ** 2)
            col = scale(rg["color"], (1 - t) * 0.9)
            sx, sy = self.to_c(rg["x"], rg["y"])
            w = max(1, int(rg["w"] * (1 - t * 0.5)))
            if r > w:
                self.add.mark(pygame.draw.aacircle(self.add.surf, col, (int(sx), int(sy)), int(r), w))
        self.rings = keep

    def _flights(self, engine) -> None:
        keep = []
        for fl in self.flights:
            t = (self.time - fl["t0"]) / fl["dur"]
            if t >= 1:
                continue
            keep.append(fl)
            aff = fl["affects"]
            tx, ty = fl["x"], fl["y"]
            if aff and aff[0] == "player":
                tx, ty = engine.paddle_shape(aff[1]).apex()
            elif aff and aff[0] == "ball":
                for b in engine.balls:
                    if b.id == aff[1]:
                        tx, ty = b.x, b.y
            e = t * t * (3 - 2 * t)
            x = fl["x"] + (tx - fl["x"]) * e
            y = fl["y"] + (ty - fl["y"]) * e
            size = int(34 * (1 - 0.4 * t))
            ic = self.icons.icon(fl["icon"], fl["type_id"], size).copy()
            ic.set_alpha(int(255 * (1 - t * 0.6)))
            sx, sy = self.to_c(x, y)
            self.canvas.blit(ic, (int(sx - size / 2), int(sy - size / 2)))
        self.flights = keep

    # ---------------------------------------------------------------- overlays per state
    def _intro(self, engine) -> None:
        g = self._g
        prog = min(1.0, engine.state_t / max(0.05, self.cfg["match.intro_s"]))
        self.dim.set_alpha(int(255 * (1 - prog) * 0.85))
        self.canvas.blit(self.dim, (0, 0))
        for side in (-1, 1):
            a = math.radians(90 + g.rot + side * 180 * prog)
            spr = self.glow.sprite((255, 255, 255), 60, 1.0)
            x, y = self.to_c(g.R * math.cos(a), g.R * math.sin(a))
            self.canvas.blit(spr, (int(x - 60), int(y - 60)), special_flags=pygame.BLEND_ADD)

    def _attract(self, engine) -> None:
        cfg = self.cfg
        g = self._g
        c = self.c
        self.dim.set_alpha(int(255 * (1 - cfg["match.attract_opacity"])))
        self.canvas.blit(self.dim, (0, 0))
        R = g.R
        bs = cfg["text.banner_size"]
        ux, uy = math.cos(math.radians(90 + g.rot)), math.sin(math.radians(90 + g.rot))
        rx, ry = -uy, ux  # "right" along the title row (screen-left for RTL reading comes first)
        # title row: «هاکی بازار» | MARKET HOCKEY, side by side, high on the arena
        fa = self._text_surface(cfg["text.title"], int(bs * 1.3), (255, 255, 255), "persian_title", outline=3, glow=0.35)
        en = self._text_surface(cfg["text.subtitle"], int(bs * 0.5), c["p1b"], "latin", glow=0.45)
        gap = bs * 1.6  # clear breathing room between the Persian and the English title
        total = fa.get_width() * 0.78 + gap + en.get_width() * 0.78  # widths include the shadow padding
        ty = R * 0.34
        fx = total / 2 - fa.get_width() * 0.39  # Persian on the right
        ex = -total / 2 + en.get_width() * 0.39  # English on the left
        self._text_at(cfg["text.title"], int(bs * 1.3), (255, 255, 255), ux * ty - rx * fx, uy * ty - ry * fx,
                      key="persian_title", outline=3, glow=0.35, reserve=True)
        self._text_at(cfg["text.subtitle"], int(bs * 0.5), c["p1b"], ux * ty - rx * ex, uy * ty - ry * ex,
                      key="latin", glow=0.45, reserve=True)
        mid = total / 2 - fa.get_width() * 0.78 - gap / 2  # the gap between the two titles
        dx0, dy0 = self.to_c(ux * ty - rx * mid, uy * ty - ry * mid)
        self.add.begin()
        self.add.mark(pygame.draw.aaline(self.add.surf, scale(c["lines"], 1.6), (dx0, dy0 - bs * 0.45),
                                         (dx0, dy0 + bs * 0.45), 2))
        self.add.composite(self.canvas)
        # player names entered on the supervisor page
        for i in (0, 1):
            if not engine.names[i]:
                continue
            gx, gy = g.goal_dir[i]
            bx, by = gx * R * 0.5, gy * R * 0.5
            self._text_at(cfg[f"text.player_{i + 1}"], int(cfg["text.toast_size"] * 0.55), c["teamb"][i],
                          bx + ux * R * 0.1, by + uy * R * 0.1, alpha=0.85, reserve=True)
            self._text_at(engine.names[i], int(bs * 0.7), c["teamb"][i], bx, by, outline=3, glow=0.6, reserve=True)
        pulse = 0.65 + 0.35 * math.sin(self.time * 2.4)
        self._text_at(cfg["text.attract_prompt"], int(cfg["text.toast_size"] * 0.85), (255, 255, 255),
                      -ux * R * 0.27, -uy * R * 0.27, alpha=pulse, reserve=True)
        if self.supervisor_url and cfg["web.show_url_on_arena"]:
            self._text_at(self.supervisor_url, 18, scale(c["text"], 0.75), -ux * R * 0.62, -uy * R * 0.62,
                          key="latin", outline=2, reserve=True)

    def _countdown(self, engine) -> None:
        cfg = self.cfg
        label, t_in, length, idx = engine.countdown_info()
        if label == "ready":
            text, size, key = cfg["text.ready"], int(cfg["text.banner_size"] * 1.3), "persian"
        elif label == "go":
            text, size, key = cfg["text.go"], int(cfg["text.banner_size"] * 1.9), "persian_title"
        else:
            text, size, key = label, cfg["countdown.size"], "digits"
        t = t_in / max(0.01, length)
        k = 1 + 0.7 * (1 - ease_out_elastic(min(1.0, t_in / 0.5)))
        a = 1.0 if t < 0.72 else max(0.0, 1 - (t - 0.72) / 0.28)
        col = (255, 255, 255)
        if label in ("3", "1"):
            col = mix(self.c["p1b"], (255, 255, 255), 0.45)
        elif label == "2":
            col = mix(self.c["p2b"], (255, 255, 255), 0.45)
        self._text_at(text, size, col, 0, 0, key=key, alpha=a, scale_k=k, outline=3, glow=0.8, reserve=True)

    def _telegraph(self, engine) -> None:
        live = engine.live_balls()
        if not live:
            return
        b = live[0]
        dx, dy = engine.geom.goal_dir[engine.serve_receiver]
        col = self.c["teamb"][engine.serve_receiver]
        for k in range(3):
            ph = (self.time * 2.2 + k / 3) % 1.0
            d = 30 + ph * 70
            x, y = b.x + dx * d, b.y + dy * d
            a = math.atan2(-dy, dx)
            sx, sy = self.to_c(x, y)
            s = 12
            p1 = (sx - s * math.cos(a - 0.7), sy - s * math.sin(a - 0.7))
            p2 = (sx - s * math.cos(a + 0.7), sy - s * math.sin(a + 0.7))
            colk = scale(col, 1 - ph)
            pygame.draw.aaline(self.canvas, colk, p1, (sx, sy), 4)
            pygame.draw.aaline(self.canvas, colk, p2, (sx, sy), 4)

    def _result(self, engine) -> None:
        cfg = self.cfg
        g = self._g
        c = self.c
        R = g.R
        st_t = engine.state_t
        self.dim.set_alpha(110)
        self.canvas.blit(self.dim, (0, 0))
        if engine.state == "FINAL":
            k = 1 + 0.5 * (1 - ease_out_elastic(min(1.0, st_t / 0.6)))
            self._text_at(cfg["text.final"], int(cfg["text.banner_size"] * 1.5), (255, 255, 255), 0, 0,
                          key="persian_title", scale_k=k, outline=3, glow=0.5)
            return
        w = engine.winner
        if w is not None:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3)
            a0 = 90 + g.rot if w == 0 else -90 + g.rot
            pts = self._arc_pts(g.wall_face, a0, a0 + 180) + [self.to_c(0, 0)]
            self.add.begin()
            self.add.mark(pygame.draw.polygon(self.add.surf, scale(c["teamb"][w], 0.10 + 0.08 * pulse), pts))
            self.add.composite(self.canvas)
            gx, gy = g.goal_dir[w]
            ux, uy = math.cos(math.radians(90 + g.rot)), math.sin(math.radians(90 + g.rot))
            bx, by = gx * R * 0.5, gy * R * 0.5
            self._text_at(cfg["text.winner"], int(cfg["text.banner_size"] * 1.1), c["teamb"][w], bx + ux * R * 0.31,
                          by + uy * R * 0.31, key="persian_title", outline=3, glow=0.6)
            k = 1 + 0.08 * math.sin(self.time * 4)
            ic = self.icons.icon("trophy", "_trophy", int(84 * k), c["smart"])
            sx, sy = self.to_c(bx + ux * R * 0.48, by + uy * R * 0.48)
            ic = self._rot(ic)
            self.add.begin()
            self.add.blit(self.glow.sprite(c["smart"], 70, 0.5), (sx, sy))
            self.add.composite(self.canvas)
            self.canvas.blit(ic, (int(sx - ic.get_width() / 2), int(sy - ic.get_height() / 2)))
        else:
            self._text_at(cfg["text.draw"], int(cfg["text.banner_size"] * 1.3), (255, 255, 255), 0, R * 0.18,
                          key="persian_title", outline=3, glow=0.4)
        for i in (0, 1):
            gx, gy = g.goal_dir[i]
            dx, dy = math.cos(math.radians(270 + g.rot)), math.sin(math.radians(270 + g.rot))
            self._text_at(str(engine.scores[i]), int(cfg["hud.score_size"] * 1.5), c["teamb"][i],
                          gx * R * 0.5 + dx * R * 0.06, gy * R * 0.5 + dy * R * 0.06, key="digits", outline=3,
                          glow=cfg["hud.glow"])
            if engine.names[i]:
                self._text_at(engine.names[i], int(cfg["text.banner_size"] * 0.75), c["teamb"][i],
                              gx * R * 0.5 - dx * R * 0.16, gy * R * 0.5 - dy * R * 0.16, outline=3, glow=0.4)
        self._text_at(cfg["text.slogan"], int(cfg["text.toast_size"] * 0.85), (255, 255, 255), 0, -R * 0.55,
                      alpha=min(1.0, st_t / 0.8))

    def _toasts(self, engine) -> None:
        cfg = self.cfg
        g = self._g
        bk = []
        for bn in self.banners:
            age = self.time - bn["t0"]
            if age >= bn["dur"]:
                continue
            bk.append(bn)
            a = min(1.0, age / 0.18) * (1.0 if age < bn["dur"] - 0.35 else max(0.0, (bn["dur"] - age) / 0.35))
            k = 0.8 + 0.2 * ease_out_back(min(1.0, age / 0.3))
            ux, uy = math.cos(math.radians(90 + g.rot)), math.sin(math.radians(90 + g.rot))
            self._text_at(bn["text"], bn["size"], bn["color"], ux * g.R * bn["y"], uy * g.R * bn["y"], alpha=a,
                          scale_k=k, outline=3, glow=0.6, reserve=True, avoid=True, axis=(-ux, uy))
        self.banners = bk
        keep = []
        per_side: dict = {}
        for t in self.toasts:
            age = self.time - t["t0"]
            if age >= t["dur"]:
                continue
            keep.append(t)
            side = t["side"]
            n = per_side.get(side, 0)
            per_side[side] = n + 1
            a = min(1.0, age / 0.15) * (1.0 if age < t["dur"] - 0.4 else max(0.0, (t["dur"] - age) / 0.4))
            k = 0.85 + 0.15 * ease_out_back(min(1.0, age / 0.25))
            extra = 0.0
            if side is None:
                x, y = 0.0, g.R * 0.32 - n * t["size"] * 1.3
            else:
                gx, gy = g.goal_dir[side]
                rr = g.R * cfg["text.toast_radius"]
                px, py = -gy, gx
                off = (n - 0.5) * t["size"] * 1.35
                x, y = gx * rr + px * off, gy * rr + py * off
                if cfg["hud.orientation"] == "toward_players":
                    extra = -90.0 if side == 0 else 90.0
            # choose a free spot once (re-check every frame in case something new appeared there)
            full = self._text_surface(t["text"], t["size"], t["color"], extra_rot=extra, outline=3, glow=0.35)
            pos = t.get("pos")
            if pos is not None:
                r = full.get_rect(center=pos)
                if not self._fits(r):
                    pos = None
            if pos is None:
                axis = (0.0, 1.0)
                if side is not None:
                    gx, gy = g.goal_dir[side]
                    axis = (-gy, -gx)  # slide along the player's side
                pos = self._free_spot(full.get_width(), full.get_height(), *self.to_c(x, y), axis)
                t["pos"] = pos
            self._text_at(t["text"], t["size"], t["color"], 0, 0, alpha=a, scale_k=k, extra_rot=extra, outline=3,
                          glow=0.35, at=pos)
            self._reserve(full.get_rect(center=pos))
        self.toasts = keep

    def _absent(self, engine) -> None:
        if engine.state == "ATTRACT":
            return
        cfg = self.cfg
        for p in engine.paddles:
            if not p.present:
                ax, ay = engine.paddle_shape(p.idx).apex()
                extra = 0.0
                if cfg["hud.orientation"] == "toward_players":
                    extra = -90.0 if p.idx == 0 else 90.0
                self._text_at(cfg["text.step_in"], int(cfg["text.toast_size"] * 0.7), self.c["teamb"][p.idx],
                              ax * 0.7, ay * 0.7, alpha=0.6 + 0.4 * math.sin(self.time * 4), extra_rot=extra)
