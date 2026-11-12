"""LiDAR input: the floor tracker in LIdar/ sees the players' feet and sends one paddle per player over OSC.

    /paddle [player 1..N, x mm, y mm, angle deg, active 0/1, confidence 0..1]     ~60 times a second

Only the angle is used (LIdar/docs/INTEGRATION.md §3): the paddle goes to the same angle on the game's circle, so it
sits under the player's feet whatever the game's own size and units. The tracker already predicts and smooths, so
the game adds no smoothing of its own. `active` 0 means nobody is in that sector: the player reads as absent, as
with any other source.

With input.lidar.autostart on, the game starts the tracker itself (lidar_tracker.py, or LidarTracker.exe in the
Windows build) and stops it on exit. Only that process opens the LiDAR's serial port.
"""

from __future__ import annotations

import logging
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from .. import paths
from . import osc
from .base import InputAdapter, PlayerSample

log = logging.getLogger(__name__)


def tracker_command(cfg) -> list[str]:
    """The command line that starts the tracker, sending to this game's port."""
    if paths.FROZEN:
        exe = paths.APP_DIR / ("LidarTracker" + (".exe" if sys.platform == "win32" else ""))
        cmd = [str(exe)]
    else:
        cmd = [sys.executable, str(paths.APP_DIR / "lidar_tracker.py")]
    settings = Path(cfg["input.lidar.settings_file"])
    if not settings.is_absolute():
        settings = paths.APP_DIR / settings
    cmd += ["--osc-ip", "127.0.0.1", "--osc-port", str(int(cfg["input.lidar.port"])), "--settings", str(settings)]
    replay = str(cfg["input.lidar.replay_file"]).strip()
    if replay:
        path = Path(replay)
        cmd += ["--replay", str(path if path.is_absolute() else paths.APP_DIR / path), "--loop"]
    else:
        cmd += ["--port", str(cfg["input.lidar.serial_port"])]
    if cfg["input.lidar.tracker_window"] == "hidden":
        cmd.append("--headless")
    return cmd + ["--parent", str(os.getpid())]


class LidarAdapter(InputAdapter):
    name = "lidar"
    smooth = False  # already predicted and smoothed by the tracker: more would only add lag

    def __init__(self, cfg):
        super().__init__(cfg)
        self.sock = None
        self.tracker: subprocess.Popen | None = None
        self.latest: dict[int, tuple] = {}  # tracker player number -> (time, angle, active, confidence)
        self.packets = 0
        self.start()

    # ------------------------------------------------------------------ lifetime
    def start(self) -> None:
        cfg = self.cfg
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((cfg["input.lidar.bind"], int(cfg["input.lidar.port"])))
            s.setblocking(False)
            self.sock = s
            log.info("LiDAR input listening on %s:%s", cfg["input.lidar.bind"], cfg["input.lidar.port"])
        except OSError as exc:
            log.error("LiDAR input unavailable: %s", exc)
            return
        if cfg["input.lidar.autostart"]:
            self._launch()

    def _launch(self) -> None:
        cmd = tracker_command(self.cfg)
        try:
            paths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            out = open(paths.LOGS_DIR / "lidar_tracker.log", "w", encoding="utf-8")
        except OSError:
            out = subprocess.DEVNULL
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if self.cfg["input.lidar.tracker_window"] == "hidden" else 0
            env = dict(os.environ, PYTHONUNBUFFERED="1")  # its log is complete even when it is stopped
            self.tracker = subprocess.Popen(cmd, cwd=str(paths.APP_DIR), stdout=out, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, creationflags=flags, env=env)
            log.info("LiDAR tracker started: %s", " ".join(cmd))
        except OSError as exc:
            log.error("LiDAR tracker could not start (%s): %s", " ".join(cmd), exc)
        finally:
            if out is not subprocess.DEVNULL:
                out.close()  # the child keeps its own handle

    def stop(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None
        t, self.tracker = self.tracker, None
        if t and t.poll() is None:
            t.terminate()
            try:
                t.wait(3)
            except subprocess.TimeoutExpired:
                t.kill()

    @property
    def tracker_running(self) -> bool:
        return self.tracker is not None and self.tracker.poll() is None

    # ------------------------------------------------------------------ input
    def feed(self, data: bytes, now: float | None = None) -> None:
        """One UDP packet (also used by tests). Anything malformed is dropped: a tracker bug must never reach the game."""
        now = time.perf_counter() if now is None else now
        try:
            messages = osc.decode(data)
        except Exception:  # noqa: BLE001 - garbage of any shape is simply not a paddle
            return
        for address, args in messages:
            if address != "/paddle" or len(args) < 6:
                continue
            try:
                player, angle, active, conf = int(args[0]), float(args[3]), int(args[4]), float(args[5])
            except (TypeError, ValueError, OverflowError):
                continue
            if not (math.isfinite(angle) and math.isfinite(conf)) or not 1 <= player <= 8:
                continue
            self.packets += 1
            self.latest[player] = (now, angle % 360.0, bool(active), min(1.0, max(0.0, conf)))

    def update(self, now, dt, engine) -> None:
        for _ in range(400 if self.sock else 0):  # 2 players x 60 Hz, with room for a busy frame
            try:
                data, _ = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except ConnectionResetError:  # Windows reports ICMP port-unreachable on UDP; just skip it
                continue
            except OSError:
                break
            self.feed(data, now)

    def game_angle(self, angle: float) -> float:
        """The tracker's angle (0 = +x, counter-clockwise) on the game's circle, after the mirror and the offset."""
        c = self.cfg
        if c["input.lidar.mirror_x"]:
            angle = 180.0 - angle
        if c["input.lidar.mirror_y"]:
            angle = -angle
        return (angle + c["input.lidar.angle_offset_deg"]) % 360.0

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        player = (2 - idx) if self.cfg["input.lidar.swap_players"] else idx + 1
        rec = self.latest.get(player)
        if rec is None or now - rec[0] > self.cfg["input.lidar.timeout_s"] or not rec[2]:
            return PlayerSample(False, None, 0.0, now, None, self.name)
        ang = math.radians(self.game_angle(rec[1]))
        xy = (math.cos(ang), math.sin(ang))  # on the rim, in the arena's normalized frame
        if engine is None:
            return PlayerSample(False, None, rec[3], now, xy, self.name)
        u = engine.geom.angle_to_u(idx, math.degrees(ang), engine.paddle_width(idx))
        return PlayerSample(True, float(u), rec[3], now, xy, self.name, bool(self.cfg["input.lidar.instant_paddle"]))
