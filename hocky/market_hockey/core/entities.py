"""Simulation entities (plain data)."""

from __future__ import annotations


class Ball:
    __slots__ = ("id", "x", "y", "vx", "vy", "px", "py", "r", "owner", "rally", "scored", "scored_t", "held",
                 "since_touch", "last_hit", "hits", "extra_until", "born", "smart_until", "removed", "chaos", "calm")

    def __init__(self, bid: int, x: float, y: float, r: float, born: float = 0.0):
        self.id = bid
        self.x, self.y = x, y
        self.px, self.py = x, y
        self.vx = self.vy = 0.0
        self.r = r
        self.owner: int | None = None
        self.rally = 0.0
        self.scored = False
        self.scored_t = 0.0
        self.held = True
        self.since_touch = 0.0
        self.last_hit: dict[int, float] = {}
        self.hits = 0
        self.extra_until: float | None = None
        self.born = born
        self.smart_until = -1.0
        self.removed = False
        self.chaos: dict | None = None  # staged "random path" sequence (see Engine.start_chaos)
        self.calm = False  # True after a random path: ignores speed-ups until a paddle hits it


class Paddle:
    __slots__ = ("idx", "theta", "prev_theta", "omega", "omega_s", "size_mult", "present", "last_seen", "target",
                 "u", "rise_t", "prev_speed", "last_smart", "width", "hold_until", "assist_off")

    def __init__(self, idx: int):
        self.idx = idx
        self.theta = 180.0 if idx == 0 else 360.0
        self.prev_theta = self.theta
        self.omega = 0.0  # deg/s
        self.omega_s = 0.0  # spring state
        self.size_mult = 1.0
        self.present = True
        self.last_seen = 0.0
        self.target = self.theta
        self.u = 0.5
        self.rise_t = -10.0
        self.prev_speed = 0.0
        self.last_smart = -10.0
        self.width = 130.0
        self.hold_until = 0.0
        self.assist_off = 0.0  # deg the catch assist adds to the player's own position


class Orb:
    __slots__ = ("id", "type_id", "cls", "slot", "hx", "hy", "x", "y", "vx", "vy", "age", "life", "state",
                 "state_t", "wobble", "pulled")

    def __init__(self, oid, type_id, cls, slot, x, y, life):
        self.id = oid
        self.type_id = type_id
        self.cls = cls
        self.slot = slot
        self.hx, self.hy = x, y
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.age = 0.0
        self.life = life
        self.state = "spawning"  # spawning | idle | despawning | collected
        self.state_t = 0.0
        self.wobble = 0.0
        self.pulled = 0.0  # 0..1, how strongly the magnet is pulling (for visuals)
