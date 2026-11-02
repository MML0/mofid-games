#!/usr/bin/env python3
"""Export every screen, power-up and visual effect of the game for the designer, into design/states/.

    .venv/bin/python tools/export_design_states.py

Each scene is staged in the real engine and renderer (headless) with the current config/settings.json, then saved as:
  frame.png            the exact 1080x1080 game frame
  bloom.png            only the additive light layer (glows, trails, particles) on black: use it with Screen / Add
  layout.svg           editable vector rebuilt from the same moment, with named layers and live Persian text
  layout_outlined.svg  the same with the text converted to curves (needs pymupdf in the system python3)
  layout.pdf           the same as a one-page vector PDF
plus design/states/elements_png/ (transparent sprites) and design/MarketHockey_Screens_and_Effects.pdf (one page per
screen, power-up and feature). The settings file is only read, never written.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import export_design_kit as kit  # noqa: E402
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from market_hockey.config import Config  # noqa: E402
from market_hockey.core.engine import Engine  # noqa: E402
from market_hockey.inputs.ai import AIAdapter  # noqa: E402
from market_hockey.paths import SETTINGS_PATH  # noqa: E402
from market_hockey.render.colors import boost, hex_rgb, mix  # noqa: E402
from market_hockey.render.renderer import Renderer  # noqa: E402

OUT = ROOT / "design" / "states"
CATALOG = ROOT / "design" / "MarketHockey_Screens_and_Effects.pdf"
HZ, FPS = 240, 60
hx, fm = kit.hx, kit.f
WEIGHT = {"persian_title": 900, "digits": 900, "persian": 700, "latin": 700}


class RecRenderer(Renderer):
    """The real renderer, also recording what the vector export needs: the text it draws and the bloom layer."""

    grab = False
    bloom = None

    def render(self, engine, alpha, dt):
        self.texts = []
        return super().render(engine, alpha, dt)

    def _text_at(self, text, size, color, x, y, key="persian", alpha=1.0, scale_k=1.0, extra_rot=0.0, outline=2,
                 glow=0.0, reserve=False, avoid=False, axis=None, at=None):
        rect = super()._text_at(text, size, color, x, y, key=key, alpha=alpha, scale_k=scale_k, extra_rot=extra_rot,
                                outline=outline, glow=glow, reserve=reserve, avoid=avoid, axis=axis, at=at)
        self.texts.append(dict(text=text, size=size * scale_k, color=color, alpha=alpha, key=key, center=rect.center,
                               rot=self._g.rot + extra_rot))
        return rect

    def _flights(self, engine):  # called right after the additive layer is composited
        if self.grab:
            self.bloom = self.add.surf.copy()
        super()._flights(engine)


class Scene:
    def __init__(self, seed=7, spawn=False, **values):
        self.cfg = Config.load(SETTINGS_PATH)
        for tid in self._types():
            self.cfg.set(f"powerups.types.{tid}.enabled", True)
        for k, v in values.items():
            self.cfg.set(k.replace("__", "."), v)
        self.eng = Engine(self.cfg, random.Random(seed))
        self.ai = AIAdapter(self.cfg, random.Random(seed + 1))
        self.rend = RecRenderer(self.cfg, random.Random(seed + 2))
        self.t = 0.0
        if not spawn:
            self.eng._update_spawner = lambda dt, demo: None

    @staticmethod
    def _types():
        from market_hockey.powerups import registry
        return registry.all_types()

    def run(self, seconds):
        for _ in range(max(1, round(seconds * FPS))):
            dt = 1 / FPS
            samples = {i: self.ai.sample(i, self.t, dt, self.eng) for i in (0, 1)}
            for _ in range(HZ // FPS):
                self.eng.step(1 / HZ, samples, [True, True])
            self.t += dt
            self.rend.handle_events(self.eng.drain_events(), self.eng)
            self.rend.render(self.eng, 0.5, dt)
        return self

    def hold(self, seconds):
        """Let only the visuals advance (the moment stays staged)."""
        self.rend.handle_events(self.eng.drain_events(), self.eng)
        for _ in range(max(1, round(seconds * FPS))):
            self.rend.render(self.eng, 0.5, 1 / FPS)
        return self

    def until(self, test, limit=12.0):
        for _ in range(int(limit * FPS)):
            if test():
                return True
            self.run(1 / FPS)
        return False

    def play(self, scores=(0, 0)):
        self.eng.start_match()
        self.until(lambda: self.eng.state == "PLAYING", 12)
        self.eng.scores = list(scores)
        return self

    def rally(self):
        """A ball on its way across the middle after a real paddle hit."""
        def ok():
            live = self.eng.live_balls()
            return live and live[0].owner is not None and live[0].hits >= 1 and math.hypot(live[0].x, live[0].y) < 200
        self.until(ok, 14)
        return self.eng.live_balls()[0]

    def orb(self, tid):
        self.eng.force_spawn(tid)
        return self.eng.orbs[-1]

    def finish(self, scores, names=("سارا", "علی")):
        self.eng.set_names(*names)
        self.play()
        self.eng.scores = list(scores)
        self.eng.time_left = 0.02
        return self


# ======================================================================= frame -> vector
class Vector:
    """Rebuilds the current moment as named SVG layers, in the same draw order as Renderer.render."""

    def __init__(self, s: Scene):
        self.s, self.eng, self.rend, self.cfg = s, s.eng, s.rend, s.cfg
        self.c = kit.palette(self.cfg)
        self.c.update(good=hex_rgb(self.cfg["colors.good"]))
        self.A = kit.Arena(self.cfg, self.c)
        self.g = self.A.g
        self.defs = [self.A.defs()]
        self.grads = set()
        self.uid = 0

    def P(self, x, y):
        return self.g.cx + x, self.g.cy - y

    def next_uid(self):
        self.uid += 1
        return f"u{self.uid}"

    def glow(self, sx, sy, r, col, inten) -> str:
        """Same falloff as GlowCache.sprite."""
        key = hx(col)[1:]
        if key not in self.grads:
            self.grads.add(key)
            stops = "".join(f'<stop offset="{d}" stop-color="#{key}" stop-opacity="{fm(math.exp(-d * d * 3.2) * (1 - d * d) ** 1.5)}"/>'
                            for d in (0, .15, .3, .45, .6, .75, .9, 1))
            self.defs.append(f'<radialGradient id="g_{key}">{stops}</radialGradient>')
        return (f'<circle cx="{fm(sx)}" cy="{fm(sy)}" r="{fm(r)}" fill="url(#g_{key})" '
                f'opacity="{fm(max(0, min(1, inten)))}"/>')

    @staticmethod
    def fx(name, items) -> str:
        return f'<g id="{name}" style="mix-blend-mode:screen">{"".join(items)}</g>' if items else ""

    def team(self, i, kind="glow"):
        return self.c[f"p{i + 1}_{kind}"]

    # ---- layers
    def ambient(self):
        r = self.rend
        if not self.cfg["fx.ambient_chart"] or not r.ambient:
            return ""
        x0 = -self.g.R - 30 - r._amb_scroll
        pts = " ".join("{},{}".format(*map(fm, self.P(x0 + k * 30, y))) for k, (y, _) in enumerate(r.ambient))
        a = min(1, self.cfg["fx.ambient_alpha"] * 2.2)
        return (f'<g id="Ambient_market_chart"><polyline points="{pts}" fill="none" stroke="{hx(self.c["lines"])}" '
                f'stroke-opacity="{fm(a)}" stroke-width="2"/></g>')

    def flash(self):
        if not self.rend.flash:
            return ""
        t0, col, inten = self.rend.flash
        k = 1 - (self.rend.time - t0) / 0.35
        if k <= 0:
            return ""
        a = min(0.6, self.cfg["fx.flash_max_alpha"] * inten) * k * k
        return (f'<g id="Screen_flash" style="mix-blend-mode:screen"><circle cx="{fm(self.g.cx)}" cy="{fm(self.g.cy)}" '
                f'r="{fm(self.g.mask_r)}" fill="{hx(col)}" opacity="{fm(a)}"/></g>')

    def wall_fx(self):
        g, out = self.g, []
        for wi, ang, t0 in self.rend.wall_hits:
            age = self.rend.time - t0
            k = max(0.0, 1 - age / 0.7)
            ar = math.radians(ang)
            out.append(self.glow(*self.P(g.wall_face * math.cos(ar), g.wall_face * math.sin(ar)), g.t * 3.2, self.c["wall_glow"], 1.1 * k))
        return self.fx("Wall_hit_flash", out)

    def final_pulse(self):
        e, cfg = self.eng, self.cfg
        if e.state not in ("PLAYING", "SERVE") or e.golden or e.time_left > cfg["hud.final_seconds"] or not cfg["fx.final_pulse"]:
            return ""
        return (f'<g id="Final_seconds_pulse" style="mix-blend-mode:screen"><circle cx="{fm(self.g.cx)}" cy="{fm(self.g.cy)}" '
                f'r="{fm(self.g.wall_face - 4)}" fill="none" stroke="{hx(self.c["timer_final"])}" stroke-width="10" stroke-opacity="0.2"/></g>')

    def goal_flash(self):
        if not self.rend.goal_flash:
            return ""
        idx, t0, _ = self.rend.goal_flash
        k = max(0.0, 1 - (self.rend.time - t0))
        arc = self.g.goals[idx]
        lw = self.cfg["goals.line_width"]
        return (f'<g id="Goal_flash" style="mix-blend-mode:screen"><path d="{self.A.arc_d(self.g.R, arc.start, arc.end)}" fill="none" '
                f'stroke="{hx(self.c["goal"])}" stroke-width="{fm(lw * 5)}" stroke-opacity="{fm(0.7 * k)}"/></g>')

    def orbs(self):
        cfg, out, tether = self.cfg, [], []
        orb_r = cfg["powerups.orb_radius"]
        for o in self.eng.orbs:
            t = self.eng.types.get(o.type_id)
            k, a = 1.0, 1.0
            if o.state == "spawning":
                from market_hockey.render.renderer import ease_out_back
                k = ease_out_back(o.state_t / max(0.01, cfg["powerups.spawn_anim_s"]))
            elif o.state == "despawning":
                k = a = 1 - o.state_t / 0.3
            elif o.state == "collected":
                k, a = 1 + o.state_t * 2.2, max(0.0, 1 - o.state_t / 0.45)
            if k <= 0.02 or a <= 0.02:
                continue
            x = o.x + math.sin(self.rend.time * 60) * o.wobble * 10
            y = o.y + math.sin(self.rend.time * 2.2 + o.id) * cfg["powerups.bob_px"]
            sx, sy = self.P(x, y)
            col = self.c[o.cls if o.cls in ("good", "bad") else "neutral"]
            off = math.hypot(o.x - o.hx, o.y - o.hy)
            if cfg["powerups.magnet.show_tether"] and off > 5:
                hxp, hyp = self.P(o.hx, o.hy)
                tether.append(f'<line x1="{fm(hxp)}" y1="{fm(hyp)}" x2="{fm(sx)}" y2="{fm(sy)}" stroke="{hx(col)}" stroke-opacity="0.45" '
                              f'stroke-width="4" stroke-linecap="round" stroke-dasharray="0.1 9"/>')
            uid = self.next_uid()
            d, b = kit.orb_body(t.icon if t else "", o.cls, self.c, orb_r, cfg["powerups.icon_scale"], uid=uid)
            rem = max(0.0, 1 - o.age / max(0.01, o.life)) if o.state in ("spawning", "idle") else 0.0
            circ = 2 * math.pi * (orb_r + 7)
            b = re.sub(r'stroke-dasharray="[\d.]+ 9999"', f'stroke-dasharray="{fm(circ * rem)} 9999"', b)
            self.defs.append(d)
            out.append(f'<g id="Orb_{o.type_id}_{o.state}" opacity="{fm(a)}" transform="translate({fm(sx)} {fm(sy)}) scale({fm(k)}) '
                       f'translate({fm(-2 * orb_r)} {fm(-2 * orb_r)})">{b}</g>')
        s = '<g id="Orb_tethers">' + "".join(tether) + "</g>" if tether else ""
        return f'<g id="Orbs">{s}{"".join(out)}</g>' if out else ""

    def predictions(self):
        cfg, out = self.cfg, []
        sp = cfg["prediction.dot_spacing"]
        for pr in self.eng.predictions.values():
            pts = pr.points
            strong = getattr(pr, "strong", True)
            if len(pts) < 2:
                continue
            ka = 1.0 if strong else cfg["prediction.assist_alpha"]
            dr = cfg["prediction.dot_radius"] * (1.0 if strong else cfg["prediction.assist_dot_scale"])
            dot = hx(mix(self.team(pr.receiver), (255, 255, 255), 0.35))
            segs = [math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]) for k in range(1, len(pts))]
            total = sum(segs)
            d = 0.0 if strong else total * (1.0 - cfg["prediction.assist_path_fraction"])
            k, acc = 0, 0.0
            while d < total and k < len(segs):
                while k < len(segs) and acc + segs[k] < d:
                    acc += segs[k]
                    k += 1
                if k >= len(segs):
                    break
                f = (d - acc) / max(1e-6, segs[k])
                x, y = self.P(pts[k][0] + (pts[k + 1][0] - pts[k][0]) * f, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * f)
                out.append(f'<circle cx="{fm(x)}" cy="{fm(y)}" r="{fm(dr)}" fill="{dot}" fill-opacity="{fm(min(1, (0.35 + 0.65 * d / total) * ka * 1.4))}"/>')
                d += sp
            if pr.contact:
                gx, gy = self.P(*pr.contact)
                r = cfg["ball.radius"] * (1.0 if strong else cfg["prediction.assist_ghost_scale"])
                if strong or cfg["prediction.assist_ghost"]:
                    out.append(f'<g id="Ghost_ball"><circle cx="{fm(gx)}" cy="{fm(gy)}" r="{fm(r)}" fill="{dot}" fill-opacity="0.3" stroke="{dot}" '
                               f'stroke-opacity="{fm(cfg["prediction.ghost_alpha"])}" stroke-width="2"/></g>')
                if pr.out_dir and not pr.goal and (strong or cfg["prediction.assist_arrow"]):
                    L = cfg["prediction.arrow_length"] if strong else cfg["prediction.assist_arrow_length"]
                    ex, ey = self.P(pr.contact[0] + pr.out_dir[0] * L, pr.contact[1] + pr.out_dir[1] * L)
                    ang = math.atan2(ey - gy, ex - gx)
                    head = "".join(f'<line x1="{fm(ex)}" y1="{fm(ey)}" x2="{fm(ex - 11 * math.cos(ang + a))}" y2="{fm(ey - 11 * math.sin(ang + a))}" '
                                   f'stroke="{dot}" stroke-width="{3 if strong else 1}"/>' for a in (-.6, .6))
                    dash = "" if pr.intercept else ' stroke-dasharray="10 10"'
                    out.append(f'<g id="Bounce_arrow" opacity="{fm(min(1, ka * (1 if strong else 2.2)))}"><line x1="{fm(gx)}" y1="{fm(gy)}" x2="{fm(ex)}" y2="{fm(ey)}" '
                               f'stroke="{dot}" stroke-width="{3 if strong else 1}"{dash}/>{head}</g>')
        return self.fx("Trajectory_prediction", out)

    def trails(self):
        cfg, r, out = self.cfg, self.rend, []
        balls = {b.id: b for b in self.eng.balls}
        for bid, tr in r.trails.items():
            b = balls.get(bid)
            if b is None or len(tr) < 2:
                continue
            dur = cfg["trails.duration_s"] * (cfg["trails.speedup_length_mult"] if self.eng.speed_mult(b) > 1.01 else 1)
            own = b.owner
            col, core = (self.team(own), self.team(own, "core")) if own is not None else (self.c["neutral_ball"], (255, 255, 255))
            ba = self.eng.effects.ball_alpha(bid)
            step = max(1, len(tr) // 36)
            pts = tr[::step] + [tr[-1]]
            halo, body = [], []
            for p, q in zip(pts, pts[1:]):
                age = (r.time - q[0]) / dur
                if age >= 1:
                    continue
                k = (1 - age) ** cfg["trails.falloff"]
                rad = b.r * cfg["trails.head_size"] * (0.22 + 0.78 * k)
                (x1, y1), (x2, y2) = self.P(p[1], p[2]), self.P(q[1], q[2])
                ln = f'x1="{fm(x1)}" y1="{fm(y1)}" x2="{fm(x2)}" y2="{fm(y2)}"'
                halo.append(f'<line {ln} stroke="{hx(col)}" stroke-width="{fm(rad * 2.8)}" stroke-opacity="{fm(k * ba * 0.3 * cfg["trails.glow"])}"/>')
                body.append(f'<line {ln} stroke="{hx(core)}" stroke-width="{fm(rad * 1.15)}" stroke-opacity="{fm(k * ba * 0.85)}" stroke-linecap="round"/>')
            out.append(f'<g id="Trail_ball_{bid}"><g id="Trail_glow">{"".join(halo)}</g><g id="Trail_core">{"".join(body)}</g></g>')
        return self.fx("Trails", out)

    def shields(self):
        out = []
        for eff in self.eng.effects.of_kind("shield"):
            arc = self.g.goals[eff.target[1]]
            span = arc.span * eff.data.get("coverage", 100) / 100
            a0 = arc.center - span / 2
            d = self.A.arc_d(self.g.R - 6, a0, a0 + span)
            good = hx(self.c["good"])
            out.append(f'<g id="Shield_P{eff.target[1] + 1}"><path d="{d}" fill="none" stroke="{good}" stroke-opacity="0.3" stroke-width="26"/>'
                       f'<path d="{d}" fill="none" stroke="{good}" stroke-width="6"/></g>')
        return self.fx("Shields", out)

    def paddles(self):
        cfg, e, out = self.cfg, self.eng, []
        for p in e.paddles:
            i = p.idx
            sh = e.paddle_shape(i, p.theta)
            pts = [self.P(x, y) for x, y in sh.outline(48)]
            inner = [self.P(x, y) for x, y in sh.outline(48, inset=6.0)][3:-3]
            team, glow = self.c[f"p{i + 1}"], self.team(i)
            present = p.present or e.state == "ATTRACT"
            mult = e.effects.paddle_mult(i, cfg["paddles.size_stacking"])
            edge = glow
            if mult > 1.02:
                edge = mix(glow, self.c["good"], 0.6)
            elif mult < 0.98:
                edge = mix(glow, self.c["bad"], 0.6)
            d = "M " + " L ".join(f"{fm(x)} {fm(y)}" for x, y in pts) + " Z"
            dd = "M " + " L ".join(f"{fm(x)} {fm(y)}" for x, y in inner)
            state = "bigger" if mult > 1.02 else "smaller" if mult < 0.98 else "normal"
            parts = [f'<path id="Glow" d="{d}" fill="none" stroke="{hx(glow)}" stroke-opacity="0.22" stroke-width="16" stroke-linejoin="round"/>',
                     f'<path id="Fill" d="{d}" fill="{hx(mix(team, (0, 0, 0), .38))}"/>',
                     f'<path id="Inner_highlight" d="{dd}" fill="none" stroke="{hx(mix(team, (255, 255, 255), .12))}" stroke-width="5" stroke-linecap="round"/>',
                     f'<path id="Edge" d="{d}" fill="none" stroke="{hx(edge)}" stroke-width="3.5" stroke-linejoin="round"/>',
                     f'<path id="Edge_highlight" d="{d}" fill="none" stroke="{hx(mix(glow, (255, 255, 255), .55))}" stroke-width="1.2" stroke-linejoin="round"/>']
            effs = e.effects.player_effects(i)
            rb = sh.rb + min(22.0, max(14.0, (self.g.R - sh.rb) * 0.55))
            for kk, eff in enumerate(effs):
                t = e.types.get(eff.type_id)
                cls = cfg.get(f"powerups.types.{eff.type_id}.class", "neutral")
                col = self.c[cls if cls in ("good", "bad") else "neutral"]
                if eff.collector is not None and eff.collector != i and cls == "good":
                    col = self.c["bad"]
                a = math.radians(p.theta + (kk - (len(effs) - 1) / 2) * 7.5)
                sx, sy = self.P(rb * math.cos(a), rb * math.sin(a))
                L = 2 * math.pi * 13
                parts.append(f'<g id="Active_effect_{eff.type_id}"><g transform="translate({fm(sx - 9)} {fm(sy - 9)}) scale(0.18)">{kit.icon_body(t.icon if t else "")}</g>'
                             f'<circle cx="{fm(sx)}" cy="{fm(sy)}" r="13" fill="none" stroke="{hx(col)}" stroke-width="3" '
                             f'stroke-dasharray="{fm(L * eff.frac)} 999" transform="rotate(-90 {fm(sx)} {fm(sy)})"/></g>')
            out.append(f'<g id="Paddle_P{i + 1}_{state}" opacity="{1 if present else 0.35}">{"".join(parts)}</g>')
        return f'<g id="Paddles">{"".join(out)}</g>'

    def balls(self):
        cfg, e, out = self.cfg, self.eng, []
        for b in e.balls:
            if b.removed:
                continue
            a = e.effects.ball_alpha(b.id)
            if b.scored:
                a *= max(0.0, 1 - (e.time - b.scored_t) / 0.5)
            if a <= 0:
                continue
            smart = e.time < b.smart_until
            uid = self.next_uid()
            d, body, size = kit.ball_body(self.c, b.owner, b.r, smart, uid)
            self.defs.append(d)
            sx, sy = self.P(b.x, b.y)
            bull = ""
            if b.owner is not None and e.effects.for_player(b.owner, "bull") is not None:
                bull = (f'<circle id="Bull_ring" cx="{fm(size / 2)}" cy="{fm(size / 2)}" r="{fm(b.r + 7)}" fill="none" '
                        f'stroke="{hx(self.c["smart"])}" stroke-width="2"/>')
            state = "gold" if smart else "held" if b.held else "neutral" if b.owner is None else f"P{b.owner + 1}"
            out.append(f'<g id="Ball_{b.id}_{state}" opacity="{fm(a)}" transform="translate({fm(sx - size / 2)} {fm(sy - size / 2)})">{body}{bull}</g>')
        return f'<g id="Balls">{"".join(out)}</g>' if out else ""

    def chaos(self):
        out, col = [], self.c["neutral"]
        colb = boost(col, 0.35)
        for b in self.eng.balls:
            ch = b.chaos
            if not ch or b.removed:
                continue
            sx, sy = self.P(b.x, b.y)
            if ch["stage"] == "intro":
                out.append(self.glow(sx, sy, b.r * 4.6, colb, 0.9))
                out.append(f'<circle id="Charging_ring" cx="{fm(sx)}" cy="{fm(sy)}" r="{fm(b.r * 3.4)}" fill="none" stroke="{hx(colb)}" stroke-width="2" stroke-dasharray="19 15"/>')
            elif ch["stage"] == "select" and ch["candidates"]:
                n = len(ch["candidates"])
                t = ch["t"] / max(0.01, ch.get("select_len", ch["p"]["select_s"]))
                locked = t >= 0.82
                from market_hockey.render.renderer import ease_out_cubic
                total = (2 if ch["rolls_done"] == 0 else 1) * n + ch["chosen"]
                hi = ch["chosen"] if locked else int(ease_out_cubic(t / 0.82) * total) % n
                out.append(self.glow(sx, sy, b.r * 3.6, colb, 0.75))
                for j, a in enumerate(ch["candidates"]):
                    dx, dy = math.cos(a), -math.sin(a)
                    bright = j == hi
                    L = ch["p"].get("ray_length", 70) * (1.3 if bright and locked else 1)
                    c2 = "#FFFFFF" if bright and locked else hx(colb if bright else col)
                    out.append(f'<line id="Ray_{j}{"_selected" if bright else ""}" x1="{fm(sx + dx * b.r * 1.5)}" y1="{fm(sy + dy * b.r * 1.5)}" x2="{fm(sx + dx * L)}" y2="{fm(sy + dy * L)}" '
                               f'stroke="{c2}" stroke-width="{4 if bright else 2}" stroke-opacity="{1 if bright else .4}" stroke-linecap="round" stroke-dasharray="0.1 7"/>')
        return self.fx("Random_path_sequence", out)

    def pending(self):
        out = []
        for pm in self.rend.pending_marks:
            k = min(1.0, (self.rend.time - pm["t0"]) / pm["dur"])
            sx, sy = self.P(pm["x"], pm["y"])
            rr = pm["r"] * (4.0 - 2.8 * (1 - (1 - k) ** 3))
            out.append(self.glow(sx, sy, pm["r"] * (1.5 + 2.5 * k), pm["color"], 0.25 + 0.6 * k))
            out.append(f'<circle cx="{fm(sx)}" cy="{fm(sy)}" r="{fm(rr)}" fill="none" stroke="{hx(pm["color"])}" stroke-width="2" stroke-opacity="{fm(0.35 + 0.65 * k)}"/>')
        return self.fx("Second_ball_telegraph", out)

    def rings(self):
        out = []
        for rg in self.rend.rings:
            t = (self.rend.time - rg["t0"]) / rg["dur"]
            if t >= 1:
                continue
            r = rg["r0"] + (rg["r1"] - rg["r0"]) * (1 - (1 - t) ** 2)
            sx, sy = self.P(rg["x"], rg["y"])
            out.append(f'<circle cx="{fm(sx)}" cy="{fm(sy)}" r="{fm(r)}" fill="none" stroke="{hx(rg["color"])}" '
                       f'stroke-opacity="{fm((1 - t) * 0.9)}" stroke-width="{fm(max(1, rg["w"] * (1 - t * 0.5)))}"/>')
        return self.fx("Impact_rings", out)

    def particles(self):
        out = []
        for p in self.rend.particles.items[:220]:
            k = p[4] / max(1e-3, p[5])
            sx, sy = self.P(p[0], p[1])
            out.append(self.glow(sx, sy, max(2.0, p[7] * 3), p[6], k))
        return self.fx("Particles", out)

    def telegraph(self):
        e = self.eng
        if e.state != "SERVE" or not self.cfg["serve.show_telegraph"] or not e.live_balls():
            return ""
        b = e.live_balls()[0]
        dx, dy = self.g.goal_dir[e.serve_receiver]
        col = hx(self.team(e.serve_receiver))
        out = []
        a = math.atan2(-dy, dx)
        for k in range(3):
            ph = (self.rend.time * 2.2 + k / 3) % 1.0
            sx, sy = self.P(b.x + dx * (30 + ph * 70), b.y + dy * (30 + ph * 70))
            p1 = (sx - 12 * math.cos(a - .7), sy - 12 * math.sin(a - .7))
            p2 = (sx - 12 * math.cos(a + .7), sy - 12 * math.sin(a + .7))
            out.append(f'<polyline points="{fm(p1[0])},{fm(p1[1])} {fm(sx)},{fm(sy)} {fm(p2[0])},{fm(p2[1])}" fill="none" stroke="{col}" stroke-width="4" stroke-opacity="{fm(1 - ph)}"/>')
        return f'<g id="Serve_direction_arrows">{"".join(out)}</g>'

    def dim(self):
        e, g = self.eng, self.g
        a = 0.0
        if e.paused:
            a = 140 / 255
        elif e.state == "ATTRACT":
            a = 1 - self.cfg["match.attract_opacity"]
        elif e.state in ("FINAL", "RESULT"):
            a = 110 / 255
        elif e.state == "INTRO":
            a = (1 - min(1.0, e.state_t / max(0.05, self.cfg["match.intro_s"]))) * 0.85
        if a <= 0:
            return ""
        return f'<g id="Dim_overlay"><circle cx="{fm(g.cx)}" cy="{fm(g.cy)}" r="{fm(g.mask_r)}" fill="#000000" opacity="{fm(a)}"/></g>'

    def winner(self):
        e, g, c = self.eng, self.g, self.c
        w = e.winner
        if e.state != "RESULT" or w is None:
            return ""
        a0 = 90 + g.rot if w == 0 else -90 + g.rot
        x0, y0 = self.A.P(g.wall_face, a0)
        x1, y1 = self.A.P(g.wall_face, a0 + 180)
        wedge = (f'<path id="Winner_half" d="M {fm(x0)} {fm(y0)} A {fm(g.wall_face)} {fm(g.wall_face)} 0 0 0 {fm(x1)} {fm(y1)} Z" '
                 f'fill="{hx(self.team(w))}" opacity="0.14" style="mix-blend-mode:screen"/>')
        gx, gy = g.goal_dir[w]
        ux, uy = math.cos(math.radians(90 + g.rot)), math.sin(math.radians(90 + g.rot))
        sx, sy = self.P(gx * g.R * .5 + ux * g.R * .48, gy * g.R * .5 + uy * g.R * .48)
        trophy = (f'<g id="Trophy">{self.glow(sx, sy, 70, c["smart"], .5)}<g transform="translate({fm(sx - 42)} {fm(sy - 42)}) scale(0.84)">'
                  f'{kit.icon_body("trophy", color=hx(c["smart"]))}</g></g>')
        return f'<g id="Winner_highlight">{wedge}{trophy}</g>'

    def texts(self):
        out = []
        for t in self.rend.texts:
            if t["alpha"] <= 0.02:
                continue
            x, y = t["center"]
            extra = f'fill-opacity="{fm(t["alpha"])}"'
            if abs(t["rot"]) > 0.01:
                extra += f' transform="rotate({fm(-t["rot"])} {x} {y})"'
            if t["key"] in ("digits", "latin"):
                extra += ' direction="ltr"'
            out.append(kit.text(x, y, t["text"], t["size"], hx(t["color"]), WEIGHT.get(t["key"], 700), "middle", extra))
        return f'<g id="Text">{"".join(out)}</g>' if out else ""

    def build(self, title) -> str:
        A = self.A
        layers = [A.background(), A.center_line(), A.tracks(), A.slots(), A.rim(), A.goals(), A.walls(), self.ambient(), self.flash(),
                  self.wall_fx(), self.final_pulse(), self.goal_flash(), self.orbs(), self.predictions(), self.trails(), self.shields(),
                  self.paddles(), self.balls(), self.chaos(), self.pending(), self.rings(), self.particles(), self.telegraph(),
                  self.dim(), self.winner(), self.texts(), A.mask()]
        return kit.svg(self.g.W, self.g.H, "\n".join(x for x in layers if x), title, "".join(self.defs))


# ======================================================================= capture
SHOTS: dict[str, dict] = {}


def shot(s: Scene, sid: str, caption: str, focus=None, expect=None):
    """Save the current moment. `focus` = (arena x, y) marks the interesting spot, for a close-up in the catalogue."""
    s.rend.grab = True
    frame = s.rend.render(s.eng, 0.5, 1 / HZ)
    s.rend.grab = False
    if expect and s.eng.state != expect:
        print(f"  ! {sid}: expected state {expect}, got {s.eng.state}")
    d = OUT / sid
    d.mkdir(parents=True, exist_ok=True)
    pygame.image.save(frame, str(d / "frame.png"))
    pygame.image.save(s.rend.bloom, str(d / "bloom.png"))
    (d / "layout.svg").write_text(Vector(s).build(f"Market Hockey · {sid}"), encoding="utf-8")
    fc = None
    if focus is not None:
        g = s.eng.geom
        fc = (g.cx + focus[0], g.cy - focus[1])
    SHOTS[sid] = dict(id=sid, caption=caption, state=s.eng.state, focus=fc)
    print("  ", sid, s.eng.state)
    return sid


def ball_pos(s):
    live = s.eng.live_balls()
    return (live[0].x, live[0].y) if live else (0, 0)


def capture_screens():
    p = "screens/"
    s = Scene(seed=11, spawn=True).run(2.4)
    shot(s, p + "01_waiting", "منتظر بازیکن‌ها", expect="ATTRACT")
    s = Scene(seed=11, spawn=True)
    s.eng.set_names("سارا", "علی")
    shot(s.run(2.4), p + "02_waiting_names", "نام بازیکن‌ها ثبت شده", expect="ATTRACT")
    s = Scene(seed=7)
    s.eng.start_match()
    shot(s.run(0.45), p + "03_intro", "ورود به مسابقه: دو نور دور زمین می‌چرخند", expect="INTRO")
    for n, label, cap in (("04_ready", "ready", "آماده‌اید؟"), ("05_count3", "3", "شمارش 3"), ("06_count2", "2", "شمارش 2"),
                          ("07_count1", "1", "شمارش 1"), ("08_go", "go", "شروع!")):
        s.until(lambda: s.eng.state == "COUNTDOWN" and s.eng.countdown_info()[0] == label and s.eng.countdown_info()[1] > 0.18, 8)
        shot(s, p + n, cap, expect="COUNTDOWN")
    s = Scene(seed=4).play((1, 1))  # the arrows appear on the serve after a goal
    s.run(0.5)
    ball = s.eng.live_balls()[0]
    a = math.radians(s.eng.geom.goals[1].center)
    ball.owner, ball.x, ball.y = 0, (s.eng.geom.R - 3) * math.cos(a), (s.eng.geom.R - 3) * math.sin(a)
    ball.vx, ball.vy = 900 * math.cos(a), 900 * math.sin(a)
    s.until(lambda: s.eng.state == "SERVE" and s.eng.state_t > s.cfg["serve.delay_s"] * 0.5, 5)
    shot(s, p + "09_serve", "سرویس: فلش‌ها سمت گیرنده را نشان می‌دهند", expect="SERVE")
    s = Scene(seed=5, spawn=True).play((3, 2))
    s.eng.set_names("سارا", "علی")
    s.run(5)
    s.rally()
    shot(s, p + "10_playing", "بازی در جریان", expect="PLAYING")
    s = Scene(seed=5).play((3, 3))
    s.rally()
    s.eng.time_left = 7.4
    shot(s.run(0.3), p + "11_final_seconds", "10 ثانیه‌ی آخر: زمان قرمز و حلقه‌ی تپنده")

    for n, scorer in (("12_goal_p1", 0), ("13_goal_p2", 1)):
        s = Scene(seed=4).play((2, 2))
        s.run(0.5)
        b = s.eng.live_balls()[0]
        conceded = 1 - scorer
        a = math.radians(s.eng.geom.goals[conceded].center)
        b.owner = scorer
        b.x, b.y = (s.eng.geom.R - 3) * math.cos(a), (s.eng.geom.R - 3) * math.sin(a)
        b.vx, b.vy = 900 * math.cos(a), 900 * math.sin(a)
        goal_at = (b.x, b.y)
        s.until(lambda: s.eng.state == "GOAL" and s.eng.state_t > 0.2, 2)
        shot(s, p + n, f"گل بازیکن {scorer + 1}", goal_at, "GOAL")

    s = Scene(seed=6, match__tie_rule="golden_goal").play((2, 2))
    s.rally()
    s.eng.time_left = 0.02
    s.until(lambda: s.eng.golden, 1)
    shot(s.run(0.45), p + "14_golden_goal", "مساوی در پایان زمان، حالت گل طلایی (در تنظیمات فعلی خاموش است)")

    for n, scores, cap in (("16_result_p1_wins", (5, 3), "نتیجه: بازیکن 1 برنده، بازیکن 2 بازنده"),
                           ("17_result_p2_wins", (3, 5), "نتیجه: بازیکن 2 برنده، بازیکن 1 بازنده"),
                           ("18_result_draw", (4, 4), "نتیجه: مساوی")):
        s = Scene(seed=3).finish(scores)
        s.until(lambda: s.eng.state == "FINAL" and s.eng.state_t > 0.45, 3)
        if n.startswith("16"):
            shot(s, p + "15_final", "پایان معاملات!", expect="FINAL")
        s.until(lambda: s.eng.state == "RESULT" and s.eng.state_t > 1.5, 6)
        shot(s, p + n, cap, expect="RESULT")

    s = Scene(seed=5).play((1, 1))
    s.rally()
    s.eng.toggle_pause()
    shot(s.hold(0.1), p + "19_paused", "توقف توسط اپراتور")
    s = Scene(seed=5).play((1, 1))
    s.rally()
    s.eng.paddles[1].present = False
    shot(s.hold(0.1), p + "20_player_absent", "بازیکن از زمین خارج شده")


POWERUP_TIMES = {"expand": (.15, 1.0, 3.0), "shrink": (.15, 1.0, 3.0), "speed_up": (.15, .7, 1.6), "slow_down": (.15, .8, 2.0),
                 "dim_ball": (.15, .8, 2.0), "shield": (.15, .8, 2.5), "bull_market": (.15, .5, .85), "double_ball": (.25, .9, 2.0)}


def capture_powerups():
    for seq, (tid, t) in enumerate(Scene._types().items(), 1):
        p = f"powerups/{seq:02d}_{tid}/"
        s = Scene(seed=20 + seq).play((2, 2))
        b = s.rally()
        collector = b.owner
        o = s.orb(tid)
        s.run(0.5)
        o.x, o.y = o.hx, o.hy
        shot(s, p + "1_orb_waiting", "گوی منتظر برخورد توپ", (o.x, o.y))
        pos = (o.x, o.y)
        b = s.eng.live_balls()[0]
        s.eng._collect(o, b, collector)
        if tid == "chaos":
            def stage(name, tmin=0.0):
                s.until(lambda: any(x.chaos and x.chaos["stage"] == name and x.chaos["t"] >= tmin for x in s.eng.live_balls()), 3)
            s.run(1 / FPS)
            stage("intro", 0.2)
            shot(s, p + "2_announce", "توقف توپ و اعلام رویداد", ball_pos(s))
            stage("select", 0.15)
            shot(s, p + "3_roulette", "چرخش مسیرهای احتمالی", ball_pos(s))
            s.until(lambda: any(x.chaos and x.chaos["stage"] == "select" and x.chaos["t"] / max(.01, x.chaos.get("select_len", x.chaos["p"]["select_s"])) >= .88 for x in s.eng.live_balls()), 2)
            shot(s, p + "4_locked", "قفل روی مسیر نهایی", ball_pos(s))
            s.run(0.22)
            shot(s, p + "5_fired", "شلیک توپ", ball_pos(s))
            continue
        if tid == "trajectory_reveal":
            s.run(0.15)
            shot(s, p + "2_collected", "لحظه‌ی برخورد", pos)
            s.until(lambda: any(getattr(x, "strong", False) and len(x.points) > 3 for x in s.eng.predictions.values()), 6)
            s.run(0.1)
            shot(s, p + "3_path_shown", "مسیر، محل برخورد و جهت برگشت نمایش داده می‌شود", ball_pos(s))
            s.run(0.35)
            shot(s, p + "4_path_later", "به‌روزرسانی مسیر با حرکت توپ", ball_pos(s))
            continue
        labels = ("لحظه‌ی برخورد", "اثر فعال", "کمی بعد")
        t0 = 0.0
        for k, (at, label) in enumerate(zip(POWERUP_TIMES[tid], labels), 2):
            s.run(at - t0)
            t0 = at
            focus = pos
            if tid in ("expand", "shield", "bull_market") and k > 2:
                focus = s.eng.paddle_shape(collector).apex()
            elif tid == "shrink" and k > 2:
                focus = s.eng.paddle_shape(1 - collector).apex()
            elif tid != "double_ball" and k > 2:
                focus = ball_pos(s)
            elif tid == "double_ball" and k > 2:
                focus = ball_pos(s)
            shot(s, p + f"{k}_{['hit', 'active', 'later'][k - 2]}", label, focus)


def capture_features():
    # balls
    p = "features/ball/"
    s = Scene(seed=5)
    s.eng.start_match()
    s.until(lambda: s.eng.state == "COUNTDOWN" and s.eng.countdown_info()[0] == "1" and s.eng.countdown_info()[1] > s.cfg["countdown.beat_s"] * 0.97, 6)  # the big number has faded
    shot(s, p + "1_charging_countdown", "توپ در حال شارژ، پایان شمارش", ball_pos(s))
    for k, (n, cap) in enumerate((("2_p1", "توپ بازیکن 1"), ("3_p2", "توپ بازیکن 2")), 0):
        s = Scene(seed=5 + k).play()
        s.until(lambda: s.eng.live_balls() and s.eng.live_balls()[0].owner == k and math.hypot(*ball_pos(s)) < 240, 16)
        shot(s, p + n, cap, ball_pos(s))
    s = Scene(seed=5).play()
    b = s.rally()
    b.smart_until = s.eng.time + 3
    shot(s.run(0.25), p + "4_smart_gold", "ضربه‌ی به‌موقع: حلقه‌ی طلایی", ball_pos(s))
    # trail
    p = "features/trail/"
    for k, (n, cap) in enumerate((("1_p1", "دنباله‌ی بازیکن 1"), ("2_p2", "دنباله‌ی بازیکن 2"))):
        s = Scene(seed=5 + k).play()
        s.until(lambda: s.eng.live_balls() and s.eng.live_balls()[0].owner == k and math.hypot(*ball_pos(s)) < 150, 16)
        shot(s, p + n, cap, ball_pos(s))
    s = Scene(seed=5).play()
    s.until(lambda: s.eng.live_balls() and s.eng.live_balls()[0].hits >= 2 and s.eng.time - s.eng.live_balls()[0].last_hit.get(s.eng.live_balls()[0].owner, -9) < .07, 16)
    shot(s, p + "3_owner_change_flash", "لحظه‌ی عوض شدن مالک توپ: فلش سفید دنباله", ball_pos(s))
    # bloom showcase
    s = Scene(seed=9).play((3, 2))
    b = s.rally()
    for tid in ("expand", "speed_up"):
        s.eng.types[tid].collect(s.eng, b, b.owner)
    for tid in ("double_ball", "shrink"):
        s.orb(tid)
    s.run(0.7)
    shot(s, "features/bloom/1_busy_moment", "صحنه‌ی شلوغ؛ لایه‌ی نور جداگانه در bloom.png", ball_pos(s))
    # paddle
    p = "features/paddle/"
    s = Scene(seed=5).play()
    s.rally()
    shot(s, p + "1_normal", "اندازه‌ی عادی", s.eng.paddle_shape(0).apex())
    for n, tid, who, cap in (("2_bigger", "expand", 0, "بزرگ‌شده با لبه‌ی سبز تپنده"), ("3_smaller", "shrink", 1, "کوچک‌شده با لبه‌ی قرمز چشمک‌زن")):
        s = Scene(seed=5).play()
        b = s.rally()
        s.eng.types[tid].collect(s.eng, b, 0)
        s.run(0.8)
        shot(s, p + n, cap, s.eng.paddle_shape(who).apex())
    s = Scene(seed=5).play()
    s.rally()
    s.eng.paddles[0].present = False
    shot(s.hold(.1), p + "4_absent", "بازیکن حاضر نیست: راکت کم‌نور", s.eng.paddle_shape(0).apex())
    # walls
    p = "features/walls/"
    s = Scene(seed=5).play()
    s.rally()
    w = s.eng.geom.walls[0]
    a = math.radians((w.start + w.end) / 2)
    fx, fy = s.eng.geom.wall_face * math.cos(a), s.eng.geom.wall_face * math.sin(a)
    shot(s, p + "1_idle", "دیواره در حالت عادی", (fx, fy))
    s.rend.handle_events([dict(type="wall_bounce", wall=0, x=fx, y=fy)], s.eng)
    shot(s.hold(.1), p + "2_hit", "برخورد توپ با دیواره: موج نور و حلقه", (fx, fy))
    # impact effects
    p = "features/impacts/"
    s = Scene(seed=5).play()
    s.rally()
    ax, ay = s.eng.paddle_shape(0).apex()
    s.rend.handle_events([dict(type="paddle_hit", player=0, ball_id=1, x=ax, y=ay, owner_changed=True)], s.eng)
    shot(s.hold(.08), p + "1_paddle_hit", "برخورد توپ با راکت: جرقه و حلقه", (ax, ay))
    s = Scene(seed=5).play()
    b = s.rally()
    ax, ay = s.eng.paddle_shape(1).apex()
    b.smart_until = s.eng.time + 2
    s.rend.handle_events([dict(type="paddle_hit", player=1, ball_id=b.id, x=ax, y=ay, smart=True)], s.eng)
    shot(s.hold(.12), p + "2_smart_hit", "ضربه‌ی به‌موقع: جرقه‌ی طلایی و پیام", (ax, ay))
    # orb lifecycle
    p = "features/orb_states/"
    s = Scene(seed=5).play()
    s.rally()
    o = s.orb("expand")
    pos = (o.hx, o.hy)
    o.state, o.state_t = "spawning", s.cfg["powerups.spawn_anim_s"] * .45
    shot(s.hold(1 / FPS), p + "1_spawning", "ظاهر شدن", pos)
    o.state, o.state_t, o.age = "idle", 0.0, o.life * .35
    shot(s.hold(1 / FPS), p + "2_idle_timer", "منتظر، حلقه‌ی خاکستری زمان باقی‌مانده است", pos)
    o.pulled, o.x, o.y = 1.0, o.hx + 50, o.hy + 30
    shot(s.hold(1 / FPS), p + "3_pulled_magnet", "کشش مغناطیسی: درخشش بیشتر و نقطه‌چین تا جای اصلی", pos)
    o.pulled, o.x, o.y = 0.0, o.hx, o.hy
    o.state, o.state_t = "collected", 0.14
    shot(s.hold(1 / FPS), p + "4_collected", "گرفته شدن: بزرگ می‌شود و محو می‌شود", pos)
    o.state, o.state_t = "despawning", 0.15
    shot(s.hold(1 / FPS), p + "5_expired", "تمام شدن زمان: کوچک می‌شود و محو می‌شود", pos)
    o.state, o.cls, o.type_id = "idle", "bad", "slow_down"
    shot(s.hold(1 / FPS), p + "6_red_orb", "گوی قرمز: حلقه‌ی خط‌چین و درخشش چشمک‌زن", pos)


def export_elements():
    d = OUT / "elements_png"
    for sub in ("orbs", "icons", "balls", "glows"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    s = Scene()
    r = s.rend
    r._ensure(s.eng)
    c, cfg = r.c, s.cfg
    for tid, t in Scene._types().items():
        cls = cfg[f"powerups.types.{tid}.class"]
        pygame.image.save(r.icons.badge(t.icon, tid, 128, c["class"][cls], cls == "bad", cfg["powerups.icon_scale"]), str(d / "orbs" / f"orb_{tid}.png"))
        pygame.image.save(r.icons.icon(t.icon, tid, 512), str(d / "icons" / f"{tid}.png"))
    pygame.image.save(r.icons.icon("trophy", "_trophy", 512, c["smart"]), str(d / "icons" / "trophy_gold.png"))
    for name, ring, tint in (("neutral", c["neutral_ball"], c["neutral_ball"]), ("p1", c["p1b"], c["p1b"]), ("p2", c["p2b"], c["p2b"]),
                             ("smart_gold", c["smart"], c["p1b"])):
        pygame.image.save(r._ball_sprite(ring, c["ball_core"], tint, 128, 1.0), str(d / "balls" / f"ball_{name}.png"))
    r.glow.dither = 0.0
    for name, col in (("p1", c["p1b"]), ("p2", c["p2b"]), ("good", c["good"]), ("bad", c["bad"]), ("neutral", c["neutral"]),
                      ("smart", c["smart"]), ("wall", c["wallb"]), ("white", (255, 255, 255))):
        pygame.image.save(r.glow.sprite(col, 256, 1.0), str(d / "glows" / f"glow_{name}_on_black.png"))


# ======================================================================= vector PDFs of every layout
BROWSERS = kit.BROWSERS


def browser():
    b = next((x for x in BROWSERS if Path(x).exists() or shutil.which(x)), None)
    if not b:
        sys.exit("Chrome / Edge not found")
    return b


FONT_DIR = ROOT / "design" / "fonts"
FACES = "".join(f'@font-face{{font-family:"{fam}";src:url("{(FONT_DIR / (fam + ".ttf")).as_uri()}")}}'
                f'@font-face{{font-family:"IRANSansX";font-weight:{w};src:url("{(FONT_DIR / (fam + ".ttf")).as_uri()}")}}'
                for w, fam in kit.FONT_W.items())


def chrome_pdf(html: str, pdf: Path, tmp: Path) -> None:
    src = tmp / f"{pdf.stem}.html"
    src.write_text(html, encoding="utf-8")
    subprocess.run([browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                    "--virtual-time-budget=30000", f"--print-to-pdf={pdf}", src.as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)


def inline(svg_text: str, prefix: str) -> str:
    """Make an SVG safe to sit next to others in one HTML page (unique ids)."""
    body = svg_text.split("?>", 1)[1]
    body = re.sub(r'\bid="', f'id="{prefix}', body)
    body = body.replace("url(#", f"url(#{prefix}").replace('href="#', f'href="#{prefix}')
    return re.sub(r"<title>.*?</title>", "", body, flags=re.S)


OUTLINE = """
import json,sys,pymupdf
pdf,ids,root=sys.argv[1],json.load(open(sys.argv[2])),sys.argv[3]
doc=pymupdf.open(pdf)
assert len(doc)==len(ids),(len(doc),len(ids))
for i,sid in enumerate(ids):
    one=pymupdf.open(); one.insert_pdf(doc,from_page=i,to_page=i); one.save(f"{root}/{sid}/layout.pdf",garbage=3,deflate=True)
    open(f"{root}/{sid}/layout_outlined.svg","w",encoding="utf-8").write(doc[i].get_svg_image(text_as_path=True))
"""


def layouts_pdf(tmp: Path) -> None:
    pages = "".join(f'<section>{inline((OUT / sid / "layout.svg").read_text(encoding="utf-8"), f"p{k}_")}</section>' for k, sid in enumerate(SHOTS))
    html = (f'<!doctype html><meta charset="utf-8"><style>{FACES}@page{{size:1080px 1080px;margin:0}}body{{margin:0;background:#000}}'
            'section{width:1080px;height:1080px;break-after:page;overflow:hidden}section:last-child{break-after:auto}section svg{display:block}</style>' + pages)
    pdf = tmp / "layouts.pdf"
    chrome_pdf(html, pdf, tmp)
    ids = tmp / "ids.json"
    ids.write_text(json.dumps(list(SHOTS)), encoding="utf-8")
    r = subprocess.run(["python3", "-c", OUTLINE, str(pdf), str(ids), str(OUT)], capture_output=True, text=True)
    if r.returncode:
        print("per-layout PDF / outlined SVG skipped (needs `pip install pymupdf` in python3):\n", r.stderr[-400:])


# ======================================================================= catalogue
def powerup_copy():
    return {
        "expand": ("راکت بزرگ", "افزایش سرمایه", "راکت خود بازیکن بزرگ می‌شود. گرفتن توپ راحت‌تر می‌شود."),
        "shrink": ("راکت کوچک", "کاهش نقدینگی", "راکت حریف کوچک می‌شود و دفاعش سخت‌تر. برای حریف قرمز و برای گیرنده سبز است."),
        "speed_up": ("نوسان بازار", "نوسان بالا", "توپ تندتر می‌شود، دنباله بلندتر می‌شود و جرقه‌ی نارنجی می‌دهد."),
        "chaos": ("مسیر تصادفی", "بازار رنج", "توپ می‌ایستد، رویداد اعلام می‌شود، مسیرها مثل گردونه می‌چرخند و توپ شلیک می‌شود."),
        "double_ball": ("دو تا توپ", "تنوع سبد", "توپ دوم با تأخیر کوتاه، کوچک‌تر و کندتر از جای گوی بیرون می‌آید."),
        "trajectory_reveal": ("تحلیل مسیر", "تحلیل تکنیکال", "مسیر نقطه‌چین، توپ شبح در محل برخورد و فلش برگشت فقط برای گیرنده‌ی قابلیت."),
        "slow_down": ("بازار آرام", "ثبات بازار", "توپ کند می‌شود. تنها گوی قرمز بازی."),
        "dim_ball": ("اصلاح بازار", "اصلاح قیمت", "توپ کم‌نور می‌شود ولی هرگز ناپدید نمی‌شود."),
        "shield": ("حد نوسان", "حد نوسان", "نوار سبز روی دروازه‌ی بازیکن یک گل را دفع می‌کند."),
        "bull_market": ("بازار صعودی", "بازار صعودی", "گل بعدی دو امتیازی است. حلقه‌ی طلایی دور توپ."),
    }


def img(sid: str, tmp: Path, crop=False, kind="frame", size=720) -> str:
    """A compact JPEG of a raw frame for the catalogue (the full PNGs stay in the folders)."""
    name = f"{sid.replace('/', '_')}_{kind}{'_c' if crop else ''}.jpg"
    path = tmp / name
    if not path.exists():
        im = Image.open(OUT / sid / f"{kind}.png").convert("RGB")
        if crop and SHOTS[sid]["focus"]:
            cx, cy = SHOTS[sid]["focus"]
            h = 170
            cx, cy = min(max(cx, h), 1080 - h), min(max(cy, h), 1080 - h)
            im = im.crop((int(cx - h), int(cy - h), int(cx + h), int(cy + h))).resize((680, 680), Image.LANCZOS)
        else:
            im = im.resize((size, size), Image.LANCZOS)
        im.save(path, quality=90)
    return name


def fig(sid, tmp, crop=False, kind="frame", label=None) -> str:
    cap = label or SHOTS[sid]["caption"]
    return f'<figure><img src="{img(sid, tmp, crop, kind)}"><figcaption>{escape(cap)}</figcaption></figure>'


def files_line(path: str) -> str:
    return f'<div class="files" dir="ltr">design/states/{escape(path)}/ — frame.png · bloom.png · layout.svg · layout_outlined.svg · layout.pdf</div>'


def page(num, title, en, intro, figures, specs=(), ask="", files="", cols=4, flag="") -> str:
    sp = "".join(f"<tr><th>{escape(a)}</th><td>{escape(str(b))}</td></tr>" for a, b in specs)
    return (f'<section class="pg"><header><span class="n">{num}</span><div><h1>{escape(title)}</h1><div class="en" dir="ltr">{escape(en)}</div></div>'
            f'{f"<span class=flag>{escape(flag)}</span>" if flag else ""}</header>'
            f'<div class="intro">{escape(intro)}</div>'
            f'<div class="figs c{cols}{" two" if len(figures) > cols else ""}">{"".join(figures)}</div>'
            f'<div class="foot"><table>{sp}</table><div class="ask"><b>از طراح می‌خواهیم</b><p>{escape(ask)}</p></div></div>{files}</section>')


def vector_fig(sid, k) -> str:
    return (f'<figure class="vec">{inline((OUT / sid / "layout.svg").read_text(encoding="utf-8"), f"v{k}_")}'
            f'<figcaption>نسخه‌ی وکتور با لایه‌های نام‌گذاری‌شده (layout.svg)</figcaption></figure>')


def build_catalog(tmp: Path) -> None:
    cfg = Config.load(SETTINGS_PATH)
    pu = powerup_copy()
    S = lambda prefix: [k for k in SHOTS if k.startswith(prefix)]  # noqa: E731
    pages, num = [], [0]
    uid = [0]

    def add(*a, **kw):
        num[0] += 1
        pages.append(page(num[0], *a, **kw))

    def vec(sid):
        uid[0] += 1
        return vector_fig(sid, uid[0])

    # ---- screens (one page each, or grouped when they are beats of one moment)
    scr = "screens/"
    common = [("بوم", f"{cfg['display.canvas_width']}×{cfg['display.canvas_height']} پیکسل، بیرون دایره کاملاً سیاه")]
    def screen(sid, title, en, intro, ask, specs=(), flag=""):
        add(title, en, intro, [fig(scr + sid, tmp), fig(scr + sid, tmp, kind="bloom", label="فقط لایه‌ی نور (bloom.png)"), vec(scr + sid)],
            specs=list(specs) + common, ask=ask, files=files_line(scr + sid), cols=3, flag=flag)

    screen("01_waiting", "صفحه‌ی انتظار", "ATTRACT · waiting", "وقتی کسی بازی نمی‌کند: دو ربات پشت لایه‌ی تیره بازی می‌کنند و عنوان و پیام شروع روی آن است.",
           "ترکیب عنوان فارسی و انگلیسی، پیام شروع و حس کلی صفحه‌ای که از دور توجه جلب کند. جای لوگوی مفید هم تعیین شود.",
           [("عنوان", cfg["text.title"]), ("پیام", cfg["text.attract_prompt"]), ("تیرگی پس‌زمینه", f"{1 - cfg['match.attract_opacity']:.0%}")])
    screen("02_waiting_names", "انتظار با نام بازیکن‌ها", "ATTRACT · names entered", "پس از ثبت نام از صفحه‌ی ناظر، نام هر بازیکن در نیمه‌ی خودش می‌آید.",
           "استایل نام‌ها و فاصله‌ی آن‌ها از عنوان؛ نام‌های بلند هم باید جا شوند.")
    screen("03_intro", "ورود به مسابقه", "INTRO", "زمین از تاریکی روشن می‌شود و دو نور سفید از بالا دور لبه‌ی زمین می‌چرخند.",
           "حرکت ورود. می‌تواند فریم‌به‌فریم یا فقط توضیحی باشد.", [("مدت", f"{cfg['match.intro_s']} ثانیه")])
    ids = ["04_ready", "05_count3", "06_count2", "07_count1", "08_go"]
    add("شمارش معکوس", "COUNTDOWN · ready 3 2 1 go", "پیام آماده باش، سپس 3 و 2 و 1 و شروع. هر ضرب با فلش، حلقه‌ی بازشونده و ذرات همگرا همراه است؛ توپ وسط زمین کم‌کم شارژ می‌شود.",
        [fig(scr + i, tmp) for i in ids], [("هر ضرب", f"{cfg['countdown.beat_s']} ثانیه"), ("آماده باش", f"{cfg['countdown.ready_s']} ثانیه"), ("شروع", f"{cfg['countdown.go_s']} ثانیه"), ("اندازه‌ی عدد", f"{cfg['countdown.size']} پیکسل")],
        "استایل عددها، کلمه‌های «آماده‌اید؟» و «شروع!» و افکت هر ضرب. 3 و 1 فیروزه‌ای و 2 بنفش است.", files_line(scr + "04_ready … 08_go"), cols=5)
    screen("09_serve", "سرویس", "SERVE", "توپ روی زمین نگه داشته می‌شود و فلش‌های متحرک به رنگ گیرنده، جهت سرویس را نشان می‌دهند.",
           "شکل فلش‌ها و حالت نگه‌داشتن توپ.")
    screen("10_playing", "بازی در جریان", "PLAYING · HUD", "صفحه‌ی اصلی: زمان وسط، امتیاز هر بازیکن در نیمه‌ی خودش، راکت‌ها، گوی‌ها، توپ و دنباله. نمودار کم‌رنگ پس‌زمینه با هر گل به نفع گلزن بالا می‌رود.",
           "طراحی HUD (زمان، امتیاز، نام)، خط وسط، پس‌زمینه و نمودار بازار. نوشته‌ها رو به بالا هستند و باید از هر دو طرف زمین خوانا باشند.",
           [("اندازه‌ی زمان", f"{cfg['hud.timer_size']} پیکسل"), ("اندازه‌ی امتیاز", f"{cfg['hud.score_size']} پیکسل"), ("اعداد", "همیشه لاتین")])
    screen("11_final_seconds", "ثانیه‌های پایانی", "PLAYING · final seconds", "در 10 ثانیه‌ی آخر زمان قرمز می‌شود و می‌تپد و حلقه‌ای قرمز همراه هر ثانیه روی زمین می‌زند.",
           "حس فوریت بدون اینکه تمرکز بازیکن را از توپ بگیرد.", [("شروع", f"{cfg['hud.final_seconds']} ثانیه‌ی آخر")])
    add("گل", "GOAL", "خط دروازه شعله‌ور می‌شود، حلقه‌ی بزرگ و انفجار ذرات به رنگ گلزن می‌آید، زمین می‌لرزد و عدد امتیاز می‌پرد.",
        [fig(scr + "12_goal_p1", tmp), fig(scr + "12_goal_p1", tmp, True, label="نمای نزدیک"), fig(scr + "13_goal_p2", tmp), fig(scr + "13_goal_p2", tmp, kind="bloom", label="لایه‌ی نور")],
        [("توقف بعد از گل", f"{cfg['match.goal_pause_s']} ثانیه"), ("لرزش", f"{cfg['fx.shake_px']} پیکسل، {cfg['fx.shake_s']} ثانیه"), ("پیام", cfg["text.goal"])],
        "افکت گل برای هر دو رنگ و استایل پیام «گل!».", files_line(scr + "12_goal_p1, 13_goal_p2"))
    screen("14_golden_goal", "گل طلایی", "PLAYING · golden goal", "اگر بازی مساوی تمام شود و این قانون روشن باشد، به‌جای زمان علامت + طلایی می‌آید و یک گل بازی را می‌بندد.",
           "حالت طلایی زمان و پیام. اگر قانون مساوی نهایی شد این صفحه لازم می‌شود.", [("پیام", cfg["text.golden_goal"])], flag="در تنظیمات فعلی خاموش")
    screen("15_final", "پایان معاملات", "FINAL", "با تمام شدن زمان یا رسیدن به سقف گل، همه‌چیز می‌ایستد، زمین تیره می‌شود و این پیام با فلش سفید می‌آید.",
           "این لحظه شعار بازی است؛ می‌تواند تصویری‌تر باشد، مثل زنگ پایان معاملات.", [("مدت", f"{cfg['match.final_freeze_s']} ثانیه"), ("پیام", cfg["text.final"])])
    add("نتیجه: برنده و بازنده", "RESULT · winner / loser", "نیمه‌ی برنده با رنگ او روشن می‌شود و می‌تپد و جام طلایی و کلمه‌ی «برنده» را می‌گیرد. نیمه‌ی بازنده امروز فقط نام و امتیاز خودش را دارد و پیام جداگانه‌ای ندارد.",
        [fig(scr + "16_result_p1_wins", tmp, label="برنده: بازیکن 1"), fig(scr + "17_result_p2_wins", tmp, label="برنده: بازیکن 2"), vec(scr + "16_result_p1_wins")],
        [("مدت", f"{cfg['match.result_s']} ثانیه"), ("شعار", cfg["text.slogan"]), ("پیام برنده", cfg["text.winner"]), ("نام‌ها", "نمونه‌اند: سارا و علی")],
        "طراحی نیمه‌ی برنده و پیشنهاد برای نیمه‌ی بازنده. پیام بازنده هنوز در بازی وجود ندارد؛ اگر طراحی شود به بازی اضافه می‌کنیم.",
        files_line(scr + "16_result_p1_wins, 17_result_p2_wins"), cols=3)
    screen("18_result_draw", "نتیجه: مساوی", "RESULT · draw", "اگر مساوی بماند هر دو نیمه خنثی می‌مانند و کلمه‌ی «مساوی» وسط زمین می‌آید.",
           "حالت مساوی بدون جام.", [("پیام", cfg["text.draw"])])
    screen("19_paused", "توقف", "PAUSED", "اپراتور بازی را نگه داشته است: زمین تیره و پیام توقف وسط.", "حالت توقف، ساده و عملی.", [("پیام", cfg["text.paused"])])
    screen("20_player_absent", "بازیکن خارج از زمین", "PLAYER ABSENT", "وقتی ردیاب بازیکن را نمی‌بیند راکتش کم‌نور می‌شود و پیام تپنده می‌آید.", "پیام و حالت راکت غایب.", [("پیام", cfg["text.step_in"])])
    sup = ROOT / "docs" / "media" / "supervisor.png"
    if sup.exists():
        shutil.copy2(sup, tmp / "supervisor.png")
        (OUT / "screens" / "21_supervisor_phone_page").mkdir(parents=True, exist_ok=True)
        shutil.copy2(sup, OUT / "screens" / "21_supervisor_phone_page" / "frame.png")
        add("صفحه‌ی ناظر روی گوشی", "Supervisor web page", "صفحه‌ی وب برای مسئول غرفه: ثبت نام بازیکن‌ها، شروع و توقف، و نتایج. روی زمین نمایش داده نمی‌شود و فقط تصویر مرجع دارد.",
            ['<figure class="phone"><img src="supervisor.png"><figcaption>تصویر واقعی صفحه</figcaption></figure>'],
            [("عرض", "گوشی، حدود 430 پیکسل")], "اختیاری: هماهنگی رنگ و فونت با بقیه‌ی طراحی.", '<div class="files" dir="ltr">design/states/screens/21_supervisor_phone_page/frame.png</div>', cols=1)

    # ---- power-ups
    for k, (tid, t) in enumerate(Scene._types().items(), 1):
        fa, meaning, what = pu[tid]
        cls = cfg[f"powerups.types.{tid}.class"]
        en = cfg[f"powerups.types.{tid}.enabled"]
        ids = S(f"powerups/{k:02d}_{tid}/")
        od, ob = kit.orb_body(t.icon, cls, kit.palette(cfg), 60, cfg["powerups.icon_scale"], uid=f"cat{tid}")
        orb = kit.svg(240, 240, ob, tid, od)
        orbfig = f'<figure class="orb">{inline(orb, f"o{k}_")}<figcaption>گوی (svg/orbs/orb_{tid}.svg)</figcaption></figure>'
        specs = [("معنی بازار", meaning), ("رنگ", {"good": "سبز", "bad": "قرمز", "neutral": "بنفش"}[cls])]
        if t.has_duration:
            specs.append(("مدت اثر", f"{cfg[f'powerups.types.{tid}.duration_s']} ثانیه"))
        for key, lab in (("toast_collector", "پیام گیرنده"), ("toast_opponent", "پیام حریف")):
            if cfg[f"powerups.types.{tid}.{key}"]:
                specs.append((lab, cfg[f"powerups.types.{tid}.{key}"]))
        if tid == "chaos":
            specs += [("عنوان", cfg["powerups.types.chaos.title"]), ("زیرعنوان", cfg["powerups.types.chaos.subtitle"])]
        figs = [orbfig] + [fig(i, tmp) for i in ids] + [fig(ids[-1 if tid != "chaos" else 2], tmp, True, label="نمای نزدیک")]
        add(fa, f"Power-up · {tid}", what, figs, specs,
            "طراحی گوی و نماد، و افکت لحظه‌ی گرفتن و اثر فعال. رنگ حلقه معنی دارد: سبز خوب، قرمز بد.",
            files_line(f"powerups/{k:02d}_{tid}/*"), cols=4, flag="" if en else "در تنظیمات فعلی خاموش")

    # ---- features
    b = [i for i in S("features/ball/")]
    add("توپ", "Feature · ball", "هسته‌ی سفید، حلقه و هاله به رنگ آخرین بازیکنی که به توپ زده؛ پیش از اولین ضربه خنثی است.",
        [fig(i, tmp, True) for i in b], [("شعاع", f"{cfg['ball.radius']} پیکسل"), ("هاله", f"{cfg['ball.glow_size']}× شعاع"), ("شدت هاله", cfg["ball.glow_intensity"])],
        "استایل توپ در چهار حالت: خنثی، هر بازیکن، طلایی. توپ دوم همین طرح با 72٪ اندازه است.", files_line("features/ball/*") + '<div class="files" dir="ltr">design/states/elements_png/balls/ · design/svg/elements/ball_*.svg</div>')
    add("دنباله‌ی توپ", "Feature · trail", "دنباله‌ی ستاره‌ای با هسته‌ی روشن و هاله‌ی رنگی، و جرقه‌های ریز. رنگش همیشه با آخرین زننده عوض می‌شود.",
        [fig(i, tmp, True) for i in S("features/trail/")], [("طول", f"{cfg['trails.duration_s']} ثانیه حرکت"), ("سر دنباله", f"{cfg['trails.head_size']}× شعاع توپ"), ("جرقه", f"{cfg['trails.sparkles']} در ثانیه"), ("با افزایش سرعت", f"{cfg['trails.speedup_length_mult']}× بلندتر")],
        "شکل دنباله و جرقه‌ها. باید با هر مسیر و برخوردی کار کند، پس به‌صورت قانون (رنگ، پهنا، محو شدن) بدهید، نه یک تصویر ثابت.", files_line("features/trail/*"), cols=3)
    bl = "features/bloom/1_busy_moment"
    add("نور و Bloom", "Feature · bloom / additive light", "همه‌ی نورها در یک لایه‌ی جدا کشیده و با حالت Add روی تصویر جمع می‌شوند. روی پروژکشن همین لایه است که زمین را می‌درخشاند. در هر پوشه bloom.png دقیقاً همین لایه است.",
        [fig(bl, tmp, label="تصویر نهایی"), fig(bl, tmp, kind="bloom", label="فقط لایه‌ی نور"), vec(bl)],
        [("قاعده‌ی هاله", "exp(−3.2 d²) · (1−d²)^1.5، d از مرکز تا لبه"), ("ترکیب", "Add / Screen روی پس‌زمینه‌ی سیاه"), ("تقویت پروژکشن", cfg["colors.projection_boost"]), ("نمونه‌ی هاله‌ها", "elements_png/glows/")],
        "میزان و رنگ نورها. لطفاً افکت‌ها را روی سیاه و با Screen تحویل دهید؛ پروژکتور سیاه را نمایش نمی‌دهد و رنگ‌های تیره روی زمین گم می‌شوند.", files_line(bl), cols=3)
    add("راکت", "Feature · paddle", "نیم‌دایره‌ای روی ریل دور زمین. لبه‌اش حالت راکت را می‌گوید و نماد اثر فعال با حلقه‌ی زمان پشت آن می‌نشیند.",
        [fig(i, tmp, True) for i in S("features/paddle/")], [("عرض پایه", f"{kit.pp(cfg, 0, 'width')} پیکسل"), ("نسبت شکل", kit.pp(cfg, 0, "shape_ratio")), ("نکته", "در بازی «پدل» و در راهنما «راکت» نوشته شده")],
        "استایل راکت در چهار حالت. عرض با قابلیت‌ها تغییر می‌کند، پس طرح باید کش بیاید.", files_line("features/paddle/*"))
    add("دیواره‌ها", "Feature · bumper walls", "دو دیواره‌ی انرژی بین دروازه‌ها: نبض نور در طولشان حرکت می‌کند و با برخورد توپ موج نور از محل ضربه پخش می‌شود.",
        [fig(i, tmp) for i in S("features/walls/")] + [fig(i, tmp, True) for i in S("features/walls/")], [("سرعت نبض", cfg["walls.flow_speed"]), ("شدت نور", cfg["walls.glow"])],
        "بافت دیواره، گره‌های دو سر آن و افکت برخورد.", files_line("features/walls/*"))
    add("افکت برخوردها", "Feature · impacts", "جرقه و حلقه‌ی بازشونده به رنگ بازیکن. ضربه‌ی به‌موقع جرقه‌ی طلایی و پیام خودش را دارد.",
        [fig(i, tmp) for i in S("features/impacts/")] + [fig(i, tmp, True) for i in S("features/impacts/")], [("سقف ذرات", cfg["fx.max_particles"]), ("پیام ضربه‌ی به‌موقع", cfg["text.smart_hit"])],
        "شکل جرقه و حلقه. به‌صورت توالی کوتاه روی سیاه.", files_line("features/impacts/*"))
    add("حالت‌های گوی", "Feature · orb states", "هر گوی این چرخه را طی می‌کند و بسته به فاصله‌ی توپ مغناطیسی به سمت آن کشیده می‌شود.",
        [fig(i, tmp, True) for i in S("features/orb_states/")], [("شعاع", f"{cfg['powerups.orb_radius']} پیکسل"), ("عمر", f"{cfg['powerups.orb_lifetime_s']} ثانیه"), ("شعاع مغناطیس", f"{cfg['powerups.magnet.radius']} پیکسل"), ("نوسان", f"{cfg['powerups.bob_px']} پیکسل")],
        "حرکت و شکل هر حالت. این حالت‌ها برای همه‌ی گوی‌ها یکسان‌اند و فقط نماد و رنگ حلقه عوض می‌شود.", files_line("features/orb_states/*") + '<div class="files" dir="ltr">design/states/elements_png/orbs/ · icons/</div>', cols=3)

    cover = ('<section class="pg cover"><h1>هاکی بازار</h1><div class="en" dir="ltr">Market Hockey · Screens, power-ups and effects for design</div>'
             f'<p>این فایل هر صفحه، حالت، قابلیت و افکت بازی را همان‌طور که امروز در بازی دیده می‌شود نشان می‌دهد ({num[0]} بخش). همه‌ی تصاویر از خود بازی گرفته شده‌اند.</p>'
             '<div class="flow" dir="ltr">ATTRACT → INTRO → COUNTDOWN → SERVE ⇄ PLAYING ⇄ GOAL → FINAL → RESULT → ATTRACT</div>'
             '<h2>فایل‌های هر بخش</h2><table class="legend">'
             '<tr><th dir="ltr">frame.png</th><td>فریم خام 1080×1080 از بازی؛ مرجع قطعی ظاهر امروز</td></tr>'
             '<tr><th dir="ltr">bloom.png</th><td>فقط لایه‌ی نور روی سیاه؛ با حالت Screen یا Add استفاده شود</td></tr>'
             '<tr><th dir="ltr">layout.svg</th><td>وکتور قابل ویرایش با لایه‌های نام‌گذاری‌شده و متن زنده</td></tr>'
             '<tr><th dir="ltr">layout_outlined.svg</th><td>همان وکتور با متن منحنی‌شده که بدون نصب فونت هم درست دیده می‌شود</td></tr>'
             '<tr><th dir="ltr">layout.pdf</th><td>همان وکتور به‌صورت PDF یک‌صفحه‌ای</td></tr></table>'
             '<h2>چه چیزی را در نظر بگیرید</h2><ul>'
             '<li>تصویر از پروژکتور روی کف تابیده می‌شود؛ بیرون دایره باید کاملاً سیاه بماند و رنگ‌های روشن و پراشباع بهتر دیده می‌شوند.</li>'
             '<li>بازیکنان روبه‌روی هم می‌ایستند؛ بیشتر توجهشان به توپ است، پس پیام‌ها باید کوتاه و درشت باشند.</li>'
             '<li>وکتورها بازسازی همان لحظه‌اند و نور در آن‌ها ساده شده است؛ برای ظاهر دقیق نور به frame.png نگاه کنید.</li>'
             '<li>بازی پویاست: توپ، دنباله و راکت هر بار جای دیگری هستند، پس طراحی‌ها باید قانون‌پذیر باشند.</li>'
             '<li>عناصر پایه، پالت، فونت‌ها و راه برگرداندن طراحی به بازی در پوشه‌ی design و README آن است.</li></ul>'
             '<h2>تصمیم‌های باز</h2><ul><li>پیام بازنده در بازی وجود ندارد و صفحه‌ی ثبت نام فقط روی گوشی ناظر است.</li>'
             '<li>پیام‌های بازی «پدل» می‌گویند و راهنمای بازیکن «راکت»؛ طرح نهایی یکی از این دو را نگه دارد.</li>'
             '<li>صفحه‌هایی که برچسب «خاموش» دارند در تنظیمات فعلی نمایش داده نمی‌شوند، ولی آماده‌اند.</li></ul></section>')
    css = (FACES + '@page{size:1600px 1000px;margin:0}*{box-sizing:border-box}body{margin:0;font-family:"IRANSansX";direction:rtl;color:#E8F4F8;background:#071C26}'
           '.pg{width:1600px;height:1000px;padding:34px 44px;display:flex;flex-direction:column;gap:12px;break-after:page;overflow:hidden;background:#071C26}'
           'header{display:flex;align-items:center;gap:16px}.n{width:52px;height:52px;border-radius:50%;background:#00A796;color:#fff;font-weight:900;font-size:24px;display:flex;align-items:center;justify-content:center}'
           'h1{margin:0;font-size:34px;font-weight:900;line-height:1.2}.en{color:#7FB0C2;font-size:15px;letter-spacing:1px}.flag{margin-inline-start:auto;background:#3A2A10;color:#FFD54A;border-radius:20px;padding:6px 16px;font-weight:700;font-size:16px}'
           '.intro{font-size:18px;line-height:1.65;color:#C6DCE4}.figs{flex:1;min-height:0;display:grid;gap:12px;align-items:center;justify-items:center}'
           '.c1{grid-template-columns:1fr}.c2{grid-template-columns:repeat(2,1fr)}.c3{grid-template-columns:repeat(3,1fr)}.c4{grid-template-columns:repeat(4,1fr)}.c5{grid-template-columns:repeat(5,1fr)}.c6{grid-template-columns:repeat(6,1fr)}'
           'figure{margin:0;width:100%;display:flex;flex-direction:column;align-items:center;gap:6px;min-width:0}figure img,figure svg{width:100%;max-height:520px;height:auto;display:block;object-fit:contain;border-radius:8px;background:#000}'
           '.two figure img,.two figure svg{max-height:262px;width:auto;max-width:100%}.orb svg{background:none}.phone img{max-height:560px;width:auto}figcaption{font-size:13px;color:#9CC0CE;text-align:center;line-height:1.5}'
           '.foot{display:grid;grid-template-columns:1.25fr 1fr;gap:20px;align-items:start}table{border-collapse:collapse;font-size:14px;width:100%}th{color:#7FB0C2;font-weight:500;text-align:right;padding:3px 0 3px 14px;white-space:nowrap;vertical-align:top}td{padding:3px 0}'
           '.ask{background:#0C2F3F;border-right:4px solid #00A796;border-radius:8px;padding:10px 16px;font-size:15px;line-height:1.6}.ask p{margin:2px 0 0}.ask b{color:#5FE0CF}'
           '.files{font-size:12px;color:#7FB0C2;text-align:left;font-family:monospace}'
           '.cover{padding:60px 90px;gap:10px}.cover h1{font-size:64px}.cover p{font-size:19px;line-height:1.7;margin:6px 0}.cover h2{font-size:22px;margin:12px 0 0;color:#5FE0CF}.cover ul{margin:0;padding-right:22px;font-size:17px;line-height:1.7}'
           '.flow{background:#0C2F3F;border-radius:8px;padding:10px 16px;font-family:monospace;font-size:17px;text-align:center}.legend{font-size:16px}.legend th{font-family:monospace;color:#fff;text-align:left;padding-left:24px}')
    html = f'<!doctype html><html lang="fa"><meta charset="utf-8"><style>{css}</style><body>{cover}{"".join(pages)}</body></html>'
    chrome_pdf(html, CATALOG, tmp)
    print("wrote", CATALOG, f"{CATALOG.stat().st_size // 1024} KB")


def main() -> int:
    pygame.init()
    pygame.display.set_mode((64, 64))
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    print("screens"); capture_screens()
    print("power-ups"); capture_powerups()
    print("features"); capture_features()
    export_elements()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        layouts_pdf(tmp)
        build_catalog(tmp)
    print(f"{len(SHOTS)} scenes written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
