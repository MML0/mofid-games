"""
Foot and player tracking for the circular floor game.

    blobs (lidar objects near the circle)
      -> FootTracker   persistent foot IDs, a lifted foot keeps its ID and
                       last spot for "Foot memory" seconds
      -> sectors       every confirmed foot belongs to the sector it stands in
                       (with a small handover margin on the dividing lines)
      -> Player        one per sector: position = weighted mean of its feet
                       (standing feet count fully, lifted feet less), smoothed,
                       held and predicted while no foot is seen (jump, hidden),
                       gently pulled to new feet when they come back. Feet far
                       from a tracked player are someone else and are ignored.
      -> paddle        the player's angle around the arena center, clamped
                       "Border limit" degrees away from the dividing lines,
                       smoothed and speed limited, always ON the circle.

Pure logic, no drawing: Game.update_scan() once per lidar scan,
Game.step() once per frame (60 Hz) for smooth paddles.
"""

import math


MERGE = 150         # mm: a new blob this close to a matched foot is part of it (heel / toes)
MAX_SPEED = 4000    # mm/s: fastest a player's body is believed to move
STATIC_MOVE = 40    # mm: an object that moves less than this is "still"
GATE_STILL = 150    # mm: a still foot keeps its ID only for objects this close
LIFT_GROWTH = 800   # mm/s: how fast that distance grows while a foot is not seen


def wrap180(a):

    return (a + 180.0) % 360.0 - 180.0



# =========================
# FEET
# =========================

class Foot:

    def __init__(self, fid, x, y, t):

        self.id = fid
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.first = t
        self.last_seen = t
        self.hits = 1
        self.confirmed = False
        self.owner = None           # player index
        self.anchor = (x, y, t)     # where and since when it stands still
        self.static = False         # an object that never moves (not a player)


    def predict(self, t):

        dt = min(t - self.last_seen, 0.2)

        return self.x + self.vx * dt, self.y + self.vy * dt



class FootTracker:

    def __init__(self, cfg):

        self.cfg = cfg
        self.feet = []
        self.next_id = 1


    def update(self, blobs, t):
        """blobs: [(x, y, points, width)] near the circle. Returns all feet (also lifted ones)."""

        cfg = self.cfg
        pairs = []

        for fi, foot in enumerate(self.feet):

            px, py = foot.predict(t)

            # a foot that stands still keeps its ID only for objects right at
            # it (no stealing by a new object nearby); a moving or lifted
            # foot may come back farther away
            dt = t - foot.last_seen
            speed = math.hypot(foot.vx, foot.vy)
            gate = GATE_STILL + 1.5 * speed * min(dt, 0.2) + LIFT_GROWTH * max(0.0, dt - 0.12)
            gate = min(gate, cfg.foot_match)

            for bi, (bx, by, _, _) in enumerate(blobs):

                d = math.hypot(bx - px, by - py)

                if d < gate:
                    pairs.append((d, fi, bi))

        pairs.sort()
        used_feet = set()
        used_blobs = set()

        for _, fi, bi in pairs:

            if fi in used_feet or bi in used_blobs:
                continue

            used_feet.add(fi)
            used_blobs.add(bi)

            foot = self.feet[fi]
            bx, by = blobs[bi][0], blobs[bi][1]
            dt = max(t - foot.last_seen, 1e-3)

            foot.vx += 0.5 * ((bx - foot.x) / dt - foot.vx)
            foot.vy += 0.5 * ((by - foot.y) / dt - foot.vy)
            foot.x, foot.y = bx, by
            foot.last_seen = t
            foot.hits += 1

            if foot.hits >= cfg.foot_confirm:
                foot.confirmed = True

            # a bag, a bottle, a chair leg put down after the background scan
            ax, ay, at = foot.anchor
            if math.hypot(bx - ax, by - ay) > STATIC_MOVE:
                foot.anchor = (bx, by, t)
                foot.static = False
            elif cfg.still_ignore > 0 and t - at > cfg.still_ignore:
                foot.static = True

        alive = []

        for fi, foot in enumerate(self.feet):

            if fi in used_feet:
                alive.append(foot)

            elif not foot.confirmed:
                pass                            # seen once and gone: noise

            elif t - foot.last_seen <= cfg.foot_keep:
                foot.vx = foot.vy = 0.0         # lifted: stays where it was put down
                alive.append(foot)

        for bi, (bx, by, _, _) in enumerate(blobs):

            if bi in used_blobs:
                continue

            if any(math.hypot(bx - f.x, by - f.y) < MERGE for f in alive if f.last_seen == t):
                continue

            foot = Foot(self.next_id, bx, by, t)
            self.next_id += 1
            foot.confirmed = cfg.foot_confirm <= 1
            alive.append(foot)

        self.feet = alive

        return alive


    def clear(self):

        self.feet = []



# =========================
# PLAYER
# =========================

class Player:

    def __init__(self, index):

        self.index = index
        self.active = False         # has a position (tracked or held)
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.conf = 0.0             # 0..1
        self.last_t = None
        self.last_fresh = None      # last scan with a foot on the floor
        self.feet = []              # feet used last scan
        self.paddle_rel = None      # paddle angle inside its sector (deg from the sector start)
        self.paddle_t = None


    @property
    def seen(self):
        """A foot of this player is on the floor right now."""

        return self.active and self.last_fresh == self.last_t


    def update_scan(self, feet, t, cfg):
        """feet: confirmed feet in this player's sector."""

        dt = 0.1 if self.last_t is None else min(max(t - self.last_t, 1e-3), 0.5)
        self.last_t = t

        # which feet are this player's
        if self.active:
            fade = math.exp(-dt / cfg.predict_time) if cfg.predict_time > 0 else 0.0
            px = self.x + self.vx * fade * dt
            py = self.y + self.vy * fade * dt
            mine = [f for f in feet if math.hypot(f.x - px, f.y - py) <= cfg.player_radius]

        else:
            fresh = [f for f in feet if f.last_seen == t]

            if fresh:
                seed = max(fresh, key=lambda f: f.hits)
                mine = [f for f in feet if math.hypot(f.x - seed.x, f.y - seed.y) <= cfg.player_radius]
            else:
                mine = []

        # a player has at most "Feet per player" feet: feet on the floor now
        # first, then the ones seen longest. A new object next to a player who
        # already has both feet is someone / something else.
        mine.sort(key=lambda f: (f.last_seen == t, f.hits), reverse=True)
        mine = mine[:cfg.feet_per_player]

        fresh = [f for f in mine if f.last_seen == t]
        self.feet = mine

        if fresh:

            sw = sx = sy = 0.0

            for f in mine:

                if f.last_seen == t:
                    w = 1.0
                else:
                    # a lifted foot counts until the last 30 % of its memory, then fades
                    left = 1.0 - (t - f.last_seen) / max(cfg.foot_keep, 1e-3)
                    w = cfg.lifted_weight * min(1.0, max(0.0, left / 0.3))

                sw += w
                sx += w * f.x
                sy += w * f.y

            mx, my = sx / sw, sy / sw

            if not self.active:
                # new player: the estimate starts at the feet, the paddle
                # glides there (paddle smoothing and max speed)
                self.active = True
                self.x, self.y = mx, my
                self.vx = self.vy = 0.0
                self.conf = 0.0

            else:
                # alpha-beta filter: predict with the walking speed, then
                # correct toward the feet. Confident = quick correction,
                # after a loss = gentle reacquire (and no speed from the jump).
                tc = cfg.correction_time + (cfg.reacquire_time - cfg.correction_time) * (1.0 - self.conf)
                a = 1.0 if tc <= 0 else 1.0 - math.exp(-dt / tc)
                b = a * a / (2.0 - a) * self.conf

                px = self.x + self.vx * dt
                py = self.y + self.vy * dt
                rx, ry = mx - px, my - py

                self.x = px + a * rx
                self.y = py + a * ry
                self.vx += b * rx / dt
                self.vy += b * ry / dt

                # walking speed is limited to what a person can do
                speed = math.hypot(self.vx, self.vy)
                if speed > MAX_SPEED:
                    self.vx *= MAX_SPEED / speed
                    self.vy *= MAX_SPEED / speed

            self.conf = min(1.0, self.conf + dt / cfg.confidence_time)
            self.last_fresh = t

        elif self.active:

            # airborne or hidden: keep going the way it went, fading out
            fade = math.exp(-dt / cfg.predict_time) if cfg.predict_time > 0 else 0.0
            self.vx *= fade
            self.vy *= fade
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.conf = max(0.0, self.conf - dt / cfg.hold_time)

            if t - self.last_fresh > cfg.hold_time:
                self.release()


    def release(self):

        self.active = False
        self.conf = 0.0
        self.vx = self.vy = 0.0
        self.feet = []


    def step_paddle(self, t, cfg, start, size):
        """Move the paddle toward the player's angle. Returns the paddle angle (deg)."""

        gap = cfg.gap(size)
        lo, hi = gap, size - gap

        if self.paddle_rel is None:
            self.paddle_rel = size / 2

        dt = 0.0 if self.paddle_t is None else min(max(t - self.paddle_t, 0.0), 0.1)
        self.paddle_t = t

        target = self.paddle_rel

        if self.active:

            tx = self.x + self.vx * cfg.lead
            ty = self.y + self.vy * cfg.lead
            angle = math.degrees(math.atan2(ty - cfg.center_y, tx - cfg.center_x))
            rel = (angle - start) % 360

            if rel > size:      # over the line (handover margin): nearer edge
                rel = size if rel - size < 360 - rel else 0.0

            target = rel

        target = min(max(target, lo), hi)

        # standing still = strong smoothing (no jitter), walking = light (no lag)
        speed = math.hypot(self.vx, self.vy) if self.active else 0.0
        w = min(1.0, speed / max(cfg.moving_speed, 1.0))
        lag = cfg.still_lag + (cfg.paddle_lag - cfg.still_lag) * w

        if lag > 0 and dt > 0:
            want = self.paddle_rel + (target - self.paddle_rel) * (1.0 - math.exp(-dt / lag))
        else:
            want = target

        step = math.degrees(cfg.paddle_speed / cfg.radius) * dt
        move = want - self.paddle_rel

        if dt > 0:
            move = min(max(move, -step), step)

        self.paddle_rel = min(max(self.paddle_rel + move, lo), hi)

        return (start + self.paddle_rel) % 360



# =========================
# GAME
# =========================

class Game:

    def __init__(self, cfg):

        self.cfg = cfg
        self.tracker = FootTracker(cfg)
        self.players = []
        self.paddles = []       # (angle, x, y) per player after step()
        self._fit_players()


    def _fit_players(self):

        n = self.cfg.players

        while len(self.players) < n:
            self.players.append(Player(len(self.players)))

        del self.players[n:]


    def _owner(self, foot, sectors):

        cfg = self.cfg
        _, angle = cfg.polar(foot.x, foot.y)
        angle = float(angle)
        hold = cfg.owner_hold

        if foot.owner is not None and foot.owner < len(sectors):
            start, size = sectors[foot.owner]
            if (angle - start + hold) % 360 < size + 2 * hold:
                return foot.owner

        return cfg.sector_of(angle)


    def update_scan(self, blobs, t):

        self._fit_players()
        sectors = self.cfg.sectors()
        feet = self.tracker.update(blobs, t)

        owned = [[] for _ in self.players]

        for foot in feet:
            if foot.confirmed and not foot.static:
                foot.owner = self._owner(foot, sectors)
                owned[foot.owner].append(foot)
            else:
                foot.owner = None

        for player, mine in zip(self.players, owned):
            player.update_scan(mine, t, self.cfg)


    def step(self, t):

        self._fit_players()
        cfg = self.cfg
        self.paddles = []

        for player, (start, size) in zip(self.players, cfg.sectors()):
            angle = player.step_paddle(t, cfg, start, size)
            x, y = cfg.on_circle(angle)
            self.paddles.append((angle, x, y))

        return self.paddles


    def reset(self):

        self.tracker.clear()

        for player in self.players:
            player.release()
