"""
Scenario tests for feet_tracker.Game (no lidar needed).

    python tests/test_tracker.py        exit code 0 = all pass

Each scenario feeds made-up foot blobs (x, y, points, width) at 10 Hz into
the tracker and checks the paddles: standing still, off the line, border
limit, two players on one border, jumping, walking at 3 speeds, spectators,
intruders, noise, reacquire, border flicker, foot-ID stealing, custom
sectors, moved arena center.
"""
import os, sys, math, random, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from game_settings import GameSettings
from feet_tracker import Game

S = tempfile.gettempdir()
random.seed(1)
fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("  " + info if info else ""))
    if not ok:
        fails.append(name)


def feet_at(angle, r, spread=150, noise=8, lift=None):
    """two feet of a person standing at angle (deg) / radius r around (0,0); lift = 'L', 'R', 'both'"""
    a = math.radians(angle)
    cx, cy = math.cos(a) * r, math.sin(a) * r
    tx, ty = -math.sin(a), math.cos(a)  # tangent
    out = []
    for side, s in (("L", -1), ("R", 1)):
        if lift in (side, "both"):
            continue
        out.append((cx + tx * s * spread + random.gauss(0, noise), cy + ty * s * spread + random.gauss(0, noise), 20, 120))
    return out


def run(cfg, frames):
    """frames: list of blob lists, one per scan at 10 Hz. Returns per-scan (players, paddles)."""
    g = Game(cfg)
    hist = []
    t = 100.0
    for blobs in frames:
        g.update_scan(blobs, t)
        for k in range(6):
            pads = g.step(t + k / 60)
        hist.append(([(p.active, p.seen, p.conf, p.x, p.y) for p in g.players], [p[0] for p in pads]))
        t += 0.1
    return g, hist


def angdiff(a, b):
    return abs((a - b + 180) % 360 - 180)


cfg = GameSettings(path=S + r"\synth.json")   # defaults: 2 players, line 90 -> P1 90..270, P2 270..450

# 1. standing still: paddle steady on the player's angle
frames = [feet_at(180, 2000) for _ in range(50)]
g, h = run(cfg, frames)
pads = [x[1][0] for x in h[20:]]
check("stand still: paddle at 180", angdiff(pads[-1], 180) < 1, f"{pads[-1]:.2f}")
check("stand still (8 mm noise): jitter < 0.4 deg", max(pads) - min(pads) < 0.4, f"{max(pads)-min(pads):.3f}")
check("stand still: P2 free", not h[-1][0][1][0])

# 2. standing off the line (500 mm inside): paddle still on circle, same angle
g, h = run(cfg, [feet_at(200, 1500) for _ in range(30)])
_, x, y = g.paddles[0]
check("off line: paddle on circle", abs(math.hypot(x, y) - 2000) < 1e-6)
check("off line: paddle at player angle", angdiff(h[-1][1][0], 200) < 1, f"{h[-1][1][0]:.1f}")

# 3. border limit: player stands right on the line at 90 deg -> paddle at 100 (P1) not beyond
g, h = run(cfg, [feet_at(95, 2000) for _ in range(30)])
check("border: P1 paddle clamped at 100", angdiff(h[-1][1][0], 100) < 0.01, f"{h[-1][1][0]:.2f}")
g, h = run(cfg, [feet_at(85, 2000) for _ in range(30)])
check("border: P2 paddle clamped at 80", angdiff(h[-1][1][1], 80) < 0.01, f"{h[-1][1][1]:.2f}")

# 4. two players at the same border never closer than 2 x gap
g, h = run(cfg, [feet_at(92, 2000) + feet_at(88, 2000, spread=100) for _ in range(30)])
d = angdiff(h[-1][1][0], h[-1][1][1])
check("two players at border: paddles >= 20 deg apart", d >= 20 - 1e-6, f"{d:.2f}")

# 5. jump: both feet gone 0.5 s -> held (no release, no move), then back
frames = [feet_at(150, 2000) for _ in range(20)] + [[] for _ in range(5)] + [feet_at(150, 2000) for _ in range(10)]
g, h = run(cfg, frames)
held = [x[0][0][0] for x in h[20:25]]
pads = [x[1][0] for x in h[18:35]]
check("jump: player kept while airborne", all(held))
check("jump: paddle stays put", max(pads) - min(pads) < 0.5, f"{max(pads)-min(pads):.2f}")

# 6. lost for longer than hold_time -> released
frames = [feet_at(150, 2000) for _ in range(20)] + [[] for _ in range(15)]
g, h = run(cfg, frames)
check("long gap: player released after hold", not h[-1][0][0][0])

# 7. realistic walking: planted feet, the swinging foot is not seen
def walk_frames(v, n=80, start=120.0, period=0.6, swing=0.2, seen_swing=False):
    """v mm/s along the circle. Each foot is planted (still) then swings forward unseen."""
    frames, truth = [], []
    for i in range(n):
        t = i * 0.1
        blobs = []
        for k, side in enumerate((-1, 1)):
            phase = (t + k * period / 2) % period
            t_plant = t - phase                       # this foot's last landing
            planted = phase < period - swing
            s = v * (t_plant + period / 2)            # lands ahead of the body
            if planted or seen_swing:
                a = math.radians(start) + s / 2000
                r = 2000 + side * 100
                blobs.append((math.cos(a) * r + random.gauss(0, 6), math.sin(a) * r + random.gauss(0, 6), 20, 120))
        frames.append(blobs)
        truth.append(start + math.degrees(v * t / 2000))
    return frames, truth

for v in (300, 800, 1500):
    frames, truth = walk_frames(v, n=int(min(80, 4500 / (v * 0.1))), start=110)   # stays in P1's sector
    g, h = run(cfg, frames)
    errs = [angdiff(x[1][0], truth[i]) for i, x in enumerate(h) if i > 15]
    back = [((h[i][1][0] - h[i - 1][1][0] + 180) % 360 - 180) for i in range(16, len(h))]
    check(f"walk {v} mm/s: follows (err < {2 + v/400:.1f} deg)", max(errs) < 2 + v / 400, f"max err {max(errs):.2f}")
    check(f"walk {v} mm/s: never moves backward > 0.5 deg", min(back) > -0.5, f"min step {min(back):.2f}")

# 8. spectator outside band and a person in the middle are ignored
frames = [feet_at(180, 2000) + feet_at(330, 3000) + feet_at(300, 600) for _ in range(30)]
g, h = run(cfg, frames)  # NOTE: band filtering is done by the background mask; emulate it
in_band = lambda b: abs(math.hypot(b[0], b[1]) - 2000) <= 600
g, h = run(cfg, [[b for b in f if in_band(b)] for f in frames])
check("outside band ignored: P2 stays free", not h[-1][0][1][0])

# 9. another person walks into P1's sector while P1 is tracked -> P1 stays on its player
frames = []
for i in range(40):
    f = feet_at(200, 2000)
    if i >= 15:
        f += feet_at(140 + (i - 15) * 0.5, 2100)   # intruder 60 deg away (> player radius)
    frames.append(f)
g, h = run(cfg, frames)
check("intruder ignored: P1 stays at 200", angdiff(h[-1][1][0], 200) < 1, f"{h[-1][1][0]:.1f}")

# 10. noise blob (single scans, random) does not create players
frames = [[(random.uniform(-2500, 2500), random.uniform(-2500, 2500), 3, 40)] if i % 4 == 0 else [] for i in range(100)]
g, h = run(cfg, frames)
check("random single-scan noise: no player", not any(any(p[0] for p in x[0]) for x in h))

# 11. reacquire: P1 lost, then player re-appears 60 deg away -> paddle glides (no jump)
frames = [feet_at(150, 2000) for _ in range(20)] + [[] for _ in range(15)] + [feet_at(210, 2000) for _ in range(30)]
g, h = run(cfg, frames)
steps = [angdiff(h[i][1][0], h[i - 1][1][0]) for i in range(36, 65)]
check("reacquire: glides, max step per scan <= speed limit", max(steps) <= math.degrees(cfg.paddle_speed / cfg.radius) * 0.1 + 0.01, f"{max(steps):.2f}")
check("reacquire: ends at new spot", angdiff(h[-1][1][0], 210) < 1, f"{h[-1][1][0]:.1f}")

# 12. sector handover hysteresis: foot straddling the line jitters +-2 deg -> no owner flicker
frames = [feet_at(90 + random.uniform(-2, 2), 2000, spread=30) for _ in range(40)]
g, h = run(cfg, frames)
owners = [x[0][0][0] for x in h[5:]]
check("border jitter: one owner only (no flicker)", len(set(owners)) == 1)

# 12b. object appears next to a standing player (one foot missed for a scan): no ID steal
def blob_at(angle, r):
    a = math.radians(angle)
    return (math.cos(a) * r, math.sin(a) * r, 20, 120)

g = Game(cfg); t = 100.0
for i in range(30):
    g.update_scan(feet_at(180, 2000, noise=3), t); g.step(t); t += 0.1
ids_before = sorted(f.id for f in g.players[0].feet)
pad_before = g.step(t)[0][0]
pads = []
for i in range(40):
    feet = feet_at(180, 2000, noise=3, lift="L" if i in (0, 1, 7) else None)
    feet.append(blob_at(180 + 7.5, 2000))      # object ~260 mm from the left foot
    if i > 20:
        feet.append(blob_at(180 - 7.5, 2050))  # and a second one on the other side
    g.update_scan(feet, t)
    for k in range(6):
        pads.append(g.step(t + k / 60)[0][0])
    t += 0.1
ids_after = sorted(f.id for f in g.players[0].feet)
check("object next to standing player: player keeps its foot IDs", ids_before == ids_after, f"{ids_before} -> {ids_after}")
check("object next to standing player: max 2 feet used", len(g.players[0].feet) == 2)
check("object next to standing player: paddle steady", max(angdiff(p, pad_before) for p in pads) < 1.0,
      f"max move {max(angdiff(p, pad_before) for p in pads):.2f}")

# 13. 4 players, custom sectors
cfg4 = GameSettings(path=S + r"\synth4.json")
cfg4.players = 4; cfg4.equal_sectors = False; cfg4.sector_1 = 60; cfg4.sector_2 = 120; cfg4.sector_3 = 60; cfg4.sector_4 = 120; cfg4.line_angle = 0
secs = cfg4.sectors()
check("custom sectors sum 360", abs(sum(s for _, s in secs) - 360) < 1e-6, str(secs))
g, h = run(cfg4, [feet_at(30, 2000) + feet_at(120, 2000) + feet_at(210, 2000) + feet_at(300, 2000) for _ in range(30)])
want = [30, 120, 210, 300]
check("4 players each tracked", all(angdiff(h[-1][1][i], want[i]) < 1 for i in range(4)), str([round(a, 1) for a in h[-1][1]]))

# 14. arena center not at lidar
cfgc = GameSettings(path=S + r"\synthc.json"); cfgc.center_x = 1000; cfgc.center_y = -500
frames = [[(b[0] + 1000, b[1] - 500, b[2], b[3]) for b in feet_at(180, 2000)] for _ in range(30)]
g, h = run(cfgc, frames)
_, x, y = g.paddles[0]
check("moved center: paddle on circle at 180", abs(math.hypot(x - 1000, y + 500) - 2000) < 1e-6 and angdiff(h[-1][1][0], 180) < 1, f"{h[-1][1][0]:.1f}")

print("\nALL PASS" if not fails else f"\n{len(fails)} FAIL: {fails}")

sys.exit(1 if fails else 0)

