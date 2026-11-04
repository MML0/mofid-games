"""
Replay test: runs a recorded lidar session through the full pipeline
(background -> feet -> players -> paddles) as fast as possible, no window,
no lidar, no real time.

    python tests/test_replay.py
    python tests/test_replay.py samples/session_2players.pkl samples/session_2players.settings.json

Prints how long each player was tracked and checks that every paddle stays
on the circle and inside its sector's border limit. Exit code 0 = pass.
"""

import math
import os
import sys
from collections import namedtuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from feet_tracker import Game
from floor_game import find_feet, load_recording
from game_settings import GameSettings
from use_lib import Background


Scan = namedtuple("Scan", "angle dist t step hz")

rec = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "samples", "session_2players.pkl")
settings = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "samples", "session_2players.settings.json")

cfg = GameSettings(settings)
cfg.load()
cfg.path = os.devnull            # never write back

data = [Scan(*s) for s in load_recording(rec)]
t0 = data[0].t
background = [s for s in data if s.t - t0 < cfg.calibration_time][3:]
play = [s for s in data if s.t - t0 >= cfg.calibration_time]

bg = Background(cfg)
bg.learn(background)
game = Game(cfg)

tracked = [0] * cfg.players
fails = []

for i, s in enumerate(play):

    x, y = cfg.to_world(s.angle, s.dist)
    mask, _ = bg.new_points(s, x, y)
    game.update_scan(find_feet(s, x, y, mask, cfg), s.t)

    nxt = play[i + 1].t if i + 1 < len(play) else s.t + 0.1

    for k in range(6):                      # 60 Hz paddle steps between scans
        paddles = game.step(s.t + (nxt - s.t) * k / 6)

    for p, (player, (angle, px, py)) in enumerate(zip(game.players, paddles)):

        tracked[p] += player.active

        if abs(math.hypot(px - cfg.center_x, py - cfg.center_y) - cfg.radius) > 1e-6:
            fails.append(f"P{p + 1} paddle off the circle at {s.t - t0:.1f} s")

        start, size = cfg.sectors()[p]
        rel = (angle - start) % 360
        gap = cfg.gap(size)

        if not (gap - 1e-6 <= rel <= size - gap + 1e-6):
            fails.append(f"P{p + 1} paddle in the border zone at {s.t - t0:.1f} s ({rel:.2f}° in sector)")

print(f"{len(play)} scans ({play[-1].t - play[0].t:.0f} s) after a {len(background)}-scan background")

for p, n in enumerate(tracked):
    print(f"P{p + 1} tracked {100 * n / len(play):.0f}% of the time")

if not any(tracked):
    fails.append("no player was ever tracked")

for f in fails[:10]:
    print("FAIL", f)

print("PASS" if not fails else f"{len(fails)} FAIL")
sys.exit(1 if fails else 0)
