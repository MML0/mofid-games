"""
Settings of the circular floor game (floor_game.py / lidar_setup.py).

Every value is changed live in the setup window and saved to
game_settings.json next to this file (the touch / ball program keeps its own
settings.json). Delete game_settings.json to go back to these defaults.

Order of work on site:
  1. Lidar tab   calibrate the lidar: scan the empty floor, turn / mirror the
                 map until it matches the room, set the noise filters.
  2. Arena tab   place the game circle and set its diameter.
  3. Players, Track, Paddle, Output   game behaviour.

Map coordinates (mm): lidar at (0, 0), turned by `rotation`, mirrored by
`flip_x` / `flip_y`. The arena center can be anywhere on the map, the lidar
does not have to be in the middle.
"""

import json
import math
import os

import numpy as np

from settings import Field, Settings


PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_settings.json")

MAX_PLAYERS = 8


def _custom(k):
    return lambda cfg: not cfg.equal_sectors and k <= cfg.players


GAME_TABS = [

    ("Lidar", [
        Field("rotation", "Rotate map", 0.0, -180, 180, 0.05, "°",
              help="Turn all lidar points so the map matches the room."),
        Field("lidar_scale", "Lidar scale", 1.0, 0.5, 2.0, 0.001, "x",
              help="Makes the whole lidar map bigger or smaller around the lidar, "
                   "without changing the arena circle. 1 = the lidar's real "
                   "distances. The 4-point calibration (K in the Floor game "
                   "window) sets this for you."),
        Field("flip_x", "Mirror X", False, help="Swap left and right (lidar mounted upside down)."),
        Field("flip_y", "Mirror Y", False, help="Swap down and up."),
        Field("min_distance", "Min distance", 100, 0, 1000, 10, "mm",
              help="Ignore everything closer than this to the lidar (its cover, cables)."),
        Field("bg_margin", "Background gap", 40, 10, 300, 5, "mm",
              help="A point must be this much in front of the empty-floor scan to "
                   "count. Raise it if white points show on the empty floor."),
        Field("bg_margin_ratio", "Extra gap far away", 1.0, 0.0, 10.0, 0.5, "%",
              help="Adds this % of the distance to the gap (noise grows with distance)."),
        Field("min_width", "Smallest foot", 50, 5, 300, 5, "mm",
              help="Narrower objects are ignored (noise, cables, bottles, table "
                   "legs). Feet are about 100-170 mm wide to the lidar."),
        Field("max_width", "Biggest foot", 450, 50, 2000, 10, "mm",
              help="Bigger objects (bag, chair) are ignored. Two feet close "
                   "together can look like one ~400 mm object."),
        Field("cluster_distance", "Join distance", 80, 20, 300, 5, "mm",
              help="Points closer than this are one foot. Too high joins both feet."),
        Field("foot_confirm", "Foot confirm", 2, 1, 5, 1, "scans",
              help="A new foot must be seen this many scans in a row (0.1 s each). "
                   "Higher = less noise, slower to start."),
        Field("calibration_time", "Background scan", 10, 2, 60, 1, "s",
              help="How long the empty floor is scanned (Scan background / B)."),
    ]),

    ("Arena", [
        Field("diameter", "Diameter", 4000, 600, 10000, 1, "mm",
              help="Diameter of the game circle. Paddles always sit on this line. "
                   "You can also drag the circle on the map."),
        Field("center_x", "Center X", 0, -5000, 5000, 1, "mm",
              help="Arena center, left / right of the lidar. You can also drag the "
                   "center cross on the map."),
        Field("center_y", "Center Y", 0, -5000, 5000, 1, "mm",
              help="Arena center, down / up of the lidar (or drag the cross)."),
        Field("band_in", "Track inside", 600, 0, 3000, 1, "mm",
              help="Feet up to this far INSIDE the circle belong to a player. "
                   "Anything deeper inside is ignored."),
        Field("band_out", "Track outside", 600, 0, 3000, 1, "mm",
              help="Feet up to this far OUTSIDE the circle belong to a player. "
                   "Anything farther out (spectators) is ignored."),
        Field("paddle_size", "Paddle size", 250, 50, 800, 10, "mm",
              help="Paddle diameter. Drawing only; the game decides collisions."),
        Field("calib_radius", "Calib. points out", 85, 30, 100, 1, "%",
              help="How far out the 4 calibration points sit, as % of the circle "
                   "radius (K in the Floor game window)."),
        Field("calib_turn", "Calib. points turn", 30, -180, 180, 1, "°",
              help="Turns the 4 calibration points around the circle. Use it when "
                   "one object hides another from the lidar."),
    ]),

    ("Players", [
        Field("players", "Players", 2, 1, MAX_PLAYERS, 1, "",
              help="Number of players. Each one owns one sector of the circle."),
        Field("line_angle", "Line rotation", 90.0, -180, 180, 0.05, "°",
              help="Angle of the first dividing line (0° = right, counter-clockwise). "
                   "Turns all sectors together. You can also drag a line's handle."),
        Field("border_gap", "Border limit", 10.0, 0.0, 45.0, 0.5, "°",
              help="A paddle stays at least this far from a dividing line, so "
                   "two paddles never meet on a border."),
        Field("equal_sectors", "Equal sectors", True,
              help="On: all sectors are the same size. Off: set each size below "
                   "(they are scaled to fill 360°)."),
    ] + [
        Field(f"sector_{k}", f"Sector P{k}", 90, 10, 350, 1, "°", show=_custom(k),
              help="Size of this player's sector. The sizes are scaled so they "
                   "fill the whole circle.")
        for k in range(1, MAX_PLAYERS + 1)
    ]),

    ("Track", [
        Field("foot_match", "Foot max step", 400, 50, 1500, 10, "mm",
              help="How far a foot may move between two scans and keep its ID."),
        Field("foot_keep", "Foot memory", 0.5, 0.1, 3.0, 0.05, "s",
              help="A lifted foot keeps its ID and last spot this long. Covers "
                   "walking steps and one foot hidden behind the other."),
        Field("feet_per_player", "Feet per player", 2, 1, 4, 1, "",
              help="A player uses at most this many feet: the ones on the floor "
                   "now, then the ones seen longest. Extra objects next to a "
                   "player (a bag, someone else's foot) are ignored."),
        Field("player_radius", "Player radius", 700, 200, 2000, 10, "mm",
              help="Feet farther than this from the player are someone else and "
                   "are ignored while the player is tracked."),
        Field("hold_time", "Hold when airborne", 1.0, 0.1, 5.0, 0.1, "s",
              help="With no foot seen (jump, hidden) the player is predicted and "
                   "held this long before the paddle is released."),
        Field("predict_time", "Prediction fade", 0.3, 0.0, 2.0, 0.05, "s",
              help="While no foot is seen the last movement continues and fades "
                   "out over this time. 0 = stop at once."),
        Field("owner_hold", "Sector handover", 5.0, 0.0, 30.0, 0.5, "°",
              help="A foot must be this far over a dividing line before it "
                   "belongs to the next player (no flicker on the border)."),
        Field("still_ignore", "Ignore still objects", 15, 0, 120, 1, "s",
              help="Something that does not move at all for this long (bag, bottle, "
                   "chair put down after the background scan) is ignored until it "
                   "moves. 0 = off. Press B to make it part of the background."),
    ]),

    ("Paddle", [
        Field("jump_distance", "Teleport from", 800, 0, 3000, 10, "mm",
              help="When the feet show up this far from where the player was "
                   "(a jump, a fast run, a new player), the player and the paddle "
                   "go there at once instead of gliding. Feet outside the Player "
                   "radius while the old spot is empty always teleport. Keep it "
                   "above half a running stride (~700 mm) or the paddle hops each "
                   "step. 0 = always glide (old behaviour)."),
        Field("correction_time", "Correction speed", 0.12, 0.0, 2.0, 0.01, "s",
              help="How fast the player position follows the feet. Lower = "
                   "faster, higher = smoother."),
        Field("reacquire_time", "Reacquire speed", 0.4, 0.0, 3.0, 0.05, "s",
              help="After the feet were lost, how gently the position moves to "
                   "the new feet (no jump)."),
        Field("lifted_weight", "Lifted foot weight", 1.0, 0.0, 1.0, 0.05, "",
              help="How much a lifted foot's last spot still counts when only one "
                   "foot is on the floor (walking). 1 = the player is between both "
                   "feet, 0 = follow the standing foot only."),
        Field("confidence_time", "Confidence build", 0.3, 0.05, 3.0, 0.05, "s",
              help="Time of steady feet until the player counts as fully tracked."),
        Field("still_lag", "Smoothing standing", 0.25, 0.0, 1.5, 0.01, "s",
              help="Paddle smoothing while the player stands still. Higher = "
                   "steadier paddle, no jitter."),
        Field("paddle_lag", "Smoothing moving", 0.05, 0.0, 1.0, 0.01, "s",
              help="Paddle smoothing while the player moves fast. Lower = less lag."),
        Field("moving_speed", "Fast move from", 600, 50, 3000, 10, "mm/s",
              help="From this walking speed on the 'moving' smoothing is used; "
                   "slower moves blend toward the 'standing' smoothing."),
        Field("paddle_speed", "Paddle max speed", 4000, 200, 20000, 100, "mm/s",
              help="The paddle never moves faster than this along the circle "
                   "(no sudden jumps)."),
        Field("lead", "Prediction lead", 0.05, 0.0, 0.5, 0.01, "s",
              help="Move the paddle this far ahead along the walking direction "
                   "to hide the lidar's 0.1 s delay."),
    ]),

    ("Output", [
        Field("normalize", "Send 0..1", False,
              help="Send x, y from 0 to 1 inside the arena box (0, 0 = bottom "
                   "left) instead of mm."),
        Field("send_feet", "Send feet", False,
              help="Also send every foot as /foot [id, x, y, player]."),
        Field("game_dots", "Lidar dots in game", False,
              help="Show the live lidar points in the game window too (blue = all "
                   "points, white = possible feet). P in the game window does the same."),
        Field("game_margin", "Game window edge", 1.0, 0.0, 30.0, 0.5, "%",
              help="Space between the circle (with its paddles) and the game "
                   "window edge. 0 = the circle touches the edges."),
    ]),
]



class GameSettings(Settings):

    def __init__(self, path=PATH):

        super().__init__(path, GAME_TABS)

        # fixed values the shared blob detector expects
        self.mode = "touch"
        self.ball_size = 0


    @property
    def radius(self):

        return self.diameter / 2


    def load(self):

        found = super().load()

        # older files stored the radius
        if found:
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if "radius" in data and "diameter" not in data:
                    self.set("diameter", 2 * float(data["radius"]))
            except (OSError, ValueError, TypeError):
                pass

        return found


    def values(self):

        return {key: getattr(self, key) for key in self.fields}


    def apply(self, values):

        for key, value in values.items():
            if key in self.fields:
                try:
                    self.set(key, value)
                except (TypeError, ValueError):
                    pass


    # -------------------------
    # SECTORS
    # -------------------------

    def sector_sizes(self):

        n = self.players

        if self.equal_sectors:
            return [360.0 / n] * n

        sizes = [float(getattr(self, f"sector_{k}")) for k in range(1, n + 1)]
        total = sum(sizes)

        return [s * 360.0 / total for s in sizes]


    def sectors(self):
        """[(start, size)] in degrees around the arena center, counter-clockwise."""

        out = []
        a = self.line_angle

        for size in self.sector_sizes():
            out.append((a % 360, size))
            a += size

        return out


    def lines(self):
        """Angle of every dividing line (line k is the start of sector k)."""

        return [start for start, _ in self.sectors()]


    def sector_of(self, angle):
        """Index of the sector that holds this angle (deg around the center)."""

        for i, (start, size) in enumerate(self.sectors()):
            if (angle - start) % 360 < size:
                return i

        return len(self.sectors()) - 1


    def gap(self, size):
        """Border limit that still leaves room in a sector of this size."""

        return min(self.border_gap, size / 2)


    # -------------------------
    # GEOMETRY (map mm)
    # -------------------------

    def to_world(self, angle, dist):

        a = np.radians(angle + self.rotation)
        x = np.cos(a) * dist * self.lidar_scale
        y = np.sin(a) * dist * self.lidar_scale

        if self.flip_x:
            x = -x

        if self.flip_y:
            y = -y

        return x, y


    def polar(self, x, y):
        """Map x, y -> (radius from the arena center, angle in deg)."""

        dx = x - self.center_x
        dy = y - self.center_y

        return np.hypot(dx, dy), np.degrees(np.arctan2(dy, dx)) % 360


    def on_circle(self, angle):

        a = math.radians(angle)

        return self.center_x + math.cos(a) * self.radius, self.center_y + math.sin(a) * self.radius


    def in_band(self, x, y):

        r, _ = self.polar(x, y)

        return (r >= self.radius - self.band_in) & (r <= self.radius + self.band_out)


    def in_area(self, x, y, dist):
        """Points that can be a player's foot: near the circle, not at the lidar."""

        return self.in_band(x, y) & (dist >= self.min_distance)


    def reach(self):
        """Farthest raw lidar distance that can land on the tracking band."""

        return (math.hypot(self.center_x, self.center_y) + self.radius + self.band_out) / self.lidar_scale


    def output(self, x, y):

        if not self.normalize:
            return x, y

        r = self.radius

        return (x - self.center_x + r) / (2 * r), (y - self.center_y + r) / (2 * r)
