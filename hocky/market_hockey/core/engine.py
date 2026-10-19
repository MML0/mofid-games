"""The game simulation: state machine, physics, scoring, serve, power-ups. Pure Python (no pygame).

`Engine.step(dt, inputs, real_presence)` advances one fixed physics step and appends event dicts to
`engine.events`; the renderer and audio react to those events and to the state.
"""

from __future__ import annotations

import logging
import math
import random

from ..powerups import registry
from ..powerups.effects import Effect, EffectManager
from ..prediction.trajectory import predict
from .collisions import (HitParams, PaddleShape, enforce_axis_ratio, paddle_contact, paddle_response,
                         reflect_static_circle, seg_point_dist, segment_exit_point)
from .entities import Ball, Orb, Paddle
from .geometry import Arc, Geometry, clamp, pp

log = logging.getLogger(__name__)

ATTRACT, INTRO, COUNTDOWN, SERVE, PLAYING, GOAL, FINAL, RESULT = (
    "ATTRACT", "INTRO", "COUNTDOWN", "SERVE", "PLAYING", "GOAL", "FINAL", "RESULT")
LIVE_STATES = (SERVE, PLAYING)


def _new_stats():
    return {"powerups": [0, 0], "smart": [0, 0], "hits": [0, 0], "goals": [0, 0]}


class Engine:
    def __init__(self, cfg, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.types = registry.all_types()
        self.geom = Geometry(cfg)
        self._gv = cfg.version
        self._hp_cache: dict = {}
        self.effects = EffectManager()
        self.paddles = [Paddle(0), Paddle(1)]
        self.balls: list[Ball] = []
        self.orbs: list[Orb] = []
        self.scores = [0, 0]
        self.events: list[dict] = []
        self.time = 0.0
        self.paused = False
        self.state = ATTRACT
        self.state_t = 0.0
        self.time_left = float(cfg["match.duration_s"])
        self.match_duration = float(cfg["match.duration_s"])
        self.play_elapsed = 0.0
        self.golden = False
        self.winner: int | None = None
        self.goal_info: dict | None = None
        self.predictions: dict = {}
        self._pred_t = 0.0
        self._pred_dirty = False
        self._next_ball_id = 1
        self._next_orb_id = 1
        self.next_spawn = 2.0
        self.last_type: str | None = None
        self.type_cd: dict[str, float] = {}
        self.match_count = 0
        self.last_first_serve = 1
        self.last_receiver: int | None = None
        self.serve_receiver = 0
        self.pending_demo_serve: tuple | None = None
        self.both_present_t = 0.0
        self.stats = _new_stats()
        self._cd_index = -1
        self._place_paddles_center()

    # ======================================================================== helpers
    def emit(self, etype: str, **kw) -> None:
        kw["type"] = etype
        kw["t"] = self.time
        self.events.append(kw)

    def drain_events(self) -> list[dict]:
        ev, self.events = self.events, []
        return ev

    def _set_state(self, st: str) -> None:
        prev = self.state
        self.state = st
        self.state_t = 0.0
        self.emit("state", state=st, prev=prev)

    def _refresh_geometry(self) -> None:
        if self.cfg.version == self._gv:
            return
        self._gv = self.cfg.version
        self._hp_cache.clear()
        self.geom = Geometry(self.cfg)
        for p in self.paddles:  # keep each paddle at the same relative position on its (new) arc
            w = self.paddle_width(p.idx)
            p.theta = p.prev_theta = p.target = self.geom.u_to_theta(p.idx, p.u, w)

    def _place_paddles_center(self) -> None:
        for p in self.paddles:
            p.u = 0.5
            p.size_mult = 1.0
            w = self.paddle_width(p.idx)
            p.theta = p.prev_theta = p.target = self.geom.u_to_theta(p.idx, 0.5, w)

    def paddle_width(self, idx: int) -> float:
        cfg = self.cfg
        base = pp(cfg, idx, "width")
        p = self.paddles[idx]
        return clamp(base * p.size_mult, pp(cfg, idx, "min_width"), max(pp(cfg, idx, "max_width"), base))

    def paddle_shape(self, idx: int, theta: float | None = None) -> PaddleShape:
        p = self.paddles[idx]
        return PaddleShape(p.theta if theta is None else theta, self.geom.paddle_back_radius(idx),
                           self.paddle_width(idx), pp(self.cfg, idx, "shape_ratio"))

    def hit_params(self, idx: int) -> HitParams:
        hp = self._hp_cache.get(idx)
        if hp is None:
            cfg = self.cfg
            fx, fy = self.geom.goal_dir[1 - idx]
            hp = HitParams(
                restitution=pp(cfg, idx, "restitution"), transfer=pp(cfg, idx, "velocity_transfer"),
                blend=pp(cfg, idx, "aim_blend"), max_aim=math.radians(pp(cfg, idx, "max_aim_angle_deg")),
                max_out=math.radians(pp(cfg, idx, "max_outgoing_angle_deg")),
                allow_backward=pp(cfg, idx, "allow_backward"), hit_gain=pp(cfg, idx, "hit_speed_gain"),
                to_ball=pp(cfg, idx, "paddle_speed_to_ball"), min_forward=pp(cfg, idx, "min_forward"),
                fwd_x=fx, fwd_y=fy, vmin=cfg["ball.min_speed"], vmax=cfg["ball.max_speed"])
            self._hp_cache[idx] = hp
        return hp

    def ball_target_speed(self, b: Ball) -> float:
        cfg = self.cfg
        return clamp(b.rally * self.effects.ball_speed_mult(b.id), cfg["ball.min_speed"], cfg["ball.max_speed"])

    def heading_to(self, b: Ball) -> int | None:
        ax, ay = self.geom.axis
        va = b.vx * ax + b.vy * ay
        if abs(va) < 1e-6:
            return None
        return 1 if va > 0 else 0

    def live_balls(self) -> list[Ball]:
        return [b for b in self.balls if not b.scored and not b.removed]

    def phase_index(self) -> int:
        """0 warm-up, 1 early, 2 mid, 3 peak, 4 final (no spawns)."""
        cfg = self.cfg
        if not cfg["phases.enabled"]:
            return 2
        dur = self.match_duration if cfg["match.timer_enabled"] else cfg["phases.nominal_duration_s"]
        f = self.play_elapsed / max(1.0, dur)
        if f < cfg["phases.warmup_end"]:
            return 0
        if f < cfg["phases.early_end"]:
            return 1
        if f < cfg["phases.mid_end"]:
            return 2
        if f < cfg["phases.peak_end"]:
            return 3
        return 4 if cfg["match.timer_enabled"] else 3

    def countdown_info(self):
        cfg = self.cfg
        seq = [("ready", cfg["countdown.ready_s"]), ("3", cfg["countdown.beat_s"]), ("2", cfg["countdown.beat_s"]),
               ("1", cfg["countdown.beat_s"]), ("go", cfg["countdown.go_s"])]
        t = self.state_t
        for i, (label, length) in enumerate(seq):
            if t < length or i == len(seq) - 1:
                return label, min(t, length), length, i
            t -= length
        return "go", 0.0, 1.0, 4

    def countdown_total(self) -> float:
        cfg = self.cfg
        return cfg["countdown.ready_s"] + 3 * cfg["countdown.beat_s"] + cfg["countdown.go_s"]

    def request_prediction(self) -> None:
        self._pred_dirty = True

    # ======================================================================== commands
    def start_match(self) -> None:
        cfg = self.cfg
        self.balls.clear()
        self.orbs.clear()
        self.effects.clear()
        self.predictions.clear()
        self.scores = [0, 0]
        self.match_duration = float(cfg["match.duration_s"])
        self.time_left = self.match_duration
        self.play_elapsed = 0.0
        self.golden = False
        self.winner = None
        self.goal_info = None
        self.next_spawn = cfg["powerups.spawn_interval_min_s"] * 0.5
        self.type_cd.clear()
        self.last_type = None
        self.stats = _new_stats()
        self.match_count += 1
        self.pending_demo_serve = None
        self._place_paddles_center()
        self._set_state(INTRO)
        self.emit("match_start")

    def reset_to_attract(self) -> None:
        self.balls.clear()
        self.orbs.clear()
        self.effects.clear()
        self.predictions.clear()
        self.scores = [0, 0]
        self.golden = False
        self.winner = None
        self.pending_demo_serve = (self.rng.choice((0, 1)), self.time + 1.0)
        self._set_state(ATTRACT)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.emit("pause", paused=self.paused)

    def force_spawn(self, type_id: str) -> bool:
        if type_id not in self.types:
            return False
        return self._spawn_orb(forced_type=type_id) is not None

    def debug_spawn_ball(self) -> None:
        live = self.live_balls()
        if live:
            self.split_ball(live[0], 1, 25, 10)

    # ======================================================================== step
    def step(self, dt: float, inputs: dict | None = None, real_presence=None) -> None:
        self._refresh_geometry()
        if self.paused:
            return
        self.time += dt
        self.state_t += dt
        self._update_paddles(dt, inputs or {})
        st = self.state
        if st == ATTRACT:
            self._attract(dt, real_presence)
        elif st == INTRO:
            if self.state_t >= self.cfg["match.intro_s"]:
                self._set_state(COUNTDOWN)
                self._cd_index = -1
                self._new_held_ball()
        elif st == COUNTDOWN:
            self._countdown()
        elif st == SERVE:
            self._serve_state(dt)
        elif st == PLAYING:
            self._playing(dt)
        elif st == GOAL:
            self._goal_state(dt)
        elif st == FINAL:
            self._update_orbs(dt)
            if self.state_t >= self.cfg["match.final_freeze_s"]:
                self.balls.clear()
                self._set_state(RESULT)
        elif st == RESULT:
            self._update_orbs(dt)
            if not self.cfg["match.result_wait_for_operator"] and self.state_t >= self.cfg["match.result_s"]:
                self.reset_to_attract()

    # ---------------------------------------------------------------- states
    def _attract(self, dt, real_presence) -> None:
        cfg = self.cfg
        if cfg["match.attract_demo"]:
            if not self.live_balls() and self.pending_demo_serve is None:
                self.pending_demo_serve = (self.rng.choice((0, 1)), self.time + 0.9)
            if self.pending_demo_serve and self.time >= self.pending_demo_serve[1]:
                b = self._new_held_ball()
                self._launch(b, self.pending_demo_serve[0], change_state=False)
                self.pending_demo_serve = None
            self._physics(dt)
            self._update_world(dt, demo=True)
            for b in list(self.balls):
                if b.scored and self.time - b.scored_t > 0.8:
                    self.balls.remove(b)
        else:
            self.balls.clear()
            self.orbs.clear()
        mode = cfg["match.start_mode"]
        if mode == "auto_when_both_present":
            if real_presence and all(real_presence):
                self.both_present_t += dt
                if self.both_present_t >= 1.5:
                    self.both_present_t = 0.0
                    self.start_match()
            else:
                self.both_present_t = 0.0
        elif mode == "auto_loop" and self.state_t >= cfg["match.auto_loop_delay_s"]:
            self.start_match()

    def _countdown(self) -> None:
        label, t_in, length, idx = self.countdown_info()
        if idx != self._cd_index:
            self._cd_index = idx
            self.emit("countdown_beat", label=label, index=idx)
        if self.state_t >= self.countdown_total():
            live = self.live_balls()
            b = live[0] if live else self._new_held_ball()
            receiver = self._first_receiver()
            self._launch(b, receiver)

    def _serve_state(self, dt) -> None:
        if self.cfg["match.timer_runs_during_serve"]:
            self._run_timer(dt)
        if self.state != SERVE:
            return
        self._update_world(dt)
        if self.state_t >= self.cfg["serve.delay_s"]:
            live = self.live_balls()
            b = live[0] if live else self._new_held_ball()
            self._launch(b, self.serve_receiver)

    def _playing(self, dt) -> None:
        self._physics(dt)
        if self.state != PLAYING:  # a goal happened during physics
            return
        self._run_timer(dt)
        if self.state != PLAYING:
            return
        self._update_world(dt)

    def _goal_state(self, dt) -> None:
        cfg = self.cfg
        if cfg["fx.goal_slowmo"] and self.state_t < 0.25:
            self._physics(dt * 0.15)
        if cfg["match.timer_runs_during_goal_pause"]:
            self._run_timer(dt, allow_finish=False)
        if self.state_t >= cfg["match.goal_pause_s"]:
            if self._should_end():
                self._finish()
            else:
                self._prepare_serve(self._receiver_after_goal())

    # ---------------------------------------------------------------- timer / end
    def _run_timer(self, dt, allow_finish=True) -> None:
        cfg = self.cfg
        self.play_elapsed += dt
        if not cfg["match.timer_enabled"] or self.golden:
            return
        before = self.time_left
        self.time_left = max(0.0, self.time_left - dt)
        if math.ceil(before) != math.ceil(self.time_left) and self.time_left <= cfg["hud.final_seconds"] and self.time_left > 0:
            self.emit("timer_tick", left=math.ceil(self.time_left))
        if self.time_left <= 0 and allow_finish:
            if self.scores[0] == self.scores[1] and cfg["match.tie_rule"] == "golden_goal":
                self.golden = True
                self.emit("golden_goal")
            else:
                self._finish()

    def _should_end(self) -> bool:
        cfg = self.cfg
        if self.golden:
            return self.scores[0] != self.scores[1]
        if cfg["match.score_limit_enabled"] and max(self.scores) >= cfg["match.score_limit"]:
            return True
        if cfg["match.timer_enabled"] and self.time_left <= 0:
            if self.scores[0] == self.scores[1] and cfg["match.tie_rule"] == "golden_goal":
                self.golden = True
                self.emit("golden_goal")
                return False
            return True
        return False

    def _finish(self) -> None:
        s0, s1 = self.scores
        self.winner = 0 if s0 > s1 else 1 if s1 > s0 else None
        self.balls = [b for b in self.balls if not b.held]
        for b in self.balls:
            b.vx = b.vy = 0.0
        for o in self.orbs:
            if o.state in ("spawning", "idle"):
                o.state, o.state_t = "despawning", 0.0
        self.effects.clear()
        self.predictions.clear()
        self._set_state(FINAL)
        self.emit("match_end", scores=list(self.scores), winner=self.winner, stats=self.stats,
                  duration=self.play_elapsed, golden=self.golden)

    # ---------------------------------------------------------------- serve
    def _new_held_ball(self) -> Ball:
        sx, sy = self.geom.serve_pos
        b = Ball(self._next_ball_id, sx, sy, self.cfg["ball.radius"], self.time)
        self._next_ball_id += 1
        b.held = True
        self.balls.append(b)
        return b

    def _first_receiver(self) -> int:
        rule = self.cfg["serve.first"]
        if rule == "p1":
            r = 0
        elif rule == "p2":
            r = 1
        elif rule == "alternate":
            r = 1 - self.last_first_serve
        else:
            r = self.rng.choice((0, 1))
        self.last_first_serve = r
        return r

    def _receiver_after_goal(self) -> int:
        info = self.goal_info or {"scorer": 0, "conceded": 1}
        rule = self.cfg["serve.after_goal"]
        if rule == "toward_scorer":
            return info["scorer"]
        if rule == "random":
            return self.rng.choice((0, 1))
        if rule == "alternate":
            return 1 - (self.last_receiver if self.last_receiver is not None else 0)
        return info["conceded"]

    def _prepare_serve(self, receiver: int) -> None:
        for b in self.balls:
            self.effects.remove_for_ball(b.id)
        self.balls.clear()
        self.predictions.clear()
        self.serve_receiver = receiver
        self._new_held_ball()
        self._set_state(SERVE)
        self.emit("serve_ready", receiver=receiver)

    def serve_direction(self, b: Ball, receiver: int) -> tuple[float, float]:
        cfg = self.cfg
        g = self.geom
        w = self.paddle_width(receiver)
        lo, hi = g.paddle_range(receiver, w)
        var = cfg["serve.angle_variation_deg"]
        base = self.paddles[receiver].theta if cfg["serve.aim_near_paddle"] else (lo + hi) / 2
        target = clamp(base + self.rng.uniform(-var, var), lo, hi)
        rt = g.paddle_back_radius(receiver) - (w / 2) * pp(cfg, receiver, "shape_ratio")
        tx, ty = rt * math.cos(math.radians(target)), rt * math.sin(math.radians(target))
        dx, dy = tx - b.x, ty - b.y
        d = math.hypot(dx, dy) or 1.0
        return dx / d, dy / d

    def _launch(self, b: Ball, receiver: int, change_state: bool = True) -> None:
        cfg = self.cfg
        dx, dy = self.serve_direction(b, receiver)
        sp = cfg["ball.serve_speed"]
        b.vx, b.vy = dx * sp, dy * sp
        b.rally = sp
        b.held = False
        b.since_touch = 0.0
        enforce_axis_ratio(b, self.geom.axis, cfg["physics.min_axis_ratio"], self.rng)
        self.last_receiver = receiver
        self.emit("serve", receiver=receiver, x=b.x, y=b.y, dx=dx, dy=dy, demo=not change_state)
        if change_state:
            self._set_state(PLAYING)

    # ---------------------------------------------------------------- paddles
    def _update_paddles(self, dt, inputs: dict) -> None:
        cfg = self.cfg
        thr = cfg["smart.min_paddle_speed"]
        stacking = cfg["paddles.size_stacking"]
        for p in self.paddles:
            i = p.idx
            target_mult = self.effects.paddle_mult(i, stacking)
            tau = max(0.02, pp(cfg, i, "size_transition_s"))
            p.size_mult += (target_mult - p.size_mult) * (1 - math.exp(-dt * 3.0 / tau))
            w = self.paddle_width(i)
            p.width = w
            lo, hi = self.geom.paddle_range(i, w)
            s = inputs.get(i)
            if s is not None and s.present:
                p.present = True
                p.last_seen = self.time
                if s.u is not None:
                    p.target = lo + (hi - lo) * clamp(s.u, 0.0, 1.0)
            else:
                p.present = False
                if self.time - p.last_seen > cfg["input.filters.lost_hold_s"]:
                    p.target = (lo + hi) / 2
            p.target = clamp(p.target, lo, hi)
            p.prev_theta = p.theta
            maxd = pp(cfg, i, "max_speed_deg_s") * dt
            if pp(cfg, i, "follow_mode") == "spring":
                k = pp(cfg, i, "follow_stiffness")
                p.omega_s += (k * k * (p.target - p.theta) - 2 * k * p.omega_s) * dt
                delta = clamp(p.omega_s * dt, -maxd, maxd)
            else:
                delta = clamp(p.target - p.theta, -maxd, maxd)
            p.theta = clamp(p.theta + delta, lo, hi)
            p.omega = (p.theta - p.prev_theta) / dt if dt > 0 else 0.0
            p.u = (p.theta - lo) / (hi - lo) if hi > lo else 0.5
            speed = abs(math.radians(p.omega)) * self.geom.paddle_back_radius(i)
            if speed >= thr > p.prev_speed:
                p.rise_t = self.time
            p.prev_speed = speed

    def _paddle_velocity(self, i: int, theta: float) -> tuple[float, float]:
        p = self.paddles[i]
        w = math.radians(p.omega) * self.geom.paddle_back_radius(i)
        t = math.radians(theta)
        return (-math.sin(t) * w, math.cos(t) * w)

    # ---------------------------------------------------------------- physics
    def _physics(self, dt: float) -> None:
        cfg = self.cfg
        balls = [b for b in self.balls if not b.removed]
        for b in balls:
            b.px, b.py = b.x, b.y
        moving = [b for b in balls if not b.held and not b.scored]
        for b in balls:
            if b.scored:  # drift out and fade (renderer); no collisions
                b.x += b.vx * dt
                b.y += b.vy * dt
        if not moving:
            return
        maxrel = max(math.hypot(b.vx, b.vy) / max(1.0, b.r) for b in moving)
        n = int(clamp(math.ceil(maxrel * dt / 0.35), 1, cfg["physics.max_substeps"]))
        h = dt / n
        vps = [self._paddle_velocity(i, self.paddles[i].theta) for i in (0, 1)]
        for k in range(1, n + 1):
            frac = k / n
            shapes = [self.paddle_shape(i, p.prev_theta + (p.theta - p.prev_theta) * frac)
                      for i, p in enumerate(self.paddles)]
            for b in moving:
                if b.scored or b.removed:
                    continue
                ox, oy = b.x, b.y
                wob = self.effects.ball_has(b.id, "wobble")
                if wob is not None:
                    w = math.radians(wob.data.get("amp", 120) * math.sin(
                        math.tau * wob.data.get("hz", 1.5) * wob.age + wob.data.get("phase", 0.0))) * h
                    c, s = math.cos(w), math.sin(w)
                    b.vx, b.vy = b.vx * c - b.vy * s, b.vx * s + b.vy * c
                b.x += b.vx * h
                b.y += b.vy * h
                for i in (0, 1):
                    self._collide_paddle(b, i, shapes[i], vps[i])
                self._collide_walls(b)
                self._collide_shields(b)
                if self._check_goal(b, ox, oy):
                    continue
                self._check_orbs(b, ox, oy)
            if cfg["physics.balls_collide"] and len(moving) > 1:
                self._collide_balls([b for b in moving if not b.scored])
        k_ease = 1 - math.exp(-cfg["ball.speed_response"] * dt)
        for b in moving:
            if b.scored:
                continue
            sp = math.hypot(b.vx, b.vy)
            if sp > 1e-6:
                tgt = self.ball_target_speed(b)
                ns = sp + (tgt - sp) * k_ease
                b.vx *= ns / sp
                b.vy *= ns / sp
            b.since_touch += dt
            if b.since_touch > cfg["physics.stall_timeout_s"]:
                self._handle_stall(b, dt)

    def _handle_stall(self, b: Ball, dt: float) -> None:
        cfg = self.cfg
        if cfg["physics.stall_action"] == "reserve" and self.state == PLAYING:
            b.since_touch = 0.0
            self.emit("stall_reserve", ball_id=b.id)
            self._prepare_serve(self.rng.choice((0, 1)))
            return
        ax, ay = self.geom.axis
        sp = math.hypot(b.vx, b.vy)
        if sp < 1e-6:
            return
        va = (b.vx * ax + b.vy * ay) / sp
        if abs(va) >= 0.6:
            return
        sign = 1.0 if va >= 0 else -1.0
        cur = math.atan2(b.vy, b.vx)
        goal = math.atan2(ay * sign, ax * sign)
        diff = (goal - cur + math.pi) % math.tau - math.pi
        rot = math.copysign(min(abs(diff), math.radians(cfg["physics.stall_steer_deg_s"]) * dt), diff)
        c, s = math.cos(rot), math.sin(rot)
        b.vx, b.vy = b.vx * c - b.vy * s, b.vx * s + b.vy * c

    def _collide_paddle(self, b: Ball, i: int, sh: PaddleShape, vp) -> None:
        hit = paddle_contact(b.x, b.y, b.r, sh)
        if hit is None:
            return
        nx, ny, rx, ry, front = hit
        b.x, b.y = rx, ry
        cfg = self.cfg
        if self.time - b.last_hit.get(i, -9.0) < pp(cfg, i, "hit_cooldown_ms") / 1000.0:
            return
        base = cfg["ball.base_speed"]
        if b.hits == 0:
            new_rally = max(base, b.rally)
        else:
            new_rally = min(b.rally * cfg["ball.rally_gain_per_hit"], base * cfg["ball.rally_cap"])
        old_rally, b.rally = b.rally, new_rally
        res = paddle_response(b.vx, b.vy, nx, ny, sh, vp[0], vp[1], self.hit_params(i), front,
                              self.ball_target_speed(b))
        if res is None:
            b.rally = old_rally
            return
        vx, vy, s = res
        smart = self._smart_check(i, s, sh, vp) if front else False
        if smart:
            k = cfg["smart.speed_bonus"]
            sp = math.hypot(vx, vy)
            ns = min(sp * k, cfg["ball.max_speed"])
            vx, vy = vx * ns / sp, vy * ns / sp
            b.smart_until = self.time + cfg["smart.trail_s"]
            self.paddles[i].last_smart = self.time
            self.stats["smart"][i] += 1
            if cfg["scoring.smart_hit_points"] and self.state in LIVE_STATES:
                self.scores[i] += cfg["scoring.smart_hit_points"]
        b.vx, b.vy = vx, vy
        prev_owner = b.owner
        b.owner = i
        b.last_hit[i] = self.time
        b.since_touch = 0.0
        b.hits += 1
        self.stats["hits"][i] += 1
        self._pred_dirty = True
        self.emit("paddle_hit", player=i, ball_id=b.id, x=b.x, y=b.y, offset=s, speed=math.hypot(vx, vy),
                  smart=smart, owner_changed=prev_owner != i, front=front)

    def _smart_check(self, i, s, sh, vp) -> bool:
        cfg = self.cfg
        if not cfg["smart.enabled"]:
            return False
        p = self.paddles[i]
        speed = math.hypot(*vp)
        if speed < cfg["smart.min_paddle_speed"]:
            return False
        if self.time - p.rise_t > cfg["smart.window_ms"] / 1000.0:
            return False
        if self.time - p.last_smart < cfg["smart.cooldown_s"]:
            return False
        side = vp[0] * sh.rx + vp[1] * sh.ry  # paddle motion toward the player's right?
        if abs(s) > 0.15 and side * s < 0:
            return False
        return True

    def _collide_walls(self, b: Ball) -> None:
        g = self.geom
        e = self.cfg["walls.restitution"]
        d = math.hypot(b.x, b.y)
        lim = g.wall_face - b.r
        if d > lim and d > 1e-6:
            ang = math.degrees(math.atan2(b.y, b.x))
            if g.in_wall(ang):
                nx, ny = b.x / d, b.y / d
                vn = b.vx * nx + b.vy * ny
                if vn > 0:
                    b.vx -= (1 + e) * vn * nx
                    b.vy -= (1 + e) * vn * ny
                    enforce_axis_ratio(b, g.axis, self.cfg["physics.min_axis_ratio"], self.rng)
                    self._pred_dirty = True
                    self.emit("wall_bounce", x=b.x, y=b.y, wall=0 if g.walls[0].contains(ang) else 1, ball_id=b.id,
                              speed=math.hypot(b.vx, b.vy))
                b.x, b.y = nx * lim, ny * lim
        for cx, cy in g.caps:
            if reflect_static_circle(b, cx, cy, g.cap_r, e):
                enforce_axis_ratio(b, g.axis, self.cfg["physics.min_axis_ratio"], self.rng)
                self._pred_dirty = True
                self.emit("wall_bounce", x=b.x, y=b.y, wall=-1, ball_id=b.id, speed=math.hypot(b.vx, b.vy))

    def _collide_shields(self, b: Ball) -> None:
        for eff in self.effects.of_kind("shield"):
            j = eff.target[1]
            g = self.geom
            arc = g.goals[j]
            cov = eff.data.get("coverage", 100) / 100.0
            span = arc.span * cov
            sub = Arc(arc.center - span / 2, span)
            rs = g.R - 6.0
            d = math.hypot(b.x, b.y)
            if d > rs - b.r and d > 1e-6:
                ang = math.degrees(math.atan2(b.y, b.x))
                if sub.contains(ang):
                    nx, ny = b.x / d, b.y / d
                    vn = b.vx * nx + b.vy * ny
                    if vn > 0:
                        b.vx -= 2 * vn * nx
                        b.vy -= 2 * vn * ny
                        b.x, b.y = nx * (rs - b.r - 0.5), ny * (rs - b.r - 0.5)
                        eff.data["charges"] = eff.data.get("charges", 1) - 1
                        self.emit("shield_block", player=j, x=b.x, y=b.y)
                        if eff.data["charges"] <= 0:
                            self.effects.remove(eff)
                            self.emit("effect_ended", effect=eff, replaced=False)
                        return

    def _collide_balls(self, balls: list[Ball]) -> None:
        for a_i in range(len(balls)):
            a = balls[a_i]
            for b in balls[a_i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                lim = a.r + b.r
                if d >= lim or d < 1e-9:
                    continue
                nx, ny = dx / d, dy / d
                push = (lim - d) / 2 + 0.1
                a.x -= nx * push
                a.y -= ny * push
                b.x += nx * push
                b.y += ny * push
                rv = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
                if rv < 0:
                    a.vx += rv * nx
                    a.vy += rv * ny
                    b.vx -= rv * nx
                    b.vy -= rv * ny
                    self.emit("ball_ball", x=(a.x + b.x) / 2, y=(a.y + b.y) / 2)

    def _check_goal(self, b: Ball, ox: float, oy: float) -> bool:
        g = self.geom
        if math.hypot(b.x, b.y) <= g.R:
            return False
        cx, cy = segment_exit_point(ox, oy, b.x, b.y, g.R) if math.hypot(ox, oy) <= g.R else (b.x, b.y)
        ang = math.degrees(math.atan2(cy, cx))
        which = g.goal_of(ang)
        if which is None:  # should be impossible (walls reflect first); bounce back to be safe
            d = math.hypot(b.x, b.y)
            nx, ny = b.x / d, b.y / d
            vn = b.vx * nx + b.vy * ny
            if vn > 0:
                b.vx -= 2 * vn * nx
                b.vy -= 2 * vn * ny
            lim = g.wall_face - b.r
            b.x, b.y = nx * lim, ny * lim
            log.warning("ball crossed the rim inside a wall arc at %.1f°", ang)
            return False
        b.scored = True
        b.scored_t = self.time
        b.vx *= 0.6
        b.vy *= 0.6
        self.effects.remove_for_ball(b.id)
        self._on_goal(b, scorer=1 - which, conceded=which, point=(cx, cy), angle=ang)
        return True

    def _on_goal(self, b: Ball, scorer: int, conceded: int, point, angle) -> None:
        cfg = self.cfg
        if self.state == ATTRACT:
            self.emit("goal", scorer=scorer, conceded=conceded, x=point[0], y=point[1], angle=angle, points=0,
                      demo=True, ball_id=b.id, owner=b.owner)
            if not self.live_balls():
                self.pending_demo_serve = (conceded, self.time + 0.9)
            return
        if self.state not in LIVE_STATES:
            return
        pts = cfg["scoring.points_per_goal"]
        bull = self.effects.for_player(scorer, "bull")
        if bull is not None:
            pts = int(round(pts * bull.value))
            self.effects.remove(bull)
            self.emit("effect_ended", effect=bull, replaced=False)
        self.scores[scorer] += pts
        self.stats["goals"][scorer] += 1
        self.emit("goal", scorer=scorer, conceded=conceded, x=point[0], y=point[1], angle=angle, points=pts,
                  demo=False, ball_id=b.id, owner=b.owner, bull=bull is not None)
        self.goal_info = {"scorer": scorer, "conceded": conceded}
        if cfg["scoring.multiball_policy"] == "continue" and self.live_balls() and not self.golden:
            if not (cfg["match.score_limit_enabled"] and max(self.scores) >= cfg["match.score_limit"]):
                return
        self._set_state(GOAL)

    # ---------------------------------------------------------------- power-ups
    def _update_world(self, dt: float, demo: bool = False) -> None:
        """Orbs, spawning, effects, extra-ball expiry and predictions."""
        self._update_spawner(dt, demo)
        self._update_orbs(dt)
        for e in self.effects.update(dt):
            self.emit("effect_ended", effect=e, replaced=False)
        for b in list(self.balls):
            if b.extra_until is not None and not b.scored and self.time >= b.extra_until:
                if len(self.live_balls()) > 1:
                    b.removed = True
                    self.effects.remove_for_ball(b.id)
                    self.balls.remove(b)
                    self.emit("ball_expired", ball_id=b.id, x=b.x, y=b.y, owner=b.owner)
                else:
                    b.extra_until = None
        self._update_predictions(dt)

    def _update_spawner(self, dt: float, demo: bool) -> None:
        cfg = self.cfg
        if not cfg["powerups.enabled"]:
            return
        phase = 2 if demo else self.phase_index()
        if phase in (0, 4):
            return
        self.next_spawn -= dt
        if self.next_spawn > 0:
            return
        lo, hi = cfg["powerups.spawn_interval_min_s"], cfg["powerups.spawn_interval_max_s"]
        mult = cfg["phases.peak_spawn_mult"] if phase == 3 else 1.0
        self.next_spawn = self.rng.uniform(min(lo, hi), max(lo, hi)) * mult
        self._spawn_orb(phase=phase)

    def _type_class(self, tid: str) -> str:
        return self.cfg[f"powerups.types.{tid}.class"]

    def _spawn_orb(self, phase: int = 3, forced_type: str | None = None) -> Orb | None:
        cfg = self.cfg
        active = [o for o in self.orbs if o.state in ("spawning", "idle")]
        if forced_type is None and len(active) >= cfg["powerups.max_active_orbs"]:
            return None
        g = self.geom
        min_d = cfg["powerups.min_distance_from_ball"]
        orb_r = cfg["powerups.orb_radius"]
        live = self.live_balls()
        used = {o.slot for o in active}
        free = []
        for si, (sx, sy) in enumerate(g.slots):
            if si in used:
                continue
            if any(math.hypot(b.x - sx, b.y - sy) < min_d for b in live) and forced_type is None:
                continue
            free.append(si)
        if not free:
            if forced_type is None or not g.slots:
                return None
            free = [min(range(len(g.slots)), key=lambda s: sum(1 for o in active if o.slot == s))]
        if forced_type:
            tid = forced_type
        else:
            bad_active = sum(1 for o in active if o.cls == "bad")
            cands = []
            for tid, t in self.types.items():
                pre = f"powerups.types.{tid}"
                if not cfg[f"{pre}.enabled"] or cfg[f"{pre}.weight"] <= 0:
                    continue
                if cfg[f"{pre}.unlock_phase"] > max(1, phase):
                    continue
                if self.time < self.type_cd.get(tid, -1):
                    continue
                if self._type_class(tid) == "bad" and bad_active >= cfg["powerups.max_bad_orbs"]:
                    continue
                if cfg["powerups.avoid_conflicting_spawns"] and t.group:
                    if self.effects.group_active(t.group) or any(
                            self.types[o.type_id].group == t.group for o in active):
                        continue
                cands.append((tid, cfg[f"{pre}.weight"]))
            if cfg["powerups.no_repeat"] and len(cands) > 1:
                cands = [c for c in cands if c[0] != self.last_type] or cands
            if not cands:
                return None
            total = sum(w for _, w in cands)
            pick = self.rng.uniform(0, total)
            tid = cands[-1][0]
            for cid, w in cands:
                pick -= w
                if pick <= 0:
                    tid = cid
                    break
        slot = self.rng.choice(free)
        x, y = g.slots[slot]
        if cfg["center_zone.layout"] == "random":
            zr = cfg["center_zone.zone_radius"]
            for _ in range(12):
                a = self.rng.uniform(0, math.tau)
                rr = zr * math.sqrt(self.rng.random())
                cx, cy = rr * math.cos(a), rr * math.sin(a)
                if all(math.hypot(cx - o.x, cy - o.y) > 2.4 * orb_r for o in active):
                    x, y = cx, cy
                    break
        orb = Orb(self._next_orb_id, tid, self._type_class(tid), slot, x, y, cfg["powerups.orb_lifetime_s"])
        self._next_orb_id += 1
        self.orbs.append(orb)
        self.last_type = tid
        self.emit("orb_spawned", orb_id=orb.id, type_id=tid, cls=orb.cls, x=x, y=y)
        return orb

    def _update_orbs(self, dt: float) -> None:
        cfg = self.cfg
        spawn_anim = cfg["powerups.spawn_anim_s"]
        mag_on = cfg["powerups.magnet.enabled"]
        strength = cfg["powerups.magnet.strength"]
        radius = cfg["powerups.magnet.radius"]
        falloff = cfg["powerups.magnet.falloff"]
        k_ret = cfg["powerups.magnet.return_strength"]
        damp = cfg["powerups.magnet.damping"]
        max_off = cfg["powerups.magnet.max_offset"]
        only_owned = cfg["powerups.magnet.only_owned_balls"]
        lim = self.geom.wall_face - cfg["powerups.orb_radius"] - 2
        live = self.live_balls()
        for o in list(self.orbs):
            o.age += dt
            o.state_t += dt
            if o.wobble > 0:
                o.wobble = max(0.0, o.wobble - dt)
            if o.state == "spawning" and o.state_t >= spawn_anim:
                o.state, o.state_t = "idle", 0.0
            if o.state in ("spawning", "idle") and o.age >= o.life:
                o.state, o.state_t = "despawning", 0.0
                self.emit("orb_expired", orb_id=o.id, x=o.x, y=o.y)
            if o.state == "despawning" and o.state_t >= 0.3:
                self.orbs.remove(o)
                continue
            if o.state == "collected" and o.state_t >= 0.45:
                self.orbs.remove(o)
                continue
            if o.state not in ("spawning", "idle"):
                continue
            ax = ay = 0.0
            o.pulled = 0.0
            if mag_on and radius > 0:
                best, bd = None, radius
                for b in live:
                    if b.held or (only_owned and b.owner is None):
                        continue
                    d = math.hypot(b.x - o.x, b.y - o.y)
                    if d < bd:
                        best, bd = b, d
                if best is not None and bd > 1e-6:
                    f = strength * (1 - bd / radius) ** falloff
                    ax += f * (best.x - o.x) / bd
                    ay += f * (best.y - o.y) / bd
                    o.pulled = min(1.0, (1 - bd / radius) ** falloff * 1.5)
            ax += -k_ret * (o.x - o.hx) - damp * o.vx
            ay += -k_ret * (o.y - o.hy) - damp * o.vy
            o.vx += ax * dt
            o.vy += ay * dt
            o.x += o.vx * dt
            o.y += o.vy * dt
            ox, oy = o.x - o.hx, o.y - o.hy
            off = math.hypot(ox, oy)
            if off > max_off:
                o.x, o.y = o.hx + ox * max_off / off, o.hy + oy * max_off / off
                o.vx *= 0.5
                o.vy *= 0.5
            d = math.hypot(o.x, o.y)
            if d > lim > 0:
                o.x, o.y = o.x * lim / d, o.y * lim / d

    def _check_orbs(self, b: Ball, ox: float, oy: float) -> None:
        cfg = self.cfg
        orb_r = cfg["powerups.orb_radius"]
        for o in self.orbs:
            if o.state not in ("spawning", "idle"):
                continue
            if o.state == "spawning" and o.state_t < cfg["powerups.spawn_anim_s"] * 0.5:
                continue
            if seg_point_dist(ox, oy, b.x, b.y, o.x, o.y) > orb_r + b.r:
                continue
            if b.owner is None and not cfg["powerups.unowned_ball_collects"]:
                if o.wobble <= 0:
                    o.wobble = 0.45
                    self.emit("orb_touch_unowned", orb_id=o.id, x=o.x, y=o.y)
                continue
            collector = b.owner if b.owner is not None else self.rng.choice((0, 1))
            self._collect(o, b, collector)

    def _collect(self, o: Orb, b: Ball, collector: int) -> None:
        cfg = self.cfg
        t = self.types.get(o.type_id)
        o.state, o.state_t = "collected", 0.0
        if t is None:
            return
        try:
            info = t.collect(self, b, collector) or {}
        except Exception:
            log.exception("power-up %s failed", o.type_id)
            info = {}
        pre = f"powerups.types.{o.type_id}"
        self.type_cd[o.type_id] = self.time + cfg[f"{pre}.cooldown_s"]
        self.stats["powerups"][collector] += 1
        self.emit("powerup_collected", orb_id=o.id, type_id=o.type_id, cls=o.cls, collector=collector,
                  ball_id=b.id, x=o.x, y=o.y, affects=info.get("affects"),
                  toast_c=cfg[f"{pre}.toast_collector"], toast_o=cfg[f"{pre}.toast_opponent"],
                  banner=getattr(t, "banner", False))

    def add_effect(self, ptype, eff: Effect):
        cfg = self.cfg
        pre = f"powerups.types.{ptype.id}"
        added, removed = self.effects.add(eff, cfg[f"{pre}.stacking"], cfg[f"{pre}.max_stack"],
                                          cfg["powerups.exclusive_policy"])
        for r in removed:
            self.emit("effect_ended", effect=r, replaced=True)
        if added is not None:
            self.emit("effect_started", effect=added)
        return added

    def chaos_deflect(self, b: Ball, collector: int, min_deg: float, max_deg: float) -> None:
        g = self.geom
        gx, gy = g.goal_dir[1 - collector]
        ratio = max(0.2, self.cfg["physics.min_axis_ratio"])
        sp = math.hypot(b.vx, b.vy) or self.cfg["ball.base_speed"]
        cur = math.atan2(b.vy, b.vx)
        lo, hi = sorted((min_deg, max_deg))
        new = None
        for _ in range(12):
            a = cur + math.radians(self.rng.uniform(lo, hi)) * self.rng.choice((-1, 1))
            dx, dy = math.cos(a), math.sin(a)
            if dx * gx + dy * gy >= ratio:
                new = a
                break
        if new is None:
            new = math.atan2(gy, gx) + math.radians(self.rng.uniform(-35, 35))
        b.vx, b.vy = math.cos(new) * sp, math.sin(new) * sp
        self._pred_dirty = True
        self.emit("chaos", ball_id=b.id, x=b.x, y=b.y)

    def split_ball(self, b: Ball, n: int, split_deg: float, lifetime: float) -> list[Ball]:
        cfg = self.cfg
        room = cfg["physics.max_balls"] - len(self.live_balls())
        n = int(min(n, room))
        if n <= 0:
            return []
        sp = math.hypot(b.vx, b.vy) or cfg["ball.base_speed"]
        cur = math.atan2(b.vy, b.vx)
        sr = math.radians(split_deg)
        if n == 1:
            angles = [cur - sr, cur + sr]
        else:
            angles = [cur + sr * (k - n / 2) * (2 / max(1, n)) for k in range(n + 1)]
        b.vx, b.vy = math.cos(angles[0]) * sp, math.sin(angles[0]) * sp
        made = []
        lim = self.geom.wall_face - b.r - 1
        for k, a in enumerate(angles[1:], start=1):
            px, py = -math.sin(a), math.cos(a)
            off = 2.4 * b.r * (1 if k % 2 else -1)
            x, y = b.x + px * off, b.y + py * off
            d = math.hypot(x, y)
            if d > lim:
                x, y = x * lim / d, y * lim / d
            nb = Ball(self._next_ball_id, x, y, b.r, self.time)
            self._next_ball_id += 1
            nb.held = False
            nb.vx, nb.vy = math.cos(a) * sp, math.sin(a) * sp
            nb.owner = b.owner
            nb.rally = b.rally
            nb.hits = b.hits
            nb.extra_until = self.time + lifetime
            nb.since_touch = b.since_touch
            nb.last_hit = dict(b.last_hit)
            self.balls.append(nb)
            made.append(nb)
            self.emit("ball_split", ball_id=nb.id, parent=b.id, x=x, y=y, owner=b.owner)
        return made

    def _update_predictions(self, dt: float) -> None:
        cfg = self.cfg
        bens = self.effects.reveal_beneficiaries()
        always = cfg["prediction.debug_always_on"]
        if not bens and not always:
            if self.predictions:
                self.predictions = {}
            return
        self._pred_t -= dt
        if self._pred_t > 0 and not self._pred_dirty:
            return
        self._pred_t = 1.0 / max(1, cfg["prediction.hz"])
        self._pred_dirty = False
        new = {}
        for b in self.live_balls():
            if b.held:
                continue
            rcv = self.heading_to(b)
            if rcv is None:
                continue
            if always or rcv in bens:
                new[b.id] = predict(self, b, rcv)
        self.predictions = new
