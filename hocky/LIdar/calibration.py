"""
4-point calibration of the lidar, done in the Floor game window (key K).

Four numbered points are drawn on the game floor. Put an object on each one.
The lidar shows each object as a dot, somewhere near its point if the
calibration is close. Drag each point onto its object's dot (or press A to
match them automatically), then press Enter: rotation, lidar scale, center and
if needed the mirror are worked out so every object lands on its point. The
game circle stays where it is on the floor.

C corrects only the position (the lidar got bumped); one object is enough.

The points are deliberately not a square: only one way of matching objects to
points fits, so A cannot pick a turned or mirrored answer.

Maths (map mm, lidar at 0,0). A new map is  new = z * old + 0,  z = scale and
turn as one complex number, so rotation and scale happen around the lidar. The
circle's offset from its center must stay what the floor shows, so we fit
z * seen + t = home - center   and the new center is -t.
"""

import itertools
import math


# degrees between one point and the next: the spread-out layout where the next
# best matching (any other order, any turn, mirrored) fits worst
GAPS = (130, 100, 80, 50)

GRAB_PX = 34            # how close a click must be to grab a point
SNAP_PX = 40            # a point dropped this close to an object sits on the object
NEAR = 800              # mm, C and A: farthest object that can belong to a point
MATCH_ERROR = 0.1       # A: worst fit error that still counts as a match, share of the points' radius
MIRROR_MIN = 30         # mm, the mirror is only tried when the normal fit is worse than this
MAX_OBJECTS = 8

OBJECT_SMOOTH = 0.25    # share of a new scan in an object's averaged position
OBJECT_MATCH = 150      # mm
OBJECT_KEEP = 0.7       # s
OBJECT_SEEN = 5         # scans before an object counts

WATCHED = ("rotation", "lidar_scale", "flip_x", "flip_y", "center_x", "center_y",
           "diameter", "calib_radius", "calib_turn")
CHANGED = ("rotation", "lidar_scale", "flip_x", "flip_y", "center_x", "center_y")



def home_points(cfg):
    """Where the 4 points are on the map (x, y mm)."""

    r = cfg.radius * cfg.calib_radius / 100
    a = float(cfg.calib_turn)
    out = []

    for gap in GAPS:
        rad = math.radians(a)
        out.append((cfg.center_x + math.cos(rad) * r, cfg.center_y + math.sin(rad) * r))
        a += gap

    return out



def fit(src, dst, shift_only=False):
    """Best complex z and t with z * src + t = dst. Returns (z, t, rms error)."""

    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    den = sum(abs(p - ma) ** 2 for p in a)
    z = 1 + 0j

    if not shift_only and len(a) >= 2 and den > 1.0:
        z = sum((q - mb) * (p - ma).conjugate() for p, q in zip(a, b)) / den

    return z, mb - z * ma, _error(z, mb - z * ma, a, b)



def _error(z, t, a, b):

    return math.sqrt(sum(abs(z * p + t - q) ** 2 for p, q in zip(a, b)) / len(a))



def solve(cfg, pairs, shift_only=False):
    """
    pairs = [(where the object is seen, its home point)], map mm.
    Returns {values, error, turn, scale, shift, mirror, limited}.
    """

    src = [p for p, _ in pairs]
    dst = [(hx - cfg.center_x, hy - cfg.center_y) for _, (hx, hy) in pairs]

    z, _, error = fit(src, dst, shift_only)
    flip_x = bool(cfg.flip_x)
    mirror = False

    if not shift_only and len(pairs) >= 3 and error > MIRROR_MIN:

        flipped = [(-x, y) for x, y in src]
        mz, _, merror = fit(flipped, dst)

        if merror < error / 2:
            src, z, error, flip_x, mirror = flipped, mz, merror, not flip_x, True

    # rotation is applied before the mirrors: one mirror turns it the other way
    sign = -1 if flip_x != bool(cfg.flip_y) else 1

    turn = math.degrees(math.atan2(z.imag, z.real))
    scale = abs(z)
    want_rotation = (cfg.rotation + sign * turn + 180) % 360 - 180
    want_scale = cfg.lidar_scale * scale

    rotation = cfg.fields["rotation"].clean(want_rotation)
    lidar_scale = cfg.fields["lidar_scale"].clean(want_scale)

    # the sliders have steps and limits: fit the center to the values really used
    used_turn = sign * (rotation - cfg.rotation)
    used = lidar_scale / cfg.lidar_scale * complex(math.cos(math.radians(used_turn)),
                                                  math.sin(math.radians(used_turn)))

    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    t = sum(q - used * p for p, q in zip(a, b)) / len(a)

    center_x = cfg.fields["center_x"].clean(-t.real)
    center_y = cfg.fields["center_y"].clean(-t.imag)

    limited = (abs(lidar_scale - want_scale) > 0.002
               or abs(center_x + t.real) > 1 or abs(center_y + t.imag) > 1)

    return {
        "values": {"rotation": rotation, "lidar_scale": lidar_scale, "flip_x": flip_x,
                   "center_x": center_x, "center_y": center_y},
        "error": _error(used, -complex(center_x, center_y), a, b),
        "turn": used_turn,
        "scale": lidar_scale / cfg.lidar_scale,
        "shift": math.hypot(center_x - cfg.center_x, center_y - cfg.center_y),
        "mirror": mirror,
        "limited": limited,
    }



def match_objects(cfg, homes, objects):
    """Which object sits on which point, however far off the calibration is. [(object, home index)] or None."""

    ring = cfg.radius * cfg.calib_radius / 100
    near = sorted(objects, key=lambda p: abs(math.hypot(p[0] - cfg.center_x, p[1] - cfg.center_y) - ring))[:MAX_OBJECTS]
    dst = [(hx - cfg.center_x, hy - cfg.center_y) for hx, hy in homes]
    best = None

    # all 4 are needed: three objects can fit the wrong three points almost as well
    for chosen in itertools.combinations(near, 4):
        for slots in itertools.permutations(range(4)):

            target = [dst[i] for i in slots]

            for src in (chosen, [(-x, y) for x, y in chosen]):

                z, _, error = fit(src, target)
                scale = cfg.lidar_scale * abs(z)

                if 0.5 <= scale <= 2.0 and (best is None or error < best[0]):
                    best = (error, chosen, slots)

    if best is not None and best[0] <= MATCH_ERROR * ring:
        return list(zip(best[1], best[2]))

    return None



class Point:
    """One draggable point. x, y is where it is now."""

    def __init__(self, x, y):

        self.x = x
        self.y = y
        self.moved = False



class Object:
    """A thing the lidar sees on the floor, averaged over a few scans."""

    def __init__(self, x, y, t):

        self.x = x
        self.y = y
        self.t = t
        self.seen = 1



class Calibrator:

    def __init__(self, cfg):

        self.cfg = cfg
        self.active = False
        self.homes = []
        self.points = []
        self.objects = []
        self.drag = None            # index of the point being dragged
        self.message = ""
        self.undo_values = None
        self.key = None


    # -------------------------
    # MODE
    # -------------------------

    def start(self, message=""):

        self.active = True
        self.message = message
        self._reset()


    def stop(self):

        self.active = False
        self.drag = None


    def _signature(self):

        return tuple(getattr(self.cfg, k) for k in WATCHED)


    def _reset(self):

        self.homes = home_points(self.cfg)
        self.points = [Point(x, y) for x, y in self.homes]
        self.objects = []
        self.drag = None
        self.key = self._signature()


    def reset_points(self):

        self.points = [Point(x, y) for x, y in self.homes]
        self.drag = None
        self.message = ""


    def sync(self):
        """A slider moved the map: the points and dots start over. Call once per frame."""

        if self.active and self._signature() != self.key:
            self._reset()


    # -------------------------
    # OBJECTS
    # -------------------------

    def feed(self, blobs, t):
        """Blobs of one scan (x, y, points, width)."""

        for b in blobs:

            best = min(self.objects, key=lambda o: math.hypot(o.x - b[0], o.y - b[1]), default=None)

            if best is not None and math.hypot(best.x - b[0], best.y - b[1]) <= OBJECT_MATCH:
                best.x += (b[0] - best.x) * OBJECT_SMOOTH
                best.y += (b[1] - best.y) * OBJECT_SMOOTH
                best.t = t
                best.seen += 1
            else:
                self.objects.append(Object(b[0], b[1], t))

        self.objects = [o for o in self.objects if t - o.t <= OBJECT_KEEP]


    def stable(self):

        return [o for o in self.objects if o.seen >= OBJECT_SEEN]


    def object_near(self, view, pos, px=SNAP_PX):

        best = None
        best_d = px

        for o in self.stable():
            sx, sy = view.to_screen(o.x, o.y)
            d = math.hypot(sx - pos[0], sy - pos[1])
            if d <= best_d:
                best, best_d = o, d

        return best


    # -------------------------
    # MOUSE
    # -------------------------

    def _point_at(self, view, pos):

        best = None
        best_d = GRAB_PX

        for i, p in enumerate(self.points):
            sx, sy = view.to_screen(p.x, p.y)
            d = math.hypot(sx - pos[0], sy - pos[1])
            if d <= best_d:
                best, best_d = i, d

        return best


    def grab(self, view, pos):

        self.drag = self._point_at(view, pos)

        return self.drag is not None


    def move(self, view, pos):

        p = self.points[self.drag]
        p.x, p.y = view.to_map(*pos)
        p.moved = True


    def release(self, view):

        p = self.points[self.drag]
        o = self.object_near(view, view.to_screen(p.x, p.y))

        if o is not None:
            p.x, p.y = o.x, o.y

        self.drag = None


    def clear(self, view, pos):
        """Right click: this point goes home and is not used."""

        i = self._point_at(view, pos)

        if i is None:
            return False

        self.points[i] = Point(*self.homes[i])

        return True


    # -------------------------
    # SOLVE
    # -------------------------

    def pairs(self):

        return [((p.x, p.y), home) for p, home in zip(self.points, self.homes) if p.moved]


    def preview(self):
        """What Enter would do now, or None."""

        pairs = self.pairs()

        return solve(self.cfg, pairs) if pairs else None


    def auto(self):
        """Put every point on the object that belongs to it."""

        objects = [(o.x, o.y) for o in self.stable()]
        found = match_objects(self.cfg, self.homes, objects)

        if found is None:
            self.message = (f"A needs 4 objects on the 4 points. The lidar sees {len(objects)} and they "
                            "do not fit. Check them, or drag the points by hand.")
            return False

        self.points = [Point(x, y) for x, y in self.homes]

        for (x, y), i in found:
            p = self.points[i]
            p.x, p.y = x, y
            p.moved = True

        self.message = f"Matched {len(found)} objects. Press Enter to apply."

        return True


    def _nearest_pairs(self):
        """For C: every point that has an object close to it."""

        used = set()
        pairs = []

        for home in self.homes:

            best = min(self.stable(), key=lambda o: math.hypot(o.x - home[0], o.y - home[1]), default=None)

            if (best is not None and id(best) not in used
                    and math.hypot(best.x - home[0], best.y - home[1]) <= NEAR):
                used.add(id(best))
                pairs.append(((best.x, best.y), home))

        return pairs


    def apply(self, shift_only=False):
        """Change the settings. Returns True when they changed."""

        pairs = self.pairs()

        if not pairs and shift_only:
            pairs = self._nearest_pairs()

        if not pairs:
            self.message = ("No object near a point. Put an object on one, or drag a point onto its dot."
                            if shift_only else "Drag the points onto their dots first, or press A.")
            return False

        result = solve(self.cfg, pairs, shift_only)

        self.undo_values = {k: getattr(self.cfg, k) for k in CHANGED}
        self.cfg.apply(result["values"])
        self._reset()
        self.message = "Applied: " + describe(result)

        if result["limited"]:
            self.message += "   A slider hit its limit: set Diameter closer to the real circle."

        return True


    def undo(self):

        if self.undo_values is None:
            self.message = "Nothing to undo."
            return False

        self.cfg.apply(self.undo_values)
        self.undo_values = None
        self._reset()
        self.message = "Back to the settings before the last Apply."

        return True



def describe(result):

    text = (f"turn {result['turn']:+.2f}°   scale x{result['scale']:.3f}   "
            f"center moved {result['shift']:.0f} mm   error {result['error']:.0f} mm")

    return text + ("   mirrored" if result["mirror"] else "")
