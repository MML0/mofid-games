"""Pygame application: display, main loop (fixed-step physics), hotkeys, live link, output transform."""

from __future__ import annotations

import csv
import logging
import logging.handlers
import math
import os
import random
import subprocess
import sys
import time

import pygame

from .audio.audio import Audio
from .config import Config
from .config.live_link import LiveLinkServer
from .core.engine import ATTRACT, RESULT, Engine
from .inputs.manager import InputManager
from .paths import LOGS_DIR, ROOT, SETTINGS_PATH, launch_command
from .render.overlays import draw_calibration, draw_debug
from .render.renderer import Renderer

log = logging.getLogger("market_hockey")


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOGS_DIR / "market_hockey.log", maxBytes=2_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:  # a windowed .exe has no console
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(logging.WARNING)
        root.addHandler(sh)


class GameApp:
    def __init__(self, config_path=SETTINGS_PATH, windowed: bool = False, headless: bool = False, seed: int | None = None):
        setup_logging()
        self.config_path = config_path
        self.cfg = Config.load(config_path)
        for w in self.cfg.warnings:
            log.warning(w)
        self.cfg.warnings.clear()
        if windowed or headless:
            self.cfg.set("display.fullscreen", False)
        self.headless = headless
        seed = seed if seed is not None else (self.cfg["debug.seed"] or None)
        self.rng = random.Random(seed)
        # SCALED windows are filtered by SDL; "nearest" makes every edge look pixelated when the window is resized
        os.environ["SDL_RENDER_SCALE_QUALITY"] = "1" if self.cfg["display.scale_quality"] == "linear" else "0"
        os.environ["SDL_HINT_RENDER_SCALE_QUALITY"] = os.environ["SDL_RENDER_SCALE_QUALITY"]
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")  # no blurry scaling at 125–200% on Windows
        pygame.init()
        self.screen = None
        self._display_key = None
        self._open_display()
        self.engine = Engine(self.cfg, random.Random(self.rng.random()))
        self.inputs = InputManager(self.cfg)
        self.renderer = Renderer(self.cfg, random.Random(self.rng.random()))
        self.renderer.debug_draw = self._debug_draw
        self.audio = Audio(self.cfg) if not headless else None
        self.live = LiveLinkServer(self.cfg["live_link.game_port"]) if (self.cfg["live_link.enabled"] and not headless) else None
        self.running = True
        self.fps = 0.0
        self._fps_acc = []
        self._state_t = 0.0
        self._esc_t = -9.0
        self._r_down = None
        self.panel_proc = None
        self.engine.reset_to_attract()

    # ------------------------------------------------------------------ display
    def _open_display(self) -> None:
        cfg = self.cfg
        W, H = int(cfg["display.canvas_width"]), int(cfg["display.canvas_height"])
        fs = cfg["display.fullscreen"] and not self.headless
        key = (W, H, fs, cfg["display.display_index"])
        if key == self._display_key and self.screen is not None:
            return
        self._display_key = key
        flags = pygame.SCALED | (pygame.FULLSCREEN if fs else pygame.RESIZABLE)
        idx = min(int(cfg["display.display_index"]), max(0, pygame.display.get_num_displays() - 1)) if not self.headless else 0
        vsync = 1 if cfg["display.vsync"] else 0
        for attempt in ((flags, vsync), (flags, 0), (pygame.SCALED, 0), (0, 0)):
            try:
                self.screen = pygame.display.set_mode((W, H), attempt[0], display=idx, vsync=attempt[1])
                break
            except pygame.error as exc:
                log.warning("set_mode %s failed: %s", attempt, exc)
        pygame.display.set_caption("Market Hockey — هاکی بازار")
        pygame.mouse.set_visible(not (fs and cfg["display.hide_cursor"]))

    def _present(self, frame: pygame.Surface) -> None:
        cfg = self.cfg
        rot = int(cfg["display.rotation"])
        fh, fv = cfg["display.flip_h"], cfg["display.flip_v"]
        sc = cfg["display.output_scale"]
        ox, oy = cfg["display.output_offset_x"], cfg["display.output_offset_y"]
        scr = self.screen
        if rot == 0 and not fh and not fv and abs(sc - 1) < 1e-3 and ox == 0 and oy == 0 and frame.get_size() == scr.get_size():
            scr.blit(frame, (0, 0))
        else:
            img = frame
            if fh or fv:
                img = pygame.transform.flip(img, fh, fv)
            if rot:
                img = pygame.transform.rotate(img, rot)
            if abs(sc - 1) > 1e-3:
                img = pygame.transform.smoothscale(img, (max(1, int(img.get_width() * sc)), max(1, int(img.get_height() * sc))))
            scr.fill((0, 0, 0))
            sw, sh = scr.get_size()
            scr.blit(img, ((sw - img.get_width()) // 2 + ox, (sh - img.get_height()) // 2 + oy))
        pygame.display.flip()

    def _debug_draw(self, renderer, engine, surf) -> None:
        if self.cfg["debug.calibration"]:
            draw_calibration(renderer, engine, surf)
        if self.cfg["debug.overlay"]:
            draw_debug(renderer, engine, surf, self.fps)

    # ------------------------------------------------------------------ loop
    def tick(self, frame_dt: float, now: float) -> pygame.Surface:
        """One frame: inputs -> fixed physics steps -> events -> render. Returns the masked frame."""
        cfg = self.cfg
        eng = self.engine
        step = 1.0 / cfg["physics.hz"]
        self._acc = getattr(self, "_acc", 0.0) + frame_dt
        demo = eng.state == ATTRACT and cfg["match.attract_demo"]
        samples, presence = self.inputs.poll(now, frame_dt, eng, demo)
        n = 0
        while self._acc >= step and n < 12:
            eng.step(step, samples, presence)
            self._acc -= step
            n += 1
        if n >= 12:
            self._acc = 0.0
        events = eng.drain_events()
        self.renderer.handle_events(events, eng)
        if self.audio:
            self.audio.handle_events(events)
        self._log_events(events)
        return self.renderer.render(eng, min(1.0, self._acc / step), frame_dt)

    def run(self, seconds: float | None = None) -> None:
        clock = pygame.time.Clock()
        last = time.perf_counter()
        t_start = last
        while self.running:
            now = time.perf_counter()
            frame_dt = min(0.1, now - last)
            last = now
            for ev in pygame.event.get():
                self._handle_event(ev, now)
            self._check_hold_keys(now)
            self._poll_live()
            self._open_display()
            frame = self.tick(frame_dt, now)
            self._present(frame)
            self._fps_acc.append(frame_dt)
            if len(self._fps_acc) >= 30:
                self.fps = len(self._fps_acc) / max(1e-6, sum(self._fps_acc))
                self._fps_acc.clear()
            self._send_state(now)
            if seconds is not None and now - t_start >= seconds:
                self.running = False
            clock.tick(self.cfg["display.fps_cap"])
        self.shutdown()

    def shutdown(self) -> None:
        self.inputs.close()
        if self.live:
            self.live.close()
        pygame.quit()

    # ------------------------------------------------------------------ input / hotkeys
    def _handle_event(self, ev, now: float) -> None:
        cfg = self.cfg
        eng = self.engine
        if ev.type == pygame.QUIT:
            self.running = False
            return
        self.inputs.handle_event(ev)
        if ev.type == pygame.KEYUP and ev.key == pygame.K_r:
            self._r_down = None
        if ev.type != pygame.KEYDOWN:
            return
        k = ev.key
        mods = pygame.key.get_mods()
        exhibition = cfg["display.exhibition_mode"]
        if k == pygame.K_ESCAPE:
            if now - self._esc_t < 1.5:
                self.running = False
            else:
                self._esc_t = now
                self.renderer.toast("برای خروج دوباره Esc را بزنید", (255, 255, 255), None, 0.7)
        elif k in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
            if eng.state in (ATTRACT, RESULT):
                eng.start_match()
        elif k == pygame.K_p:
            eng.toggle_pause()
        elif k == pygame.K_r:
            self._r_down = now
        elif k == pygame.K_F11:
            cfg.set("display.fullscreen", not cfg["display.fullscreen"])
        elif k == pygame.K_d and (mods & pygame.KMOD_CTRL) and (mods & pygame.KMOD_SHIFT):
            cfg.set("debug.overlay", not cfg["debug.overlay"])
        elif exhibition:
            return
        elif k == pygame.K_F1:
            self.open_panel()
        elif k == pygame.K_F2:
            cfg.set("debug.calibration", not cfg["debug.calibration"])
        elif k == pygame.K_F3:
            cfg.set("debug.overlay", not cfg["debug.overlay"])
        elif cfg["debug.overlay"]:
            nums = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8,
                    pygame.K_9, pygame.K_0]
            if k in nums:
                ids = list(eng.types)
                i = nums.index(k)
                if i < len(ids):
                    eng.force_spawn(ids[i])
            elif k == pygame.K_b:
                eng.debug_spawn_ball()

    def _check_hold_keys(self, now: float) -> None:
        if self._r_down is not None and now - self._r_down >= 0.5:
            self._r_down = None
            self.engine.reset_to_attract()

    def open_panel(self) -> None:
        if self.panel_proc is not None and self.panel_proc.poll() is None:
            return
        try:
            self.panel_proc = subprocess.Popen(launch_command("panel"), cwd=str(ROOT))
        except OSError as exc:
            log.error("could not open the control panel: %s", exc)

    # ------------------------------------------------------------------ live link
    def _poll_live(self) -> None:
        if not self.live:
            return
        for msg, addr in self.live.poll():
            t = msg.get("type")
            if t == "set":
                ok, v, warn = self.cfg.set(str(msg.get("path")), msg.get("value"))
                self.live.send({"type": "ack", "seq": msg.get("seq"), "ok": ok, "value": v, "warning": warn}, addr)
            elif t == "set_many":
                vals = msg.get("values") or {}
                if isinstance(vals, dict):
                    warns = self.cfg.update(vals)
                    if warns:
                        self.live.send({"type": "ack", "ok": False, "warning": "; ".join(warns[:5])}, addr)
            elif t == "command":
                self._command(str(msg.get("name")), msg.get("args") or {})
            elif t == "hello":
                self._state_t = 0.0

    def _command(self, name: str, args: dict) -> None:
        eng = self.engine
        cfg = self.cfg
        if name == "start_match":
            eng.start_match()
        elif name in ("pause", "resume", "toggle_pause"):
            if name == "toggle_pause" or (name == "pause") != eng.paused:
                eng.toggle_pause()
        elif name == "reset_match":
            eng.reset_to_attract()
        elif name == "spawn_powerup":
            eng.force_spawn(str(args.get("id", "")))
        elif name == "spawn_ball":
            eng.debug_spawn_ball()
        elif name == "toggle_debug":
            cfg.set("debug.overlay", not cfg["debug.overlay"])
        elif name == "toggle_calibration":
            cfg.set("debug.calibration", not cfg["debug.calibration"])
        elif name == "apply_display":
            self._display_key = None
        elif name == "reload_from_disk":
            try:
                cfg.update(Config.load(self.config_path).values)
            except Exception:
                log.exception("reload failed")
        elif name == "quit":
            self.running = False

    def _send_state(self, now: float) -> None:
        if not self.live or not self.live.clients:
            return
        if now - self._state_t < 1.0 / max(0.5, self.cfg["live_link.state_hz"]):
            return
        self._state_t = now
        eng = self.engine
        self.live.broadcast({
            "type": "state", "fps": round(self.fps, 1), "state": eng.state, "paused": eng.paused,
            "time_left": round(eng.time_left, 1), "golden": eng.golden, "scores": list(eng.scores),
            "balls": len(eng.live_balls()), "orbs": len(eng.orbs), "phase": eng.phase_index(),
            "effects": [{"id": e.type_id, "target": list(e.target), "left": round(e.remaining, 1)} for e in eng.effects.effects],
            "inputs": [{"u": round(p.u, 3), "present": p.present} for p in eng.paddles],
            "text_backend": self.renderer.text.backend,
            "warnings": self.cfg.warnings[-5:],
        })

    # ------------------------------------------------------------------ logging
    def _log_events(self, events) -> None:
        if not self.cfg["debug.log_matches"]:
            return
        for e in events:
            if e["type"] == "match_end":
                path = LOGS_DIR / "matches.csv"
                new = not path.exists()
                try:
                    with open(path, "a", newline="", encoding="utf-8") as fh:
                        w = csv.writer(fh)
                        if new:
                            w.writerow(["datetime", "duration_s", "score_p1", "score_p2", "winner", "golden_goal",
                                        "powerups_p1", "powerups_p2", "smart_p1", "smart_p2", "hits_p1", "hits_p2"])
                        st = e["stats"]
                        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), round(e["duration"], 1), e["scores"][0],
                                    e["scores"][1], "draw" if e["winner"] is None else f"p{e['winner'] + 1}", e["golden"],
                                    st["powerups"][0], st["powerups"][1], st["smart"][0], st["smart"][1],
                                    st["hits"][0], st["hits"][1]])
                except OSError as exc:
                    log.warning("could not write matches.csv: %s", exc)


# ====================================================================== headless tools
def _headless_env() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def capture_states(out_dir, seed: int = 7) -> list:
    """Render PNGs of every state (used for visual checks and the mask-leak test)."""
    from pathlib import Path

    _headless_env()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    app = GameApp(headless=True, seed=seed)
    app.cfg.set("input.p1.source", "ai")
    app.cfg.set("input.p2.source", "ai")
    eng = app.engine
    dt = 1 / 60
    saved = []
    clock = [0.0]

    def run(sec):
        frame = None
        for _ in range(max(1, int(sec / dt))):
            clock[0] += dt
            frame = app.tick(dt, clock[0])
        return frame

    def save(name, frame):
        p = out / f"{name}.png"
        pygame.image.save(frame, str(p))
        saved.append(p)

    save("01_attract", run(2.5))
    eng.start_match()
    save("02_intro", run(0.45))
    run(0.45 + app.cfg["countdown.ready_s"] + app.cfg["countdown.beat_s"] * 1.15)
    save("03_countdown", run(0.01))
    run(3.0)
    for tid in ("expand", "shrink", "double_ball", "trajectory_reveal"):
        eng.force_spawn(tid)
    save("04_playing", run(1.2))
    # collect a few effects directly so trails, multi-ball and the trajectory reveal are visible
    live = eng.live_balls()
    if live:
        b = live[0]
        if b.owner is None:
            b.owner = 0
        for tid in ("double_ball", "trajectory_reveal", "speed_up", "expand", "shrink"):
            eng.types[tid].collect(eng, b, b.owner)
    save("05_effects", run(0.6))
    save("06_effects_later", run(1.0))
    # force a goal: place a ball just inside P1's goal heading out
    live = eng.live_balls()
    if live:
        b = live[0]
        a = math.radians(eng.geom.goals[0].center)
        b.x, b.y = (eng.geom.R - 3) * math.cos(a), (eng.geom.R - 3) * math.sin(a)
        b.vx, b.vy = 900 * math.cos(a), 900 * math.sin(a)
    save("07_goal", run(0.35))
    eng.time_left = 0.05
    run(app.cfg["match.goal_pause_s"] + 0.6)
    save("08_final", run(0.5))
    save("09_result", run(app.cfg["match.final_freeze_s"] + 0.8))
    app.cfg.set("debug.calibration", True)
    save("10_calibration", run(0.1))
    app.shutdown()
    return saved


def export_icons(out_dir) -> list:
    from pathlib import Path

    _headless_env()
    pygame.init()
    pygame.display.set_mode((64, 64))
    cfg = Config.load(SETTINGS_PATH)
    from .powerups import registry
    from .render.colors import hex_rgb
    from .render.icons import IconCache

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ic = IconCache()
    made = []
    for tid, t in registry.all_types().items():
        cls = cfg[f"powerups.types.{tid}.class"]
        col = hex_rgb(cfg[f"colors.{cls}"])
        s = ic.badge(t.icon, tid, 48, col, cls == "bad", cfg["powerups.icon_scale"])
        bg = pygame.Surface(s.get_size())
        bg.fill((3, 20, 28))
        bg.blit(s, (0, 0))
        p = out / f"{tid}.png"
        pygame.image.save(bg, str(p))
        made.append(p)
    pygame.quit()
    return made


def selftest_text(out_dir) -> list:
    """Render Persian test strings with each available backend (look at the PNGs)."""
    from pathlib import Path

    _headless_env()
    pygame.init()
    pygame.display.set_mode((64, 64))
    from .render.text import TextRenderer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tests = ["واکنش به‌موقع!", "حجم معاملات افزایش یافت!", "بازار همیشه در حرکته؛ آماده‌ی تغییر باش.",
             "بازیکن 1", "گل بعدی ×2", "پایان معاملات!", "MARKET HOCKEY 60"]
    made = []
    for backend in ("harfbuzz", "reshaper"):
        cfg = Config()
        cfg.set("text.shaping_backend", backend)
        tr = TextRenderer(cfg)
        surf = pygame.Surface((1000, 80 * len(tests) + 40))
        surf.fill((6, 28, 40))
        y = 20
        for t in tests:
            s = tr.render(t, 44, (255, 255, 255))
            surf.blit(s, (980 - s.get_width(), y))
            y += 80
        tag = tr.render(f"backend: {tr.backend}", 22, (0, 220, 180), "latin")
        surf.blit(tag, (12, 8))
        p = out / f"text_{backend}.png"
        pygame.image.save(surf, str(p))
        made.append(p)
    pygame.quit()
    return made
