#!/usr/bin/env python3
"""Simulate a LiDAR / pose tracker: sends two moving players over UDP to the game's network input.

    python tools/send_fake_tracking.py                 # 'tracking' messages to 127.0.0.1:9100
    python tools/send_fake_tracking.py --blobs         # anonymous blobs (the game assigns players by side)
    python tools/send_fake_tracking.py --host 192.168.1.20 --port 9100

In the control panel set Inputs → Player 1 input / Player 2 input to "network".
Coordinates are normalized to the arena: center (0,0), rim radius 1, +y up.
"""
import argparse
import json
import math
import socket
import time

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=9100)
ap.add_argument("--hz", type=float, default=60)
ap.add_argument("--blobs", action="store_true")
args = ap.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0 = time.perf_counter()
print(f"sending to {args.host}:{args.port} at {args.hz} Hz — Ctrl+C to stop")
try:
    while True:
        t = time.perf_counter() - t0
        a1 = math.radians(180 + 45 * math.sin(t * 0.9))  # player 1 walks along the left arc
        a2 = math.radians(0 + 45 * math.sin(t * 0.7 + 1.3))  # player 2 along the right arc
        r = 0.93
        p1 = {"x": r * math.cos(a1), "y": r * math.sin(a1), "conf": 0.95}
        p2 = {"x": r * math.cos(a2), "y": r * math.sin(a2), "conf": 0.9}
        if args.blobs:
            msg = {"type": "blobs", "t": time.time(), "blobs": [p2, p1, {"x": 0.1, "y": 0.05, "conf": 0.5}]}
        else:
            msg = {"type": "tracking", "t": time.time(), "source": "fake",
                   "players": [{"id": "p1", **p1}, {"id": "p2", **p2}]}
        sock.sendto(json.dumps(msg).encode(), (args.host, args.port))
        time.sleep(1 / args.hz)
except KeyboardInterrupt:
    pass
