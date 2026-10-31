#!/usr/bin/env python3
"""Render the pictures in the READMEs from the real game (headless), so they can never drift from what it looks like.

    pip install pillow            # only this tool needs it; ffmpeg is needed for the GIF, Chrome for the phone page
    python tools/make_readme_media.py

Writes docs/media/ (in this game's folder) and ../media/ (the repo's front page).
"""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from market_hockey.config import Config  # noqa: E402
from market_hockey.core.engine import ATTRACT, PLAYING, RESULT, Engine  # noqa: E402
from market_hockey.inputs.ai import AIAdapter  # noqa: E402
from market_hockey.render.renderer import Renderer  # noqa: E402
from market_hockey.render.text import TextRenderer  # noqa: E402
from market_hockey.web.server import SupervisorServer  # noqa: E402

OUT = HERE / "docs" / "media"
REPO_OUT = HERE.parent / "media"
HZ = 240
FPS = 60
STILL_SIZE = 640
GIF_SIZE = 460
PHONE = (430, 900)


class Game:
    def __init__(self, seed=7, **values):
        self.cfg = Config({"debug.seed": seed, **values})
        self.eng = Engine(self.cfg, random.Random(seed))
        self.ai = AIAdapter(self.cfg, random.Random(seed + 1))
        self.rend = Renderer(self.cfg, random.Random(seed + 2))
        self.t = 0.0
        self.frame = None

    def run(self, seconds):
        for _ in range(max(1, int(seconds * FPS))):
            dt = 1 / FPS
            samples = {i: self.ai.sample(i, self.t, dt, self.eng) for i in (0, 1)}
            for _ in range(HZ // FPS):
                self.eng.step(1 / HZ, samples, [True, True])
            self.t += dt
            self.rend.handle_events(self.eng.drain_events(), self.eng)
            self.frame = self.rend.render(self.eng, 0.5, dt)
        return self.frame

    def to_playing(self):
        self.eng.start_match()
        while self.eng.state != PLAYING:
            self.run(1 / FPS)

    def wait_for_rally(self):
        """Run until a player has hit the ball and it is on its way across: that is when the trail looks best."""
        for _ in range(FPS * 12):
            self.run(1 / FPS)
            live = self.eng.live_balls()
            if live and live[0].owner is not None and abs(live[0].x) < 180 and live[0].hits >= 1:
                return live[0]
        return self.eng.live_balls()[0]

    def collect(self, tid, ball=None):
        ball = ball or self.eng.live_balls()[0]
        if ball.owner is None:
            ball.owner = 0
        self.eng.types[tid].collect(self.eng, ball, ball.owner)


def to_image(frame) -> Image.Image:
    arr = pygame.surfarray.array3d(frame).swapaxes(0, 1)
    return Image.fromarray(np.asarray(arr, dtype=np.uint8), "RGB")


def disc(frame, size=STILL_SIZE) -> Image.Image:
    """The floor as a floating disc: transparent outside the circle, so it sits well on light and dark pages."""
    img = to_image(frame).convert("RGBA")
    w, h = img.size
    mask = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(mask).ellipse((4, 4, w * 2 - 5, h * 2 - 5), fill=255)
    img.putalpha(mask.resize((w, h), Image.LANCZOS))
    return img.resize((size, size), Image.LANCZOS)


def save_still(name, frame) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    disc(frame).save(OUT / f"{name}.png", optimize=True)
    print("wrote", OUT / f"{name}.png")


def stills() -> None:
    g = Game(seed=11)
    g.eng.set_names("سارا", "علی")
    save_still("waiting", g.run(2.4))

    g = Game(seed=7)
    g.eng.start_match()
    for _ in range(FPS * 10):
        g.run(1 / FPS)
        info = g.eng.countdown_info() if g.eng.state == "COUNTDOWN" else None
        if info and info[0] == "2" and info[1] > 0.12:
            break
    save_still("countdown", g.frame)

    g = Game(seed=5)
    g.to_playing()
    g.run(2.0)
    for tid in ("expand", "shrink", "double_ball", "trajectory_reveal"):
        g.eng.force_spawn(tid)
    g.wait_for_rally()
    save_still("rally", g.run(0.05))

    g = Game(seed=5)
    g.to_playing()
    b = g.wait_for_rally()
    g.collect("trajectory_reveal", b)
    g.collect("double_ball", b)
    g.run(1.3)
    save_still("powerups", g.run(0.05))

    g = Game(seed=9)
    g.to_playing()
    b = g.wait_for_rally()
    g.collect("chaos", b)
    for _ in range(FPS * 3):
        g.run(1 / FPS)
        if any(x.chaos and x.chaos["stage"] == "select" and x.chaos["t"] > 0.25 for x in g.eng.live_balls()):
            break
    save_still("chaos", g.frame)

    g = Game(seed=3, **{"match.score_limit": 3})
    g.eng.set_names("سارا", "علی")
    g.to_playing()
    g.eng.scores = [4, 2]
    g.eng.time_left = 0.1
    for _ in range(FPS * 20):
        g.run(1 / FPS)
        if g.eng.state == RESULT and g.eng.state_t > 1.5:
            break
    save_still("result", g.frame)

    g = Game(seed=4)
    g.to_playing()
    b = g.eng.live_balls()[0]
    a = math.radians(g.eng.geom.goals[1].center + 12)
    b.owner = 0
    b.x, b.y = (g.eng.geom.R - 90) * math.cos(a), (g.eng.geom.R - 90) * math.sin(a)
    b.vx, b.vy = 900 * math.cos(a), 900 * math.sin(a)
    g.ai.sample = lambda i, now, dt, eng, _s=g.ai.sample: _s(i, now, dt, eng) if i == 0 else type(_s(i, now, dt, eng))(True, 0.02)
    for _ in range(FPS):
        g.run(1 / FPS)
        if g.eng.state == "GOAL" and g.eng.state_t > 0.22:
            break
    save_still("goal", g.frame)


def gif() -> None:
    """A short highlight: the last beat of the countdown, a rally, power-ups, the roulette, and a goal."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found: skipping the GIF")
        return
    g = Game(seed=5)
    g.eng.start_match()
    with tempfile.TemporaryDirectory() as tmp:
        n = [0]

        def shoot(seconds, every=2):
            for _ in range(int(seconds * FPS)):
                g.run(1 / FPS)
                if n[0] % every == 0:
                    to_image(g.frame).resize((GIF_SIZE, GIF_SIZE), Image.LANCZOS).save(Path(tmp) / f"{n[0] // every:05d}.png")
                n[0] += 1

        while not (g.eng.state == "COUNTDOWN" and g.eng.state_t > g.eng.countdown_total() - 1.6):
            g.run(1 / FPS)
        shoot(1.6)
        g.run(0.5)
        shoot(1.2)
        for tid in ("expand", "double_ball", "trajectory_reveal"):
            g.eng.force_spawn(tid)
        shoot(2.2)
        live = g.eng.live_balls()
        if live:
            g.collect("double_ball", live[0])
            g.collect("trajectory_reveal", live[0])
        shoot(2.4)
        live = g.eng.live_balls()
        if live:
            g.collect("chaos", live[0])
        shoot(3.2)
        out = OUT / "gameplay.gif"
        vf = (f"split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];"
              f"[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", "30", "-i", str(Path(tmp) / "%05d.png"),
                        "-vf", vf, "-loop", "0", str(out)], check=True)
        print("wrote", out, f"{out.stat().st_size / 1e6:.1f} MB")


def banner(path: Path, fa: str, en: str, sub: str, discs: list) -> None:
    """A wide title card with the game's own colors, fonts and pictures."""
    W, H = 1600, 520
    cfg = Config()
    x, y = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H), indexing="ij")
    d = np.clip(np.hypot((x - 0.72) * 1.4, y - 0.5), 0, 1)[..., None]
    rgb = np.array((7, 44, 60)) * (1 - d) + np.array((2, 13, 20)) * d
    rgb = rgb + (np.random.default_rng(1).random(rgb.shape) - 0.5) * 1.2
    surf = pygame.surfarray.make_surface(np.clip(rgb, 0, 255).astype(np.uint8))
    tr = TextRenderer(cfg)
    margin = 90
    s_fa = tr.render(fa, 104, (255, 255, 255), "persian")
    surf.blit(s_fa, (margin, 110))
    s_en = tr.render(en, 54, (0, 214, 190), "latin")
    surf.blit(s_en, (margin, 110 + s_fa.get_height() + 2))
    s_sub = tr.render(sub, 30, (168, 200, 210), "persian")
    surf.blit(s_sub, (margin, 110 + s_fa.get_height() + s_en.get_height() + 22))
    img = to_image(surf).convert("RGBA")
    for src, cx, size in discs:
        small = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
        img.alpha_composite(small, (cx - size // 2, (H - size) // 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, optimize=True)
    print("wrote", path)


def phone_page() -> None:
    """The supervisor page as it looks on a phone, filled with a believable session."""
    chrome = next((c for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "chrome", "google-chrome",
                               "chromium", "msedge") if shutil.which(c) or Path(c).exists()), None)
    if not chrome:
        print("Chrome not found: skipping the supervisor page")
        return
    with tempfile.TemporaryDirectory() as tmp:
        hist = Path(tmp) / "h.jsonl"
        people = [("سارا", 7, "علی", 5, 0), ("مریم", 4, "رضا", 7, 1), ("نیما", 6, "سارا", 7, 1), ("علی", 7, "رضا", 3, 0)]
        with open(hist, "w", encoding="utf-8") as fh:
            for k, (a, sa, b, sb, w) in enumerate(people):
                fh.write(json.dumps({"time": f"2026-10-31 1{k}:2{k}:00", "duration_s": 60.0, "winner": w, "golden_goal": False,
                                     "players": [{"name": a, "score": sa, "powerups": 2, "smart": 1},
                                                 {"name": b, "score": sb, "powerups": 1, "smart": 0}]},
                                    ensure_ascii=False) + "\n")
        srv = SupervisorServer("127.0.0.1", 0, history_path=hist)
        srv.start()
        cfg = Config()
        srv.publish({"state": "PLAYING", "paused": False, "time_left": 42.3, "duration": 60.0, "timer_enabled": True,
                     "golden": False, "scores": [3, 2], "score_limit": 7, "names": ["سارا", "علی"],
                     "labels": [cfg["text.player_1"], cfg["text.player_2"]], "colors": [cfg["colors.p1"], cfg["colors.p2"]],
                     "colors_glow": [cfg["colors.p1"], cfg["colors.p2"]], "winner": None, "match_count": 5,
                     "last_result": None, "urls": [srv.url]})
        shot = Path(tmp) / "page.png"
        # headless Chrome will not open a window narrower than 500 px, so the phone is an iframe inside it
        phone = Path(tmp) / "phone.html"
        phone.write_text(f'<body style="margin:0;background:#000"><iframe src="{srv.url}" width="{PHONE[0]}" '
                         f'height="{PHONE[1]}" style="border:0"></iframe>', encoding="utf-8")
        try:
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--screenshot={shot}",
                            "--force-device-scale-factor=2", f"--window-size=600,{PHONE[1]}",
                            "--virtual-time-budget=4000", phone.as_uri()],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        finally:
            srv.stop()
        OUT.mkdir(parents=True, exist_ok=True)
        page = Image.open(shot).convert("RGB").crop((0, 0, PHONE[0] * 2, PHONE[1] * 2))
        page.save(OUT / "supervisor.png", optimize=True)
        print("wrote", OUT / "supervisor.png")


def main() -> int:
    pygame.init()
    pygame.display.set_mode((64, 64))
    t0 = time.time()
    stills()
    gif()
    phone_page()
    banner(OUT / "banner.png", "هاکی بازار", "Market Hockey",
           "یک بازی دونفره روی کف نورانی، برای کارگزاری مفید",
           [(OUT / "rally.png", 1200, 470)])
    banner(REPO_OUT / "banner.png", "بازی‌های مفید", "Mofid Games",
           "بازی‌های تعاملی روی کف نورانی، برای نمایشگاه کارگزاری مفید",
           [(OUT / "rally.png", 1040, 310), (OUT / "powerups.png", 1370, 310)])
    print(f"done in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
