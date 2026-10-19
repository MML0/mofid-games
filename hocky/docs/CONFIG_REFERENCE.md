# Market Hockey: configuration reference

Generated from `market_hockey/config/schema.py`. Every key lives in `config/settings.json` and is editable in the control panel (`python settings_app.py`).

Live = applies instantly while the game runs; restart = applies on the next launch.

## Display & Projection

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `display.canvas_width` | 1080 | 256 … 4096 px | live | Canvas width — Logical render width. The circle is inscribed in the smaller side. |
| `display.canvas_height` | 1080 | 256 … 4096 px | live | Canvas height |
| `display.fullscreen` | True | bool | live | Fullscreen — F11 toggles while running. |
| `display.display_index` | 0 | 0 … 8 | restart | Display index — Which monitor/projector to open on. |
| `display.vsync` | True | bool | restart | VSync — Sync to the display refresh (applies on restart). |
| `display.fps_cap` | 120 | 30 … 240 fps | live | Render FPS cap |
| `display.hide_cursor` | True | bool | live | Hide mouse cursor |
| `display.exhibition_mode` | False | bool | live | Exhibition mode — Disables debug hotkeys (Ctrl+Shift+D still toggles debug). |
| `display.output_scale` | 1.0 | 0.5 … 2.0 × | live | Output scale — Uniform zoom applied to the final image. |
| `display.output_offset_x` | 0 | -1000 … 1000 px | live | Output offset X |
| `display.output_offset_y` | 0 | -1000 … 1000 px | live | Output offset Y |
| `display.rotation` | 0 | 0, 90, 180, 270 | live | Output rotation — Rotate the whole image for the projector mount. |
| `display.flip_h` | False | bool | live | Mirror horizontally — For rear projection or mirrors. |
| `display.flip_v` | False | bool | live | Mirror vertically |

## Arena & Walls

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `arena.center_offset_x` | 0 | -400 … 400 px | live | Center offset X |
| `arena.center_offset_y` | 0 | -400 … 400 px | live | Center offset Y |
| `arena.mask_radius` | 540 | 100 … 2048 px | live | Mask radius — The physical projected circle. Everything outside is pure black. |
| `arena.mask_feather` | 1.5 | 0.0 … 6.0 px | live | Mask edge feather |
| `arena.rim_radius` | 520 | 100 … 2048 px | live | Rim radius — Radius of the goal lines and bumper walls. |
| `arena.layout_rotation_deg` | 0.0 | -180 … 180 ° | live | Layout rotation — Rotates goals, walls, paddles and HUD together. |
| `arena.show_center_line` | True | bool | live | Show center line |
| `arena.center_line_alpha` | 0.35 | 0 … 1 | live | Center line opacity |
| `arena.rim_line_width` | 3 | 0 … 12 px | live | Rim line width |
| `arena.rim_glow` | 0.5 | 0 … 1 | live | Rim glow |
| `arena.show_tracks` | True | bool | live | Show paddle tracks — Faint guide arcs where each paddle can slide. |
| `arena.track_alpha` | 0.18 | 0 … 1 | live | Track opacity |
| `walls.top_percent` | 14.0 | 2 … 30 % | live | Top wall size — Size of the top bumper arc as % of the full circumference. |
| `walls.bottom_percent` | 14.0 | 2 … 30 % | live | Bottom wall size |
| `walls.link_sizes` | True | bool | live | Link top & bottom — Bottom wall uses the top wall size. |
| `walls.thickness` | 16 | 4 … 60 px | live | Wall thickness — Drawn inward from the rim; the ball bounces on the inner face. |
| `walls.restitution` | 1.0 | 0.5 … 1.2 | live | Wall bounciness |
| `walls.band_alpha` | 0.85 | 0.1 … 1 | live | Wall opacity |
| `walls.hatch` | True | bool | live | Wall hatch pattern |
| `goals.line_width` | 6 | 1 … 24 px | live | Goal line width |
| `goals.glow` | 0.6 | 0 … 1 | live | Goal line glow |
| `center_zone.layout` | pentagon | pentagon, cross, ring, random | live | Slot layout — Where power-up orbs can appear. |
| `center_zone.slot_count` | 5 | 1 … 8 | live | Slot count (ring/random) |
| `center_zone.slot_radius` | 130 | 0 … 400 px | live | Slot distance from center |
| `center_zone.rotation_deg` | 90.0 | -180 … 180 ° | live | Slot rotation |
| `center_zone.zone_radius` | 170 | 40 … 500 px | live | Zone radius (random layout) |
| `center_zone.show_slot_rings` | True | bool | live | Show empty slot rings |
| `center_zone.slot_ring_alpha` | 0.22 | 0 … 1 | live | Slot ring opacity |

## HUD & Text

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `hud.timer_offset` | 64 | 0 … 400 px | live | Timer distance below top wall |
| `hud.timer_size` | 80 | 20 … 260 px | live | Timer size |
| `hud.timer_format` | seconds | seconds, mm:ss, auto | live | Timer format |
| `hud.final_seconds` | 10 | 0 … 30 s | live | Final-seconds warning |
| `hud.score_offset` | 90 | 0 … 400 px | live | Scores distance above bottom wall |
| `hud.score_size` | 110 | 20 … 300 px | live | Score size |
| `hud.score_spread` | 110 | 0 … 400 px | live | Score distance from center line |
| `hud.show_player_labels` | False | bool | live | Show player labels |
| `hud.label_size` | 26 | 10 … 80 px | live | Label size |
| `hud.orientation` | upright | upright, toward_players | live | Message orientation — toward_players rotates each player's messages to face them. |
| `hud.safe_margin` | 20 | 0 … 120 px | live | Safe margin from rim |
| `hud.alpha` | 0.92 | 0.1 … 1 | live | HUD opacity |
| `text.shaping_backend` | auto | auto, harfbuzz, reshaper | live | Persian shaping — auto = HarfBuzz (SDL_ttf) when available, otherwise arabic-reshaper. |
| `fonts.persian` | IRANSansX-Bold.ttf | IRANSansX-Black.ttf, IRANSansX-Bold.ttf, IRANSansX-DemiBold.ttf, IRANSansX-ExtraBold.ttf, IRANSansX-Light.ttf, IRANSansX-Medium.ttf, IRANSansX-Regular.ttf | live | Persian text font |
| `fonts.persian_title` | IRANSansX-Black.ttf | IRANSansX-Black.ttf, IRANSansX-Bold.ttf, IRANSansX-DemiBold.ttf, IRANSansX-ExtraBold.ttf, IRANSansX-Light.ttf, IRANSansX-Medium.ttf, IRANSansX-Regular.ttf | live | Title font |
| `fonts.digits` | IRANSansX-Black.ttf | IRANSansX-Black.ttf, IRANSansX-Bold.ttf, IRANSansX-DemiBold.ttf, IRANSansX-ExtraBold.ttf, IRANSansX-Light.ttf, IRANSansX-Medium.ttf, IRANSansX-Regular.ttf | live | Digits font — Timer, scores and countdown (always Latin digits). |
| `fonts.latin` | IRANSansX-Bold.ttf | IRANSansX-Black.ttf, IRANSansX-Bold.ttf, IRANSansX-DemiBold.ttf, IRANSansX-ExtraBold.ttf, IRANSansX-Light.ttf, IRANSansX-Medium.ttf, IRANSansX-Regular.ttf | live | Latin text font |
| `text.toast_size` | 40 | 14 … 120 px | live | Message size |
| `text.banner_size` | 64 | 20 … 200 px | live | Banner size |
| `text.toast_duration` | 1.8 | 0.3 … 6 s | live | Message duration |
| `text.toast_radius` | 0.52 | 0.1 … 0.9 ×R | live | Message distance from center |
| `text.title` | هاکی بازار | str | live | Title |
| `text.subtitle` | MARKET HOCKEY | str | live | Subtitle |
| `text.attract_prompt` | برای شروع، روبه‌روی هم بایستید | str | live | Attract prompt |
| `text.ready` | آماده‌اید؟ | str | live | Countdown: ready |
| `text.go` | شروع! | str | live | Countdown: go |
| `text.goal` | گل! | str | live | Goal |
| `text.golden_goal` | گل طلایی! | str | live | Golden goal |
| `text.final` | پایان معاملات! | str | live | Match end |
| `text.winner` | برنده | str | live | Winner |
| `text.draw` | مساوی | str | live | Draw |
| `text.slogan` | بازار همیشه در حرکته؛ آماده‌ی تغییر باش. | str | live | Result slogan |
| `text.paused` | توقف | str | live | Paused |
| `text.step_in` | وارد زمین شوید | str | live | Player absent |
| `text.smart_hit` | واکنش به‌موقع! | str | live | Smart hit |
| `text.player_1` | بازیکن 1 | str | live | Player 1 label |
| `text.player_2` | بازیکن 2 | str | live | Player 2 label |

## Match & Scoring

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `match.timer_enabled` | True | bool | live | Timer enabled |
| `match.duration_s` | 60 | 10 … 900 s | live | Match duration — Applies from the next match. |
| `match.score_limit_enabled` | True | bool | live | Score limit enabled |
| `match.score_limit` | 7 | 1 … 50 goals | live | Score limit |
| `match.tie_rule` | draw | draw, golden_goal | live | When time runs out tied |
| `match.start_mode` | operator_key | operator_key, auto_when_both_present, auto_loop | live | Start trigger — operator_key = Space/Enter or the panel; auto modes start by themselves. |
| `match.auto_loop_delay_s` | 8.0 | 1 … 60 s | live | Auto-loop idle time |
| `match.attract_demo` | True | bool | live | Attract demo (AI vs AI) |
| `match.attract_opacity` | 0.55 | 0.1 … 1 | live | Demo opacity |
| `match.intro_s` | 0.9 | 0.0 … 4 s | live | Intro length |
| `match.goal_pause_s` | 1.4 | 0.2 … 5 s | live | Pause after goal |
| `match.timer_runs_during_goal_pause` | False | bool | live | Timer runs during goal pause |
| `match.timer_runs_during_serve` | True | bool | live | Timer runs during serve |
| `match.final_freeze_s` | 1.6 | 0.2 … 6 s | live | Final freeze |
| `match.result_s` | 6.0 | 1 … 60 s | live | Result screen time |
| `match.result_wait_for_operator` | False | bool | live | Result waits for operator |
| `scoring.points_per_goal` | 1 | 1 … 10 | live | Points per goal |
| `scoring.smart_hit_points` | 0 | 0 … 5 | live | Bonus points per smart hit |
| `scoring.multiball_policy` | end_rally | end_rally, continue | live | Multi-ball goal policy — end_rally: any goal clears all balls and re-serves. continue: other balls keep playing. |
| `phases.enabled` | True | bool | live | Use phases — Power-ups unlock progressively during the match. |
| `phases.warmup_end` | 0.167 | 0 … 1 of match | live | Warm-up ends — No power-ups before this point. |
| `phases.early_end` | 0.417 | 0 … 1 of match | live | Early phase ends |
| `phases.mid_end` | 0.75 | 0 … 1 of match | live | Mid phase ends |
| `phases.peak_end` | 0.917 | 0 … 1 of match | live | Peak phase ends — No new spawns after this point. |
| `phases.peak_spawn_mult` | 0.6 | 0.2 … 2 × | live | Peak spawn interval × |
| `phases.nominal_duration_s` | 60 | 10 … 900 s | live | Nominal length (no timer) |

## Serve

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `serve.first` | random | random, p1, p2, alternate | live | First serve goes to |
| `serve.after_goal` | toward_conceder | toward_conceder, toward_scorer, random, alternate | live | Serve after a goal — toward_conceder: the player who just conceded receives the ball. |
| `serve.angle_variation_deg` | 25.0 | 0 … 70 ° | live | Random angle variation — Spread of the aim point along the receiver's arc. |
| `serve.aim_near_paddle` | False | bool | live | Aim near receiver's paddle |
| `serve.delay_s` | 0.7 | 0 … 3 s | live | Serve delay |
| `serve.position_x` | 0 | -300 … 300 px | live | Serve point X |
| `serve.position_y` | 0 | -300 … 300 px | live | Serve point Y |
| `serve.show_telegraph` | True | bool | live | Show serve direction chevrons |

## Ball & Physics

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `ball.radius` | 14 | 4 … 60 px | live | Ball radius |
| `ball.serve_speed` | 420.0 | 100 … 2000 px/s | live | Serve speed |
| `ball.base_speed` | 520.0 | 150 … 2500 px/s | live | Base speed — Speed after the first paddle hit, before rally gain and effects. |
| `ball.min_speed` | 300.0 | 50 … 2000 px/s | live | Minimum speed |
| `ball.max_speed` | 1500.0 | 200 … 4000 px/s | live | Maximum speed |
| `ball.rally_gain_per_hit` | 1.03 | 1.0 … 1.2 × | live | Rally speed gain per hit |
| `ball.rally_cap` | 1.6 | 1.0 … 3.0 × base | live | Rally speed cap |
| `ball.speed_response` | 3.0 | 0.3 … 20 /s | live | Speed easing rate — How quickly the ball eases toward its target speed. |
| `ball.glow_size` | 3.0 | 1 … 8 × radius | live | Glow size |
| `ball.glow_intensity` | 0.85 | 0 … 1.5 | live | Glow intensity |
| `physics.hz` | 240 | 60 … 600 Hz | live | Physics rate |
| `physics.max_substeps` | 8 | 1 … 20 | live | Max substeps per step |
| `physics.min_axis_ratio` | 0.25 | 0.0 … 0.7 | live | Min sideways ratio — Prevents endless vertical bouncing between the top and bottom walls. |
| `physics.stall_timeout_s` | 6.0 | 1 … 30 s | live | Stall timeout — Time without a paddle touch before the ball is steered. |
| `physics.stall_action` | steer | steer, reserve | live | Stall action |
| `physics.stall_steer_deg_s` | 45.0 | 5 … 360 °/s | live | Stall steering rate |
| `physics.balls_collide` | True | bool | live | Balls collide with each other |
| `physics.max_balls` | 3 | 1 … 6 | live | Max balls on field |

## Paddles

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `paddles.link_players` | True | bool | live | Same settings for both players — When on, Player 2 uses Player 1's paddle values. |
| `paddles.size_stacking` | multiply | multiply, replace | live | Size effect stacking |
| `paddles.p1.width` | 130 | 40 … 400 px | live | Width |
| `paddles.p1.shape_ratio` | 1.0 | 0.25 … 1.0 | live | Dome depth — 1.0 = true semicircle; lower = flatter dome, gentler angles. |
| `paddles.p1.rim_padding` | 36 | 0 … 220 px | live | Rim padding — Distance from the rim to the paddle's flat back edge. |
| `paddles.p1.end_margin_deg` | 4.0 | 0 … 30 ° | live | End margin — Keeps the paddle away from the bumper walls. |
| `paddles.p1.min_width` | 60 | 20 … 300 px | live | Minimum width (effects) |
| `paddles.p1.max_width` | 260 | 60 … 600 px | live | Maximum width (effects) |
| `paddles.p1.size_transition_s` | 0.3 | 0.02 … 2 s | live | Size change time |
| `paddles.p1.follow_mode` | direct | direct, spring | live | Follow mode |
| `paddles.p1.max_speed_deg_s` | 320.0 | 30 … 1500 °/s | live | Max slide speed |
| `paddles.p1.follow_stiffness` | 30.0 | 1 … 120 | live | Spring stiffness |
| `paddles.p1.restitution` | 1.0 | 0.5 … 1.3 | live | Bounciness |
| `paddles.p1.velocity_transfer` | 0.35 | 0 … 1 | live | Paddle motion transfer — How much the paddle's sideways motion drags the ball. |
| `paddles.p1.aim_blend` | 0.4 | 0 … 1 | live | Arcade aim blend — 0 = pure physical reflection, 1 = pure hit-position steering. |
| `paddles.p1.max_aim_angle_deg` | 60.0 | 0 … 85 ° | live | Max aim angle |
| `paddles.p1.max_outgoing_angle_deg` | 72.0 | 10 … 89 ° | live | Max outgoing angle — Never sends the ball backward from a dome hit. |
| `paddles.p1.min_forward` | 0.15 | -1 … 0.8 | live | Min forward component — Outgoing ball always moves this much toward the opponent (-1 = off). |
| `paddles.p1.allow_backward` | False | bool | live | Allow backward deflection |
| `paddles.p1.hit_speed_gain` | 1.0 | 0.8 … 1.6 × | live | Hit speed gain |
| `paddles.p1.paddle_speed_to_ball` | 0.25 | 0 … 1.5 | live | Flick power — Extra ball speed from fast paddle motion. |
| `paddles.p1.hit_cooldown_ms` | 60 | 0 … 300 ms | live | Hit cooldown |
| `paddles.p2.width` | 130 | 40 … 400 px | live | Width |
| `paddles.p2.shape_ratio` | 1.0 | 0.25 … 1.0 | live | Dome depth — 1.0 = true semicircle; lower = flatter dome, gentler angles. |
| `paddles.p2.rim_padding` | 36 | 0 … 220 px | live | Rim padding — Distance from the rim to the paddle's flat back edge. |
| `paddles.p2.end_margin_deg` | 4.0 | 0 … 30 ° | live | End margin — Keeps the paddle away from the bumper walls. |
| `paddles.p2.min_width` | 60 | 20 … 300 px | live | Minimum width (effects) |
| `paddles.p2.max_width` | 260 | 60 … 600 px | live | Maximum width (effects) |
| `paddles.p2.size_transition_s` | 0.3 | 0.02 … 2 s | live | Size change time |
| `paddles.p2.follow_mode` | direct | direct, spring | live | Follow mode |
| `paddles.p2.max_speed_deg_s` | 320.0 | 30 … 1500 °/s | live | Max slide speed |
| `paddles.p2.follow_stiffness` | 30.0 | 1 … 120 | live | Spring stiffness |
| `paddles.p2.restitution` | 1.0 | 0.5 … 1.3 | live | Bounciness |
| `paddles.p2.velocity_transfer` | 0.35 | 0 … 1 | live | Paddle motion transfer — How much the paddle's sideways motion drags the ball. |
| `paddles.p2.aim_blend` | 0.4 | 0 … 1 | live | Arcade aim blend — 0 = pure physical reflection, 1 = pure hit-position steering. |
| `paddles.p2.max_aim_angle_deg` | 60.0 | 0 … 85 ° | live | Max aim angle |
| `paddles.p2.max_outgoing_angle_deg` | 72.0 | 10 … 89 ° | live | Max outgoing angle — Never sends the ball backward from a dome hit. |
| `paddles.p2.min_forward` | 0.15 | -1 … 0.8 | live | Min forward component — Outgoing ball always moves this much toward the opponent (-1 = off). |
| `paddles.p2.allow_backward` | False | bool | live | Allow backward deflection |
| `paddles.p2.hit_speed_gain` | 1.0 | 0.8 … 1.6 × | live | Hit speed gain |
| `paddles.p2.paddle_speed_to_ball` | 0.25 | 0 … 1.5 | live | Flick power — Extra ball speed from fast paddle motion. |
| `paddles.p2.hit_cooldown_ms` | 60 | 0 … 300 ms | live | Hit cooldown |

## Trails

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `trails.duration_s` | 0.35 | 0.05 … 2.0 s | live | Trail length (time) |
| `trails.width_scale` | 0.9 | 0.1 … 2 × ball | live | Trail width |
| `trails.alpha` | 0.9 | 0 … 1 | live | Trail opacity |
| `trails.glow` | 0.6 | 0 … 1.5 | live | Trail glow |
| `trails.color_mode` | current_owner | current_owner, history | live | Color mode — current_owner recolors the whole trail on a hit; history keeps old segments' colors. |
| `trails.sparks_on_hit` | 14 | 0 … 80 | live | Sparks per hit |
| `trails.speedup_length_mult` | 1.6 | 1 … 4 × | live | Trail length when sped up |

## Power-ups

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `powerups.enabled` | True | bool | live | Power-ups enabled |
| `powerups.spawn_interval_min_s` | 4.0 | 0.5 … 30 s | live | Spawn interval min |
| `powerups.spawn_interval_max_s` | 7.0 | 0.5 … 60 s | live | Spawn interval max |
| `powerups.max_active_orbs` | 2 | 0 … 8 | live | Max orbs at once |
| `powerups.max_bad_orbs` | 1 | 0 … 8 | live | Max red orbs at once |
| `powerups.orb_radius` | 30 | 10 … 90 px | live | Orb radius |
| `powerups.orb_lifetime_s` | 9.0 | 1 … 60 s | live | Orb lifetime |
| `powerups.spawn_anim_s` | 0.35 | 0.05 … 2 s | live | Spawn animation |
| `powerups.min_distance_from_ball` | 120 | 0 … 500 px | live | Min spawn distance from ball |
| `powerups.unowned_ball_collects` | False | bool | live | Untouched ball collects — Off: a fresh serve passes through orbs harmlessly. |
| `powerups.exclusive_policy` | replace | replace, block | live | Opposite effects — Opposite events (speed up / slow down) are never active together: replace the old one, or block the new one. |
| `powerups.avoid_conflicting_spawns` | True | bool | live | Avoid spawning conflicting orbs |
| `powerups.no_repeat` | True | bool | live | No same type twice in a row |
| `powerups.icon_scale` | 0.62 | 0.3 … 1 × orb | live | Icon size |
| `powerups.bob_px` | 4.0 | 0 … 20 px | live | Idle bob |
| `powerups.magnet.enabled` | True | bool | live | Magnet enabled |
| `powerups.magnet.strength` | 900.0 | 0 … 8000 px/s² | live | Pull strength |
| `powerups.magnet.radius` | 200 | 0 … 700 px | live | Pull radius |
| `powerups.magnet.falloff` | 1.5 | 0.3 … 4 | live | Falloff — Higher = pull only when the ball is very close. |
| `powerups.magnet.max_offset` | 80 | 0 … 400 px | live | Max drift from slot |
| `powerups.magnet.return_strength` | 6.0 | 0 … 60 /s² | live | Return spring |
| `powerups.magnet.damping` | 4.0 | 0 … 40 /s | live | Damping |
| `powerups.magnet.only_owned_balls` | True | bool | live | Only toward balls someone has touched |
| `powerups.magnet.show_tether` | True | bool | live | Show tether to slot |
| `powerups.types.expand.enabled` | True | bool | live | Enabled |
| `powerups.types.expand.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.expand.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.expand.duration_s` | 8.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.expand.unlock_phase` | 1 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.expand.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.expand.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.expand.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.expand.toast_collector` | بالکرت بزرگ شد! | str | live | Message (collector side) |
| `powerups.types.expand.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.expand.multiplier` | 1.5 | 1.05 … 3.0 × | live | Size multiplier |
| `powerups.types.shrink.enabled` | True | bool | live | Enabled |
| `powerups.types.shrink.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.shrink.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.shrink.duration_s` | 8.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.shrink.unlock_phase` | 1 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.shrink.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.shrink.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.shrink.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.shrink.toast_collector` | بالکر حریف کوچک شد! | str | live | Message (collector side) |
| `powerups.types.shrink.toast_opponent` | بالکرت کوچک شد! | str | live | Message (opponent side) |
| `powerups.types.shrink.multiplier` | 0.6 | 0.2 … 0.95 × | live | Size multiplier |
| `powerups.types.speed_up.enabled` | True | bool | live | Enabled |
| `powerups.types.speed_up.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.speed_up.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.speed_up.duration_s` | 6.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.speed_up.unlock_phase` | 1 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.speed_up.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.speed_up.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.speed_up.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.speed_up.toast_collector` | نوسان بازار افزایش یافت! | str | live | Message (collector side) |
| `powerups.types.speed_up.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.speed_up.multiplier` | 1.4 | 1.05 … 3.0 × | live | Speed multiplier |
| `powerups.types.speed_up.scope` | this_ball | this_ball, all_balls | live | Affects |
| `powerups.types.chaos.enabled` | True | bool | live | Enabled |
| `powerups.types.chaos.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.chaos.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.chaos.duration_s` | 2.5 | 0.5 … 30 s | live | Duration |
| `powerups.types.chaos.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.chaos.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.chaos.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.chaos.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.chaos.toast_collector` | بازار غیرقابل پیش‌بینی شد! | str | live | Message (collector side) |
| `powerups.types.chaos.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.chaos.mode` | instant | instant, wobble | live | Mode — wobble uses Duration as its length. |
| `powerups.types.chaos.min_angle_deg` | 20.0 | 0 … 90 ° | live | Min turn |
| `powerups.types.chaos.max_angle_deg` | 55.0 | 0 … 90 ° | live | Max turn |
| `powerups.types.chaos.wobble_deg_s` | 140.0 | 10 … 600 °/s | live | Wobble strength |
| `powerups.types.chaos.wobble_hz` | 1.6 | 0.2 … 6 Hz | live | Wobble frequency |
| `powerups.types.double_ball.enabled` | True | bool | live | Enabled |
| `powerups.types.double_ball.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.double_ball.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.double_ball.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.double_ball.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.double_ball.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.double_ball.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.double_ball.toast_collector` | حجم معاملات افزایش یافت! | str | live | Message (collector side) |
| `powerups.types.double_ball.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.double_ball.extra_balls` | 1 | 1 … 3 | live | Extra balls |
| `powerups.types.double_ball.split_angle_deg` | 18.0 | 2 … 60 ° | live | Split angle |
| `powerups.types.double_ball.extra_lifetime_s` | 10.0 | 1 … 60 s | live | Extra ball lifetime |
| `powerups.types.trajectory_reveal.enabled` | True | bool | live | Enabled |
| `powerups.types.trajectory_reveal.class` | bad | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.trajectory_reveal.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.trajectory_reveal.duration_s` | 7.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.trajectory_reveal.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.trajectory_reveal.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.trajectory_reveal.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.trajectory_reveal.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.trajectory_reveal.toast_collector` | مسیرت لو رفت! | str | live | Message (collector side) |
| `powerups.types.trajectory_reveal.toast_opponent` | مسیر حرکت را تحلیل کن! | str | live | Message (opponent side) |
| `powerups.types.slow_down.enabled` | False | bool | live | Enabled |
| `powerups.types.slow_down.class` | bad | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.slow_down.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.slow_down.duration_s` | 6.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.slow_down.unlock_phase` | 1 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.slow_down.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.slow_down.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.slow_down.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.slow_down.toast_collector` | بازار وارد دوره‌ی آرام شد. | str | live | Message (collector side) |
| `powerups.types.slow_down.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.slow_down.multiplier` | 0.7 | 0.2 … 0.95 × | live | Speed multiplier |
| `powerups.types.slow_down.scope` | this_ball | this_ball, all_balls | live | Affects |
| `powerups.types.dim_ball.enabled` | False | bool | live | Enabled |
| `powerups.types.dim_ball.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.dim_ball.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.dim_ball.duration_s` | 5.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.dim_ball.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.dim_ball.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.dim_ball.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.dim_ball.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.dim_ball.toast_collector` | بازار در مسیر اصلاح قرار گرفت. | str | live | Message (collector side) |
| `powerups.types.dim_ball.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.dim_ball.alpha` | 0.35 | 0.05 … 1 | live | Ball opacity |
| `powerups.types.dim_ball.min_visibility` | 0.25 | 0.05 … 1 | live | Never below |
| `powerups.types.shield.enabled` | False | bool | live | Enabled |
| `powerups.types.shield.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.shield.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.shield.duration_s` | 8.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.shield.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.shield.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.shield.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.shield.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.shield.toast_collector` | حد نوسان فعال شد! | str | live | Message (collector side) |
| `powerups.types.shield.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.shield.coverage_percent` | 100.0 | 20 … 100 % | live | Goal coverage |
| `powerups.types.shield.charges` | 1 | 1 … 5 | live | Blocks |
| `powerups.types.bull_market.enabled` | False | bool | live | Enabled |
| `powerups.types.bull_market.class` | good | good, bad, neutral | live | Color class — good = green (helps whoever collects it), bad = red (helps the opponent). |
| `powerups.types.bull_market.weight` | 1.0 | 0 … 10 | live | Spawn weight |
| `powerups.types.bull_market.duration_s` | 12.0 | 0.5 … 30 s | live | Duration |
| `powerups.types.bull_market.unlock_phase` | 2 | 1 … 3 | live | Unlocks in phase — 1 = early, 2 = mid, 3 = peak. |
| `powerups.types.bull_market.stacking` | refresh | refresh, extend, stack, ignore | live | If collected again |
| `powerups.types.bull_market.max_stack` | 3 | 1 … 5 | live | Max stack |
| `powerups.types.bull_market.cooldown_s` | 3.0 | 0 … 60 s | live | Re-spawn cooldown |
| `powerups.types.bull_market.toast_collector` | بازار صعودی! گل بعدی دو امتیازی | str | live | Message (collector side) |
| `powerups.types.bull_market.toast_opponent` |  | str | live | Message (opponent side) |
| `powerups.types.bull_market.multiplier` | 2 | 2 … 5 × | live | Points multiplier |

## Trajectory

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `prediction.hz` | 30 | 5 … 120 Hz | live | Update rate |
| `prediction.max_time_s` | 2.5 | 0.3 … 6 s | live | Look-ahead time |
| `prediction.max_bounces` | 4 | 0 … 10 | live | Max wall bounces |
| `prediction.debug_always_on` | False | bool | live | Always show (debug) |
| `prediction.dot_spacing` | 14 | 4 … 60 px | live | Dot spacing |
| `prediction.dot_radius` | 3.0 | 1 … 10 px | live | Dot radius |
| `prediction.march_speed` | 60.0 | 0 … 300 px/s | live | Dot march speed |
| `prediction.ghost_alpha` | 0.45 | 0.05 … 1 | live | Ghost ball opacity |
| `prediction.arrow_length` | 70 | 10 … 200 px | live | Bounce arrow length |
| `prediction.color_mode` | receiver | receiver, white | live | Guide color |

## Smart Move

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `smart.enabled` | True | bool | live | Smart move enabled |
| `smart.min_paddle_speed` | 600.0 | 100 … 3000 px/s | live | Min paddle speed |
| `smart.window_ms` | 150 | 20 … 600 ms | live | Timing window — The flick must start this close to contact. |
| `smart.speed_bonus` | 1.12 | 1.0 … 2.0 × | live | Speed bonus |
| `smart.cooldown_s` | 2.0 | 0 … 20 s | live | Cooldown |
| `smart.trail_s` | 1.2 | 0.1 … 5 s | live | Gold trail duration |

## FX & Countdown

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `countdown.ready_s` | 0.9 | 0 … 3 s | live | 'Ready' time |
| `countdown.beat_s` | 0.8 | 0.3 … 2 s | live | Beat length (3, 2, 1) |
| `countdown.go_s` | 0.6 | 0.2 … 2 s | live | 'Go' time |
| `countdown.size` | 300 | 60 … 600 px | live | Number size |
| `countdown.particles` | 40 | 0 … 200 | live | Particles per beat |
| `fx.flash_max_alpha` | 0.35 | 0 … 0.6 | live | Flash intensity — Kept ≤ 0.6 for photosensitivity safety. |
| `fx.reduce_flashing` | False | bool | live | Reduce flashing |
| `fx.max_particles` | 600 | 0 … 3000 | live | Max particles |
| `fx.shake_px` | 6.0 | 0 … 20 px | live | Goal shake |
| `fx.shake_s` | 0.2 | 0 … 1 s | live | Shake duration |
| `fx.goal_slowmo` | True | bool | live | Goal slow motion |
| `fx.wall_ripples` | True | bool | live | Wall ripples |
| `fx.ambient_chart` | True | bool | live | Ambient market chart |
| `fx.ambient_alpha` | 0.12 | 0 … 0.5 | live | Ambient chart opacity |
| `fx.final_pulse` | True | bool | live | Final-seconds pulse |

## Colors

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `colors.p1` | #00A796 | color | live | Player 1 (Mofid turquoise) |
| `colors.p2` | #832C73 | color | live | Player 2 (Mofid purple) |
| `colors.neutral_ball` | #E8F4F8 | color | live | Untouched ball |
| `colors.ball_core` | #FFFFFF | color | live | Ball core |
| `colors.projection_boost` | 0.35 | 0 … 1 | live | Projection boost — Lifts glow/trail brightness of dark brand colors (keeps hue). |
| `colors.good` | #39E46F | color | live | Good (green) |
| `colors.bad` | #FF3B3B | color | live | Bad (red) |
| `colors.neutral` | #9B6BFF | color | live | Neutral (violet) |
| `colors.smart` | #FFD54A | color | live | Smart hit gold |
| `colors.arena_inner` | #03141C | color | live | Arena center |
| `colors.arena_outer` | #062A3A | color | live | Arena edge |
| `colors.lines` | #1F7A99 | color | live | Arena lines |
| `colors.goal` | #F3716D | color | live | Goal lines (brand red) |
| `colors.wall` | #CFE8EE | color | live | Bumper walls |
| `colors.wall_hatch` | #004C6A | color | live | Wall hatch (brand dark blue) |
| `colors.text` | #FFFFFF | color | live | Text |
| `colors.timer_final` | #F3716D | color | live | Timer (final seconds) |

## Audio

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `audio.enabled` | True | bool | live | Sound enabled |
| `audio.master` | 0.8 | 0 … 1 | live | Master volume |
| `audio.hits` | 0.7 | 0 … 1 | live | Hits & bounces |
| `audio.powerups` | 0.8 | 0 … 1 | live | Power-ups |
| `audio.match` | 0.9 | 0 … 1 | live | Countdown, goals, match |

## Inputs

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `input.p1.source` | keyboard | keyboard, ai, mouse, network, replay | live | Player 1 input — network = LiDAR / CCTV pose tracker over UDP. |
| `input.p2.source` | keyboard | keyboard, ai, mouse, network, replay | live | Player 2 input |
| `input.keyboard.p1_left` | a | key | live | P1 left key |
| `input.keyboard.p1_right` | d | key | live | P1 right key |
| `input.keyboard.p2_left` | left | key | live | P2 left key |
| `input.keyboard.p2_right` | right | key | live | P2 right key |
| `input.keyboard.alt_keys_enabled` | True | bool | live | Alternate up/down keys — W/S and ↑/↓ move paddles up/down on screen. |
| `input.keyboard.p1_up` | w | key | live | P1 screen-up key |
| `input.keyboard.p1_down` | s | key | live | P1 screen-down key |
| `input.keyboard.p2_up` | up | key | live | P2 screen-up key |
| `input.keyboard.p2_down` | down | key | live | P2 screen-down key |
| `input.keyboard.invert_p1` | False | bool | live | Invert P1 |
| `input.keyboard.invert_p2` | False | bool | live | Invert P2 |
| `input.keyboard.max_speed` | 1.6 | 0.1 … 6 range/s | live | Key slide speed |
| `input.keyboard.accel` | 10.0 | 0.5 … 60 range/s² | live | Key acceleration |
| `input.keyboard.friction` | 14.0 | 0.5 … 80 range/s² | live | Key release braking |
| `input.ai.difficulty` | 0.6 | 0 … 1 | live | AI difficulty |
| `input.ai.reaction_s` | 0.15 | 0.02 … 1 s | live | AI reaction time |
| `input.ai.max_speed` | 1.5 | 0.1 … 5 range/s | live | AI max speed |
| `input.ai.noise` | 0.06 | 0 … 0.5 range | live | AI aim noise |
| `input.mouse.player` | p1 | p1, p2 | live | Mouse controls |
| `input.network.port` | 9100 | 1024 … 65535 | restart | UDP port |
| `input.network.bind` | 127.0.0.1 | 127.0.0.1, 0.0.0.0 | restart | Listen on — 0.0.0.0 accepts trackers on other machines. |
| `input.network.offset_x` | 0.0 | -1 … 1 | live | Calibration offset X |
| `input.network.offset_y` | 0.0 | -1 … 1 | live | Calibration offset Y |
| `input.network.scale_x` | 1.0 | 0.1 … 5 | live | Calibration scale X |
| `input.network.scale_y` | 1.0 | 0.1 … 5 | live | Calibration scale Y |
| `input.network.rotation_deg` | 0.0 | -180 … 180 ° | live | Calibration rotation |
| `input.network.flip_x` | False | bool | live | Flip X |
| `input.network.flip_y` | False | bool | live | Flip Y |
| `input.network.timeout_s` | 0.5 | 0.05 … 5 s | live | Message timeout |
| `input.filters.min_confidence` | 0.4 | 0 … 1 | live | Min confidence |
| `input.filters.dead_zone` | 0.002 | 0 … 0.05 range | live | Dead zone |
| `input.filters.max_jump_per_s` | 6.0 | 0.5 … 50 range/s | live | Spike rejection |
| `input.filters.jump_confirm_ms` | 120 | 0 … 1000 ms | live | Spike confirm time |
| `input.filters.one_euro_min_cutoff` | 1.0 | 0.05 … 10 Hz | live | Smoothing min cutoff |
| `input.filters.one_euro_beta` | 0.02 | 0 … 1 | live | Smoothing speed coefficient |
| `input.filters.lost_hold_s` | 0.5 | 0 … 5 s | live | Hold position when lost |
| `input.filters.absent_timeout_s` | 3.0 | 0.2 … 30 s | live | Absent after |
| `input.record` | False | bool | live | Record inputs |
| `input.replay_file` | logs/input_replay.jsonl | str | live | Replay file |

## Live Link & Debug

| Key | Default | Range / options | Live | Description |
|---|---|---|---|---|
| `live_link.enabled` | True | bool | restart | Live link enabled |
| `live_link.game_port` | 9201 | 1024 … 65535 | restart | Game UDP port |
| `live_link.state_hz` | 4.0 | 0.5 … 30 Hz | live | Telemetry rate |
| `debug.overlay` | False | bool | live | Debug overlay (F3) |
| `debug.colliders` | False | bool | live | Show colliders |
| `debug.calibration` | False | bool | live | Calibration overlay (F2) |
| `debug.seed` | 0 | 0 … 999999 | restart | Random seed (0 = random) |
| `debug.log_matches` | True | bool | live | Log matches to CSV |
