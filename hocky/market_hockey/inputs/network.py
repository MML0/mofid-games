"""Network adapter: receives tracked player positions over UDP (LiDAR, TouchDesigner, CCTV pose, ...).

Messages (JSON, UTF-8), coordinates normalized to the arena: center (0,0), rim radius 1, +y up:
  {"type":"tracking","t":..., "players":[{"id":"p1","x":-0.9,"y":0.1,"conf":0.9}, {"id":"p2",...}]}
  {"type":"blobs","t":..., "blobs":[{"x":..,"y":..,"conf":..}, ...]}   # assigned to players by region
Optional "u" per player (0..1 along its arc) skips the geometry mapping entirely.
Use the calibration settings (offset/scale/rotation/flip) when the tracker's frame differs.
"""

from __future__ import annotations

import json
import logging
import math
import socket
import time

from .base import InputAdapter, PlayerSample

log = logging.getLogger(__name__)


class NetworkAdapter(InputAdapter):
    name = "network"
    smooth = True

    def __init__(self, cfg):
        super().__init__(cfg)
        self.sock = None
        self.latest: dict[int, tuple] = {}  # idx -> (time, x, y, conf, u)
        self.blobs: tuple | None = None
        self.messages = 0
        self.start()

    def start(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.cfg["input.network.bind"], int(self.cfg["input.network.port"])))
            s.setblocking(False)
            self.sock = s
            log.info("network input listening on %s:%s", self.cfg["input.network.bind"], self.cfg["input.network.port"])
        except OSError as exc:
            log.error("network input unavailable: %s", exc)

    def stop(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def calibrate(self, x: float, y: float) -> tuple[float, float]:
        c = self.cfg
        if c["input.network.flip_x"]:
            x = -x
        if c["input.network.flip_y"]:
            y = -y
        x *= c["input.network.scale_x"]
        y *= c["input.network.scale_y"]
        a = math.radians(c["input.network.rotation_deg"])
        x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        return x + c["input.network.offset_x"], y + c["input.network.offset_y"]

    def feed(self, msg: dict, now: float | None = None) -> None:
        """Process one decoded message (also used by tests)."""
        now = time.perf_counter() if now is None else now
        self.messages += 1
        if msg.get("type") == "tracking":
            for pl in msg.get("players", []):
                pid = str(pl.get("id", "")).lower()
                idx = 0 if pid in ("p1", "1", "0", "player1") else 1 if pid in ("p2", "2", "player2") else None
                if idx is None:
                    continue
                x, y = self.calibrate(float(pl.get("x", 0)), float(pl.get("y", 0)))
                self.latest[idx] = (now, x, y, float(pl.get("conf", 1.0)), pl.get("u"))
        elif msg.get("type") == "blobs":
            pts = []
            for bl in msg.get("blobs", []):
                x, y = self.calibrate(float(bl.get("x", 0)), float(bl.get("y", 0)))
                pts.append((x, y, float(bl.get("conf", 1.0))))
            self.blobs = (now, pts)

    def update(self, now, dt, engine):
        for _ in range(200 if self.sock else 0):
            try:
                data, _ = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except ConnectionResetError:  # Windows reports ICMP port-unreachable on UDP; just skip it
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(msg, dict):
                self.feed(msg, now)
        if self.blobs is not None and engine is not None:
            t0, pts = self.blobs
            for idx in (0, 1):
                arc = engine.geom.goals[idx]
                best = None
                for x, y, conf in pts:
                    ang = math.degrees(math.atan2(y, x))
                    if arc.contains(ang, margin=12.0):
                        r = math.hypot(x, y)
                        if best is None or r > best[0]:
                            best = (r, x, y, conf)
                if best:
                    self.latest[idx] = (t0, best[1], best[2], best[3], None)
            self.blobs = None

    def sample(self, idx, now, dt, engine) -> PlayerSample:
        rec = self.latest.get(idx)
        if rec is None or now - rec[0] > self.cfg["input.network.timeout_s"]:
            return PlayerSample(False, None, 0.0, now, None, self.name)
        t0, x, y, conf, u = rec
        if u is None:
            if engine is None:
                return PlayerSample(False, None, 0.0, now, (x, y), self.name)
            ang = math.degrees(math.atan2(y, x))
            u = engine.geom.angle_to_u(idx, ang, engine.paddle_width(idx))
        return PlayerSample(True, float(u), conf, now, (x, y), self.name)
