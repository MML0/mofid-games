"""Draws the engine state onto a logical canvas. Everything outside the circle is masked to pure black last."""

from __future__ import annotations

import math
import random

import pygame

from ..core.geometry import pp
from .colors import boost, hex_rgb, mix, scale
from .glow import AddLayer, GlowCache
from .icons import IconCache
from .particles import Particles
from .text import TextRenderer

STATIC_PREFIXES = ("display.canvas", "arena.", "walls.", "goals.", "center_zone.", "colors.", "paddles.",
                   "powerups.orb_radius", "hud.")
MASK_PREFIXES = ("display.canvas", "arena.mask", "arena.center")


def ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


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
        self.glow = GlowCache()
        self.icons = IconCache()
        self.particles = Particles(self.rng)
        self._cfg_v = -1
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
        self.score_pop = [-9.0, -9.0]
        self.goal_flash: tuple | None = None
        self.flash: tuple | None = None
        self.shake_until = 0.0
        self.ambient = []
        self._amb_scroll = 0.0
        self._amb_bias = (0.0, None, 0)
        self.debug_draw = None  # set by app: callable(renderer, engine, surface)

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
        c["class"] = {"good": c["good"], "bad": c["bad"], "neutral": c["neutral"]}
        self.c = c

    def _ensure(self, engine) -> None:
        cfg = self.cfg
        g = engine.geom
        changes = cfg.changes_since(self._cfg_v) if self._cfg_v >= 0 else {"*"}
        if not changes and self.canvas is not None:
            return
        self._cfg_v = cfg.version
        allc = "*" in changes
        size = (g.W, g.H)
        if allc or any(p.startswith("colors.") for p in changes):
            self._colors()
        if allc or any(p.startswith(("fonts.", "text.shaping")) for p in changes):
            self.text.clear()
        if self.canvas is None or size != self.size:
            self.size = size
            self.canvas = pygame.Surface(size)
            self.out = pygame.Surface(size)
            self.add = AddLayer(size)
            allc = True
        if allc or any(p.startswith(MASK_PREFIXES) for p in changes):
            self._build_mask(g)
        if allc or any(p.startswith(STATIC_PREFIXES) for p in changes):
            self._build_static(engine)

    def to_c(self, x, y):
        g = self._g
        return (g.cx + x, g.cy - y)

    def _arc_pts(self, r, a0, a1, steps=None):
        g = self._g
        steps = steps or max(8, int(abs(a1 - a0) / 1.5))
        out = []
        for k in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * k / steps)
            out.append((g.cx + r * math.cos(a), g.cy - r * math.sin(a)))
        return out

    def _band(self, r_in, r_out, a0, a1):
        return self._arc_pts(r_out, a0, a1) + self._arc_pts(r_in, a1, a0)

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
            # re-assert hard black well outside the feather band
            hard = pygame.Surface((W, H), pygame.SRCALPHA)
            hard.fill((0, 0, 0, 255))
            pygame.draw.circle(hard, (0, 0, 0, 0), (int(g.cx), int(g.cy)), int(g.mask_r + feather + 1))
            mask.blit(hard, (0, 0))
        self.mask = mask.convert_alpha() if pygame.display.get_surface() else mask
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.circle(dim, (0, 0, 0, 255), (int(g.cx), int(g.cy)), int(g.mask_r))
        self.dim = dim

    def _build_static(self, engine) -> None:
        cfg = self.cfg
        g = engine.geom
        self._g = g
        c = self.c
        S = pygame.Surface((g.W, g.H))
        S.fill((0, 0, 0))
        N = 90
        for i in range(N):
            r = g.mask_r * (1 - i / N)
            col = mix(c["arena_outer"], c["arena_inner"], (i / N) ** 0.8)
            pygame.draw.circle(S, col, (int(g.cx), int(g.cy)), max(1, int(r)))
        bg = c["arena_inner"]
        # center line (between the two halves, from top wall to bottom wall)
        if cfg["arena.show_center_line"]:
            col = mix(c["arena_outer"], c["lines"], cfg["arena.center_line_alpha"])
            a = math.radians(90 + g.rot)
            dx, dy = math.cos(a), math.sin(a)
            L = g.wall_face - 6
            seg, gap = 18, 12
            t = -L
            while t < L:
                t2 = min(L, t + seg)
                p1, p2 = self.to_c(dx * t, dy * t), self.to_c(dx * t2, dy * t2)
                pygame.draw.line(S, col, p1, p2, 2)
                t = t2 + gap
        # paddle tracks
        if cfg["arena.show_tracks"]:
            for i in (0, 1):
                w = pp(cfg, i, "width")
                lo, hi = g.paddle_range(i, w)
                lo2, hi2 = g.paddle_range(i, 0)
                rb = g.paddle_back_radius(i)
                col = mix(bg, c["teamb"][i], cfg["arena.track_alpha"])
                pts = self._arc_pts(rb, lo2, hi2)
                for k in range(0, len(pts) - 1, 2):
                    pygame.draw.line(S, col, pts[k], pts[k + 1], 2)
        # slot rings
        if cfg["center_zone.show_slot_rings"] and cfg["center_zone.layout"] != "random":
            col = mix(bg, c["lines"], cfg["center_zone.slot_ring_alpha"])
            rr = cfg["powerups.orb_radius"] + 5
            for x, y in g.slots:
                pygame.draw.circle(S, col, [int(v) for v in self.to_c(x, y)], int(rr), 2)
        # rim
        rim_w = cfg["arena.rim_line_width"]
        if rim_w > 0:
            pygame.draw.circle(S, mix(bg, c["lines"], 0.8), (int(g.cx), int(g.cy)), int(g.R), rim_w)
        # goal arcs with glow
        lw = cfg["goals.line_width"]
        gl = cfg["goals.glow"]
        for arc in g.goals:
            for k, (wmul, a) in enumerate(((5.0, 0.10), (3.0, 0.22), (1.8, 0.45))):
                if gl <= 0:
                    break
                col = mix(c["arena_outer"], c["goal"], a * gl)
                pygame.draw.polygon(S, col, self._band(g.R - lw * wmul / 2, g.R + lw * wmul / 2, arc.start, arc.end))
            pygame.draw.polygon(S, c["goal"], self._band(g.R - lw / 2, g.R + lw / 2, arc.start, arc.end))
        # bumper walls
        wc = mix(c["arena_outer"], c["wall"], cfg["walls.band_alpha"])
        hc = mix(wc, c["wall_hatch"], 0.85)
        for w in g.walls:
            pygame.draw.polygon(S, mix(c["arena_outer"], c["wall"], 0.18),
                                self._band(g.wall_face - 8, g.R + 4, w.start - 1, w.end + 1))
            pygame.draw.polygon(S, wc, self._band(g.wall_face, g.R, w.start, w.end))
            for a in (w.start, w.end):
                ar = math.radians(a)
                rc = g.R - g.t / 2
                pygame.draw.circle(S, wc, [int(v) for v in self.to_c(rc * math.cos(ar), rc * math.sin(ar))],
                                   max(1, int(g.t / 2)))
            if cfg["walls.hatch"]:
                step = 5.0
                a = w.start + step / 2
                while a < w.end - step / 4:
                    p1 = self.to_c((g.wall_face + 3) * math.cos(math.radians(a)), (g.wall_face + 3) * math.sin(math.radians(a)))
                    a2 = a + step * 0.55
                    p2 = self.to_c((g.R - 3) * math.cos(math.radians(a2)), (g.R - 3) * math.sin(math.radians(a2)))
                    pygame.draw.line(S, hc, p1, p2, 3)
                    a += step
            pygame.draw.lines(S, mix(wc, (255, 255, 255), 0.5), False, self._arc_pts(g.wall_face, w.start, w.end), 2)
        self.static = S.convert() if pygame.display.get_surface() else S

    # ====================================================================== events
    def handle_events(self, events, engine) -> None:
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
            elif et == "wall_bounce" and cfg["fx.wall_ripples"]:
                self.rings.append(dict(x=e["x"], y=e["y"], t0=self.time, dur=0.4, r0=6, r1=40,
                                       color=scale(c["wall"], 0.8), w=2))
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
            elif et == "golden_goal":
                self.toast(cfg["text.golden_goal"], c["smart"], None, size_mult=1.4)
            elif et == "match_end":
                self.flash = (self.time, (255, 255, 255), 0.8)
            elif et == "match_start":
                self.trails.clear()
                self.toasts.clear()
            elif et == "state" and e["state"] == "ATTRACT":
                self.toasts.clear()

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
        aff = e.get("affects")
        t = engine.types.get(e["type_id"])
        icon = t.icon if t else ""
        self.flights.append(dict(t0=self.time, dur=0.5, x=e["x"], y=e["y"], affects=aff, icon=icon,
                                 type_id=e["type_id"], color=col_cls))
        if e.get("toast_c"):
            self.toast(e["toast_c"], col_team, e["collector"], cls_color=col_cls)
            if e.get("banner"):
                pass
        if e.get("toast_o"):
            self.toast(e["toast_o"], c["teamb"][1 - e["collector"]], 1 - e["collector"], cls_color=col_cls)

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
        if st not in ("ATTRACT", "RESULT", "FINAL"):
            self._hud(engine)
        self._final_pulse(engine)
        self._goal_flash(engine)
        self._orbs(engine)
        self._predictions(engine)
        self._trails(engine, alpha)
        self._shields(engine)
        self._paddles(engine, alpha)
        self._balls(engine, alpha)
        self._rings()
        self.particles.draw(add, self.to_c)
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
            for k in range(int(2 * R / spacing) + 3):
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
            self.add.mark(pygame.draw.line(self.add.surf, col, pts[k - 1][0], pts[k][0], 2))

    def _draw_flash(self) -> None:
        if not self.flash:
            return
        t0, col, inten = self.flash
        cfg = self.cfg
        dur = 0.35
        k = 1 - (self.time - t0) / dur
        if k <= 0:
            self.flash = None
            return
        mx = cfg["fx.flash_max_alpha"] * (0.3 if cfg["fx.reduce_flashing"] else 1.0)
        a = min(0.6, mx * inten) * k * k
        g = self._g
        self.add.mark(pygame.draw.circle(self.add.surf, scale(col, a), (int(g.cx), int(g.cy)), int(g.mask_r)))

    def _final_pulse(self, engine) -> None:
        cfg = self.cfg
        if not cfg["fx.final_pulse"] or engine.state not in ("PLAYING", "SERVE") or not cfg["match.timer_enabled"]:
            return
        if engine.time_left > cfg["hud.final_seconds"] or engine.golden:
            return
        frac = engine.time_left - math.floor(engine.time_left)
        k = 0.25 * frac ** 2
        g = self._g
        self.add.mark(pygame.draw.circle(self.add.surf, scale(self.c["timer_final"], k), (int(g.cx), int(g.cy)),
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
        k = (1 - t / dur)
        lw = self.cfg["goals.line_width"]
        pts = self._arc_pts(g.R, arc.start, arc.end)
        self.add.mark(pygame.draw.lines(self.add.surf, scale(self.c["goal"], 0.9 * k), False, pts, int(lw * 3)))
        # a pulse running outward along the arc from the crossing point
        a0 = arc.unwrap(ang)
        spread = arc.span * min(1.0, t / 0.5)
        for side in (-1, 1):
            a = a0 + side * spread
            if arc.start <= a <= arc.end:
                x, y = g.R * math.cos(math.radians(a)), g.R * math.sin(math.radians(a))
                self.add.blit(self.glow.sprite(self.c["goal"], 40, 1.2 * k), self.to_c(x, y))

    # ---------------------------------------------------------------- HUD
    def _rot(self, surf, extra=0.0):
        ang = self._g.rot + extra
        return pygame.transform.rotate(surf, ang) if abs(ang) > 0.01 else surf

    def _text_at(self, text, size, color, x, y, key="persian", alpha=1.0, scale_k=1.0, extra_rot=0.0, outline=2):
        s = self.text.render(text, size, color, key, outline=outline, outline_color=(0, 8, 12))
        if abs(scale_k - 1.0) > 0.01:
            s = pygame.transform.rotozoom(s, 0, scale_k)
        s = self._rot(s, extra_rot)
        if alpha < 0.999:
            s = s.copy()
            s.set_alpha(int(255 * max(0.0, alpha)))
        cx, cy = self.to_c(x, y)
        self.canvas.blit(s, (int(cx - s.get_width() / 2), int(cy - s.get_height() / 2)))

    def timer_text(self, engine) -> str:
        cfg = self.cfg
        if engine.golden:
            return "+"
        tl = engine.time_left if engine.state not in ("INTRO", "COUNTDOWN") else engine.match_duration
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
            self._text_at(txt, cfg["hud.timer_size"], col, *g.timer_pos, key="digits", alpha=ha, scale_k=k)
        for i in (0, 1):
            t = self.time - self.score_pop[i]
            k = 1.0 + (0.5 * math.sin(math.pi * t / 0.6) if 0 <= t < 0.6 else 0)
            self._text_at(str(engine.scores[i]), cfg["hud.score_size"], c["teamb"][i], *g.score_pos[i],
                          key="digits", alpha=ha, scale_k=k)
            if cfg["hud.show_player_labels"]:
                x, y = g.score_pos[i]
                self._text_at(cfg[f"text.player_{i + 1}"], cfg["hud.label_size"], c["teamb"][i], x,
                              y + cfg["hud.score_size"] * 0.62, alpha=ha * 0.9)

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
                        self.add.mark(pygame.draw.circle(self.add.surf, scale(cls_col, 0.35), (int(px), int(py)), 2))
            blink = 1.0
            if o.cls == "bad":
                blink = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.time * math.tau * 1.5))
            gi = (0.45 + 0.6 * o.pulled) * blink * a
            self.add.blit(self.glow.sprite(cls_col, orb_r * 2.3 * max(0.3, k), gi), self.to_c(x, y))
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
        dr = cfg["prediction.dot_radius"]
        phase = (self.time * cfg["prediction.march_speed"]) % spacing
        for bid, pr in engine.predictions.items():
            pts = pr.points
            if len(pts) < 2:
                continue
            col = c["teamb"][pr.receiver] if cfg["prediction.color_mode"] == "receiver" else (255, 255, 255)
            dotc = mix(col, (255, 255, 255), 0.35)
            total = 0.0
            seglens = []
            for k in range(1, len(pts)):
                L = math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
                seglens.append(L)
                total += L
            if total < 1:
                continue
            d = phase
            k = 0
            acc = 0.0
            while d < total:
                while k < len(seglens) and acc + seglens[k] < d:
                    acc += seglens[k]
                    k += 1
                if k >= len(seglens):
                    break
                f = (d - acc) / max(1e-6, seglens[k])
                x = pts[k][0] + (pts[k + 1][0] - pts[k][0]) * f
                y = pts[k][1] + (pts[k + 1][1] - pts[k][1]) * f
                fade = 0.35 + 0.65 * (d / total)
                sx, sy = self.to_c(x, y)
                self.add.mark(pygame.draw.circle(self.add.surf, scale(dotc, fade), (int(sx), int(sy)), max(1, int(dr))))
                d += spacing
            if pr.contact:
                gx, gy = pr.contact
                sx, sy = self.to_c(gx, gy)
                r = int(cfg["ball.radius"])
                pulse = 0.75 + 0.25 * math.sin(self.time * 8)
                ga = cfg["prediction.ghost_alpha"] * pulse
                ghost = pygame.Surface((4 * r, 4 * r), pygame.SRCALPHA)
                pygame.draw.circle(ghost, (*dotc, int(255 * ga)), (2 * r, 2 * r), r, 2)
                pygame.draw.circle(ghost, (*dotc, int(110 * ga)), (2 * r, 2 * r), max(1, r - 3))
                self.canvas.blit(ghost, (int(sx - 2 * r), int(sy - 2 * r)))
                if pr.out_dir and not pr.goal:
                    L = cfg["prediction.arrow_length"]
                    ex, ey = gx + pr.out_dir[0] * L, gy + pr.out_dir[1] * L
                    p1, p2 = (sx, sy), self.to_c(ex, ey)
                    if pr.intercept:
                        self.add.mark(pygame.draw.line(self.add.surf, dotc, p1, p2, 3))
                    else:
                        n = 6
                        for s in range(0, n, 2):
                            a0, a1 = s / n, (s + 1) / n
                            q1 = (p1[0] + (p2[0] - p1[0]) * a0, p1[1] + (p2[1] - p1[1]) * a0)
                            q2 = (p1[0] + (p2[0] - p1[0]) * a1, p1[1] + (p2[1] - p1[1]) * a1)
                            self.add.mark(pygame.draw.line(self.add.surf, dotc, q1, q2, 3))
                    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                    hs = 11
                    for s in (-0.6, 0.6):
                        q = (p2[0] - hs * math.cos(ang + s), p2[1] - hs * math.sin(ang + s))
                        self.add.mark(pygame.draw.line(self.add.surf, dotc, p2, q, 3))

    # ---------------------------------------------------------------- trails
    def _trails(self, engine, alpha) -> None:
        cfg = self.cfg
        c = self.c
        base_dur = cfg["trails.duration_s"]
        live_ids = set()
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
        for bid in list(self.trails):
            if bid not in live_ids:
                if bid not in self.dead_trails:
                    self.dead_trails[bid] = (self.time, self.trails[bid])
                del self.trails[bid]
        for bid, (t0, tr) in list(self.dead_trails.items()):
            if self.time - t0 > base_dur * 2:
                del self.dead_trails[bid]
        mode = cfg["trails.color_mode"]
        ta, tg, ws = cfg["trails.alpha"], cfg["trails.glow"], cfg["trails.width_scale"]
        balls = {b.id: b for b in engine.balls}
        items = [(bid, tr, balls.get(bid)) for bid, tr in self.trails.items()]
        items += [(bid, tr, None) for bid, (t0, tr) in self.dead_trails.items()]
        for bid, tr, b in items:
            dur = base_dur
            if b is not None and engine.effects.ball_speed_mult(b.id) > 1.01:
                dur *= cfg["trails.speedup_length_mult"]
            while tr and self.time - tr[0][0] > dur:
                tr.pop(0)
            if len(tr) < 2:
                continue
            r = (b.r if b is not None else cfg["ball.radius"])
            owner_now = b.owner if b is not None else tr[-1][3]
            ball_a = engine.effects.ball_alpha(bid) if b is not None else 0.6
            flash = self.time - self.trail_flash.get(bid, -9)
            smart = b is not None and engine.time < b.smart_until
            pts = []
            for (t, x, y, own) in tr:
                own_c = owner_now if mode == "current_owner" else own
                col = c["teamb"][own_c] if own_c is not None else c["neutral_ball"]
                if flash < 0.12:
                    col = mix(col, (255, 255, 255), 0.6 * (1 - flash / 0.12))
                f = 1 - (self.time - t) / dur
                pts.append((self.to_c(x, y), col, max(0.0, f)))
            surf = self.add.surf
            for k in range(1, len(pts)):
                (p0, _, _), (p1, col, f) = pts[k - 1], pts[k]
                if f <= 0:
                    continue
                w = max(1, int(2 * r * ws * f))
                if tg > 0:
                    gw = int(w * 2.4) + 2
                    self.add.mark(pygame.draw.line(surf, scale(col, 0.32 * tg * f * ta * ball_a), p0, p1, gw))
                cc = scale(col, f * ta * ball_a)
                self.add.mark(pygame.draw.line(surf, cc, p0, p1, w))
                if w > 3:
                    pygame.draw.circle(surf, cc, (int(p1[0]), int(p1[1])), w // 2)
                if smart and k % 2 == 0:
                    sc = scale(c["smart"], f * 0.9)
                    self.add.mark(pygame.draw.circle(surf, sc, (int(p1[0]), int(p1[1])), max(1, w // 3)))

    # ---------------------------------------------------------------- shields
    def _shields(self, engine) -> None:
        g = self._g
        for eff in engine.effects.of_kind("shield"):
            j = eff.target[1]
            arc = g.goals[j]
            span = arc.span * eff.data.get("coverage", 100) / 100
            a0 = arc.center - span / 2
            pulse = 0.6 + 0.4 * math.sin(self.time * 6)
            pts = self._arc_pts(g.R - 6, a0, a0 + span)
            self.add.mark(pygame.draw.lines(self.add.surf, scale(self.c["good"], 0.5 * pulse), False, pts, 12))
            self.add.mark(pygame.draw.lines(self.add.surf, scale(self.c["good"], 0.9), False, pts, 3))

    # ---------------------------------------------------------------- paddles
    def _paddles(self, engine, alpha) -> None:
        cfg = self.cfg
        c = self.c
        for p in engine.paddles:
            i = p.idx
            th = p.prev_theta + (p.theta - p.prev_theta) * alpha
            sh = engine.paddle_shape(i, th)
            outline = [self.to_c(x, y) for x, y in sh.outline(30)]
            team = c["team"][i]
            teamb = c["teamb"][i]
            present = p.present or engine.state == "ATTRACT"
            dimk = 1.0 if present else 0.35
            pygame.draw.polygon(self.canvas, scale(mix(team, (0, 0, 0), 0.35), dimk), outline)
            # glow
            surf = self.add.surf
            self.add.mark(pygame.draw.lines(surf, scale(teamb, 0.22 * dimk), False, outline, 16))
            self.add.mark(pygame.draw.lines(surf, scale(teamb, 0.45 * dimk), False, outline, 7))
            pygame.draw.lines(self.canvas, scale(teamb, dimk), True, outline, 4)
            pygame.draw.aalines(self.canvas, scale(mix(teamb, (255, 255, 255), 0.4), dimk), True, outline)
            # size effect cues
            mult = engine.effects.paddle_mult(i, cfg["paddles.size_stacking"])
            if mult > 1.02:
                k = 0.6 + 0.4 * math.sin(self.time * 7)
                self.add.mark(pygame.draw.lines(surf, scale(c["good"], 0.8 * k), False, outline, 4))
            elif mult < 0.98:
                if int(self.time * 12) % 3 != 0:
                    self.add.mark(pygame.draw.lines(surf, scale(c["bad"], 0.85), False, outline, 3))
            # active effects affecting this player: icons with countdown rings, behind the paddle
            effs = engine.effects.player_effects(i)
            if effs:
                n = len(effs)
                rb = sh.rb + min(22.0, max(14.0, (engine.geom.R - sh.rb) * 0.55))
                for k, eff in enumerate(effs):
                    t = engine.types.get(eff.type_id)
                    cls = cfg.get(f"powerups.types.{eff.type_id}.class", "neutral")
                    ccol = c["class"].get(cls, c["neutral"])
                    if eff.collector is not None and eff.collector != i and cls == "good":
                        ccol = c["bad"]  # good for the collector = bad for this player
                    a = math.radians(th + (k - (n - 1) / 2) * 7.5)
                    x, y = rb * math.cos(a), rb * math.sin(a)
                    sx, sy = self.to_c(x, y)
                    ic = self.icons.icon(t.icon if t else "", eff.type_id, 18)
                    self.canvas.blit(ic, (int(sx - 9), int(sy - 9)))
                    rect = pygame.Rect(0, 0, 28, 28)
                    rect.center = (int(sx), int(sy))
                    self.add.mark(pygame.draw.arc(surf, ccol, rect, math.pi / 2, math.pi / 2 + math.tau * eff.frac, 3))

    # ---------------------------------------------------------------- balls
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
            spd = engine.effects.ball_has(b.id, "ball_speed")
            if spd is not None and spd.value > 1 and not b.held and self.rng.random() < 0.7:
                ang = math.atan2(b.vy, b.vx) + math.pi
                self.particles.burst(x, y, (255, 150, 60), 2, (60, 200), (0.15, 0.35), (1.5, 3.0), cap=cap,
                                     direction=ang, spread=0.5)
            if engine.time < b.smart_until and self.rng.random() < 0.6:
                self.particles.burst(x, y, c["smart"], 1, (20, 90), (0.2, 0.5), cap=cap)
            if engine.effects.ball_has(b.id, "wobble") is not None and self.rng.random() < 0.5:
                self.particles.burst(x, y, c["neutral"], 1, (20, 80), (0.2, 0.5), cap=cap)
            body = pygame.Surface((int(4 * r + 8), int(4 * r + 8)), pygame.SRCALPHA)
            C2 = body.get_width() // 2
            ring = c["smart"] if engine.time < b.smart_until else col
            pygame.draw.circle(body, (*ring, int(255 * max(a, 0.6 if not b.scored else a))), (C2, C2), int(r + 3), 3)
            pygame.draw.circle(body, (*c["ball_core"], int(255 * a)), (C2, C2), int(r))
            pygame.draw.circle(body, (*mix(c["ball_core"], col, 0.35), int(200 * a)), (C2 + int(r * 0.25), C2 + int(r * 0.25)),
                               max(1, int(r * 0.45)))
            if b.owner is not None and engine.effects.for_player(b.owner, "bull") is not None:
                pygame.draw.circle(body, (*c["smart"], int(200 * a)), (C2, C2), int(r + 7), 2)
            self.canvas.blit(body, (int(sx - C2), int(sy - C2)))

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
            self.add.mark(pygame.draw.circle(self.add.surf, col, (int(sx), int(sy)), max(1, int(r)),
                                             max(1, int(rg["w"] * (1 - t * 0.5)))))
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
                sh = engine.paddle_shape(aff[1])
                tx, ty = sh.apex()
            elif aff and aff[0] == "ball":
                for b in engine.balls:
                    if b.id == aff[1]:
                        tx, ty = b.x, b.y
            e = t * t * (3 - 2 * t)
            x = fl["x"] + (tx - fl["x"]) * e
            y = fl["y"] + (ty - fl["y"]) * e
            size = int(34 * (1 - 0.4 * t))
            ic = self.icons.icon(fl["icon"], fl["type_id"], size)
            ic = ic.copy()
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
            x, y = g.R * math.cos(a), g.R * math.sin(a)
            spr = self.glow.sprite((255, 255, 255), 60, 1.0)
            self.canvas.blit(spr, [int(v - 60) for v in self.to_c(x, y)], special_flags=pygame.BLEND_ADD)

    def _attract(self, engine) -> None:
        cfg = self.cfg
        g = self._g
        self.dim.set_alpha(int(255 * (1 - cfg["match.attract_opacity"])))
        self.canvas.blit(self.dim, (0, 0))
        R = g.R
        pulse = 0.65 + 0.35 * math.sin(self.time * 2.4)
        self._text_at(cfg["text.title"], int(cfg["text.banner_size"] * 1.8), (255, 255, 255), 0, R * 0.16,
                      key="persian_title", outline=3)
        self._text_at(cfg["text.subtitle"], int(cfg["text.banner_size"] * 0.6), self.c["p1b"], 0, R * 0.0,
                      key="latin")
        self._text_at(cfg["text.attract_prompt"], cfg["text.toast_size"], (255, 255, 255), 0, -R * 0.3, alpha=pulse)

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
        self._text_at(text, size, col, 0, 0, key=key, alpha=a, scale_k=k, outline=3)

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
            pygame.draw.line(self.canvas, colk, p1, (sx, sy), 4)
            pygame.draw.line(self.canvas, colk, p2, (sx, sy), 4)

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
                          key="persian_title", scale_k=k, outline=3)
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
            self._text_at(cfg["text.winner"], int(cfg["text.banner_size"] * 1.1), c["teamb"][w], bx + ux * R * 0.27,
                          by + uy * R * 0.27, key="persian_title", outline=3)
            k = 1 + 0.08 * math.sin(self.time * 4)
            ic = self.icons.icon("trophy", "_trophy", int(84 * k), c["smart"])
            sx, sy = self.to_c(bx + ux * R * 0.48, by + uy * R * 0.48)
            ic = self._rot(ic)
            self.canvas.blit(ic, (int(sx - ic.get_width() / 2), int(sy - ic.get_height() / 2)))
        else:
            self._text_at(cfg["text.draw"], int(cfg["text.banner_size"] * 1.3), (255, 255, 255), 0, R * 0.18,
                          key="persian_title", outline=3)
        for i in (0, 1):
            gx, gy = g.goal_dir[i]
            dx, dy = math.cos(math.radians(270 + g.rot)), math.sin(math.radians(270 + g.rot))
            self._text_at(str(engine.scores[i]), int(cfg["hud.score_size"] * 1.5), c["teamb"][i],
                          gx * R * 0.5 + dx * R * 0.04, gy * R * 0.5 + dy * R * 0.04, key="digits", outline=3)
        self._text_at(cfg["text.slogan"], int(cfg["text.toast_size"] * 0.85), (255, 255, 255), 0, -R * 0.55,
                      alpha=min(1.0, st_t / 0.8))

    def _toasts(self, engine) -> None:
        cfg = self.cfg
        g = self._g
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
                px, py = -gy, gx  # perpendicular
                off = (n - 0.5) * t["size"] * 1.35
                x, y = gx * rr + px * off, gy * rr + py * off
                if cfg["hud.orientation"] == "toward_players":
                    extra = -90.0 if side == 0 else 90.0
            self._text_at(t["text"], t["size"], t["color"], x, y, alpha=a, scale_k=k, extra_rot=extra, outline=3)
        self.toasts = keep

    def _absent(self, engine) -> None:
        if engine.state == "ATTRACT":
            return
        cfg = self.cfg
        for p in engine.paddles:
            if not p.present:
                sh = engine.paddle_shape(p.idx)
                ax, ay = sh.apex()
                k = 0.7
                extra = 0.0
                if cfg["hud.orientation"] == "toward_players":
                    extra = -90.0 if p.idx == 0 else 90.0
                self._text_at(cfg["text.step_in"], int(cfg["text.toast_size"] * 0.7), self.c["teamb"][p.idx],
                              ax * k, ay * k, alpha=0.6 + 0.4 * math.sin(self.time * 4), extra_rot=extra)
