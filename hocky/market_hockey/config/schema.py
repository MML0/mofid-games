"""The single source of truth for every tunable setting.

Each `Param` describes one value: its JSON path, default, type, range, and where it appears in the
control panel. The game, the control panel, validation, defaults.json and the config reference
are all generated from this list. Power-up types contribute their own params (see powerups/base.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..inputs.registry import ADAPTERS
from ..paths import FONTS_DIR

SCHEMA_VERSION = 13

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
    "Kinetic Type",
    "Brand Motion",
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
    sb.e("display.scale_quality", "linear", ("linear", "nearest"), "Window scaling filter",
         "linear = smooth edges when the window/projector size differs from the canvas.", live=False)
    sb.i("display.supersample", 2, 1, 3, 1, "×", "Anti-aliasing (supersampling)",
         "Static art and paddles are drawn at this multiple and smoothed down.")
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
    sb.b("walls.hatch", True, "Wall pattern")
    sb.e("walls.style", "energy", ("energy", "classic"), "Wall style", "energy = glowing force-field barrier.")
    sb.f("walls.glow", 0.85, 0, 1.5, 0.01, "", "Wall glow")
    sb.f("walls.flow_speed", 35.0, 0, 200, 1, "°/s", "Energy flow speed")
    sb.i("walls.pulses", 3, 0, 10, 1, "", "Energy pulses per wall")
    sb.b("walls.hit_flash", True, "Flash when hit")
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
    sb.b("hud.show_names", True, "Show player names", "Names entered on the supervisor page appear near the scores.")
    sb.i("hud.name_size", 30, 10, 90, 1, "px", "Name size")
    sb.i("hud.label_size", 26, 10, 80, 1, "px", "Label size")
    sb.section("HUD & Text", "Layout")
    sb.e("hud.orientation", "upright", ("upright", "toward_players"), "Message orientation",
         "toward_players rotates each player's messages to face them.")
    sb.i("hud.safe_margin", 20, 0, 120, 1, "px", "Safe margin from rim")
    sb.f("hud.alpha", 0.92, 0.1, 1, 0.01, "", "HUD opacity")
    sb.f("hud.glow", 0.55, 0, 1.5, 0.01, "", "HUD glow")
    sb.f("text.shadow_alpha", 0.55, 0, 1, 0.01, "", "Text soft shadow")
    sb.section("HUD & Text", "Fonts")
    sb.e("text.shaping_backend", "auto", ("auto", "harfbuzz", "reshaper"), "Persian shaping",
         "auto = HarfBuzz (SDL_ttf) when available, otherwise arabic-reshaper.")
    sb.font("fonts.persian", "Pinar-Bold.ttf", "Persian text font")
    sb.font("fonts.persian_title", "Pinar-Black.ttf", "Title font")
    sb.font("fonts.digits", "SF-Compact-Display-Heavy.ttf", "Digits font", "Timer, scores and countdown (always Latin digits).")
    sb.font("fonts.latin", "SF-Compact-Display-Bold.ttf", "Latin text font")
    sb.section("HUD & Text", "Messages")
    sb.i("text.toast_size", 34, 14, 120, 1, "px", "Message size")
    sb.i("text.banner_size", 56, 20, 200, 1, "px", "Banner size")
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
    sb.f("match.attract_opacity", 0.9, 0.1, 1, 0.01, "", "Demo opacity")
    sb.f("match.title_backing", 0.82, 0, 1, 0.01, "", "Dark backing behind the waiting text",
         "Keeps the game's name and the prompt readable over the moving visuals. 0 removes it.")
    sb.b("match.attract_toasts", False, "Power-up messages in the demo", "Off keeps the waiting screen clean.")
    sb.b("match.clear_names_after_game", True, "Clear player names after each game",
         "Names stay on the result screen, then clear for the next pair of players.")
    sb.f("match.intro_s", 2.8, 0.0, 6, 0.1, "s", "Intro length", "How long the logo takes to come to the center, grow and fade after Start.")
    sb.f("match.goal_pause_s", 1.4, 0.2, 5, 0.1, "s", "Pause after goal")
    sb.b("match.timer_runs_during_goal_pause", False, "Timer runs during goal pause")
    sb.b("match.timer_runs_during_serve", True, "Timer runs during serve")
    sb.f("match.final_freeze_s", 1.6, 0.2, 6, 0.1, "s", "Final freeze")
    sb.f("match.result_s", 15.0, 1, 60, 0.5, "s", "Result screen time")
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
        sb.f(f"{p}.shape_ratio", 1.0, 0.1, 1.0, 0.01, "", "Dome depth (curvature)",
             "How curved the paddle is. The physical bounce turns by about 2× the surface tilt where the ball touches: "
             "1.0 = semicircle (tip hits go very sideways), 0.25 = shallow (tip ≈ 40°), 0.1 = almost flat.")
        sb.i(f"{p}.rim_padding", 36, 0, 220, 1, "px", "Rim padding",
             "Gap between the red goal line (rim) and the paddle's flat back edge. 52 px ≈ 10% of the rim radius.")
        sb.f(f"{p}.end_margin_deg", 4.0, 0, 30, 0.5, "°", "End margin", "Keeps the paddle away from the bumper walls.")
        sb.i(f"{p}.min_width", 60, 20, 300, 1, "px", "Minimum width (effects)")
        sb.i(f"{p}.max_width", 260, 60, 600, 1, "px", "Maximum width (effects)")
        sb.f(f"{p}.size_transition_s", 0.3, 0.02, 2, 0.01, "s", "Size change time")
        sb.section("Paddles", f"{name} — movement")
        sb.e(f"{p}.follow_mode", "direct", ("direct", "spring"), "Follow mode")
        sb.f(f"{p}.max_speed_deg_s", 320, 30, 1500, 5, "°/s", "Max slide speed")
        sb.f(f"{p}.follow_stiffness", 30, 1, 120, 1, "", "Spring stiffness")
        sb.section("Paddles", f"{name} — bounce")
        sb.f(f"{p}.restitution", 1.0, 0.5, 1.3, 0.01, "", "Bounciness", "1.0 = the ball keeps its speed off the paddle.")
        sb.f(f"{p}.velocity_transfer", 0.1, 0, 1, 0.01, "", "Sliding drag (paddle motion → ball)",
             "How much a SLIDING paddle drags the ball sideways with it. 0 = none (pure reflection). "
             "Keyboard paddles slide very fast, so values above ~0.15 throw the ball sideways even on a center hit.")
        sb.f(f"{p}.aim_blend", 0.4, 0, 1, 0.01, "", "Arcade steering blend",
             "0 = purely physical: the angle comes from the dome's curvature at the contact point. "
             "1 = purely 'distance from center': angle = (hit offset ÷ half-width) × Arcade max angle.")
        sb.f(f"{p}.max_aim_angle_deg", 60, 0, 85, 1, "°", "Arcade max angle (at the tip)",
             "Only matters when Arcade steering blend > 0.")
        sb.f(f"{p}.max_outgoing_angle_deg", 55, 10, 89, 1, "°", "Max outgoing angle (safety cap)",
             "No bounce leaves more than this from straight back toward the opponent.")
        sb.f(f"{p}.max_impulse_speed", 450, 0, 3000, 10, "px/s", "Paddle speed used for bounces",
             "Caps how fast the paddle 'swings' in the bounce physics. Keyboard paddles slide ~1500 px/s, a walking "
             "player ~200–400 px/s; lower = calmer, more realistic hits while moving.")
        sb.b(f"{p}.rounded_tips", True, "Rounded tips",
             "A hit on the very tip uses the dome's own edge angle instead of a sharp corner, so tip bounces follow the curvature.")
        sb.f(f"{p}.tip_extra_deg", 5, 0, 45, 1, "°", "Tip extra angle", "How much steeper than the dome's edge a tip hit may be.")
        sb.f(f"{p}.min_forward", 0.15, -1, 0.8, 0.01, "", "Min forward component", "Outgoing ball always moves this much toward the opponent (-1 = off).")
        sb.b(f"{p}.allow_backward", False, "Allow backward deflection")
        sb.f(f"{p}.hit_speed_gain", 1.0, 0.8, 1.6, 0.01, "×", "Hit speed gain")
        sb.f(f"{p}.paddle_speed_to_ball", 0.1, 0, 1.5, 0.01, "", "Flick power",
             "Extra ball SPEED (not direction) from a fast-moving paddle.")
        sb.i(f"{p}.hit_cooldown_ms", 60, 0, 300, 5, "ms", "Hit cooldown")

    # ------------------------------------------------------------------ trails
    sb.section("Trails", "Ownership trail")
    sb.e("trails.style", "comet", ("comet", "ribbon"), "Trail style", "comet = soft glowing star trail.")
    sb.f("trails.duration_s", 0.45, 0.05, 2.0, 0.01, "s", "Trail length (time)")
    sb.f("trails.head_size", 1.15, 0.3, 3.0, 0.05, "× radius", "Trail head size")
    sb.f("trails.falloff", 1.7, 0.4, 5.0, 0.05, "", "Trail fade curve", "Higher = fades faster behind the ball.")
    sb.f("trails.sparkles", 45, 0, 300, 1, "/s", "Star sparkles")
    sb.f("trails.width_scale", 0.9, 0.1, 2, 0.05, "× ball", "Trail width")
    sb.f("trails.alpha", 0.9, 0, 1, 0.01, "", "Trail opacity")
    sb.f("trails.glow", 0.8, 0, 2.0, 0.01, "", "Trail glow")
    sb.e("trails.color_mode", "current_owner", ("current_owner", "history"), "Color mode",
         "current_owner recolors the whole trail on a hit; history keeps old segments' colors.")
    sb.i("trails.sparks_on_hit", 14, 0, 80, 1, "", "Sparks per hit")
    sb.f("trails.speedup_length_mult", 1.6, 1, 4, 0.05, "×", "Trail length when sped up")

    # ------------------------------------------------------------------ power-ups (global)
    sb.section("Power-ups", "Spawning")
    sb.b("powerups.enabled", True, "Power-ups enabled")
    sb.f("powerups.spawn_interval_min_s", 2.5, 0.5, 30, 0.5, "s", "Spawn interval min")
    sb.f("powerups.spawn_interval_max_s", 5.0, 0.5, 60, 0.5, "s", "Spawn interval max")
    sb.i("powerups.max_active_orbs", 3, 0, 8, 1, "", "Max orbs at once")
    sb.i("powerups.max_bad_orbs", 1, 0, 8, 1, "", "Max red orbs at once")
    sb.i("powerups.orb_radius", 30, 10, 90, 1, "px", "Orb radius")
    sb.f("powerups.hitbox_scale", 1.35, 0.5, 3.0, 0.05, "× orb", "Orb hitbox size", "Collection radius relative to the drawn orb.")
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
    sb.f("powerups.magnet.strength", 2200, 0, 10000, 10, "px/s²", "Pull strength")
    sb.i("powerups.magnet.radius", 260, 0, 700, 5, "px", "Pull radius")
    sb.f("powerups.magnet.lead_s", 0.1, 0, 0.5, 0.01, "s", "Lead", "Pull toward where the ball is about to be.")
    sb.f("powerups.magnet.falloff", 1.5, 0.3, 4, 0.05, "", "Falloff", "Higher = pull only when the ball is very close.")
    sb.i("powerups.magnet.max_offset", 120, 0, 400, 1, "px", "Max drift from slot")
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
    sb.section("Trajectory", "Faint aim assist (always on)")
    sb.b("prediction.assist_always", True, "Faint aim assist", "A ghostly hint of where the ball is heading, for the receiver.")
    sb.f("prediction.assist_alpha", 0.13, 0.02, 1, 0.01, "", "Assist opacity")
    sb.f("prediction.assist_dot_scale", 0.55, 0.1, 2, 0.05, "×", "Assist dot size")
    sb.f("prediction.assist_path_fraction", 0.45, 0.05, 1, 0.05, "", "Assist path shown",
         "Only the last part of the path, near the paddle, is drawn.")
    sb.f("prediction.assist_ghost_scale", 0.6, 0.2, 1.5, 0.05, "× ball", "Assist ghost size")
    sb.i("prediction.assist_arrow_length", 30, 5, 150, 1, "px", "Assist bounce arrow length")
    sb.f("prediction.assist_time_s", 1.1, 0.2, 4, 0.05, "s", "Assist look-ahead")
    sb.b("prediction.assist_ghost", True, "Assist ghost ball")
    sb.b("prediction.assist_arrow", True, "Assist bounce arrow", "A tiny faint arrow: how it will bounce off.")
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
    sb.f("countdown.ready_s", 1.2, 0, 3, 0.05, "s", "'Ready' time")
    sb.i("countdown.start", 5, 1, 9, 1, "", "Count down from", "5 counts 5, 4, 3, 2, 1.")
    sb.f("countdown.beat_s", 1.0, 0.3, 2, 0.05, "s", "Beat length", "Seconds per number.")
    sb.f("countdown.go_s", 0.8, 0.2, 2, 0.05, "s", "'Go' time")
    sb.i("countdown.size", 300, 60, 600, 5, "px", "Number size")
    sb.i("countdown.particles", 40, 0, 200, 1, "", "Particles per beat")
    sb.section("FX & Countdown", "Flashes & effects")
    sb.b("fx.dither", True, "Dither gradients", "Removes visible banding steps in the background and glows.")
    sb.f("fx.dither_strength", 1.0, 0, 3, 0.05, "", "Dither strength")
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

    # ------------------------------------------------------------------ kinetic typography backdrop
    sb.section("Kinetic Type", "Backdrop")
    sb.b("kinetic.enabled", True, "Kinetic type backdrop", "The faint wave of letters behind splash, countdown, goals and results.")
    sb.b("kinetic.splash", True, "Splash on launch")
    sb.b("kinetic.on_goal", True, "Shock wave on goals")
    sb.b("kinetic.goal_at_impact", False, "Start goal wave at the impact point", "Off keeps every effect on the exact center.")
    sb.f("kinetic.moment_pace", 1.0, 0.4, 2, 0.05, "×", "Moment pace", "Below 1 plays goal, go, result and splash slower.")
    sb.section("Kinetic Type", "Grid & typography")
    sb.i("kinetic.density", 55, 10, 120, 1, "", "Grid density", "Cells per side. On a 4 m floor, 55 makes letters about 5 cm tall.")
    sb.f("kinetic.font_scale", 0.9, 0.3, 2, 0.05, "", "Font scale", "Letter height as a share of the row height.")
    sb.s("kinetic.attract_text", "MOFID SECURITIES|STEADY PROGRESS|MARKET HOCKEY",
         "Waiting-screen texts", "Separate with | . They take turns, each spreading out from the center.")
    sb.f("kinetic.text_interval_s", 9.0, 2, 60, 0.5, "s", "Text change interval")
    sb.b("kinetic.space_marks", True, "Spaces become brand dots", "Echoes the dot grid of the brand book. Off leaves empty rings.")
    sb.s("kinetic.text_start", "MARKET HOCKEY", "Match start text")
    sb.s("kinetic.text_ready", "READY", "Ready text")
    sb.s("kinetic.text_go", "GO", "Go text")
    sb.s("kinetic.text_goal", "GOAL", "Goal text")
    sb.s("kinetic.text_final", "MARKET CLOSED", "Match end text")
    sb.s("kinetic.text_winner", "WINNER", "Winner's side text")
    sb.s("kinetic.text_draw", "DRAW", "Draw text")
    sb.s("kinetic.loser_text", "STEADY PROGRESS", "Other side's text on the result",
         "The brand slogan: the brand book rules out sad or discouraging imagery.")
    sb.font("kinetic.font_latin", "SF-Compact-Display-Bold.ttf", "Latin font")
    sb.font("kinetic.font_persian", "Pinar-Black.ttf", "Persian font", "Only used if you type Persian into the texts above.")
    sb.section("Kinetic Type", "Motion & wave")
    sb.f("kinetic.speed", 0.06, 0.01, 0.2, 0.01, "", "Animation speed", "Radians per frame at 60 fps. How fast the rings travel.")
    sb.f("kinetic.frequency", 0.03, 0.005, 0.1, 0.001, "", "Wave frequency", "Radians per reference pixel. Higher = more, tighter waves.")
    sb.f("kinetic.min_stretch", 0.25, 0.05, 1, 0.05, "×", "Min stretch", "Width multiplier in the wave's trough.")
    sb.f("kinetic.max_stretch", 2.6, 1, 8, 0.1, "×", "Max stretch", "Width multiplier on the wave's crest.")
    sb.f("kinetic.max_overlap", 1.5, 0.5, 8, 0.1, "cells", "Max letter width", "How far one letter may spread over its neighbors. Lower = more readable.")
    sb.f("kinetic.drift", 1.0, 0, 2, 0.05, "", "Waiting-screen drift", "How far the sliders wander by themselves while waiting.")
    sb.section("Kinetic Type", "Colors & rings")
    sb.c("kinetic.color1", "#00A796", "Color 1 (brand turquoise)")
    sb.c("kinetic.color2", "#53D5FD", "Color 2 (sky blue)")
    sb.c("kinetic.color3", "#94E3FE", "Color 3 (pale sky blue)")
    sb.c("kinetic.loser_color", "#F3716D", "Other side on the result (brand red)")
    sb.f("kinetic.ring_width", 50, 20, 200, 5, "", "Ring width", "Rings of one color. Smaller = more color changes.")
    sb.f("kinetic.letter_width", 24, 10, 200, 1, "", "Letter ring width", "Rings of one letter. Close to the cell size keeps words readable.")
    sb.b("kinetic.color_swap", False, "Color swap (flicker)", "Rotates the colors between rings. Ignored with Reduce flashing.")
    sb.i("kinetic.swap_interval", 140, 10, 300, 10, "frames", "Color swap interval")
    sb.section("Kinetic Type", "Opacity wave (waiting screen)")
    sb.f("kinetic.opacity_wave_speed", 0.025, 0, 0.2, 0.001, "", "Speed", "How fast the letters fade and return, like a heartbeat.")
    sb.f("kinetic.opacity_wave_frequency", 0.003, 0, 0.05, 0.001, "", "Frequency", "0 fades the whole visual together. Higher = rings of light and dark.")
    sb.f("kinetic.opacity_wave_min", 0.1, 0, 1, 0.01, "", "Valley opacity", "0 disappears completely.")
    sb.f("kinetic.opacity_wave_max", 1.0, 0, 1, 0.01, "", "Peak opacity")
    sb.f("kinetic.opacity_wave_sharpness", 1.5, 0.5, 5, 0.1, "", "Sharpness", "1 is a plain sine. Higher = shorter peaks, like a pulse.")
    sb.section("Kinetic Type", "Faintness")
    sb.f("kinetic.edge_fade_start", 0.5, 0, 1, 0.01, "×R", "Fade starts", "Letters begin fading here, so they stay clear of the rim.")
    sb.f("kinetic.edge_fade_end", 0.82, 0, 1.2, 0.01, "×R", "Fade ends", "Letters are gone by here: inside the paddles, walls and goal lines.")
    sb.f("kinetic.opacity_waiting", 0.85, 0, 1, 0.01, "", "Waiting screen", "The waiting screen's dim also applies on top of this.")
    sb.f("kinetic.opacity_countdown", 0.4, 0, 1, 0.01, "", "Countdown")
    sb.f("kinetic.opacity_moment", 0.75, 0, 1, 0.01, "", "Peak of a moment", "Goal, go, final and result at their brightest.")
    sb.f("kinetic.opacity_result", 0.35, 0, 1, 0.01, "", "Result screen (resting)")
    sb.f("kinetic.opacity_play", 0.0, 0, 0.3, 0.01, "", "During play", "0 keeps the arena clean while the ball is live.")

    # ------------------------------------------------------------------ colors
    sb.section("Brand Motion", "Moving objects")
    sb.b("motion.enabled", True, "Moving brand objects", "Paper planes, flipping coins, pulsing rings and marks from the brand book.")
    sb.b("motion.splash", True, "Opening flood on launch")
    sb.b("motion.waiting_loop", True, "Loop on the waiting screen", "A 46 second show of every object, one after another.")
    sb.b("motion.on_goal", True, "Burst on goals")
    sb.b("motion.in_play", True, "Paper planes during play", "They cross under the ball at the Level during play below.")
    sb.f("motion.plane_every_s", 14.0, 4, 60, 1, "s", "Plane interval during play")
    sb.section("Brand Motion", "Mofid logo")
    sb.b("motion.logo_waiting", True, "Logo on the waiting screen", "Always there in the background.")
    sb.b("motion.logo_zoom", True, "Logo grows and fades after Start", "It brightens, springs to the center, grows, and fades out while still growing.")
    sb.b("motion.logo_result", True, "Logo on the result screen")
    sb.f("motion.logo_rest", 0.75, 0.05, 1, 0.01, "", "Waiting opacity", "How visible the logo is while waiting.")
    sb.f("motion.logo_size", 0.32, 0.1, 0.7, 0.01, "×D", "Waiting width")
    sb.f("motion.logo_result_size", 0.24, 0.08, 0.5, 0.01, "×D", "Result screen width")
    sb.b("motion.logo_play", True, "Logo in the middle during the match", "Faint, under the game, like a mark on the ice.")
    sb.f("motion.logo_play_opacity", 0.14, 0.02, 0.6, 0.01, "", "Match opacity")
    sb.f("motion.logo_play_size", 0.36, 0.1, 0.8, 0.01, "×D", "Match width")
    sb.section("Brand Motion", "Sizes (share of the arena's diameter)")
    sb.f("motion.plane_size", 0.15, 0.04, 0.4, 0.005, "×D", "Paper plane")
    sb.f("motion.coin_size", 0.072, 0.03, 0.2, 0.002, "×D", "Coin", "The coins that fly and fill the wall.")
    sb.f("motion.hero_size", 0.27, 0.08, 0.6, 0.01, "×D", "Center coin")
    sb.section("Brand Motion", "Strength")
    sb.f("motion.level_waiting", 1.0, 0, 1, 0.01, "", "Waiting screen", "The waiting screen's dim also applies on top of this.")
    sb.f("motion.level_countdown", 0.9, 0, 1, 0.01, "", "Countdown")
    sb.f("motion.level_moment", 1.0, 0, 1, 0.01, "", "Goals, match start and end")
    sb.f("motion.level_result", 0.95, 0, 1, 0.01, "", "Result screen")
    sb.f("motion.level_play", 0.45, 0, 1, 0.01, "", "During play", "Keep it low: the ball must stay the brightest thing.")
    sb.f("motion.result_wall", 0.85, 0, 1, 0.01, "", "Winner's coin wall once settled", "Lower keeps the names and scores easier to read.")
    sb.f("motion.object_opacity", 0.6, 0, 1, 0.01, "", "Objects as background",
         "Coins, planes, charts and marks all together. Lower sits them further behind the game.")
    sb.f("motion.flood_strength", 0.6, 0, 1, 0.01, "", "Floods as background", "How strongly the floods color the floor.")
    sb.f("motion.chart_strength", 0.7, 0, 1, 0.01, "", "Market chart", "The candles and line, on top of the objects' opacity.")
    sb.f("motion.edge_fade_start", 0.72, 0, 1, 0.01, "×R", "Rim fade starts", "Objects begin fading here, near the outer circle.")
    sb.f("motion.edge_fade_end", 0.92, 0, 1.2, 0.01, "×R", "Rim fade ends", "Gone by here. Shorter than the letters' fade, so objects keep their size.")
    sb.section("Brand Motion", "Colors")
    sb.c("motion.color_pale", "#DEF1EE", "Flood and light coins (brand tint)")
    sb.c("motion.color_teal", "#00A796", "Turquoise (brand)")
    sb.c("motion.color_tint", "#5BC4BF", "Light turquoise (brand tint)")
    sb.c("motion.color_dark", "#004C6A", "Dark coins (brand dark blue)")
    sb.c("motion.color_accent", "#832C73", "Accent coins (brand purple)")

    sb.section("Colors", "Teams")
    sb.c("colors.p1", "#00A796", "Player 1 (Mofid turquoise)")
    sb.c("colors.p2", "#832C73", "Player 2 (Mofid purple)")
    sb.c("colors.neutral_ball", "#E8F4F8", "Untouched ball")
    sb.c("colors.ball_core", "#FFFFFF", "Ball core")
    sb.f("colors.projection_boost", 0.35, 0, 1, 0.01, "", "Projection boost", "Lifts glow/trail brightness of dark brand colors (keeps hue).")
    sb.section("Colors", "Power-up classes")
    sb.c("colors.good", "#7DD87D", "Good (green, clear of the turquoise team)")
    sb.c("colors.bad", "#F3716D", "Bad (Mofid red)")
    sb.c("colors.neutral", "#DEF1EE", "Neutral (Mofid pale, a silver coin)")
    sb.c("colors.smart", "#FFD54A", "Smart hit gold")
    sb.section("Colors", "Arena")
    sb.c("colors.arena_inner", "#03141C", "Arena center")
    sb.c("colors.arena_outer", "#062A3A", "Arena edge")
    sb.c("colors.lines", "#1F7A99", "Arena lines")
    sb.c("colors.goal", "#F3716D", "Goal lines (brand red)")
    sb.c("colors.wall", "#A8F0FF", "Bumper walls (energy)")
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
    src = tuple(ADAPTERS)
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
    sb.f("input.ai.noise", 0.04, 0, 0.5, 0.005, "range", "AI aim noise")
    sb.f("input.ai.smoothing", 7.0, 1, 30, 0.5, "", "AI movement smoothness", "Lower = softer, more human motion.")
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
    sb.section("Live Link & Debug", "Supervisor web page")
    sb.b("web.enabled", True, "Supervisor page enabled", "A local web page to enter player names, start matches and see results.",
         live=False)
    sb.i("web.port", 8765, 1024, 65535, 1, "", "Web port", live=False)
    sb.e("web.bind", "0.0.0.0", ("0.0.0.0", "127.0.0.1"), "Listen on",
         "0.0.0.0 = phones/tablets on the same network can open the page; 127.0.0.1 = this computer only.", live=False)
    sb.b("web.show_url_on_arena", False, "Show the page address on the waiting screen",
         "Off by default: the addresses are printed in the terminal when the game starts.")
    sb.b("web.open_browser", False, "Open the page when the game starts", live=False)
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
