"""Kinetic type lab: the reference sketch's control panel in Python, with every moment and brand object one click away.

    .venv/bin/python tools/kinetic_lab.py

The sliders are live in both directions: drag one to change the look, or fire a moment and watch the
handles move as the moment animates them. "Site" shows the exact port at the reference page's values;
"Mofid" shows the brand look inside the round arena, at the faintness it has in the game.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from land_hockey.config import Config  # noqa: E402
from land_hockey.render.brand_motion import BrandMotion  # noqa: E402
from land_hockey.render.colors import hex_rgb  # noqa: E402
from land_hockey.render.kinetic import REF_SIZE, SITE_CANVAS, KineticBackdrop, KineticField, KineticParams  # noqa: E402
from land_hockey.render.text import TextRenderer  # noqa: E402

W, H = 1280, 880
PANEL = 480
STAGE = (W - PANEL, H)
INK, DIM, LINE, BG = (232, 240, 242), (130, 150, 158), (46, 62, 70), (16, 24, 28)
ACCENT = (0, 167, 150)

SITE_VALUES = dict(density=28, speed=0.06, frequency=0.03, min_stretch=0.25, max_stretch=2.6, ring_width=75,
                   swap_interval=140, font_scale=0.9)
SLIDERS = [
    ("density", "Grid Density", 10, 120, 1),
    ("font_scale", "Font Scale", 0.3, 2, 0.05),
    ("speed", "Animation Speed", 0.01, 0.2, 0.01),
    ("frequency", "Wave Frequency", 0.005, 0.1, 0.001),
    ("min_stretch", "Min Stretch", 0.05, 1, 0.05),
    ("max_stretch", "Max Stretch", 1, 8, 0.1),
    ("ring_width", "Ring Width", 20, 200, 5),
    ("swap_interval", "Color Swap Interval", 10, 300, 10),
    ("max_overlap", "Max Letter Width (cells)", 0.5, 8, 0.1),
    ("letter_width", "Letter Ring Width", 10, 200, 1),
    ("op_speed", "Opacity Wave Speed", 0, 0.2, 0.001),
    ("op_frequency", "Opacity Wave Frequency", 0, 0.05, 0.001),
    ("op_min", "Opacity Wave Valley", 0, 1, 0.01),
    ("op_max", "Opacity Wave Peak", 0, 1, 0.01),
    ("op_sharpness", "Opacity Wave Sharpness", 0.5, 5, 0.1),
    ("edge_start", "Rim Fade Starts", 0, 1, 0.01),
    ("edge_end", "Rim Fade Ends", 0, 1.2, 0.01),
]
CONFIG_KEYS = {"op_speed": "opacity_wave_speed", "op_frequency": "opacity_wave_frequency", "op_min": "opacity_wave_min",
               "op_max": "opacity_wave_max", "op_sharpness": "opacity_wave_sharpness", "edge_start": "edge_fade_start",
               "edge_end": "edge_fade_end"}
SEQUENCE = [(0.0, "state", "ATTRACT"), (0.0, "splash", None), (5.5, "state", "INTRO"), (8.3, "beat", "ready"),
            (9.5, "beat", "5"), (10.5, "beat", "4"), (11.5, "beat", "3"), (12.5, "beat", "2"), (13.5, "beat", "1"),
            (14.5, "beat", "go"), (15.3, "state", "PLAYING"), (17.6, "goal", 0), (21.1, "goal", 1), (24.6, "state", "FINAL"),
            (26.2, "result", 0), (36.2, "state", "ATTRACT")]


class Lab:
    def __init__(self, screen):
        self.screen = screen
        self.cfg = Config({})
        self.tr = TextRenderer(self.cfg)
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 19)
        self.mode = "site"
        self.site = KineticParams()
        self.site_field = KineticField(SITE_CANVAS)
        self.site_canvas = pygame.Surface(SITE_CANVAS)
        self.backdrop = KineticBackdrop(self.cfg)
        self.state = "ATTRACT"
        side = min(STAGE) - 40
        self.side = side
        self.arena = pygame.Surface((side, side))
        self.mask = self._circle_mask(side)
        self.backdrop.attach((side, side), (side / 2, side / 2, side / 2), 0.0, REF_SIZE / side)
        self.motion = BrandMotion(self.cfg)
        self.motion.attach((side // 2, side // 2), side // 2, side // 2 * 0.96, 0.0)
        self.drag = None
        self.typing = False
        self.seq_t = None
        self.seq_i = 0
        self.buttons: list = []

    @staticmethod
    def _circle_mask(side):
        m = pygame.Surface((side, side), pygame.SRCALPHA)
        m.fill((0, 0, 0, 255))
        pygame.draw.circle(m, (0, 0, 0, 0), (side // 2, side // 2), side // 2)
        return m

    # ---------------------------------------------------------------- values
    def get(self, key):
        return getattr(self.site, key) if self.mode == "site" else getattr(self.backdrop.p, key)

    def set(self, key, v):
        if self.mode == "site":
            setattr(self.site, key, v)
            return
        self.cfg.set(f"kinetic.{CONFIG_KEYS.get(key, key)}", int(v) if key == "swap_interval" else v)

    def text(self):
        return self.site.chars if self.mode == "site" else self.backdrop.p.chars

    def set_text(self, s):
        if self.mode == "site":
            self.site.chars = s.upper()
        else:
            self.backdrop.set_text(s, snap=True)
            self.cfg.set("kinetic.attract_text", s)

    # ---------------------------------------------------------------- moments
    def fire(self, kind, arg=None):
        b = self.backdrop
        m = self.motion
        if self.mode == "site":
            self.mode = "mofid"
        if kind == "cue":
            self.state = "ATTRACT"
            m.state = "ATTRACT"
            getattr(m, "cue_" + arg)()
        elif kind == "state":
            self.state = arg
            b.on_state(arg, "x")
            m.on_state(arg, "x")
        elif kind == "splash":
            b.play("splash", gain=self.cfg["kinetic.opacity_moment"])
        elif kind == "beat":
            self.state = "COUNTDOWN"
            length = self.cfg["countdown.ready_s"] if arg == "ready" else self.cfg["countdown.beat_s"]
            b.on_beat(arg, length)
            m.state = "COUNTDOWN"
            m.cue_beat(arg, length)
        elif kind == "goal":
            self.state = "GOAL"
            b.on_goal(arg, -0.98 if arg == 1 else 0.98, 0.1)
            m.state = "GOAL"
            m.cue_goal(arg)
        elif kind == "result":
            self.state = "RESULT"
            b.winner = arg
            b.on_state("RESULT", "FINAL")
            m.winner = arg
            m.on_state("RESULT", "FINAL")

    def run_sequence(self):
        self.seq_t, self.seq_i = 0.0, 0

    # ---------------------------------------------------------------- frame
    def update(self, dt):
        if self.seq_t is not None:
            self.seq_t += dt
            while self.seq_i < len(SEQUENCE) and SEQUENCE[self.seq_i][0] <= self.seq_t:
                _, kind, arg = SEQUENCE[self.seq_i]
                self.fire(kind, arg)
                self.seq_i += 1
            if self.seq_i >= len(SEQUENCE):
                self.seq_t = None
        if self.mode == "site":
            self.site_field.advance(dt, self.site)
        self.backdrop.update(dt, self.state)
        self.motion.update(dt, self.state)

    def draw(self):
        sc = self.screen
        sc.fill((0, 0, 0))
        if self.mode == "site":
            c = self.site_canvas
            c.fill((15, 15, 15))
            self.site_field.draw(c, self.site)
            h = H - 40
            w = int(h * SITE_CANVAS[0] / SITE_CANVAS[1])
            sc.blit(pygame.transform.smoothscale(c, (w, h)), ((STAGE[0] - w) // 2, 20))
        else:
            a = self.arena
            a.fill(hex_rgb(self.cfg["colors.arena_inner"]))
            self.backdrop.draw(a, self.motion.type_dim)
            self.motion.draw(a)
            self.motion.draw_logo_zoom(a)
            a.blit(self.mask, (0, 0))
            sc.blit(a, ((STAGE[0] - self.side) // 2, (H - self.side) // 2))
        self.draw_panel()

    def draw_panel(self):
        sc = self.screen
        x0 = W - PANEL
        pygame.draw.rect(sc, BG, (x0, 0, PANEL, H))
        pygame.draw.line(sc, LINE, (x0, 0), (x0, H))
        self.buttons = []
        y = 14
        for label, mode in (("Site (exact)", "site"), ("Mofid (arena)", "mofid")):
            bx = x0 + 16 + (0 if mode == "site" else 228)
            self._button(label, (bx, y, 220, 28), lambda m=mode: setattr(self, "mode", m), self.mode == mode)
        y += 44
        self.slider_rects = {}
        col_w = (PANEL - 44) // 2
        for i, (key, label, lo, hi, step) in enumerate(SLIDERS):
            v = self.get(key)
            cx = x0 + 16 + (i % 2) * (col_w + 12)
            cy = y + (i // 2) * 40
            sc.blit(self.small.render(label, True, DIM), (cx, cy))
            txt = f"{v:.0f}" if step >= 1 else f"{v:.3f}".rstrip("0").rstrip(".") or "0"
            t = self.small.render(txt, True, INK)
            sc.blit(t, (cx + col_w - t.get_width(), cy))
            r = pygame.Rect(cx, cy + 18, col_w, 8)
            f = max(0.0, min(1.0, (v - lo) / (hi - lo)))
            pygame.draw.rect(sc, LINE, r)
            pygame.draw.rect(sc, (99, 120, 128), (r.x, r.y, int(r.w * f), r.h))
            pygame.draw.rect(sc, INK, (r.x + int(r.w * f) - 3, r.y - 4, 6, 16))
            self.slider_rects[key] = (r.inflate(0, 14), lo, hi, step)
        y += 40 * ((len(SLIDERS) + 1) // 2)
        sc.blit(self.small.render("Character Set (click to type)", True, DIM), (x0 + 16, y))
        y += 18
        box = pygame.Rect(x0 + 16, y, PANEL - 32, 30)
        pygame.draw.rect(sc, (30, 44, 50) if not self.typing else (0, 70, 66), box)
        show = self.tr.render(self.text()[-26:] or " ", 19, INK, "persian", outline=0)
        sc.blit(show, (box.x + 8, box.y + (box.h - show.get_height()) // 2))
        self.buttons.append((box, self._start_typing))
        y += 44
        sc.blit(self.small.render("Moments", True, DIM), (x0 + 16, y))
        y += 20
        moments = [("Whole match", self.run_sequence), ("Splash", lambda: self.fire("splash")),
                   ("Start", lambda: self.fire("state", "INTRO")), ("Ready", lambda: self.fire("beat", "ready")),
                   ("5", lambda: self.fire("beat", "5")), ("4", lambda: self.fire("beat", "4")),
                   ("3", lambda: self.fire("beat", "3")), ("2", lambda: self.fire("beat", "2")),
                   ("1", lambda: self.fire("beat", "1")), ("Go", lambda: self.fire("beat", "go")),
                   ("Goal P1", lambda: self.fire("goal", 0)), ("Goal P2", lambda: self.fire("goal", 1)),
                   ("Final", lambda: self.fire("state", "FINAL")), ("Win P1", lambda: self.fire("result", 0)),
                   ("Win P2", lambda: self.fire("result", 1)), ("Draw", lambda: self.fire("result", None)),
                   ("Waiting", lambda: self.fire("state", "ATTRACT")), ("Playing", lambda: self.fire("state", "PLAYING"))]
        bw = (PANEL - 32 - 12) // 3
        for i, (label, fn) in enumerate(moments):
            self._button(label, (x0 + 16 + (i % 3) * (bw + 6), y + (i // 3) * 32, bw, 27), fn,
                         label == "Whole match" and self.seq_t is not None)
        y += 32 * ((len(moments) + 2) // 3) + 4
        sc.blit(self.small.render("Brand objects", True, DIM), (x0 + 16, y))
        y += 20
        for i, (label, cue) in enumerate((("Flood", "flood"), ("Coins", "flyers"), ("Dots", "dots"), ("Chart", "market"),
                                          ("Rings", "pulse"), ("Wall", "wall"))):
            self._button(label, (x0 + 16 + (i % 6) * ((PANEL - 32) // 6), y, (PANEL - 32) // 6 - 4, 27),
                         lambda c=cue: self.fire("cue", c))

    def _button(self, label, rect, fn, on=False):
        r = pygame.Rect(rect)
        pygame.draw.rect(self.screen, ACCENT if on else (34, 48, 54), r)
        t = self.small.render(label, True, INK)
        self.screen.blit(t, t.get_rect(center=r.center))
        self.buttons.append((r, fn))

    def _start_typing(self):
        self.typing = True
        pygame.key.start_text_input()

    # ---------------------------------------------------------------- input
    def event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.typing = False
            for key, (r, *_rest) in self.slider_rects.items():
                if r.collidepoint(e.pos):
                    self.drag = key
                    self.mouse(e.pos)
                    return
            for r, fn in self.buttons:
                if r.collidepoint(e.pos):
                    fn()
                    return
        elif e.type == pygame.MOUSEBUTTONUP:
            self.drag = None
        elif e.type == pygame.MOUSEMOTION and self.drag:
            self.mouse(e.pos)
        elif e.type == pygame.TEXTINPUT and self.typing:
            self.set_text(self.text() + e.text)
        elif e.type == pygame.KEYDOWN and self.typing:
            if e.key == pygame.K_BACKSPACE:
                self.set_text(self.text()[:-1])
            elif e.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.typing = False

    def mouse(self, pos):
        r, lo, hi, step = self.slider_rects[self.drag]
        f = max(0.0, min(1.0, (pos[0] - r.x) / r.w))
        self.set(self.drag, round((lo + f * (hi - lo)) / step) * step)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    pygame.init()
    pygame.display.set_caption("Land Hockey: kinetic type lab")
    screen = pygame.display.set_mode((W, H))
    lab = Lab(screen)
    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and not lab.typing):
                running = False
            elif not lab.__dict__.get("slider_rects"):
                continue
            else:
                lab.event(e)
        lab.update(min(dt, 1 / 20))
        lab.draw()
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
