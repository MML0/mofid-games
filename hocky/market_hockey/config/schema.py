"""The single source of truth for every tunable setting.

Each `Param` describes one value: its JSON path, default, type, range, and where it appears in the
control panel. The game, the control panel, validation, defaults.json and the config reference
are all generated from this list. Power-up types contribute their own params (see powerups/base.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..paths import FONTS_DIR

SCHEMA_VERSION = 1

TABS = [
    "Display & Projection",
    "Arena & Walls",
    "HUD & Text",
    "Match & Scoring",
    "Serve",
    "Ball & Physics",
    "Paddles",
    "Trails",
    "Power-ups",
    "Trajectory",
    "Smart Move",
    "FX & Countdown",
    "Colors",
    "Audio",
    "Inputs",
    "Live Link & Debug",
]

KINDS = ("float", "int", "bool", "color", "enum", "str", "key", "font")


@dataclass
class Param:
    path: str
    default: Any
    kind: str
    tab: str
    group: str
    label: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str = ""
    options: tuple = ()
    help: str = ""
    live: bool = True
    rtl: bool = False


def _font_options() -> tuple:
    try:
        names = sorted(p.name for p in FONTS_DIR.iterdir() if p.suffix.lower() in (".ttf", ".otf"))
    except FileNotFoundError:
        names = []
    return tuple(names) or ("IRANSansX-Bold.ttf",)


class SchemaBuilder:
    def __init__(self):
        self.params: dict[str, Param] = {}
        self.tab = TABS[0]
        self.group = "General"
        self.fonts = _font_options()

    def section(self, tab: str, group: str):
        if tab not in TABS:
            raise ValueError(f"unknown tab {tab!r}")
        self.tab, self.group = tab, group
        return self

    def _add(self, p: Param):
        if p.path in self.params:
            raise ValueError(f"duplicate setting {p.path}")
        if not p.label:
            p.label = p.path.rsplit(".", 1)[-1].replace("_", " ").capitalize()
        self.params[p.path] = p
        return p

    def f(self, path, default, lo, hi, step=0.01, unit="", label="", help="", live=True):
        return self._add(Param(path, float(default), "float", self.tab, self.group, label, lo, hi, step, unit, (), help, live))

    def i(self, path, default, lo, hi, step=1, unit="", label="", help="", live=True):
        return self._add(Param(path, int(default), "int", self.tab, self.group, label, lo, hi, step, unit, (), help, live))

    def b(self, path, default, label="", help="", live=True):
        return self._add(Param(path, bool(default), "bool", self.tab, self.group, label, help=help, live=live))

    def c(self, path, default, label="", help="", live=True):
        return self._add(Param(path, default.upper(), "color", self.tab, self.group, label, help=help, live=live))

    def e(self, path, default, options, label="", help="", live=True):
        return self._add(Param(path, default, "enum", self.tab, self.group, label, options=tuple(options), help=help, live=live))

    def s(self, path, default, label="", help="", rtl=False, live=True):
        return self._add(Param(path, default, "str", self.tab, self.group, label, help=help, live=live, rtl=rtl))

    def k(self, path, default, label="", help="", live=True):
        return self._add(Param(path, default, "key", self.tab, self.group, label, help=help, live=live))

    def font(self, path, default, label="", help="", live=True):
        opts = self.fonts if default in self.fonts else (default,) + self.fonts
        return self._add(Param(path, default, "font", self.tab, self.group, label, options=opts, help=help, live=live))


ZWNJ = "‌"


def _core(sb: SchemaBuilder) -> None:
    # ------------------------------------------------------------------ display
    sb.section("Display & Projection", "Canvas")
    sb.i("display.canvas_width", 1080, 256, 4096, 8, "px", "Canvas width", "Logical render width. The circle is inscribed in the smaller side.")
    sb.i("display.canvas_height", 1080, 256, 4096, 8, "px", "Canvas height")
    sb.b("display.fullscreen", True, "Fullscreen", "F11 toggles while running.")
    sb.i("display.display_index", 0, 0, 8, 1, "", "Display index", "Which monitor/projector to open on.", live=False)
    sb.b("display.vsync", True, "VSync", "Sync to the display refresh (applies on restart).", live=False)
    sb.i("display.fps_cap", 120, 30, 240, 1, "fps", "Render FPS cap")
    sb.b("display.hide_cursor", True, "Hide mouse cursor")
    sb.b("display.exhibition_mode", False, "Exhibition mode", "Disables debug hotkeys (Ctrl+Shift+D still toggles debug).")
    sb.section("Display & Projection", "Projector alignment")
    sb.f("display.output_scale", 1.0, 0.5, 2.0, 0.005, "×", "Output scale", "Uniform zoom applied to the final image.")
    sb.i("display.output_offset_x", 0, -1000, 1000, 1, "px", "Output offset X")
    sb.i("display.output_offset_y", 0, -1000, 1000, 1, "px", "Output offset Y")
    sb.e("display.rotation", "0", ("0", "90", "180", "270"), "Output rotation", "Rotate the whole image for the projector mount.")
    sb.b("display.flip_h", False, "Mirror horizontally", "For rear projection or mirrors.")
    sb.b("display.flip_v", False, "Mirror vertically")

    # ------------------------------------------------------------------ arena
    sb.section("Arena & Walls", "Circle")
    sb.i("arena.center_offset_x", 0, -400, 400, 1, "px", "Center offset X")
    sb.i("arena.center_offset_y", 0, -400, 400, 1, "px", "Center offset Y")
    sb.i("arena.mask_radius", 540, 100, 2048, 1, "px", "Mask radius", "The physical projected circle. Everything outside is pure black.")
    sb.f("arena.mask_feather", 1.5, 0.0, 6.0, 0.1, "px", "Mask edge feather")
    sb.i("arena.rim_radius", 520, 100, 2048, 1, "px", "Rim radius", "Radius of the goal lines and bumper walls.")
    sb.f("arena.layout_rotation_deg", 0.0, -180, 180, 0.5, "°", "Layout rotation", "Rotates goals, walls, paddles and HUD together.")
    sb.section("Arena & Walls", "Lines")
    sb.b("arena.show_center_line", True, "Show center line")
    sb.f("arena.center_line_alpha", 0.35, 0, 1, 0.01, "", "Center line opacity")
    sb.i("arena.rim_line_width", 3, 0, 12, 1, "px", "Rim line width")
    sb.f("arena.rim_glow", 0.5, 0, 1, 0.01, "", "Rim glow")
    sb.b("arena.show_tracks", True, "Show paddle tracks", "Faint guide arcs where each paddle can slide.")
    sb.f("arena.track_alpha", 0.18, 0, 1, 0.01, "", "Track opacity")
    sb.section("Arena & Walls", "Bumper walls (top / bottom)")
    sb.f("walls.top_percent", 14.0, 2, 30, 0.5, "%", "Top wall size", "Size of the top bumper arc as % of the full circumference.")
    sb.f("walls.bottom_percent", 14.0, 2, 30, 0.5, "%", "Bottom wall size")
    sb.b("walls.link_sizes", True, "Link top & bottom", "Bottom wall uses the top wall size.")
    sb.i("walls.thickness", 16, 4, 60, 1, "px", "Wall thickness", "Drawn inward from the rim; the ball bounces on the inner face.")
    sb.f("walls.restitution", 1.0, 0.5, 1.2, 0.01, "", "Wall bounciness")
    sb.f("walls.band_alpha", 0.85, 0.1, 1, 0.01, "", "Wall opacity")
    sb.b("walls.hatch", True, "Wall hatch pattern")
    sb.section("Arena & Walls", "Goal lines")
    sb.i("goals.line_width", 6, 1, 24, 1, "px", "Goal line width")
    sb.f("goals.glow", 0.6, 0, 1, 0.01, "", "Goal line glow")
    sb.section("Arena & Walls", "Center zone (power-up slots)")
    sb.e("center_zone.layout", "pentagon", ("pentagon", "cross", "ring", "random"), "Slot layout", "Where power-up orbs can appear.")
    sb.i("center_zone.slot_count", 5, 1, 8, 1, "", "Slot count (ring/random)")
    sb.i("center_zone.slot_radius", 130, 0, 400, 1, "px", "Slot distance from center")
    sb.f("center_zone.rotation_deg", 90.0, -180, 180, 1, "°", "Slot rotation")
    sb.i("center_zone.zone_radius", 170, 40, 500, 1, "px", "Zone radius (random layout)")
    sb.b("center_zone.show_slot_rings", True, "Show empty slot rings")
    sb.f("center_zone.slot_ring_alpha", 0.22, 0, 1, 0.01, "", "Slot ring opacity")

    # ------------------------------------------------------------------ HUD & text
    sb.section("HUD & Text", "Timer")
    sb.i("hud.timer_offset", 64, 0, 400, 1, "px", "Timer distance below top wall")
    sb.i("hud.timer_size", 80, 20, 260, 1, "px", "Timer size")
    sb.e("hud.timer_format", "seconds", ("seconds", "mm:ss", "auto"), "Timer format")
    sb.i("hud.final_seconds", 10, 0, 30, 1, "s", "Final-seconds warning")
    sb.section("HUD & Text", "Scores")
    sb.i("hud.score_offset", 90, 0, 400, 1, "px", "Scores distance above bottom wall")
    sb.i("hud.score_size", 110, 20, 300, 1, "px", "Score size")
    sb.i("hud.score_spread", 110, 0, 400, 1, "px", "Score distance from center line")
    sb.b("hud.show_player_labels", False, "Show player labels")
    sb.i("hud.label_size", 26, 10, 80, 1, "px", "Label size")
    sb.section("HUD & Text", "Layout")
    sb.e("hud.orientation", "upright", ("upright", "toward_players"), "Message orientation",
         "toward_players rotates each player's messages to face them.")
    sb.i("hud.safe_margin", 20, 0, 120, 1, "px", "Safe margin from rim")
    sb.f("hud.alpha", 0.92, 0.1, 1, 0.01, "", "HUD opacity")
    sb.section("HUD & Text", "Fonts")
    sb.e("text.shaping_backend", "auto", ("auto", "harfbuzz", "reshaper"), "Persian shaping",
         "auto = HarfBuzz (SDL_ttf) when available, otherwise arabic-reshaper.")
    sb.font("fonts.persian", "IRANSansX-Bold.ttf", "Persian text font")
    sb.font("fonts.persian_title", "IRANSansX-Black.ttf", "Title font")
    sb.font("fonts.digits", "IRANSansX-Black.ttf", "Digits font", "Timer, scores and countdown (always Latin digits).")
    sb.font("fonts.latin", "IRANSansX-Bold.ttf", "Latin text font")
    sb.section("HUD & Text", "Messages")
    sb.i("text.toast_size", 40, 14, 120, 1, "px", "Message size")
    sb.i("text.banner_size", 64, 20, 200, 1, "px", "Banner size")
    sb.f("text.toast_duration", 1.8, 0.3, 6, 0.1, "s", "Message duration")
    sb.f("text.toast_radius", 0.52, 0.1, 0.9, 0.01, "×R", "Message distance from center")
    strings = [
        ("title", "هاکی بازار", "Title"),
        ("subtitle", "MARKET HOCKEY", "Subtitle"),
        ("attract_prompt", f"برای شروع، روبه{ZWNJ}روی هم بایستید", "Attract prompt"),
        ("ready", f"آماده{ZWNJ}اید؟", "Countdown: ready"),
        ("go", "شروع!", "Countdown: go"),
        ("goal", "گل!", "Goal"),
        ("golden_goal", "گل طلایی!", "Golden goal"),
        ("final", "پایان معاملات!", "Match end"),
        ("winner", "برنده", "Winner"),
        ("draw", "مساوی", "Draw"),
        ("slogan", f"بازار همیشه در حرکته؛ آماده{ZWNJ}ی تغییر باش.", "Result slogan"),
        ("paused", "توقف", "Paused"),
        ("step_in", "وارد زمین شوید", "Player absent"),
        ("smart_hit", f"واکنش به{ZWNJ}موقع!", "Smart hit"),
        ("player_1", "بازیکن 1", "Player 1 label"),
        ("player_2", "بازیکن 2", "Player 2 label"),
    ]
    for key, val, label in strings:
        sb.s(f"text.{key}", val, label, rtl=True)

    # ------------------------------------------------------------------ match
    sb.section("Match & Scoring", "End conditions")
    sb.b("match.timer_enabled", True, "Timer enabled")
    sb.i("match.duration_s", 60, 10, 900, 5, "s", "Match duration", "Applies from the next match.")
    sb.b("match.score_limit_enabled", True, "Score limit enabled")
    sb.i("match.score_limit", 7, 1, 50, 1, "goals", "Score limit")
    sb.e("match.tie_rule", "draw", ("draw", "golden_goal"), "When time runs out tied")
    sb.section("Match & Scoring", "Flow")
    sb.e("match.start_mode", "operator_key", ("operator_key", "auto_when_both_present", "auto_loop"), "Start trigger",
         "operator_key = Space/Enter or the panel; auto modes start by themselves.")
    sb.f("match.auto_loop_delay_s", 8.0, 1, 60, 0.5, "s", "Auto-loop idle time")
    sb.b("match.attract_demo", True, "Attract demo (AI vs AI)")
    sb.f("match.attract_opacity", 0.55, 0.1, 1, 0.01, "", "Demo opacity")
    sb.f("match.intro_s", 0.9, 0.0, 4, 0.1, "s", "Intro length")
    sb.f("match.goal_pause_s", 1.4, 0.2, 5, 0.1, "s", "Pause after goal")
    sb.b("match.timer_runs_during_goal_pause", False, "Timer runs during goal pause")
    sb.b("match.timer_runs_during_serve", True, "Timer runs during serve")
    sb.f("match.final_freeze_s", 1.6, 0.2, 6, 0.1, "s", "Final freeze")
    sb.f("match.result_s", 6.0, 1, 60, 0.5, "s", "Result screen time")
    sb.b("match.result_wait_for_operator", False, "Result waits for operator")
    sb.section("Match & Scoring", "Scoring")
    sb.i("scoring.points_per_goal", 1, 1, 10, 1, "", "Points per goal")
    sb.i("scoring.smart_hit_points", 0, 0, 5, 1, "", "Bonus points per smart hit")
    sb.e("scoring.multiball_policy", "end_rally", ("end_rally", "continue"), "Multi-ball goal policy",
         "end_rally: any goal clears all balls and re-serves. continue: other balls keep playing.")
    sb.section("Match & Scoring", "Phases (from the concept timeline)")
    sb.b("phases.enabled", True, "Use phases", "Power-ups unlock progressively during the match.")
    sb.f("phases.warmup_end", 0.167, 0, 1, 0.001, "of match", "Warm-up ends", "No power-ups before this point.")
    sb.f("phases.early_end", 0.417, 0, 1, 0.001, "of match", "Early phase ends")
    sb.f("phases.mid_end", 0.75, 0, 1, 0.001, "of match", "Mid phase ends")
    sb.f("phases.peak_end", 0.917, 0, 1, 0.001, "of match", "Peak phase ends", "No new spawns after this point.")
    sb.f("phases.peak_spawn_mult", 0.6, 0.2, 2, 0.05, "×", "Peak spawn interval ×")
    sb.i("phases.nominal_duration_s", 60, 10, 900, 5, "s", "Nominal length (no timer)")

    # ------------------------------------------------------------------ serve
    sb.section("Serve", "Serve")
    sb.e("serve.first", "random", ("random", "p1", "p2", "alternate"), "First serve goes to")
    sb.e("serve.after_goal", "toward_conceder", ("toward_conceder", "toward_scorer", "random", "alternate"),
         "Serve after a goal", "toward_conceder: the player who just conceded receives the ball.")
    sb.f("serve.angle_variation_deg", 25.0, 0, 70, 1, "°", "Random angle variation", "Spread of the aim point along the receiver's arc.")
    sb.b("serve.aim_near_paddle", False, "Aim near receiver's paddle")
    sb.f("serve.delay_s", 0.7, 0, 3, 0.05, "s", "Serve delay")
    sb.i("serve.position_x", 0, -300, 300, 1, "px", "Serve point X")
    sb.i("serve.position_y", 0, -300, 300, 1, "px", "Serve point Y")
    sb.b("serve.show_telegraph", True, "Show serve direction chevrons")

    # ------------------------------------------------------------------ ball & physics
    sb.section("Ball & Physics", "Ball")
    sb.i("ball.radius", 14, 4, 60, 1, "px", "Ball radius")
    sb.f("ball.serve_speed", 420, 100, 2000, 10, "px/s", "Serve speed")
    sb.f("ball.base_speed", 520, 150, 2500, 10, "px/s", "Base speed", "Speed after the first paddle hit, before rally gain and effects.")
    sb.f("ball.min_speed", 300, 50, 2000, 10, "px/s", "Minimum speed")
    sb.f("ball.max_speed", 1500, 200, 4000, 10, "px/s", "Maximum speed")
    sb.f("ball.rally_gain_per_hit", 1.03, 1.0, 1.2, 0.005, "×", "Rally speed gain per hit")
    sb.f("ball.rally_cap", 1.6, 1.0, 3.0, 0.05, "× base", "Rally speed cap")
    sb.f("ball.speed_response", 3.0, 0.3, 20, 0.1, "/s", "Speed easing rate", "How quickly the ball eases toward its target speed.")
    sb.f("ball.glow_size", 3.0, 1, 8, 0.1, "× radius", "Glow size")
    sb.f("ball.glow_intensity", 0.85, 0, 1.5, 0.01, "", "Glow intensity")
    sb.section("Ball & Physics", "Simulation")
    sb.i("physics.hz", 240, 60, 600, 10, "Hz", "Physics rate")
    sb.i("physics.max_substeps", 8, 1, 20, 1, "", "Max substeps per step")
    sb.f("physics.min_axis_ratio", 0.25, 0.0, 0.7, 0.01, "", "Min sideways ratio",
         "Prevents endless vertical bouncing between the top and bottom walls.")
    sb.f("physics.stall_timeout_s", 6.0, 1, 30, 0.5, "s", "Stall timeout", "Time without a paddle touch before the ball is steered.")
    sb.e("physics.stall_action", "steer", ("steer", "reserve"), "Stall action")
    sb.f("physics.stall_steer_deg_s", 45.0, 5, 360, 5, "°/s", "Stall steering rate")
    sb.b("physics.balls_collide", True, "Balls collide with each other")
    sb.i("physics.max_balls", 3, 1, 6, 1, "", "Max balls on field")

    # ------------------------------------------------------------------ paddles
    sb.section("Paddles", "General")
    sb.b("paddles.link_players", True, "Same settings for both players", "When on, Player 2 uses Player 1's paddle values.")
    sb.e("paddles.size_stacking", "multiply", ("multiply", "replace"), "Size effect stacking")
    for pid, name in (("p1", "Player 1"), ("p2", "Player 2")):
        p = f"paddles.{pid}"
        sb.section("Paddles", f"{name} — shape & track")
        sb.i(f"{p}.width", 130, 40, 400, 1, "px", "Width")
        sb.f(f"{p}.shape_ratio", 1.0, 0.25, 1.0, 0.01, "", "Dome depth", "1.0 = true semicircle; lower = flatter dome, gentler angles.")
        sb.i(f"{p}.rim_padding", 36, 0, 220, 1, "px", "Rim padding", "Distance from the rim to the paddle's flat back edge.")
        sb.f(f"{p}.end_margin_deg", 4.0, 0, 30, 0.5, "°", "End margin", "Keeps the paddle away from the bumper walls.")
        sb.i(f"{p}.min_width", 60, 20, 300, 1, "px", "Minimum width (effects)")
        sb.i(f"{p}.max_width", 260, 60, 600, 1, "px", "Maximum width (effects)")
        sb.f(f"{p}.size_transition_s", 0.3, 0.02, 2, 0.01, "s", "Size change time")
        sb.section("Paddles", f"{name} — movement")
        sb.e(f"{p}.follow_mode", "direct", ("direct", "spring"), "Follow mode")
        sb.f(f"{p}.max_speed_deg_s", 320, 30, 1500, 5, "°/s", "Max slide speed")
        sb.f(f"{p}.follow_stiffness", 30, 1, 120, 1, "", "Spring stiffness")
        sb.section("Paddles", f"{name} — bounce")
        sb.f(f"{p}.restitution", 1.0, 0.5, 1.3, 0.01, "", "Bounciness")
        sb.f(f"{p}.velocity_transfer", 0.35, 0, 1, 0.01, "", "Paddle motion transfer", "How much the paddle's sideways motion drags the ball.")
        sb.f(f"{p}.aim_blend", 0.4, 0, 1, 0.01, "", "Arcade aim blend", "0 = pure physical reflection, 1 = pure hit-position steering.")
        sb.f(f"{p}.max_aim_angle_deg", 60, 0, 85, 1, "°", "Max aim angle")
        sb.f(f"{p}.max_outgoing_angle_deg", 72, 10, 89, 1, "°", "Max outgoing angle", "Never sends the ball backward from a dome hit.")
        sb.f(f"{p}.min_forward", 0.15, -1, 0.8, 0.01, "", "Min forward component", "Outgoing ball always moves this much toward the opponent (-1 = off).")
        sb.b(f"{p}.allow_backward", False, "Allow backward deflection")
        sb.f(f"{p}.hit_speed_gain", 1.0, 0.8, 1.6, 0.01, "×", "Hit speed gain")
        sb.f(f"{p}.paddle_speed_to_ball", 0.25, 0, 1.5, 0.01, "", "Flick power", "Extra ball speed from fast paddle motion.")
        sb.i(f"{p}.hit_cooldown_ms", 60, 0, 300, 5, "ms", "Hit cooldown")

    # ------------------------------------------------------------------ trails
    sb.section("Trails", "Ownership trail")
    sb.f("trails.duration_s", 0.35, 0.05, 2.0, 0.01, "s", "Trail length (time)")
    sb.f("trails.width_scale", 0.9, 0.1, 2, 0.05, "× ball", "Trail width")
    sb.f("trails.alpha", 0.9, 0, 1, 0.01, "", "Trail opacity")
    sb.f("trails.glow", 0.6, 0, 1.5, 0.01, "", "Trail glow")
    sb.e("trails.color_mode", "current_owner", ("current_owner", "history"), "Color mode",
         "current_owner recolors the whole trail on a hit; history keeps old segments' colors.")
    sb.i("trails.sparks_on_hit", 14, 0, 80, 1, "", "Sparks per hit")
    sb.f("trails.speedup_length_mult", 1.6, 1, 4, 0.05, "×", "Trail length when sped up")

    # ------------------------------------------------------------------ power-ups (global)
    sb.section("Power-ups", "Spawning")
    sb.b("powerups.enabled", True, "Power-ups enabled")
    sb.f("powerups.spawn_interval_min_s", 4.0, 0.5, 30, 0.5, "s", "Spawn interval min")
    sb.f("powerups.spawn_interval_max_s", 7.0, 0.5, 60, 0.5, "s", "Spawn interval max")
    sb.i("powerups.max_active_orbs", 2, 0, 8, 1, "", "Max orbs at once")
    sb.i("powerups.max_bad_orbs", 1, 0, 8, 1, "", "Max red orbs at once")
    sb.i("powerups.orb_radius", 30, 10, 90, 1, "px", "Orb radius")
    sb.f("powerups.orb_lifetime_s", 9.0, 1, 60, 0.5, "s", "Orb lifetime")
    sb.f("powerups.spawn_anim_s", 0.35, 0.05, 2, 0.05, "s", "Spawn animation")
    sb.i("powerups.min_distance_from_ball", 120, 0, 500, 5, "px", "Min spawn distance from ball")
    sb.b("powerups.unowned_ball_collects", False, "Untouched ball collects", "Off: a fresh serve passes through orbs harmlessly.")
    sb.e("powerups.exclusive_policy", "replace", ("replace", "block"), "Opposite effects",
         "Opposite events (speed up / slow down) are never active together: replace the old one, or block the new one.")
    sb.b("powerups.avoid_conflicting_spawns", True, "Avoid spawning conflicting orbs")
    sb.b("powerups.no_repeat", True, "No same type twice in a row")
    sb.f("powerups.icon_scale", 0.62, 0.3, 1, 0.01, "× orb", "Icon size")
    sb.f("powerups.bob_px", 4.0, 0, 20, 0.5, "px", "Idle bob")
    sb.section("Power-ups", "Magnet (orbs drawn toward the ball)")
    sb.b("powerups.magnet.enabled", True, "Magnet enabled")
    sb.f("powerups.magnet.strength", 900, 0, 8000, 10, "px/s²", "Pull strength")
    sb.i("powerups.magnet.radius", 200, 0, 700, 5, "px", "Pull radius")
    sb.f("powerups.magnet.falloff", 1.5, 0.3, 4, 0.05, "", "Falloff", "Higher = pull only when the ball is very close.")
    sb.i("powerups.magnet.max_offset", 80, 0, 400, 1, "px", "Max drift from slot")
    sb.f("powerups.magnet.return_strength", 6.0, 0, 60, 0.5, "/s²", "Return spring")
    sb.f("powerups.magnet.damping", 4.0, 0, 40, 0.5, "/s", "Damping")
    sb.b("powerups.magnet.only_owned_balls", True, "Only toward balls someone has touched")
    sb.b("powerups.magnet.show_tether", True, "Show tether to slot")

    # ------------------------------------------------------------------ trajectory
    sb.section("Trajectory", "Prediction")
    sb.i("prediction.hz", 30, 5, 120, 1, "Hz", "Update rate")
    sb.f("prediction.max_time_s", 2.5, 0.3, 6, 0.1, "s", "Look-ahead time")
    sb.i("prediction.max_bounces", 4, 0, 10, 1, "", "Max wall bounces")
    sb.b("prediction.debug_always_on", False, "Always show (debug)")
    sb.section("Trajectory", "Look")
    sb.i("prediction.dot_spacing", 14, 4, 60, 1, "px", "Dot spacing")
    sb.f("prediction.dot_radius", 3.0, 1, 10, 0.5, "px", "Dot radius")
    sb.f("prediction.march_speed", 60.0, 0, 300, 5, "px/s", "Dot march speed")
    sb.f("prediction.ghost_alpha", 0.45, 0.05, 1, 0.01, "", "Ghost ball opacity")
    sb.i("prediction.arrow_length", 70, 10, 200, 1, "px", "Bounce arrow length")
    sb.e("prediction.color_mode", "receiver", ("receiver", "white"), "Guide color")

    # ------------------------------------------------------------------ smart move
    sb.section("Smart Move", f"ضربه{ZWNJ}ی ویژه — timed flick")
    sb.b("smart.enabled", True, "Smart move enabled")
    sb.f("smart.min_paddle_speed", 600, 100, 3000, 10, "px/s", "Min paddle speed")
    sb.i("smart.window_ms", 150, 20, 600, 5, "ms", "Timing window", "The flick must start this close to contact.")
    sb.f("smart.speed_bonus", 1.12, 1.0, 2.0, 0.01, "×", "Speed bonus")
    sb.f("smart.cooldown_s", 2.0, 0, 20, 0.1, "s", "Cooldown")
    sb.f("smart.trail_s", 1.2, 0.1, 5, 0.1, "s", "Gold trail duration")

    # ------------------------------------------------------------------ fx
    sb.section("FX & Countdown", "Countdown")
    sb.f("countdown.ready_s", 0.9, 0, 3, 0.05, "s", "'Ready' time")
    sb.f("countdown.beat_s", 0.8, 0.3, 2, 0.05, "s", "Beat length (3, 2, 1)")
    sb.f("countdown.go_s", 0.6, 0.2, 2, 0.05, "s", "'Go' time")
    sb.i("countdown.size", 300, 60, 600, 5, "px", "Number size")
    sb.i("countdown.particles", 40, 0, 200, 1, "", "Particles per beat")
    sb.section("FX & Countdown", "Flashes & effects")
    sb.f("fx.flash_max_alpha", 0.35, 0, 0.6, 0.01, "", "Flash intensity", "Kept ≤ 0.6 for photosensitivity safety.")
    sb.b("fx.reduce_flashing", False, "Reduce flashing")
    sb.i("fx.max_particles", 600, 0, 3000, 10, "", "Max particles")
    sb.f("fx.shake_px", 6.0, 0, 20, 0.5, "px", "Goal shake")
    sb.f("fx.shake_s", 0.2, 0, 1, 0.05, "s", "Shake duration")
    sb.b("fx.goal_slowmo", True, "Goal slow motion")
    sb.b("fx.wall_ripples", True, "Wall ripples")
    sb.b("fx.ambient_chart", True, "Ambient market chart")
    sb.f("fx.ambient_alpha", 0.12, 0, 0.5, 0.01, "", "Ambient chart opacity")
    sb.b("fx.final_pulse", True, "Final-seconds pulse")

    # ------------------------------------------------------------------ colors
    sb.section("Colors", "Teams")
    sb.c("colors.p1", "#00A796", "Player 1 (Mofid turquoise)")
    sb.c("colors.p2", "#832C73", "Player 2 (Mofid purple)")
    sb.c("colors.neutral_ball", "#E8F4F8", "Untouched ball")
    sb.c("colors.ball_core", "#FFFFFF", "Ball core")
    sb.f("colors.projection_boost", 0.35, 0, 1, 0.01, "", "Projection boost", "Lifts glow/trail brightness of dark brand colors (keeps hue).")
    sb.section("Colors", "Power-up classes")
    sb.c("colors.good", "#39E46F", "Good (green)")
    sb.c("colors.bad", "#FF3B3B", "Bad (red)")
    sb.c("colors.neutral", "#9B6BFF", "Neutral (violet)")
    sb.c("colors.smart", "#FFD54A", "Smart hit gold")
    sb.section("Colors", "Arena")
    sb.c("colors.arena_inner", "#03141C", "Arena center")
    sb.c("colors.arena_outer", "#062A3A", "Arena edge")
    sb.c("colors.lines", "#1F7A99", "Arena lines")
    sb.c("colors.goal", "#F3716D", "Goal lines (brand red)")
    sb.c("colors.wall", "#CFE8EE", "Bumper walls")
    sb.c("colors.wall_hatch", "#004C6A", "Wall hatch (brand dark blue)")
    sb.c("colors.text", "#FFFFFF", "Text")
    sb.c("colors.timer_final", "#F3716D", "Timer (final seconds)")

    # ------------------------------------------------------------------ audio
    sb.section("Audio", "Volume")
    sb.b("audio.enabled", True, "Sound enabled")
    sb.f("audio.master", 0.8, 0, 1, 0.01, "", "Master volume")
    sb.f("audio.hits", 0.7, 0, 1, 0.01, "", "Hits & bounces")
    sb.f("audio.powerups", 0.8, 0, 1, 0.01, "", "Power-ups")
    sb.f("audio.match", 0.9, 0, 1, 0.01, "", "Countdown, goals, match")

    # ------------------------------------------------------------------ inputs
    src = ("keyboard", "ai", "mouse", "network", "replay")
    sb.section("Inputs", "Sources")
    sb.e("input.p1.source", "keyboard", src, "Player 1 input", "network = LiDAR / CCTV pose tracker over UDP.")
    sb.e("input.p2.source", "keyboard", src, "Player 2 input")
    sb.section("Inputs", "Keyboard")
    sb.k("input.keyboard.p1_left", "a", "P1 left key")
    sb.k("input.keyboard.p1_right", "d", "P1 right key")
    sb.k("input.keyboard.p2_left", "left", "P2 left key")
    sb.k("input.keyboard.p2_right", "right", "P2 right key")
    sb.b("input.keyboard.alt_keys_enabled", True, "Alternate up/down keys", "W/S and ↑/↓ move paddles up/down on screen.")
    sb.k("input.keyboard.p1_up", "w", "P1 screen-up key")
    sb.k("input.keyboard.p1_down", "s", "P1 screen-down key")
    sb.k("input.keyboard.p2_up", "up", "P2 screen-up key")
    sb.k("input.keyboard.p2_down", "down", "P2 screen-down key")
    sb.b("input.keyboard.invert_p1", False, "Invert P1")
    sb.b("input.keyboard.invert_p2", False, "Invert P2")
    sb.f("input.keyboard.max_speed", 1.6, 0.1, 6, 0.05, "range/s", "Key slide speed")
    sb.f("input.keyboard.accel", 10.0, 0.5, 60, 0.5, "range/s²", "Key acceleration")
    sb.f("input.keyboard.friction", 14.0, 0.5, 80, 0.5, "range/s²", "Key release braking")
    sb.section("Inputs", "AI / demo")
    sb.f("input.ai.difficulty", 0.6, 0, 1, 0.01, "", "AI difficulty")
    sb.f("input.ai.reaction_s", 0.15, 0.02, 1, 0.01, "s", "AI reaction time")
    sb.f("input.ai.max_speed", 1.5, 0.1, 5, 0.05, "range/s", "AI max speed")
    sb.f("input.ai.noise", 0.06, 0, 0.5, 0.005, "range", "AI aim noise")
    sb.section("Inputs", "Mouse (debug)")
    sb.e("input.mouse.player", "p1", ("p1", "p2"), "Mouse controls")
    sb.section("Inputs", "Network (LiDAR / pose tracker)")
    sb.i("input.network.port", 9100, 1024, 65535, 1, "", "UDP port", live=False)
    sb.e("input.network.bind", "127.0.0.1", ("127.0.0.1", "0.0.0.0"), "Listen on", "0.0.0.0 accepts trackers on other machines.", live=False)
    sb.f("input.network.offset_x", 0.0, -1, 1, 0.001, "", "Calibration offset X")
    sb.f("input.network.offset_y", 0.0, -1, 1, 0.001, "", "Calibration offset Y")
    sb.f("input.network.scale_x", 1.0, 0.1, 5, 0.001, "", "Calibration scale X")
    sb.f("input.network.scale_y", 1.0, 0.1, 5, 0.001, "", "Calibration scale Y")
    sb.f("input.network.rotation_deg", 0.0, -180, 180, 0.1, "°", "Calibration rotation")
    sb.b("input.network.flip_x", False, "Flip X")
    sb.b("input.network.flip_y", False, "Flip Y")
    sb.f("input.network.timeout_s", 0.5, 0.05, 5, 0.05, "s", "Message timeout")
    sb.section("Inputs", "Filters & presence")
    sb.f("input.filters.min_confidence", 0.4, 0, 1, 0.01, "", "Min confidence")
    sb.f("input.filters.dead_zone", 0.002, 0, 0.05, 0.001, "range", "Dead zone")
    sb.f("input.filters.max_jump_per_s", 6.0, 0.5, 50, 0.5, "range/s", "Spike rejection")
    sb.i("input.filters.jump_confirm_ms", 120, 0, 1000, 10, "ms", "Spike confirm time")
    sb.f("input.filters.one_euro_min_cutoff", 1.0, 0.05, 10, 0.05, "Hz", "Smoothing min cutoff")
    sb.f("input.filters.one_euro_beta", 0.02, 0, 1, 0.005, "", "Smoothing speed coefficient")
    sb.f("input.filters.lost_hold_s", 0.5, 0, 5, 0.05, "s", "Hold position when lost")
    sb.f("input.filters.absent_timeout_s", 3.0, 0.2, 30, 0.1, "s", "Absent after")
    sb.section("Inputs", "Record / replay")
    sb.b("input.record", False, "Record inputs")
    sb.s("input.replay_file", "logs/input_replay.jsonl", "Replay file")

    # ------------------------------------------------------------------ live link & debug
    sb.section("Live Link & Debug", "Live link")
    sb.b("live_link.enabled", True, "Live link enabled", live=False)
    sb.i("live_link.game_port", 9201, 1024, 65535, 1, "", "Game UDP port", live=False)
    sb.f("live_link.state_hz", 4.0, 0.5, 30, 0.5, "Hz", "Telemetry rate")
    sb.section("Live Link & Debug", "Debug")
    sb.b("debug.overlay", False, "Debug overlay (F3)")
    sb.b("debug.colliders", False, "Show colliders")
    sb.b("debug.calibration", False, "Calibration overlay (F2)")
    sb.i("debug.seed", 0, 0, 999999, 1, "", "Random seed (0 = random)", live=False)
    sb.b("debug.log_matches", True, "Log matches to CSV")


_SCHEMA: dict[str, Param] | None = None


def build_schema() -> dict[str, Param]:
    sb = SchemaBuilder()
    _core(sb)
    from ..powerups import registry

    for ptype in registry.all_types().values():
        ptype.add_schema(sb)
    return sb.params


def get_schema() -> dict[str, Param]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = build_schema()
    return _SCHEMA


def defaults() -> dict[str, Any]:
    return {path: p.default for path, p in get_schema().items()}
