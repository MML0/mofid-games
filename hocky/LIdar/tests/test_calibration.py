"""
Tests of the lidar scale, the 4-point calibration and the settings panel's
precise number controls (no lidar and no screen needed).

    python tests/test_calibration.py        exit code 0 = all pass

Set CAL_SHOTS to a folder to also save pictures of the Floor game window.
"""
import itertools, math, os, random, sys, tempfile, time
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pygame

import calibration as C
import floor_game as FG
from game_settings import GameSettings
from game_view import View
from lib import Scan
from settings_ui import SettingsPanel
from use_lib import make_blobs

S = tempfile.gettempdir()
SHOTS = os.environ.get("CAL_SHOTS")
random.seed(2)
fails = []


def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("  " + info if info else ""))
    if not ok:
        fails.append(name)


def make(**values):
    cfg = GameSettings(path=os.path.join(S, "cal_test.json"))
    for k, v in values.items():
        cfg.set(k, v)
    return cfg


def raw_of(cfg, x, y):
    """Lidar (angle, distance) of a map point: the inverse of cfg.to_world."""
    if cfg.flip_x:
        x = -x
    if cfg.flip_y:
        y = -y
    return math.degrees(math.atan2(y, x)) - cfg.rotation, math.hypot(x, y) / cfg.lidar_scale


def world(cfg, angle, dist):
    x, y = cfg.to_world(angle, dist)
    return float(x), float(y)


def floor_raw(true_cfg, wrong_cfg):
    """The objects stand where the floor shows the points: home offsets, read by the true calibration."""
    out = []
    for hx, hy in C.home_points(wrong_cfg):
        out.append(raw_of(true_cfg, hx - wrong_cfg.center_x + true_cfg.center_x,
                          hy - wrong_cfg.center_y + true_cfg.center_y))
    return out


def lands_on_homes(cfg, raws, homes_rel, tol):
    """Largest distance between an object, after calibration, and its point."""
    worst = 0.0
    for (a, d), (rx, ry) in zip(raws, homes_rel):
        x, y = world(cfg, a, d)
        worst = max(worst, math.hypot(x - cfg.center_x - rx, y - cfg.center_y - ry))
    return worst <= tol, worst


TRUE = dict(rotation=150.5, flip_x=True, diameter=2100, center_x=-340, center_y=2530, lidar_scale=1.0)
WRONG = dict(rotation=143.0, flip_x=True, diameter=2100, center_x=-100, center_y=2300, lidar_scale=0.95)


# -------------------------
# SCALE
# -------------------------

cfg = make(lidar_scale=1.25)
x, y = cfg.to_world(0.0, 2000.0)
check("scale stretches the map around the lidar", abs(float(x) - 2500) < 1e-6 and abs(float(y)) < 1e-6)

cfg = make(lidar_scale=2.0, center_x=0, center_y=1000, diameter=2000, band_out=500)
check("reach is in raw lidar distance", abs(cfg.reach() - 1250) < 1e-6, f"{cfg.reach()}")

ang = np.arange(0, 3, 0.5)
dist = np.full(len(ang), 2000.0)
scan = Scan(ang, dist, None, None, None, 0.0, 0.5, 10.0)
cfg = make(lidar_scale=1.5, min_width=5)
cfg.rotation = 0
xs, ys = cfg.to_world(ang, dist)
blobs = make_blobs(scan, xs, ys, np.ones(len(ang), bool), cfg)
check("feet use the scale too", len(blobs) == 1 and abs(math.hypot(blobs[0][0], blobs[0][1]) - 3000) < 1,
      f"{blobs}")


# -------------------------
# SOLVE
# -------------------------

true_cfg, wrong_cfg = make(**TRUE), make(**WRONG)
raws = floor_raw(true_cfg, wrong_cfg)
homes = C.home_points(wrong_cfg)
rel = [(hx - wrong_cfg.center_x, hy - wrong_cfg.center_y) for hx, hy in homes]
seen = [world(wrong_cfg, a, d) for a, d in raws]

r = C.solve(wrong_cfg, list(zip(seen, homes)))
wrong_cfg.apply(r["values"])
ok, worst = lands_on_homes(wrong_cfg, raws, rel, 3)
check("4 points: objects land on the points", ok, f"worst {worst:.2f} mm")
check("4 points: finds rotation", abs(wrong_cfg.rotation - 150.5) <= 0.06, f"{wrong_cfg.rotation}")
check("4 points: finds scale", abs(wrong_cfg.lidar_scale - 1.0) <= 0.002, f"{wrong_cfg.lidar_scale}")
check("circle size is left alone", wrong_cfg.diameter == 2100)

for fx, fy in itertools.product((False, True), repeat=2):
    t = make(**dict(TRUE, flip_x=fx, flip_y=fy))
    w = make(**dict(WRONG, flip_x=fx, flip_y=fy))
    raws = floor_raw(t, w)
    homes = C.home_points(w)
    rel = [(hx - w.center_x, hy - w.center_y) for hx, hy in homes]
    w.apply(C.solve(w, list(zip([world(w, a, d) for a, d in raws], homes)))["values"])
    ok, worst = lands_on_homes(w, raws, rel, 3)
    check(f"mirrors X={fx} Y={fy}", ok, f"worst {worst:.2f} mm")

t = make(**TRUE)
w = make(**dict(WRONG, flip_x=False))
raws = floor_raw(t, w)
homes = C.home_points(w)
rel = [(hx - w.center_x, hy - w.center_y) for hx, hy in homes]
r = C.solve(w, list(zip([world(w, a, d) for a, d in raws], homes)))
w.apply(r["values"])
ok, worst = lands_on_homes(w, raws, rel, 3)
check("wrong mirror is found and fixed", r["mirror"] and w.flip_x and ok, f"worst {worst:.2f} mm")

w = make(**WRONG)
before = (w.rotation, w.lidar_scale)
homes = C.home_points(w)
r = C.solve(w, [((homes[0][0] + 120, homes[0][1] - 80), homes[0])], shift_only=True)
check("position only keeps rotation and scale",
      (r["values"]["rotation"], r["values"]["lidar_scale"]) == before)
check("position only moves the center by the error",
      r["values"]["center_x"] == w.center_x + 120 and r["values"]["center_y"] == w.center_y - 80, f"{r['values']}")


# -------------------------
# AUTOMATIC MATCH
# -------------------------

w = make(**WRONG)
homes = C.home_points(w)
dst = [(hx - w.center_x, hy - w.center_y) for hx, hy in homes]
wrong_fit = min(C.fit(homes, [dst[i] for i in perm])[2]
                for perm in itertools.permutations(range(4)) if perm != (0, 1, 2, 3))
mirror_fit = min(C.fit([(-x, y) for x, y in homes], [dst[i] for i in perm])[2]
                 for perm in itertools.permutations(range(4)))
check("no other matching fits the points", min(wrong_fit, mirror_fit) > 2 * C.MATCH_ERROR * w.radius * w.calib_radius / 100,
      f"next best fit {wrong_fit:.0f} mm, mirrored {mirror_fit:.0f} mm")

t = make(**dict(TRUE, rotation=70))     # map turned 73 degrees from the truth, nothing near its point
raws = floor_raw(t, w)
objects = [world(w, a, d) for a, d in raws]
noisy = [(x + random.gauss(0, 12), y + random.gauss(0, 12)) for x, y in objects]
order = [2, 0, 3, 1]
found = C.match_objects(w, homes, [noisy[i] for i in order])
check("finds every object far from its point",
      found is not None and sorted(i for _, i in found) == [0, 1, 2, 3]
      and all(math.dist(p, noisy[i]) < 1 for p, i in found))

extra = [noisy[i] for i in order] + [(w.center_x + 300, w.center_y - 200), (w.center_x - 900, w.center_y + 700)]
found = C.match_objects(w, homes, extra)
check("ignores extra things on the floor",
      found is not None and len(found) == 4 and all(math.dist(p, noisy[i]) < 1 for p, i in found))

check("automatic match does not guess with 3 objects", C.match_objects(w, homes, noisy[:3]) is None)


# -------------------------
# PANEL
# -------------------------

pygame.init()
screen = pygame.display.set_mode((1240, 900))
cfg = make(rotation=10.0, center_x=100)
changes = []
panel = SettingsPanel(cfg, lambda final: changes.append(final), [], 380)
panel.pin_open()
panel.place((1240, 900))


def press(key, char=""):
    panel.handle(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=char, mod=0))


def click(pos):
    panel.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    panel.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def parts_of(key):
    return next(p for f, _, p in panel.rows if f.key == key)


click(parts_of("rotation")["plus"].center)
check("+ moves one small step", abs(cfg.rotation - 10.05) < 1e-9, f"{cfg.rotation}")
click(parts_of("rotation")["minus"].center)
check("- moves it back", abs(cfg.rotation - 10.0) < 1e-9, f"{cfg.rotation}")

click(parts_of("rotation")["value"].center)
check("typing box starts with the value", panel.edit is not None and panel.text == "10.00", panel.text)
for ch in "45.25":
    press(ord(ch), ch)
press(pygame.K_RETURN)
check("typing replaces the value", abs(cfg.rotation - 45.25) < 1e-9, f"{cfg.rotation}")

click(parts_of("rotation")["value"].center)
press(pygame.K_UP)
check("Up nudges while typing", abs(cfg.rotation - 45.3) < 1e-9, f"{cfg.rotation}")
press(pygame.K_ESCAPE)
check("Esc goes back", abs(cfg.rotation - 45.25) < 1e-9, f"{cfg.rotation}")

click(parts_of("rotation")["value"].center)
press(pygame.K_TAB)
check("Tab goes to the next number", panel.edit is not None and panel.edit.key == "lidar_scale",
      panel.edit.key if panel.edit else "")
for ch in "۱.۰۲۵":
    press(ord(ch), ch)
press(pygame.K_RETURN)
check("Persian digits work", abs(cfg.lidar_scale - 1.025) < 1e-9, f"{cfg.lidar_scale}")

track = parts_of("rotation")["track"]
panel.drag = next(f for f, _, _ in panel.rows if f.key == "rotation")
panel.fine = None
real_mods = pygame.key.get_mods
pygame.key.get_mods = lambda: pygame.KMOD_LSHIFT
try:
    panel._slide(track.x + 50)      # Shift: no jump where the mouse is
    first = cfg.rotation
    panel._slide(track.x + 70)
    second = cfg.rotation
finally:
    pygame.key.get_mods = real_mods
    panel.drag = None
    panel.fine = None
check("Shift drag does not jump", abs(first - 45.25) < 1e-9, f"{first}")
check("Shift drag is slow", abs(second - (45.25 + 20 / track.width * 360 * 0.05)) < 0.06, f"{second}")

cfg.set("center_x", 100)
panel.tab = 1
panel.place((1240, 900))
minus = parts_of("center_x")["minus"].center
panel.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=minus, button=1))
panel.hold[2] = 0.0
panel.tick()
panel.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=minus, button=1))
panel.tick()
check("holding - repeats, letting go stops", cfg.center_x == 98 and panel.hold is None, f"{cfg.center_x}")
pygame.quit()


# -------------------------
# THE REAL WINDOW LOOP
# -------------------------

class FakeLidar:
    """Walls 6 m away plus objects standing on the floor, at 10 Hz."""

    crc_errors = 0
    split_angle = 0.0
    finished = False

    def __init__(self):
        self.objects = []       # (angle, distance)
        self.last = time.monotonic()

    def get_scans(self, timeout=0.2):
        now = time.monotonic()
        if now - self.last < 0.02:
            time.sleep(0.002)
            return []
        self.last = now
        angle = np.arange(0.25, 360, 0.5)
        dist = 6000 + np.random.normal(0, 4, len(angle))
        for a, d in self.objects:
            half = math.degrees(60 / d)
            near = np.abs((angle - a + 180) % 360 - 180) <= half
            dist[near] = d + np.random.normal(0, 4, int(near.sum()))
        return [Scan(angle, dist, None, None, None, now, 0.5, 10.0)]

    def close(self):
        pass


path = os.path.join(S, "cal_window.json")
if os.path.exists(path):
    os.remove(path)
true_cfg = make(**TRUE)
cfg = GameSettings(path=path)
for k, v in WRONG.items():
    cfg.set(k, v)
cfg.set("calibration_time", 2)
cfg.set("max_width", 450)
rel = [(hx - cfg.center_x, hy - cfg.center_y) for hx, hy in C.home_points(cfg)]
raws = floor_raw(true_cfg, cfg)

lidar = FakeLidar()
engine = FG.Engine(cfg, lidar, None)
frames = {"n": 0, "at": None}
real_get = pygame.event.get
states = {}


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0)


def script():
    """Events of this frame; the steps wait for the lidar's objects to settle."""
    if engine.background.distance is None:
        return []
    frames["n"] += 1
    n = frames["n"]
    if n == 1:
        lidar.objects = raws            # objects go on the floor after the empty scan
        return [key(pygame.K_k)]
    if n == 60:
        states["objects"] = len(engine.calib.stable())
        return [key(pygame.K_a)]
    if n == 62:
        states["matched"] = sum(p.moved for p in engine.calib.points)
        states["before"] = (cfg.rotation, cfg.lidar_scale, cfg.center_x, cfg.center_y)
        if SHOTS:
            pygame.image.save(pygame.display.get_surface(), os.path.join(SHOTS, "floor_matched.png"))
        return [key(pygame.K_RETURN)]
    if n == 64:
        states["applied"] = (cfg.rotation, cfg.lidar_scale, cfg.center_x, cfg.center_y)
        states["rev"] = engine.calib_rev
        states["active"] = engine.calib.active
    if n == 110:
        if SHOTS:
            pygame.image.save(pygame.display.get_surface(), os.path.join(SHOTS, "floor_applied.png"))
        states["after_objects"] = [(o.x, o.y) for o in engine.calib.stable()]
        return [key(pygame.K_u)]
    if n == 112:
        states["undone"] = (cfg.rotation, cfg.lidar_scale, cfg.center_x, cfg.center_y)
    if n == 114:                        # the lidar got bumped: every object seen 90 mm away
        cfg.apply(dict(zip(("rotation", "lidar_scale", "center_x", "center_y"), states["applied"])))
    if n == 170:
        states["bump_home"] = (cfg.center_x, cfg.center_y)
        cfg.set("center_x", cfg.center_x + 90)
    if n == 230:
        states["bumped_rot"] = cfg.rotation
        return [key(pygame.K_c)]
    if n == 232:
        states["bump_fixed"] = (cfg.center_x, cfg.center_y, cfg.rotation)
    if n == 234:
        return [key(pygame.K_k)]
    if n == 236:
        states["closed"] = not engine.calib.active
        return [pygame.event.Event(pygame.QUIT)]
    return []


pygame.event.get = script
try:
    FG.run_window(engine, setup=False)
finally:
    pygame.event.get = real_get
    engine.link.close()

check("window: lidar sees the 4 objects", states.get("objects") == 4, f"{states.get('objects')}")
check("window: A matches all 4 points", states.get("matched") == 4, f"{states.get('matched')}")
check("window: Enter changes the settings", states.get("applied") != states.get("before"), f"{states.get('applied')}")
# the lidar's beams are 0.5 degrees apart: about 25 mm at the far objects, so about 0.6 degrees over the points
check("window: finds the true rotation", abs(states["applied"][0] - 150.5) < 0.7, f"{states['applied'][0]}")
check("window: finds the true scale", abs(states["applied"][1] - 1.0) < 0.01, f"{states['applied'][1]}")
check("window: finds the true center",
      math.hypot(states["applied"][2] + 340, states["applied"][3] - 2530) < 25, f"{states['applied'][2:]}")
check("window: told the setup window", states.get("rev") == 1)
check("window: mode stays open to check the result", states.get("active") is True)

after = states["after_objects"]
landed = len(after) == 4 and all(
    min(math.hypot(x - states["applied"][2] - rx, y - states["applied"][3] - ry) for x, y in after) < 25
    for rx, ry in rel)
check("window: objects now sit on the points", landed)
check("window: U puts everything back", states.get("undone") == states.get("before"), f"{states.get('undone')}")
check("window: C corrects only the position",
      abs(states["bump_fixed"][0] - states["bump_home"][0]) <= 12
      and abs(states["bump_fixed"][1] - states["bump_home"][1]) <= 12
      and states["bump_fixed"][2] == states["bumped_rot"],
      f"{states['bump_fixed']} wanted {states['bump_home']}")
check("window: K closes the mode", states.get("closed") is True)
check("window: the calibration was saved", os.path.exists(path))

print("\nFAILED: " + ", ".join(fails) if fails else "\nAll passed")
sys.exit(1 if fails else 0)
