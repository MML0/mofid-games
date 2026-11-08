"""
Circular floor game: lidar foot tracking -> one paddle per player -> OSC.

Players stand around a circle on the floor, each in their own sector. The
lidar sees their feet; every player gets a virtual paddle that sits exactly
on the circle at the player's angle, never closer than "Border limit" to a
dividing line. Feet far from the circle (spectators, the middle of the
arena) are ignored.

Two windows:
  game window    this program. Only the game; the circle fills the window.
  setup window   lidar_setup.py, opened automatically: live lidar view and
                 all settings (Lidar calibration first, then Arena ...).
                 Every change is applied live and saved to game_settings.json.

Run     python floor_game.py --port COM4
        python floor_game.py --port COM4 --headless          (no game window)
        python floor_game.py --port COM4 --record s.pkl      (save raw scans)
        python floor_game.py --replay s.pkl                  (play them back)

Keys    P lidar dots on / off   V fit view   F fullscreen   S open the setup window
        B scan background   H key hint   ESC quit
        K calibrate with 4 points on the floor (see calibration.py)
        C put the circle back after the lidar got bumped (one object on a point)
Mouse   drag move the map, wheel zoom

OSC     /paddle [player, x, y, angle, active, confidence]   every frame
        /foot   [id, x, y, player]                          with "Send feet"
        x, y in mm on the map (or 0..1 in the arena box), angle in degrees
        around the arena center (0 = right, counter-clockwise)
"""

import argparse
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from calibration import CHANGED, Calibrator
from feet_tracker import Game
from game_settings import GameSettings
from game_view import BACK, DIM, TEXT, View, draw_arena, draw_calibration, draw_chips, snapshot
from lib import Scan
from link import ENGINE_PORT, SETUP_PORT, Endpoint, pack_array
from use_lib import BG_BIN, Background, make_blobs, scan_background


PORT = "COM4"

OSC_IP = "127.0.0.1"
OSC_PORT = 7000

GAME_SIZE = 860
FPS = 60
SETUP_FPS = 30          # state packets to the setup window per second

HERE = os.path.dirname(os.path.abspath(__file__))



# =========================
# LIDAR SOURCES
# =========================

def load_recording(path):
    """Scans of a --record file: [(angle, dist, t, step, hz)]."""

    data = []

    with open(path, "rb") as f:
        while True:
            try:
                data.extend(pickle.load(f))
            except EOFError:
                break

    return data



class ReplayLidar:
    """Plays a recorded session (--record) in real time, like a lidar."""

    def __init__(self, path, loop=False):

        self.data = load_recording(path)
        self.loop = loop
        self.crc_errors = 0
        self.split_angle = 0.0
        self._restart()


    def _restart(self):

        self.start = time.monotonic()
        self.t0 = self.data[0][2]
        self.pos = 0


    def get_scans(self, timeout=0.2):

        if self.pos >= len(self.data):

            if not self.loop:
                time.sleep(timeout)
                return []

            self._restart()

        now = time.monotonic() - self.start
        next_t = self.data[self.pos][2] - self.t0

        if next_t > now:
            time.sleep(min(timeout, next_t - now))
            now = time.monotonic() - self.start

        scans = []

        while self.pos < len(self.data) and self.data[self.pos][2] - self.t0 <= now:
            angle, dist, t, step, hz = self.data[self.pos]
            scans.append(Scan(angle, dist, None, None, None, self.start + t - self.t0, step, hz))
            self.pos += 1

        return scans


    @property
    def finished(self):

        return not self.loop and self.pos >= len(self.data)


    def close(self):
        pass



class RecordingLidar:
    """Passes a real lidar through and appends every scan to a file (safe if the program is killed)."""

    def __init__(self, lidar, path):

        self.lidar = lidar
        self.path = path
        self.file = open(path, "wb")
        self.count = 0
        self.finished = False


    def get_scans(self, timeout=0.2):

        scans = self.lidar.get_scans(timeout)

        if scans:
            pickle.dump([(s.angle, s.dist, s.t, s.step, s.hz) for s in scans], self.file)
            self.file.flush()
            self.count += len(scans)

        return scans


    @property
    def crc_errors(self):
        return self.lidar.crc_errors


    @property
    def split_angle(self):
        return self.lidar.split_angle


    @split_angle.setter
    def split_angle(self, value):
        self.lidar.split_angle = value


    def close(self):

        self.lidar.close()
        self.file.close()
        print(f"Recorded {self.count} scans to {self.path}")



# =========================
# ENGINE
# =========================

def find_feet(scan, x, y, mask, cfg):
    """Objects in the tracking band that are wide enough to be a foot."""

    return [b for b in make_blobs(scan, x, y, mask, cfg) if b[3] >= cfg.min_width]


class Engine:
    """Lidar -> background -> feet -> players -> paddles. Talks to OSC and the setup window."""

    def __init__(self, cfg, lidar, osc):

        self.cfg = cfg
        self.lidar = lidar
        self.osc = osc
        self.background = Background(cfg)
        self.game = Game(cfg)
        self.link = Endpoint(ENGINE_PORT, SETUP_PORT)
        self.scan = None
        self.x = self.y = self.mask = None
        self.blobs = []
        self.new_scan = False
        self.rescan = False
        self.last_link = 0.0
        self.centers = (np.arange(self.background.bins) + 0.5) * BG_BIN
        self.calib = Calibrator(cfg)
        self.loose = None           # calibrating: new points anywhere, not only near the circle
        self.calib_rev = 0          # counts calibrations so the setup window follows them


    # -------------------------
    # BACKGROUND
    # -------------------------

    def calibrate(self, on_progress=None):
        """Scan the empty floor. on_progress(left) may return False to abort."""

        cfg = self.cfg

        def progress(left):
            self.link.send({"calib": max(left, 0.0)})
            self.receive()          # settings stay live while scanning
            if on_progress is not None:
                return on_progress(left)

        print(f"Scanning the empty floor for {cfg.calibration_time} s - keep it clear...")
        scans = scan_background(self.lidar, cfg.calibration_time, progress)

        if scans is None:
            return False

        self.background.learn(scans)
        self.game.reset()
        self.lidar.split_angle = self.background.split_angle
        print(f"Background ready: {len(scans)} scans")

        return True


    # -------------------------
    # LOOP
    # -------------------------

    def tick(self, timeout):
        """Read scans, move paddles, send OSC and the setup state. Call every frame."""

        cfg = self.cfg
        self.receive()

        for scan in self.lidar.get_scans(timeout=timeout):
            self.scan = scan
            self.x, self.y = cfg.to_world(scan.angle, scan.dist)
            self.mask, _ = self.background.new_points(scan, self.x, self.y)
            self.blobs = find_feet(scan, self.x, self.y, self.mask, cfg)
            self.game.update_scan(self.blobs, scan.t)
            self.new_scan = True

            if self.calib.active and self.background.threshold is not None:
                bg = self.background
                self.loose = (scan.dist >= cfg.min_distance) & (scan.dist < bg.threshold[bg._bin(scan.angle)])
                self.calib.feed(make_blobs(scan, self.x, self.y, self.loose, cfg), scan.t)

        now = time.monotonic()
        self.game.step(now)
        self.send_osc()

        if now - self.last_link >= 1 / SETUP_FPS:
            self.last_link = now
            self.send_setup()


    def calibration_changed(self):
        """The 4-point calibration changed the map: use it now, save it, tell the setup window."""

        self.background.update_split()
        self.lidar.split_angle = self.background.split_angle
        self.game.reset()
        self.calib_rev += 1

        try:
            self.cfg.save()
        except OSError as e:
            self.calib.message += f"   Not saved: {e}"


    def snap(self):

        return snapshot(self.game, self.scan.t if self.scan is not None else None)


    def send_osc(self):

        if self.osc is None:
            return

        cfg = self.cfg

        for i, (player, (angle, x, y)) in enumerate(zip(self.game.players, self.game.paddles)):
            ox, oy = cfg.output(x, y)
            self.osc.send_message("/paddle", [i + 1, float(ox), float(oy), float(angle),
                                              int(player.active), float(player.conf)])

        if cfg.send_feet:
            for foot in self.game.tracker.feet:
                if foot.confirmed and foot.owner is not None:
                    ox, oy = cfg.output(foot.x, foot.y)
                    self.osc.send_message("/foot", [foot.id, float(ox), float(oy), foot.owner + 1])


    def send_setup(self):

        message = dict(self.snap())
        scan = self.scan

        message["hz"] = scan.hz if scan is not None else 0.0
        message["crc"] = self.lidar.crc_errors
        message["blobs"] = len(self.blobs)
        message["game_dots"] = bool(self.cfg.game_dots)     # P in the game window changes it

        if self.calib_rev:      # sent every time, so a lost packet does not matter
            message["calib_rev"] = self.calib_rev
            message["calib_values"] = {k: getattr(self.cfg, k) for k in CHANGED}

        if scan is not None and self.new_scan:
            self.new_scan = False
            message["points"] = len(scan.dist)
            message["x"] = pack_array(self.x)
            message["y"] = pack_array(self.y)
            message["mask"] = pack_array(self.mask, np.uint8)

        bg = self.background

        if bg.distance is not None:
            ok = np.isfinite(bg.distance)
            bx, by = self.cfg.to_world(self.centers[ok], bg.distance[ok])
            message["bx"] = pack_array(bx)
            message["by"] = pack_array(by)

        self.link.send(message)


    def receive(self):

        for message in self.link.receive():

            cmd = message.get("cmd")

            if cmd == "set":
                self.cfg.apply(message.get("values", {}))
                self.background.update_threshold()
                if message.get("final"):
                    self.background.update_split()
                    self.lidar.split_angle = self.background.split_angle

            elif cmd == "rescan":
                self.rescan = True



# =========================
# HEADLESS
# =========================

def run_headless(engine, run_time):

    engine.calibrate()
    print("Ready")

    start = time.time()
    last_print = 0.0

    try:
        while (run_time is None or time.time() - start < run_time) and not getattr(engine.lidar, "finished", False):

            if engine.rescan:
                engine.rescan = False
                engine.calibrate()

            engine.tick(1 / FPS)

            if time.time() - last_print >= 1.0:
                last_print = time.time()
                parts = []
                for i, (player, (angle, _, _)) in enumerate(zip(engine.game.players, engine.game.paddles)):
                    state = "seen" if player.seen else ("hold" if player.active else "----")
                    parts.append(f"P{i + 1} {state} {angle:5.1f}°")
                print("  ".join(parts))

    except KeyboardInterrupt:
        pass



# =========================
# GAME WINDOW
# =========================

def open_setup(cfg):

    path = os.path.join(HERE, "lidar_setup.py")

    try:
        return subprocess.Popen([sys.executable, path, "--settings", cfg.path])
    except OSError as e:
        print(f"Setup window not started: {e}")
        return None


def run_window(engine, setup=True, run_time=None, shot=None):

    import pygame

    cfg = engine.cfg

    os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "20,40")
    pygame.init()

    flags = pygame.RESIZABLE
    screen = pygame.display.set_mode((GAME_SIZE, GAME_SIZE), flags)
    pygame.display.set_caption("Floor game")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 15)
    big = pygame.font.SysFont("Segoe UI", 28)
    label_font = pygame.font.SysFont("Segoe UI", 15, bold=True)

    view = View()
    auto_view = True            # the circle fills the window until you zoom or drag
    pan = None                  # (mouse, view x, view y) while dragging
    hint_until = time.time() + 8
    fullscreen = False
    setup_proc = open_setup(cfg) if setup else None
    cal = engine.calib


    def draw_dots():

        if engine.x is None:
            return

        w, h = screen.get_size()
        z = view.zoom
        sx = (w / 2 + (engine.x - view.x) * z).astype(np.int32)
        sy = (h / 2 - (engine.y - view.y) * z).astype(np.int32)
        ok = (sx >= 0) & (sx < w - 3) & (sy >= 0) & (sy < h - 3)
        feet = engine.loose if cal.active and engine.loose is not None else engine.mask
        feet = feet if feet is not None else np.zeros(len(sx), bool)

        for px, py in zip(sx[ok & ~feet].tolist(), sy[ok & ~feet].tolist()):
            screen.fill((40, 75, 125), (px, py, 2, 2))

        for px, py in zip(sx[ok & feet].tolist(), sy[ok & feet].tolist()):
            screen.fill((235, 235, 235), (px, py, 3, 3))


    def calibrate():

        def progress(left):

            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    return False

            w, h = screen.get_size()
            screen.fill(BACK)
            text = big.render(f"Scanning the empty floor  {max(left, 0):.0f}", True, TEXT)
            screen.blit(text, (w // 2 - text.get_width() // 2, h // 2 - 26))
            text = font.render("keep the circle clear", True, DIM)
            screen.blit(text, (w // 2 - text.get_width() // 2, h // 2 + 14))
            pygame.display.flip()

        return engine.calibrate(progress)


    def open_calibration(message=""):

        nonlocal auto_view

        auto_view = True            # the points must be where the floor shows them
        engine.loose = None
        cal.start(message)


    def calibration_key(key):
        """Keys of the calibration mode. Returns True when it used the key."""

        nonlocal auto_view

        if key in (pygame.K_k, pygame.K_ESCAPE):
            cal.stop()

        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_c):
            if cal.apply(shift_only=key == pygame.K_c):
                engine.calibration_changed()
                auto_view = True

        elif key == pygame.K_a:
            cal.auto()

        elif key == pygame.K_u:
            if cal.undo():
                engine.calibration_changed()
                auto_view = True

        elif key == pygame.K_r:
            cal.reset_points()

        else:
            return False

        return True


    try:
        if not calibrate():
            return

        started = time.time()
        running = True

        while running:

            screen = pygame.display.get_surface()

            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:

                    if cal.active and calibration_key(event.key):
                        pass

                    elif event.key == pygame.K_k:
                        open_calibration()

                    elif event.key == pygame.K_c:
                        open_calibration("Put an object on any point, then press C again.")

                    elif event.key == pygame.K_ESCAPE:
                        if fullscreen:
                            fullscreen = False
                            screen = pygame.display.set_mode((GAME_SIZE, GAME_SIZE), pygame.RESIZABLE)
                        else:
                            running = False

                    elif event.key == pygame.K_f:
                        fullscreen = not fullscreen
                        if fullscreen:
                            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                        else:
                            screen = pygame.display.set_mode((GAME_SIZE, GAME_SIZE), pygame.RESIZABLE)

                    elif event.key == pygame.K_s:
                        if setup_proc is None or setup_proc.poll() is not None:
                            setup_proc = open_setup(cfg)

                    elif event.key == pygame.K_b:
                        engine.rescan = True

                    elif event.key == pygame.K_p:
                        cfg.game_dots = not cfg.game_dots
                        try:
                            cfg.save()
                        except OSError:
                            pass

                    elif event.key == pygame.K_v:
                        auto_view = True

                    elif event.key == pygame.K_h:
                        hint_until = time.time() + 8

                elif event.type == pygame.MOUSEWHEEL:
                    auto_view = False
                    view.zoom_at(1.15 ** event.y, pygame.mouse.get_pos())

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                    if not (cal.active and (cal.grab(view, event.pos) if event.button == 1
                                            else cal.clear(view, event.pos))):
                        pan = (event.pos, view.x, view.y)

                elif event.type == pygame.MOUSEMOTION and cal.drag is not None:
                    cal.move(view, event.pos)

                elif event.type == pygame.MOUSEMOTION and pan is not None:
                    (sx, sy), vx, vy = pan
                    if auto_view and abs(event.pos[0] - sx) + abs(event.pos[1] - sy) < 4:
                        continue
                    auto_view = False
                    view.x = vx - (event.pos[0] - sx) / view.zoom
                    view.y = vy + (event.pos[1] - sy) / view.zoom

                elif event.type == pygame.MOUSEBUTTONUP and event.button in (1, 3):
                    pan = None
                    if cal.drag is not None and event.button == 1:
                        cal.release(view)

            if engine.rescan:
                engine.rescan = False
                if not calibrate():
                    break

            engine.tick(0.001)
            cal.sync()

            # the circle with its paddles fills the window
            w, h = screen.get_size()
            view.size = (w, h)
            if auto_view:
                fit_r = cfg.radius + cfg.paddle_size / 2
                view.fit(cfg.center_x, cfg.center_y, fit_r * (1 + cfg.game_margin / 100))

            screen.fill(BACK)

            if cfg.game_dots or cal.active:
                draw_dots()

            draw_arena(screen, view, cfg, engine.snap(), label_font)
            draw_chips(screen, font, engine.snap(), 10, 6)

            if cal.active:
                draw_calibration(screen, view, cal, font, big)

            if time.time() < hint_until:
                hint = "drag move   wheel zoom   V fit   P lidar dots   F fullscreen   S setup   K calibrate   H help"
                screen.blit(font.render(hint, True, (70, 74, 86)), (10, h - 26))

            pygame.display.flip()
            clock.tick(FPS)

            if run_time is not None and time.time() - started >= run_time:
                running = False

        if shot:
            pygame.image.save(screen, shot)

    finally:
        if setup_proc is not None and setup_proc.poll() is None:
            setup_proc.terminate()
        pygame.quit()



# =========================
# MAIN
# =========================

def main():

    parser = argparse.ArgumentParser(description="Circular floor game: lidar feet -> paddles -> OSC")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--headless", action="store_true", help="no game window, print paddles")
    parser.add_argument("--no-setup", action="store_true", help="do not open the setup window")
    parser.add_argument("--time", type=float, default=None, help="stop after N seconds")
    parser.add_argument("--no-osc", action="store_true")
    parser.add_argument("--osc-ip", default=OSC_IP, help=f"where the game listens (default {OSC_IP})")
    parser.add_argument("--osc-port", type=int, default=OSC_PORT, help=f"OSC port (default {OSC_PORT})")
    parser.add_argument("--settings", default=None, help="settings file (default: game_settings.json)")
    parser.add_argument("--record", default=None, help="save every raw scan to this file")
    parser.add_argument("--replay", default=None, help="play a recorded file instead of the lidar")
    parser.add_argument("--loop", action="store_true", help="replay: start over at the end")
    parser.add_argument("--shot", default=None, help="save a screenshot of the game window when it closes")
    args = parser.parse_args()

    cfg = GameSettings(args.settings) if args.settings else GameSettings()
    print(f"Settings loaded: {cfg.path}" if cfg.load() else "Settings: defaults")

    osc = None

    if not args.no_osc:
        from pythonosc.udp_client import SimpleUDPClient
        osc = SimpleUDPClient(args.osc_ip, args.osc_port)
        print(f"OSC to {args.osc_ip}:{args.osc_port}")

    if args.replay:
        lidar = ReplayLidar(args.replay, loop=args.loop)
    else:
        from lib import D800
        lidar = D800(args.port)
        if args.record:
            lidar = RecordingLidar(lidar, args.record)

    engine = Engine(cfg, lidar, osc)

    try:
        if args.headless:
            run_headless(engine, args.time)
        else:
            run_window(engine, not args.no_setup, args.time, args.shot)
    finally:
        engine.link.close()
        lidar.close()



if __name__ == "__main__":
    main()
