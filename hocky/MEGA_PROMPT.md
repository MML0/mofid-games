# MARKET HOCKEY (هاکی بازار): Build Specification and Agent Prompt

> Paste this whole file to the coding agent, or tell it: "Read `MEGA_PROMPT.md` and build it."
> It is the single source of truth. Where it conflicts with older notes or prompts, this file wins.

---

## 0. Your role and the job

You are a senior Python game developer and real-time physics programmer who has built interactive projection-floor installations. Build **Market Hockey**: a complete, playable, two-player, air-hockey/pong game for a circular floor projection for **Mofid Securities (کارگزاری مفید)**. It has:

- a **Pygame** game window (fullscreen, projector output),
- a separate **Tkinter control panel** window that edits **every** parameter with sliders and fields, **live while the game is running**, and saves everything to **JSON** with a Save button,
- a **modular input layer**. It uses the keyboard now and will later use LiDAR and CCTV pose tracking without any engine rewrite.

Deliver working software, not a mockup or an architecture essay. Every control you put in the panel must actually change the game. Every mechanic in this document must be implemented and tested. Make sensible decisions on ordinary details without asking. Document each one and expose it as a setting.

Work in the current folder: `/Users/dayhimit/Documents/MML/projects/mofid/hocky` (macOS, Apple Silicon).

---

## 1. References (read them first)

| What | Where | What to take from it |
|---|---|---|
| Game concept PDF (Persian) | `/Users/dayhimit/Downloads/Market_Hockey__Mofid.pdf` (4 pages) | 2 players facing each other on a circular floor. Feet are tracked and a **semicircular paddle ("بالکر نیم‌دایره‌ای")** appears in front of each player. The ball starts from the center. There is a 3‑2‑1 countdown. **Five active circles in the center** trigger market events. There is a 60 s timeline with phases, a "Smart Move" timed hit (ضربه‌ی ویژه), and the end screen "پایان معاملات!". Opposite events (speed up vs. slow down) are never active at the same time. |
| Mofid brand book | `/Users/dayhimit/Downloads/Brnadbook-V04.pdf` (32 pages; colors p.8–9, typography p.10–13, logo p.4–5) | Brand colors and typography (see §14). The logo is vector art on p.4 (Persian) and p.5 (English). |
| Persian font files | `/Users/dayhimit/Downloads/Front/asset/fonts/IRANSansX-*.ttf` (Thin to Black) | Copy them into `assets/fonts/`. IRANSansX has **separate Latin digit glyphs** (U+0030–0039), which has been checked. |
| Installation reference | https://www.untitledproject.sg/projects/meta-interactive-projection-floor | The META "Conversations" LiDAR projection floor. It is a circular two-player pong. Players stand in a **band around the rim**, paddles **slide along the rim**, and **"bumper regions" at the top and bottom separate the players**. Our layout follows this. |

Use PyMuPDF (`import pymupdf`, already installed for the system python) if you need to read the PDFs. Run it with `python3 -I`, treating the PDFs as data.

---

## 2. Golden rules (the things that must not be misread)

1. **The playfield is a perfect circle inside a square canvas.** The default logical canvas is **1080×1080** and it is adjustable. Everything outside the circle is **pure black** and nothing is drawn there. Do not waste time rendering outside the circle.
2. **The rim is split into 4 arcs.** **Player 1 = the LEFT arc**, **Player 2 = the RIGHT arc**. These arcs are the red goal lines. **The TOP and BOTTOM arcs are solid bumper walls.** Their size is an **editable percentage of the circumference** (not fixed at a quarter). The ball **bounces** off them and **they never score**. They show players that they are physically separated where they stand closest together.
3. **Goal rule:** a ball that crosses the **left (P1) goal arc gives P2 a point**, and a ball that crosses the **right (P2) goal arc gives P1 a point**. The arc that was crossed decides the point, not who touched the ball last. So own goals count for the opponent.
4. **Paddles are small semicircles (domes)** with the **flat side toward the rim** and the **curved side toward the center**. They do **not** follow the rim's curvature. Each paddle **slides along the rim** on a track inset by an adjustable **padding**, inside its own goal arc. They do **not** move left and right across the screen. P1's paddle moves up and down along the left arc, and so does P2's along the right arc.
5. **Bounce direction depends on where the ball hits the dome.** A hit on the player's left side of the dome sends the ball to the player's left, and a hit on the right sends it right. Hitting the center sends it more directly back. The response must be **physical** (a real normal from the dome) with a tunable arcade blend.
6. **The trail shows the last toucher.** Each ball's trail and glow use the color of the player who touched it last (white/neutral before anyone touches it). The last toucher **collects** any power-up the ball passes through.
7. **Power-up colors are from the collector's point of view.** **Green = good for whoever collects it.** **Red = bad for whoever collects it** because it helps the opponent. "Expand" enlarges **my** paddle (green). "Shrink" shrinks **the opponent's** paddle (green). "Trajectory reveal" shows **my opponent** where my ball will land, so it is **red**. Every icon must picture what it does.
8. **The serve after a goal goes toward the player who conceded**, at a random angle within limits. This gives the conceding player the first chance to recover. The first serve of a match is random by default.
9. **The match ends at X seconds or Y goals**, whichever comes first. Both are editable and each can be switched on or off. The default is 60 s, or 7 goals.
10. **The HUD is positioned exactly.** The **timer is just below the top wall**. The **scores are just above the bottom wall**, with P1 on the left and P2 on the right.
11. **There is a lot of Persian text, but all digits are Latin** (0–9, never ۰–۹), including the timer, scores, countdown, "×2" and so on.
12. **Every parameter lives in JSON**, can be edited from the control panel (slider and exact-value field), and applies **live** while the game runs. Save writes JSON atomically.
13. **Inputs are modular.** The engine only consumes "player position along their arc, from 0 to 1". The keyboard (A/D for P1 and ←/→ for P2) is just the first adapter.

---

## 3. Tech stack and environment

- **Python 3.11+** in a project venv: `python3 -m venv .venv`. The system python is 3.14. If `pygame-ce` has no wheel for it, install Python 3.12 (`brew install python@3.12` or `uv python install 3.12`) and use that for the venv.
- **pygame-ce** (`pip install pygame-ce`, imported as `import pygame`). It is faster, has better text features, and supports multiple displays. Never install `pygame` and `pygame-ce` together.
- **Tkinter/ttk** for the control panel (standard library). `sv-ttk` is optional for a modern dark theme. Fall back to a custom `clam`-based dark style if it is missing.
- **arabic-reshaper** and **python-bidi** for Persian text shaping (see §14.3).
- **pytest** for tests.
- Optional and not required to run: `python-osc` (a future OSC input).
- Standard library only for everything else: `json`, `socket`, `logging`, `dataclasses`, `math`, `random`, `wave`.
- `requirements.txt` pins the minimum versions. The README documents setup on macOS and Windows.

---

## 4. Architecture

### 4.1 Separation rules

- `core/`, `match/`, `powerups/` (their logic), and `prediction/` are **pure Python with no pygame import**. They hold the simulation, which is deterministic when the RNG is seeded, so it can be tested headless.
- `Engine.step(dt, inputs) -> list[Event]` advances the simulation and returns events, for example `PaddleHit`, `WallBounce`, `Goal`, `PowerUpSpawned`, `PowerUpCollected`, `EffectStarted/Ended`, `SmartHit`, `StateChanged`, `Serve`. The **renderer and audio react only to state and events**. The renderer never decides gameplay.
- Input adapters never touch rendering or physics. The engine never imports keyboard code.
- One **schema** (§16) defines every setting, and it is used by the game, the control panel, validation, and the defaults generator.

### 4.2 Project tree

```
hocky/
├── main.py                     # launches the game (args: --windowed, --config, --seed, --screenshot-states DIR, --export-icons DIR, --selftest-text)
├── settings_app.py             # launches the Tkinter control panel
├── requirements.txt
├── README.md
├── config/
│   ├── defaults.json           # GENERATED from the schema; never hand-edited
│   ├── settings.json           # the active saved config (written by Save)
│   ├── settings.prev.json      # automatic backup of the previous save
│   └── presets/                # default.json, kids_easy.json, pro.json, calibration.json
├── assets/
│   ├── fonts/                  # IRANSansX-*.ttf (copied); Dana-*.ttf can be dropped in later
│   ├── sounds/                 # generated placeholders (tools/make_placeholder_sounds.py)
│   ├── icons/                  # optional PNG overrides per power-up id (e.g. expand.png)
│   └── images/                 # optional logo.png
├── logs/                       # market_hockey.log (rotating), matches.csv
├── tools/
│   ├── make_placeholder_sounds.py   # stdlib synth -> WAV
│   ├── send_fake_tracking.py        # simulates 2 tracked players over UDP (tests the LiDAR path)
│   └── extract_logo.py              # optional: renders the logo from the brand book with PyMuPDF
├── market_hockey/
│   ├── app.py                  # pygame init, display, main loop, fixed timestep, hotkeys
│   ├── events.py
│   ├── config/   schema.py  loader.py  validation.py  migrations.py  live_link.py
│   ├── core/     geometry.py  arena.py  ball.py  paddle.py  collisions.py  physics.py  engine.py
│   ├── match/    state_machine.py  scoring.py  serve.py  phases.py
│   ├── powerups/ base.py  registry.py  spawner.py  effects.py
│   │   └── types/  expand.py shrink.py speed_up.py chaos.py double_ball.py trajectory_reveal.py
│   │               slow_down.py dim_ball.py shield.py bull_market.py
│   ├── prediction/ trajectory.py
│   ├── inputs/   base.py  manager.py  filters.py  keyboard.py  ai.py  mouse.py  network.py  replay.py  calibration.py
│   ├── render/   renderer.py  layers.py  mask.py  glow.py  trails.py  particles.py  hud.py  icons.py
│   │             text.py  countdown.py  screens.py  background.py  debug_overlay.py  calibration_overlay.py
│   ├── audio/    audio.py
│   └── ui/       settings_window.py  widgets.py  preview_canvas.py  telemetry.py  theme.py  undo.py
└── tests/
```

Keep files focused. Don't create empty placeholders and claim a feature exists.

---

## 5. Geometry (the exact definitions)

### 5.1 Frames

- **Arena frame** (used by all physics): the origin is at the circle center, **+x right, +y up**, units are logical pixels, and angles are in degrees, **counter-clockwise from +x**. So 0° = right (P2 side), 90° = top, 180° = left (P1 side), and 270° = bottom.
- **Canvas frame** (used for rendering): `screen = (cx + x, cy − y)`, where `(cx, cy)` = canvas center plus `arena.center_offset_x/y`.
- `display.rotation` (0/90/180/270) and `display.flip_h/flip_v` (for mirrored or rear projection) are applied only to the final output image. Gameplay never sees them.

### 5.2 Radii

| Name | Default (1080 canvas) | Meaning |
|---|---|---|
| `arena.mask_radius` | 540 | The physical projected circle. Outside it is pure black. |
| `arena.rim_radius` (R) | 520 | Where the goal arcs and walls live. The gap up to the mask holds the rim glow only. |
| `walls.thickness` (t) | 16 | The wall band is drawn inward from R. Its **collision face is at R − t**. |
| `paddles.rim_padding` | 36 | **The distance from R to the paddle's flat back edge (chord)**, measured radially. This is the "platform padding". |
| `center_zone.radius` | 170 | The area where power-up slots live. |

Validate: `R ≤ mask_radius`, `t < R*0.1`, the paddle fits inside the goal arc, and all HUD boxes sit inside `R − hud.safe_margin`. The panel shows warnings and the game clamps the values.

### 5.3 Rim segmentation (editable percentages)

- `walls.top_percent` (default **14%** of 360° = 50.4°), centered at **90°**.
- `walls.bottom_percent` (default **14%**), centered at **270°**. A `walls.link_sizes` toggle keeps the two equal.
- `layout.rotation_deg` (default 0) rotates the whole layout if the installation is turned.
- **The P2 goal arc** runs from `270° + bottom/2` counter-clockwise to `90° − top/2` (it passes through 0°). **The P1 goal arc** runs from `90° + top/2` to `270° − bottom/2` (it passes through 180°).
- Validation: `top + bottom ≤ 60%`, so each goal arc keeps at least 20%.
- Implement `angle_in_arc(angle, start, end)` with correct wraparound and test it at 0°/360°.
- **Wall end caps**: each wall arc ends in a rounded cap, a circle of radius t/2 at radius R − t/2 that is also a collider. This keeps the corner where a wall meets a goal clean and physical.

### 5.4 Paddle track

- The flat back of each paddle sits at `R_back = R − rim_padding`. The paddle center angle θp moves within its player's goal arc, shrunk by `paddles.end_margin_deg` (default 4°) **plus** the paddle's own angular half-width (`asin((w/2)/R_back)`). The paddle never overlaps a wall zone (switch: `paddles.allow_wall_overlap`, default false). The range is recomputed whenever the paddle size changes.
- **Input mapping is from each player's point of view.** P1 stands at the left facing the center (east), so P1's left is the top. P2 stands at the right facing west, so P2's left is the bottom.
  - P1: `u = 0` means the end nearest the **top** wall and `u = 1` the end nearest the **bottom** wall.
  - P2: `u = 0` means nearest the **bottom** wall and `u = 1` nearest the **top** wall.
  - θp = lerp(θ_left_end, θ_right_end, u).

### 5.5 Power-up slots

There are **5 slots** in the center zone (from the PDF). The layout preset `center_zone.layout` can be `pentagon` (default, radius 130, rotation 90°), `cross`, `ring_n`, or `random_in_zone`. Every slot position can be edited individually. Empty slots are drawn as **faint outline rings**, so "five circles in the center" is visible even when they are empty.

### 5.6 HUD anchors

- **Timer**: x = cx, y = (top wall face) + `hud.timer_offset` (default 64 px below the wall face). Font size 80.
- **Scores**: y = (bottom wall face) − `hud.score_offset` (default 90). P1 at x = cx − `hud.score_spread` (110), in P1's color. P2 at x = cx + 110, in P2's color. Font size 110.
- Optional player labels "بازیکن 1" and "بازیکن 2" (default off).
- Use `hud.orientation`: `upright` (default) or `toward_players`. In `toward_players`, player-specific messages rotate ±90° to face each player. The timer always stays upright.
- The control panel's preview flags any HUD box that crosses `R − safe_margin` in red.

```
                 TOP WALL (bounce, no score, % editable)
                    ____==========____
              .--'       ( 0:42 )       '--.
           .-'      ∘                ∘      '-.
         /   P1 track    ∘   ●   ∘    P2 track  \
  P1    |   ◖)              ∘             (◗    |   P2
 GOAL   |   (dome faces center)                  |  GOAL
 (red)   \                                      /   (red)
           '-.        7          5          .-'
              '--.____==========____.--'
                 BOTTOM WALL (bounce, no score)
   ∘ = power-up slots (5)   ● = serve point   ◖) (◗ = paddles sliding along the rim
```

---

## 6. Circular mask and projection output

1. Render all gameplay into an off-screen **logical canvas** (`W×H`, default 1080×1080).
2. Build a **mask overlay** once, and rebuild it only when mask settings change: opaque black outside `mask_radius`, transparent inside, with a **supersampled antialiased edge** (`arena.mask_feather_px`, default 1.5). **Blit it last, after everything** (glow, particles, HUD, countdown, toasts), so nothing can leak.
3. Add an automated test: render frames of each state headless and assert that every pixel beyond `mask_radius + feather` is exactly `(0,0,0)`.
4. Don't draw anything that lies wholly outside the circle (cull it), and keep background effects inside the circle.
5. **Output transform**: scale the logical canvas uniformly to fit the window (letterbox with black), then apply `display.output_scale`, `display.output_offset_x/y`, `display.rotation` and `display.flip_h/v`. Never stretch the circle into an ellipse. Non-square canvases are allowed, with the circle inscribed in `min(W,H)` unless overridden.
6. **Display**: fullscreen by default on `display.index` (the projector can be display 1 while the control panel sits on display 0). `display.vsync`, `display.fps_cap` (default 120), and a windowed mode (`--windowed`, size `display.window_size`). F11 toggles fullscreen. Handle Retina drawable sizes. Hide the cursor in fullscreen.
7. **Calibration overlay** (F2 or a panel button) helps align the projector with the physical circle. It shows a thin bright circle at `mask_radius`, a center crosshair, rings every 10%, angle ticks every 15° with labels, the wall/goal boundary angles, the paddle tracks, and color-test swatches (team colors, good green, bad red). Every calibration value is a live slider.

---

## 7. Physics (fixed timestep, physically convincing)

### 7.1 Loop

- Fixed physics at `physics.hz` (default **240**) with an accumulator. Clamp the frame dt to 0.1 s, run at most 12 steps per frame, and interpolate render positions.
- **Substeps per step**: `n = ceil(|v|·dt / (0.35·r_ball))`, capped at 8. Each substep advances the balls and the paddle pose (interpolated), then resolves **paddles → walls/caps → ball–ball → power-up overlap → goal crossing** using swept tests.
- Seeded RNG (`--seed`) and an injectable `random.Random` everywhere.

### 7.2 Ball

State: `pos`, `vel`, `radius` (14), `owner` (None/P1/P2), `alpha`, `flags` (smart, bull, …), `trail` (a time-based ring buffer), `scored`, `last_paddle_contact` (per paddle), `stall_timer`.

Speed model (no arbitrary velocity hacks):
- `rally_speed` starts at `ball.serve_speed` (420 px/s), steps up to `ball.base_speed` (520) after the first hit, then multiplies by `ball.rally_gain_per_hit` (1.03) on each paddle hit, capped at `ball.rally_cap` (1.6× base). It resets on every serve.
- `target_speed = rally_speed × Π(active effect multipliers)`, clamped to [`ball.min_speed` 300, `ball.max_speed` 1500].
- Each step, |v| eases toward `target_speed` at `ball.speed_response` (6/s), so effects ramp smoothly. **The direction is never changed by speed easing.**

### 7.3 Walls and caps

- If `|p| > (R − t) − r` and the contact angle is inside a wall arc, reflect: `n = p/|p|`, `v ← v − (1+e)(v·n)n` (`walls.restitution` default 1.0), then push the ball back to `R − t − r − ε`. Emit `WallBounce`, which drives a ripple effect and a sound.
- End caps: circle–circle reflection.
- Inside a goal arc there is no rim collision. The ball can leave (see the goal rules).

### 7.4 Anti-stall (important for circles)

- A ball bouncing straight up and down between the top and bottom walls would loop forever. After every wall bounce, enforce `physics.min_axis_ratio` (default 0.25), where `|v·a| / |v| ≥ ratio` and **a is the play axis** (the unit vector from the P1 goal center to the P2 goal center, rotated with the layout). If the ratio is too low, rotate v toward the side it is already heading (choose randomly if exactly 0).
- `physics.stall_timeout_s` (6): if no paddle touch happens for this long, gently steer the ball toward a goal side (or re-serve, depending on `physics.stall_action`).

### 7.5 Paddle collision model (the core of the game)

**Shape.** Each paddle is a circular **cap** (a segment of a circle), defined by:
- chord width `w = paddles.width × size_multiplier` (default width 130),
- depth `d = (w/2) × paddles.shape_ratio` (1.0 makes a true **semicircle**, the default, and smaller values make it flatter),
- cap circle radius `ρ = (w²/4 + d²) / (2d)`, with its center Q at a distance `ρ − d` **behind** the chord (toward the rim),
- chord midpoint `M = R_back·(cos θp, sin θp)`, facing `f = −M/|M|` (toward the arena center), dome apex `M + f·d`, `Q = M − f·(ρ − d)`,
- the player's right-hand direction `rgt = (f.y, −f.x)`,
- small rounded chord corners (`paddles.corner_radius` 4).

**Detection.** Compute the closest point on the paddle outline (the cap arc together with the chord) to the ball center B. Use a point-in-shape test to handle penetration. A collision happens when `dist < r` or B is inside. The normal `n` points from the surface to B. On the dome, this equals `(B − Q)/|B − Q|`. The back face (behind the chord) is a real collider too, pushing the ball toward the goal.

**Response.** The paddle is kinematic (infinite mass) and moves at `v_p` = its tangential velocity along the track.
1. `v_rel = v_ball − v_p`. Respond only if the two are approaching: `v_rel·n < 0`.
2. Physical reflection: `v_rel' = v_rel − (1 + e)(v_rel·n)n` (`paddles.restitution` 1.0). Then add `v_p × paddles.velocity_transfer` (0.35). The result is `d_phys`.
3. **Contact offset**: `s = clamp(signed_angle(f → n, positive toward rgt) / α, −1, 1)`, where `α = asin((w/2)/ρ)` is the cap's half-angle.
4. **Arcade steering** (tunable): `d_aim = rotate(f, s × paddles.max_aim_angle_deg)` (60°). Then `d = slerp(d_phys, d_aim, paddles.aim_blend)` (0.4). An `aim_blend` of 0 is pure physics and 1 is pure arcade.
5. **Never backward**: for dome hits, clamp the angle between d and f to `paddles.max_outgoing_angle_deg` (72°), unless `paddles.allow_backward` is set. Back-face hits stay purely physical.
6. Speed: `speed_out = clamp(max(|v_in|, rally_speed) × paddles.hit_speed_gain + |v_p| × paddles.paddle_speed_to_ball, min, max)`. Then `v = d·speed_out`.
7. Separate the ball from the surface by `r + ε`, set `owner = player`, and record the contact time. Apply a per ball/paddle cooldown of `paddles.hit_cooldown_ms` (60) so jitter cannot cause double impulses.

Why this feels right: on a dome, the normal turns with the contact point, so a hit left of center physically deflects the ball left. `shape_ratio`, `aim_blend`, `max_aim_angle` and `max_outgoing_angle` let you tune anything from forgiving to "pro".

**Tunnelling.** Move the paddle in the same substeps as the ball. Limit its speed (`paddles.max_speed_deg_s`). If a size change or a fast move puts the paddle over a ball, resolve the overlap as a gentle push without changing the owner.

### 7.6 Ball–ball (multi-ball)

Equal-mass elastic collision (`physics.balls_collide`, default true), with separation. Owners don't change.

### 7.7 Goal detection

For each substep: if `|p_prev| ≤ R` and `|p| > R`, intersect the segment with the circle to get the crossing angle φ. If φ is in the P1 arc, emit `Goal(scorer=P2, conceded=P1, ball_id)`. If φ is in the P2 arc, emit `Goal(scorer=P1, conceded=P2)`. If φ is in a wall arc (which shouldn't happen), reflect and log a warning. Mark the ball `scored` so it stops colliding and fades out. **A goal counts only once, never during the goal pause, and never after the match has ended.** A ball nobody has touched still scores: if you miss the serve, your opponent scores.

---

## 8. Paddles (movement and size)

- The input gives a target `u ∈ [0,1]` (or "not present"). The paddle follows in one of two modes. In `direct` mode (for keyboard and sensors that are already filtered), it follows with limits on max angular speed and acceleration. In `spring` mode (critically damped), it follows with `paddles.follow_stiffness`.
- The paddle's tangential velocity is measured from its actual motion. It feeds the collision response and the Smart Move.
- **Size effects** ease over `paddles.size_transition_s` (0.3 s) and are clamped to [`paddles.min_width` 60, `paddles.max_width` 260]. Stacking expand and shrink on the same player follows `paddles.size_stacking` = `multiply` (default) or `replace`.
- **Absent player**: hold the last position for `input.hold_s`, then glide to the middle of the range. Draw the paddle at 40% opacity with a "step in" footprint icon and the text "وارد زمین شوید".
- Future 2D: keep a `radial_offset` in the paddle model (0 for now). Setting `paddles.radial_mode` to `fixed_track` (now) or `follow_xy` (later, when LiDAR gives foot depth) lets a player step forward.
- Each player has their own copy of every paddle setting. The panel has a "link players" toggle that mirrors P1 to P2, except color and keys.

---

## 9. Ownership and trails

- Ball look: a hot white core, a **halo in the owner's color**, and a 2–3 px **ring in the owner's color**. A neutral ball (before the first touch) uses `colors.neutral_ball` (#E8F4F8).
- **The trail length is set in time**, not points (`trails.duration_s`, 0.35 s), so it looks the same at any speed or fps. It is a tapered polyline (from 0.9× ball diameter down to 0) with alpha falling from 0.9 to 0, drawn in two passes: an additive glow pass (wide, faint) and a core pass.
- `trails.color_mode` is `current_owner` (default: the whole trail switches to the new owner with a 0.12 s cross-fade flash) or `history` (each segment keeps the color it was drawn in).
- On a paddle hit, emit a spark burst and a small shock ring in the **new owner's color** at the contact point.
- Effect overlays sit **on top of** the owner color and never replace it: speed-up adds a flame flicker and a 1.6× longer trail, chaos a violet sine "wobble" overlay, a smart hit a gold/white double trail with sparkles, dim lowers the alpha but keeps the owner ring, and bull market adds a gold shimmer.
- When an orb is collected: a burst in the collector's color plus the orb's class color, then the icon **flies to its target** (the collector's paddle for expand, the opponent's paddle for shrink, around the ball for ball effects), and then a Persian toast appears on the collector's side.
- Multi-ball: every ball has its own owner, trail and effects.

---

## 10. Match flow, scoring and serve

### 10.1 State machine

`BOOT → ATTRACT → INTRO → COUNTDOWN → SERVE → PLAYING ⇄ GOAL → SERVE … → FINAL → RESULT → ATTRACT`, with `PAUSED` (overlay) and `CALIBRATION` (overlay) available from any state.

- **Start trigger** (`match.start_mode`): `operator_key` (Space/Enter or the panel's Start button, the default), `auto_when_both_present` (both inputs present for 1.5 s, for LiDAR later), or `auto_loop` (demo).
- **ATTRACT**: AI vs. AI demo play at 60% opacity, the title "هاکی بازار / MARKET HOCKEY", an optional logo, the prompt "برای شروع، روبه‌روی هم بایستید", and a gentle ambient background.
- **INTRO** (0.8 s): the rim draws itself on, sweeping from the top wall around both sides. The walls light up, the goal arcs glow red, and each paddle materializes in its team color.
- **COUNTDOWN**: "آماده‌اید؟", then **3 → 2 → 1 → "شروع!"** (`countdown.beat_s` 0.8). Each number pops (scale 1.6 → 1.0 with an elastic ease) with a ring shockwave from the center and a **background flash** in alternating team colors (intensity ≤ `fx.flash_max_alpha` 0.35). Particles stream toward the center while the ball charges up (its glow grows). On "GO" there is a white flash (0.5 alpha, 120 ms) and the ball launches. A beep plays on each beat. **The timer does not run during the countdown.**
- **SERVE**: the ball sits at the serve point for `serve.delay_s` (0.7) with a pulsing ring and **telegraph chevrons** pointing at the receiver, then launches at `ball.serve_speed`.
- **GOAL**: add the points, slow motion (time scale 0.15 for 0.25 s), then freeze. A red pulse runs along the crossed goal arc, a shockwave starts from the crossing point, the scorer's score pops (1.0 → 1.5 → 1.0 with a glow), "گل!" appears in the scorer's color, and there is a small shake (≤ 6 px, 200 ms, **inside the mask only**). After `match.goal_pause_s` (1.4), check the end conditions, then SERVE.
- **Final seconds**: in the last 10 s the timer pulses and turns coral (#F3716D) and ticks each second. In the last 5 s it is bigger. The background tempo rises.
- **FINAL**: the banner "پایان معاملات!", the balls fade and stop, effects end, and the screen freezes for 1.5 s.
- **RESULT**: the winner's half fills with a wash of their team color, a crown or bull icon appears above the winner's score, then "برنده" or "مساوی", the large final scores, and the slogan "بازار همیشه در حرکته؛ آماده‌ی تغییر باش.". After `match.result_s` (6) it returns to ATTRACT, or waits for the operator if `match.result_wait_for_operator` is set.

### 10.2 End conditions and scoring

- `match.timer_enabled` (true) with `match.duration_s` (60). `match.score_limit_enabled` (true) with `match.score_limit` (7). Whichever comes first ends the match.
- `match.timer_format`: `seconds` (default, "60" … "0"), `mm:ss`, or `auto`. Latin digits only.
- `match.timer_runs_during_goal_pause` (false).
- Ties: `match.tie_rule` is `draw` (default) or `golden_goal` (play continues, the timer shows "+", and the next goal wins with "گل طلایی!").
- `scoring.points_per_goal` (1). Multipliers come from effects (bull market). The optional `scoring.smart_hit_points` defaults to 0.
- **Multi-ball goals**: with `scoring.multiball_policy` = `end_rally` (the default), any goal clears all balls and serves a single ball. With `continue`, the remaining balls play on and the serve waits for the last ball.
- Append every match to `logs/matches.csv` (time, duration, scores, winner, power-ups collected per player, smart hits). This is useful for exhibition stats.

### 10.3 Serve rules

- First serve: `serve.first` is `random` (the default), `p1`, `p2`, or `alternate` across matches.
- After a goal: `serve.after_goal` is `toward_conceder` (**the default and the user's rule**), `toward_scorer`, `random`, or `alternate`.
- Direction: aim from the serve point toward the receiver's goal center, with a random offset of ±`serve.angle_variation_deg` (25). **Constrain the ray so it lands inside the receiver's paddle range** (with a margin) and never at a wall. Optional `serve.aim_near_paddle` targets the receiver's current paddle position ± the variation.
- Serve point: `serve.position_x/y` (the center by default).

### 10.4 Match phases (from the PDF timeline, editable)

`phases.timing` is `relative` (the default: fractions of the duration) or `absolute` (seconds). The defaults for 60 s:

| Phase | 60 s match | Allowed power-ups | Spawn interval × |
|---|---|---|---|
| Warm-up | 0–10 s | none | — |
| Early | 10–25 s | expand, shrink, speed_up (+ slow_down if enabled) | 1.0 |
| Mid | 25–45 s | all enabled | 1.0 |
| Peak | 45–55 s | all enabled | 0.6 (more frequent) |
| Final | 55–60 s | no new spawns | — |

Matches decided by score limit only use a nominal 60 s timeline.

---

## 11. Power-up system (modular, easy to add or remove)

### 11.1 Framework

- `powerups/base.py` defines `class PowerUp`. Each type is a class with: `id`, `display_name`, a `schema` (its own settings, merged into the global schema under `powerups.types.<id>.*`), and `on_collect(ctx, ball, collector)`, which returns `Effect` objects.
- `class Effect` has `target` (`collector_paddle`, `opponent_paddle`, `ball`, `all_balls`, `player`, or `global`), `duration_s`, `exclusive_group`, `stacking`, `on_start`, `on_update(dt)`, `on_end`, `on_goal`, and `multipliers()`.
- `powerups/registry.py` **auto-discovers** every module in `powerups/types/`, which registers itself with `@register_powerup`. **Adding a power-up means dropping in one file**: it appears automatically in the spawner, the JSON and the control panel (because the panel is schema-driven). **Removing one** means setting `enabled: false` (or deleting the file). Config entries for missing types are kept but ignored, with a warning, and never crash the game.
- `EffectManager` tracks the active effects. When an effect expires it **restores the exact previous state**. Expired effects can never linger.
- **Exclusive groups**: `ball_speed` (speed_up versus slow_down) and `paddle_size:<player>`. The PDF rule is that opposite events never run at the same time, so the policy `powerups.exclusive_policy` = `replace` (the default) ends the old effect. The spawner also avoids spawning an orb whose group conflicts with an active effect (`powerups.avoid_conflicting_spawns`, true).
- `stacking` per type: `refresh` (the default: restart the duration), `extend`, `stack` (multiply up to `max_stack`), or `ignore`.

### 11.2 Collection rules

- The ball's **owner (last toucher) is the collector**.
- `powerups.unowned_ball_collects` (default **false**): a fresh serve passes through orbs harmlessly and the orb wobbles. This also stops the serve from triggering a center orb.
- The overlap test is swept (segment-to-point distance < `orb_radius + ball_radius`).

### 11.3 Visual language

- Orbs have a circular badge with a procedural vector icon (drawn with pygame primitives, crisp at any size). The class color sits on the rim and glow:
  - **good = green `#39E46F`** (deliberately lime, so it is not confused with the turquoise P1 color),
  - **bad = red `#FF3B3B`**, with a dashed hazard rim and a slow 1.5 Hz warning blink,
  - **neutral = violet `#9B6BFF`**.
- Life cycle: a spawn animation (scale-in over 0.35 s with a ring flash), an idle bob and slow rotation, a **lifetime ring** that drains around the orb, and a 0.3 s despawn fade.
- When a file `assets/icons/<id>.png` exists, use it instead of the procedural icon, so designers can replace icons.
- When an effect is active, show a small icon with a radial countdown next to the affected paddle (or the ball). An expanded paddle gets a green pulsing outline, and a shrunk paddle gets a red crackle on its edge.
- `main.py --export-icons DIR` writes every icon to PNG, and the control panel shows those previews.

### 11.4 Catalog (build all of them; 1–6 enabled by default)

Every number below is a setting. "Toast C" is shown on the collector's side, and "Toast O" on the opponent's side.

| # | id | Class | Default on | Effect | Defaults | Icon | Persian toasts |
|---|---|---|---|---|---|---|---|
| 1 | `expand` | **good** | ✅ | **Collector's** paddle grows | ×1.5 width, 8 s, refresh | a paddle bar with **outward** arrows ◀▬▶ | C: «بالکرت بزرگ شد!» |
| 2 | `shrink` | **good** | ✅ | **Opponent's** paddle shrinks | ×0.6, 8 s, min width respected | a paddle bar with **inward** arrows ▶▬◀ and a small "opponent" marker | C: «بالکر حریف کوچک شد!» · O: «بالکرت کوچک شد!» |
| 3 | `speed_up` (High Volatility) | **good** | ✅ | The ball speeds up (`scope`: this_ball / all_balls), with a flame trail | ×1.4, 6 s, group ball_speed | a lightning bolt with up-chevrons | «نوسان بازار افزایش یافت!» |
| 4 | `chaos` (Random path) | **good** | ✅ | The ball's direction turns by a random angle. `mode` is `instant` (default) or `wobble` (a sinusoidal curve for `wobble_s`). The ball must keep heading to the **opponent's half**, satisfy min_axis_ratio, and never aim straight at a wall. | ±20°…55°, wobble 2.5 s | crossed shuffle arrows | «بازار غیرقابل پیش‌بینی شد!» |
| 5 | `double_ball` (Trading Volume) | **good** | ✅ | The ball splits into 1 extra ball (±`split_angle` 18°), both owned by the collector. Extra balls fade after `extra_ball_lifetime_s`. There are never more than `max_balls`. Spawn only at valid, non-overlapping positions. | +1 ball, 10 s, max 3 | two overlapping circles | «حجم معاملات افزایش یافت!» |
| 6 | `trajectory_reveal` (Market Analysis) | **BAD** | ✅ | For `duration_s`, **the collector's opponent** sees the predicted path of every ball heading toward them: where it will meet their paddle and how it will bounce off (§12). | 7 s | a dotted curved path ending in a target crosshair | C: «مسیرت لو رفت!» · O: «مسیر حرکت را تحلیل کن!» |
| 7 | `slow_down` (Market Stability) | **bad** (slowing my shot helps the receiver) | ❌ | The ball slows down | ×0.7, 6 s, group ball_speed | a calm wave with a down-chevron | «بازار وارد دوره‌ی آرام شد.» |
| 8 | `dim_ball` (Market Correction) | **good** | ❌ | The ball dims to 0.35 alpha (**never below `min_ball_visibility` 0.25**). The owner ring stays visible. | 5 s | a half-filled circle (moon) | «بازار در مسیر اصلاح قرار گرفت.» |
| 9 | `shield` (Circuit Breaker, حد نوسان) | **good** | ❌ | A glowing barrier arc covers the collector's goal (by `coverage_percent`). It blocks **one** ball, then shatters, or expires. | 8 s, 100% | a shield with a pause bar | «حد نوسان فعال شد!» |
| 10 | `bull_market` | **good** | ❌ | The collector's **next goal** within the window counts ×2. Their ball shimmers gold. This nods to the Mofid bull logo. | ×2, 12 s | bull horns / "×2" | «بازار صعودی! گل بعدی ×2» |

Common per-type settings: `enabled`, `weight`, `class` (good/bad/neutral; this decides the default color), `color_override`, `duration_s`, the strength parameters, `stacking`, `max_stack`, `exclusive_group`, `cooldown_s` (no re-spawn of the same type for this long), `allowed_phases`, `toast_collector_fa`, `toast_opponent_fa`, `sound`, and `icon`.

### 11.5 Spawner

`powerups.spawn_interval_min/max_s` (4 / 7), multiplied by the phase multiplier. `powerups.max_active_orbs` (2), `powerups.max_bad_orbs` (1), `powerups.orb_radius` (30), `powerups.orb_lifetime_s` (9), and `powerups.min_distance_from_ball` (120). Pick a free slot at random. The type is a weighted random choice among types that are enabled, allowed in the current phase, not cooling down and not conflicting. `powerups.no_repeat` (true) prevents the same type twice in a row. A debug action can force-spawn any type (from the panel, or the number keys in debug mode).

---

## 12. Trajectory prediction and ghost ball

- `prediction/trajectory.py` exposes the pure function `predict(ball, arena, paddles, params) -> Prediction(points, contact_point, contact_time, outgoing_dir, valid)`. It uses **the same collision functions** on a **copied** lightweight state (walls, caps, other effects' multipliers; it ignores other balls). It looks ahead at most `prediction.max_time_s` (2.5) and `prediction.max_bounces` (4). **It never mutates the real state**, and a test asserts this.
- It stops when the ball reaches the receiver's contact band (`|p| ≥ R_back − d − r` inside the receiver's arc) or crosses a goal.
- **Bounce preview**: if the receiver's paddle *at its current position* would intercept, simulate that hit and show the resulting outgoing direction (solid arrow). Otherwise show the bounce as if the paddle were centered on the contact point (dashed arrow, meaning "if you are here"). Because it updates continuously, the receiver sees how stepping left or right changes their return.
- Update at `prediction.hz` (30), and immediately after any collision or effect change.
- **Look: tiny and cute.** Small dots (3 px, every 14 px) in a **marching animation**, with alpha fading along the path. A **ghost ball** (a ring the size of the ball, 40% alpha, gently pulsing) sits at the contact point, with a tiny tick on the paddle track and a short **70 px outgoing arrow** with a chevron head. Colors: the receiver's team color with a white core. It is shown only during PLAYING and is clipped by the mask.
- `prediction.debug_always_on` (draws predictions for every ball in the debug overlay).

---

## 13. Smart Move (ضربه‌ی ویژه, from the PDF)

- A hit counts as smart when the paddle's tangential speed at contact is at least `smart.min_paddle_speed` (600 px/s) **and** the paddle crossed that speed within `smart.window_ms` (150 ms) before contact (a timed flick), **and** the flick direction matches the deflection side.
- Reward: ball speed ×`smart.speed_bonus` (1.12, capped), the ball flashes gold (the owner ring stays), a double gold/white trail with sparkles for 1.2 s, the toast «واکنش به‌موقع!» near the hitter, and a sound. Optional `scoring.smart_hit_points`. Per-player cooldown is `smart.cooldown_s` (2).
- `smart.enabled` defaults to true. With the keyboard, tapping a direction key right before contact triggers it.

---

## 14. Visual design

### 14.1 Palette (all editable; brand values from the Mofid brand book)

| Token | Default | Note |
|---|---|---|
| outside mask | `#000000` | not editable |
| arena background | radial gradient `#03141C` → `#062A3A` | derived from brand Dark Blue `#004C6A`; kept dark for projector contrast |
| arena lines (rim, dashed center line, center ring, slot rings) | `#1F7A99` @ 50% | |
| **P1 team** | **Turquoise `#00A796`** | brand primary |
| **P2 team** | **Purple `#832C73`** | brand secondary |
| goal arcs | brand red `#F3716D`, 6 px line plus a soft glow | they flash on a goal |
| bumper walls | `#CFE8EE` band at 85% with slow-moving diagonal hatching in `#004C6A` | they must read as **solid and safe** |
| good / bad / neutral | `#39E46F` / `#FF3B3B` / `#9B6BFF` | |
| text | `#FFFFFF`; timer in the final seconds `#F3716D` | |

- **Projection boost**: brand colors are dark on a projector. For glows, trails and halos, derive a lifted variant (raise HSV value and saturation by `colors.projection_boost`, default 0.35) and keep the hue. Fills use the exact brand value.
- **Confusability check**: the panel computes CIE76 ΔE between the team colors and the good/bad/neutral colors, and warns below 25. The trail owner must never be confused with a power-up class.

### 14.2 Typography

- Copy `IRANSansX-{Light,Regular,Medium,Bold,ExtraBold,Black}.ttf` from `/Users/dayhimit/Downloads/Front/asset/fonts/` into `assets/fonts/`.
- `fonts.persian` = IRANSansX-Bold (toasts and banners), `fonts.persian_title` = IRANSansX-Black, `fonts.digits` = IRANSansX-Black (its ASCII digits are Latin glyphs). All of these can be selected in the panel from the files in `assets/fonts/`.
- The brand's primary font is **Dana**, which is not available yet. If `Dana-*.ttf` is dropped into `assets/fonts/`, it becomes selectable. The README notes that the brand book reserves main headings for Dana.
- **Latin digits everywhere**: `latin_digits(s)` maps ۰–۹ and ٠–٩ to 0–9, and it runs on every string before rendering. Numbers are rendered as their own runs, so bidi never reorders them incorrectly (for example «بازار صعودی! گل بعدی ×2»).

### 14.3 Persian text rendering (must be correct)

Plain Pygame does not shape Arabic script by default. Implement `render/text.py` with these backends:
1. `pygame` (pygame-ce): if the `Font` has `set_script` and `set_direction`, use `set_script("Arab")` and `set_direction(pygame.DIRECTION_RTL)`.
2. `reshaper`: `arabic_reshaper.reshape()` followed by `bidi.algorithm.get_display()`, then render.

`text.shaping_backend` is `auto`, `pygame` or `reshaper`. `main.py --selftest-text` renders «واکنش به‌موقع!», «حجم معاملات افزایش یافت!», «بازار همیشه در حرکته؛ آماده‌ی تغییر باش.» and «گل بعدی ×2» to PNGs with each backend. **Look at them**: letters must be joined, the order must be right-to-left, the ZWNJ (U+200C in «به‌موقع») must break the join without drawing a box glyph, and the digits must be Latin. Make `auto` choose the backend that passes. **Cache** rendered text surfaces, keyed by (text, font, size, color); never re-render static text every frame.

### 14.4 Layers (back to front)

background → ambient chart → arena lines and slots → walls and goal arcs → HUD → orbs → trails → balls → paddles → particles and shockwaves → toasts and banners → countdown overlay → debug and calibration overlays → **mask (last)**.

- Static layers (background, rim, walls, goal arcs, slot rings, mask) are **pre-rendered and cached**. A cache is invalidated only when a config path it depends on changes.
- Glow comes from cached radial-gradient sprites per (color, radius), blitted with `BLEND_ADD`. Never blur the full screen each frame.
- **Ambient market chart** (`fx.ambient_chart`, opacity ≤ 0.08): a faint line or candlestick chart drifting inside the circle. After a goal it ticks up in the scorer's color.
- Ripples on wall bounces, shock rings on hits, and a particle pool capped at `fx.max_particles` (600).
- **Photosensitivity**: at most 3 flashes per second, flash alpha ≤ 0.5, and `fx.reduce_flashing` disables strong flashes.

### 14.5 Toasts

Player toasts appear in that player's half at about 0.55R, hold for 1.6 s, slide and fade, are capped at 2 per side, and respect `hud.orientation`. Global market events also show a central banner. All texts are settings under `text.*` (so they can be edited in the panel). Entry fields are right-justified for RTL.

---

## 15. Audio

- Events: paddle hit (pitch rises with speed), wall bounce, good orb, bad orb, effect end, goal, countdown beeps (3 short and 1 long), final-10 s tick, match end, and smart hit.
- `tools/make_placeholder_sounds.py` synthesizes WAVs using only the standard library (`wave`, `math`, `struct`), so the game ships with sounds. Real files can replace them.
- Settings: `audio.master`, per-category volumes, and `audio.mute`. The same sound cannot retrigger within 40 ms. If the mixer fails to start, the game runs silently and logs it.

---

## 16. Settings system (schema-first, JSON, live)

### 16.1 The schema is the single source of truth

`config/schema.py` declares **every** parameter with helpers, for example:
```python
F("ball.base_speed", 520, min=150, max=2000, step=10, unit="px/s", tab="Ball & Physics", group="Speed",
  label="Base speed", help="Speed after the first paddle hit, before rally gain and effects.", live=True)
C("players.p1.color", "#00A796", tab="Colors", label="Player 1 color")
B("match.timer_enabled", True, ...)
E("serve.after_goal", "toward_conceder", options=["toward_conceder", "toward_scorer", "random", "alternate"], ...)
K("input.keyboard.p1_left", "a", ...)                     # key binding
S("text.toast.expand_collector", "بالکرت بزرگ شد!", rtl=True, ...)
L("center_zone.slots", [...], item=Vec2(...), ...)          # list editor
```
Power-up types contribute their own entries. Nothing that affects gameplay, layout, visuals, audio, input or timing may be hardcoded outside the schema. `python -m market_hockey.config.generate_defaults` writes `config/defaults.json`.

### 16.2 Files and safety

- `config/settings.json` is the full nested config, human-readable, with 2-space indentation, UTF-8 and `ensure_ascii=False` so Persian stays readable. It includes `schema_version` and `saved_at`.
- Load: start from the defaults, then merge the user file and validate each value (coerce types, clamp to the range, check enum values). Log a warning for each fix. **Unknown keys are preserved**, flagged, and never crash the game. Migrations run by `schema_version`.
- **Atomic save**: write `settings.json.tmp`, flush and `fsync`, then `os.replace`. Copy the previous file to `settings.prev.json`. A corrupt or missing file falls back to the defaults with a visible warning.
- Presets in `config/presets/`: `default`, `kids_easy` (slower ball, bigger paddles, aim_blend 0.6), `pro` (faster ball, aim_blend 0.15), and `calibration`.
- Each setting has `live=True`, applied instantly, or `live=False`. A `live=False` setting is applied at the next match or on "Apply display settings", and the panel shows an orange "restart" badge.

### 16.3 Live link (control panel ⇄ running game)

- **UDP on 127.0.0.1 only.** The game listens on `live_link.game_port` (9201) and the panel on `live_link.panel_port` (9202). Both use non-blocking sockets that the game polls once per frame, so no threads are needed.
- Panel → game:
  - `{"type":"set","path":"ball.base_speed","value":600,"seq":12}`
  - `{"type":"set_many","values":{...}}`
  - `{"type":"command","name":"start_match|pause|resume|reset_match|spawn_powerup|spawn_ball|toggle_debug|toggle_calibration|apply_display|reload_from_disk|quit","args":{...}}`
  - `{"type":"hello"}`
- Game → panel: `{"type":"state","fps":…,"state":"PLAYING","time_left":…,"scores":[3,5],"balls":2,"effects":[…],"warnings":[…]}` at 4 Hz, plus `{"type":"ack","seq":12}`.
- The game **validates every incoming value against the same schema** and applies it on the main thread at the start of the next frame. Slider drags are throttled to 30 messages per second at most.
- Live edits are **not saved until Save is pressed**. The panel shows "● unsaved changes", and "Revert to saved" re-sends the saved file.
- Each side works without the other: the game runs from `settings.json` without the panel, and the panel edits the file when the game is offline.

---

## 17. The Tkinter control panel (on its own window or monitor; make it look good)

- The window title is "Market Hockey: Control Panel". It is 1280×820 and resizable, with a dark theme in brand colors (background `#0B1F2A`, cards `#11303F`, accent turquoise `#00A796`, warnings coral `#F3716D`). It works on macOS (Command-key shortcuts) and Windows.
- **Top bar**: the live-link status pill ("● Connected to game" or "○ Offline: editing file"), then the buttons **Launch Game**, **Start Match**, **Pause/Resume**, **Reset Match**, **SAVE** (the primary turquoise button, ⌘/Ctrl+S), **Save as Preset…**, **Load Preset ▾**, **Revert to Saved**, and **Reset All to Defaults** (which asks for confirmation).
- **Left sidebar**: a search box (⌘/Ctrl+F filters every setting by label or key) and these tabs:
  - Display & Projection
  - Arena & Walls
  - HUD & Text
  - Match & Scoring
  - Serve
  - Ball & Physics
  - Paddles (P1 / P2 with "link players")
  - Trails & Ownership
  - Power-ups (an overview table plus a page per type, generated from the registry)
  - Phases (a timeline row editor)
  - Trajectory
  - Smart Move
  - FX & Countdown
  - Colors
  - Audio
  - Inputs (sources, keyboard bindings, network, filters, calibration)
  - Live Link
  - Advanced / Debug
- **Setting rows**, generated from the schema, contain:
  - the label with an ⓘ tooltip,
  - a **slider** (`ttk.Scale` that snaps to the step),
  - an **exact-value field**. It validates on Enter or when focus leaves. An invalid value gets a red border and is not applied.
  - the unit,
  - a ↺ reset-to-default button,
  - a live or restart badge.

  Booleans are toggle switches. Colors are a swatch, a hex field and a **Pick…** button (`tkinter.colorchooser`), with ΔE warnings. Enums are comboboxes. Persian strings use right-justified entries. Key bindings use a "Press a key…" capture button. Lists use small row editors.
- **Right panel, Live Preview**: a Tk Canvas mini-map (about 360×360) that redraws instantly as values change, even with the game offline. It shows the mask, the rim, the **wall arcs with their percentages**, the red goal arcs, the paddle tracks with the current paddle sizes and padding, the 5 slots, the serve point, and the timer and score boxes. Anything out of bounds is drawn in red.
- **Telemetry** (when connected): fps, state, time left, scores, active effects, and input values per player. There are also a **Spawn power-up** dropdown with a button, plus Calibration and Debug toggles.
- **Footer**: "Saved 14:02:11 → config/settings.json", a count of validation warnings, and an undo stack (⌘/Ctrl+Z) for recent edits.
- Settings are **generated from the schema**, so a new power-up file or a new schema key appears in the panel with no UI code. Add a test that every schema key gets a widget.

---

## 18. Modular input system

### 18.1 Contract

```python
@dataclass
class PlayerSample:
    present: bool                 # tracked / someone is there
    u: float | None               # 0..1 along this player's own arc; 0 = player's LEFT end
    confidence: float = 1.0       # 0..1
    timestamp: float = 0.0        # time.perf_counter()
    xy: tuple[float, float] | None = None   # optional normalized arena point (-1..1, rim = 1), for future 2D
    source: str = ""

class InputAdapter(Protocol):
    name: str
    def start(self) -> None: ...
    def handle_event(self, event) -> None: ...      # pygame events; only the keyboard/mouse adapters use them
    def poll(self, now: float) -> dict[str, PlayerSample]: ...   # keys "p1", "p2"
    def stop(self) -> None: ...
```

`InputManager` picks a source per player (`input.p1.source` / `input.p2.source`: `keyboard | ai | mouse | network | replay`). It applies the filters and the presence policy, then passes `u` and `present` to the engine, which maps `u` to θp (§5.4).

### 18.2 Adapters

- **KeyboardAdapter** (now): **P1 = A/D, P2 = ←/→**. `input.keyboard.direction_mode` is `player_view` (the default: A and ← move toward *that player's* left, per §5.4) or `screen_view` (A and ← move up on screen for both players), with a per-player `invert` option. W/S and ↑/↓ can be enabled as alternates for screen up and down. The adapter integrates a virtual `u` with `max_speed` (1.6 u/s), `accel` and `friction`, so the keyboard behaves like a position sensor. Every key can be rebound, and both players' keys can be held at the same time.
- **AIAdapter**: used for attract mode, for single-player against the CPU (`input.p2.source = ai`), and for soak tests. It uses `prediction/` with a reaction delay, aim noise and a speed limit, all set by a difficulty slider.
- **MouseAdapter** (debug): the mouse angle around the center drives the selected player.
- **NetworkAdapter** (the LiDAR and CCTV pose path; implement and test it now with `tools/send_fake_tracking.py`): a non-blocking UDP JSON listener on `input.network.port` (9100). It accepts two message types:
  ```json
  {"type":"tracking","t":1712345678.12,"source":"lidar",
   "players":[{"id":"p1","x":-0.62,"y":0.10,"conf":0.93},{"id":"p2","x":0.58,"y":-0.05,"conf":0.88}]}
  {"type":"blobs","t":1712345678.12,"blobs":[{"x":-0.6,"y":0.1,"conf":0.9},{"x":0.55,"y":0.0,"conf":0.8}]}
  ```
  With `blobs`, the adapter assigns players by region: it picks the blob in each player's angular region that is closest to the rim and above `min_confidence`. Points arrive in normalized arena coordinates. If a sender uses sensor coordinates instead, apply `input.network.homography` (3×3). The Inputs tab has a **4-point calibration tool**: click the projected markers and enter the sensor points. Points are converted to an angle and then to `u` within the player's range, and `xy` is kept for future 2D. The README documents how any tracker sends this, whether a LiDAR SDK, TouchDesigner (which the team uses), or a CCTV pose estimator such as MediaPipe or YOLO-pose running as a **separate process** using the ankle keypoints. Never import heavy vision models into the game.
- **ReplayAdapter**: records inputs to JSONL and plays them back, for reproducing bugs and testing sensors offline.

### 18.3 Filters and presence (`inputs/filters.py`)

- Dead zone, `min_confidence` (0.4), and spike rejection: `max_jump_u_per_s`, unless the jump lasts `jump_confirm_ms`.
- A **One Euro filter** (`min_cutoff` 1.0, `beta` 0.02, `d_cutoff` 1.0) for jittery sensors.
- Tracking loss: hold the paddle for `lost_hold_s` (0.5). After `absent_timeout_s` (3), the player counts as absent (the paddle dims and shows "وارد زمین شوید").
- With `auto_when_both_present`, presence starts the match.

---

## 19. In-game hotkeys (configurable; most are disabled in `exhibition_mode`)

| Key | Action |
|---|---|
| Space / Enter | start match, or skip the result screen |
| P | pause or resume |
| R (hold 0.5 s) | reset match |
| F1 | open the control panel (spawns `settings_app.py` if it isn't running) |
| F2 | calibration overlay |
| F3 | debug overlay: fps, physics Hz, colliders, normals, contact offsets, predictions, input values |
| F11 | toggle fullscreen |
| 1–0 (debug only) | force-spawn power-up types; B spawns an extra ball |
| Esc twice within 1.5 s | quit |

`exhibition_mode` (default false) hides the cursor and disables the debug keys, except for a secret combo (Ctrl+Shift+D).

---

## 20. Performance and reliability

- Target **≥ 60 fps at 1080×1080 on an M-series MacBook**, with physics at a steady 240 Hz and up to 3 balls. Profile with `cProfile` and record the numbers in the README.
- Reuse surfaces: no per-frame allocation of full-screen alpha surfaces. Call `convert()`/`convert_alpha()` on everything. Particles come from a fixed pool, trails use bounded buffers, and caches are bounded too.
- Nothing blocks the main loop: sockets are non-blocking and file saves happen in the panel.
- Logging goes to `logs/market_hockey.log` (rotating). Exit gracefully on Ctrl+C or window close. Missing optional assets only produce warnings.
- **Soak test**: run AI against AI for 30 simulated minutes, accelerated and headless. Assert there are no exceptions, NaN values or stuck balls, that memory stays stable (`tracemalloc`), and that scores and the match flow keep cycling.

---

## 21. Tests (pytest, headless: `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`)

- **Geometry**: arcs computed from the percentages, membership across the 0° wrap, layout rotation, the u↔θ mapping for both players (P1 u=0 near the top, P2 u=0 near the bottom), and recomputing the paddle range when the size changes.
- **Walls**: reflection with no score, end caps, and the vertical ping-pong case (a ball fired straight up must reach a goal side within N bounces).
- **Goals**: the left arc gives P2 +1 and the right arc gives P1 +1. Detection works at maximum speed. A crossing counts exactly once. No goals count during GOAL or after FINAL. An unowned ball still scores.
- **Paddle**: a center hit returns along f (within a tolerance). A hit on the player's left side deflects to the player's left, **tested for both players**. The deflection grows monotonically with the contact offset. The outgoing-angle clamp holds. A moving paddle adds a tangential component. Nothing tunnels at maximum ball speed and maximum paddle speed. The ball never stays inside a paddle. Speed stays ≤ max after 1,000 hits.
- **Serve**: after P1 concedes, the ball launches toward P1's arc within the variation and never toward a wall. The first-serve policies all work.
- **Ownership**: a hit sets the owner. With two balls, each keeps its own owner and trail color.
- **Power-ups**: each type applies and restores its state on expiry. Expand targets the collector, shrink the opponent, and trajectory_reveal benefits the opponent. The speed effects respect the clamp and the exclusive group. double_ball spawns at valid positions with owners that are independent. An unowned ball doesn't collect. Disabled types never spawn. The registry discovers a new type file (via a temporary test module). A config entry for a missing type doesn't crash. The phase rules are respected.
- **Prediction**: the state is unchanged after `predict`. The predicted contact matches the simulated contact for a still paddle (within a tolerance).
- **Config**: generating the defaults gives a valid config, and save then load round-trips it. Missing keys are filled and bad values clamped or rejected. Unknown keys are preserved. The save is atomic (simulate a failure partway through writing). A migration upgrades an old `schema_version`. **Every schema key maps to a panel widget.**
- **Live link**: a `set` message changes the engine config, and an invalid value is rejected with a warning.
- **Input**: keyboard direction signs for both players and both modes; the network parser, side assignment, homography and filters; lost tracking.
- **Text**: `latin_digits`, backend selection, and a smoke test that renders text.
- **Rendering**: `--screenshot-states DIR` writes PNGs of attract, countdown "2", play (two balls, trails, orbs, a trajectory preview), goal, and result. **Open the PNGs and look at them.** The automated **mask-leak test** must pass for each of them.

---

## 22. Deliverables

1. The complete source code (tree in §4), `requirements.txt`, and a generated `config/defaults.json`, plus `config/settings.json` and the 4 presets.
2. The fullscreen Pygame game with everything in this document.
3. The Tkinter control panel with live link, Save, presets, preview, telemetry and search.
4. The inputs: keyboard, AI, mouse, network (LiDAR/pose-ready), and replay. `tools/send_fake_tracking.py` demonstrates the network path end to end.
5. Generated placeholder sounds, copied fonts, and procedural icons with an `--export-icons` option.
6. A test suite that passes, with the soak test included.
7. **README.md** covering:
   - setup (venv and pygame-ce)
   - how to run the game and the panel
   - hotkeys
   - how live editing and Save work, and where the JSON lives
   - projector calibration steps
   - **how to add or remove a power-up** (a worked example)
   - **how to connect LiDAR, TouchDesigner or CCTV pose tracking** (the message format, calibration, and filter tuning)
   - the configuration reference (generated from the schema: key, default, range, description)
   - troubleshooting
   - what is implemented versus what needs hardware

   Also provide `docs/CONFIG_REFERENCE.md`, generated from the schema.

---

## 23. Work plan (finish all stages; verify each one before moving on)

1. **Foundation**: the venv, dependencies, schema, loader with validation and atomic save, defaults generation, geometry with its tests, the display and output transform, the mask with the mask-leak test, and the calibration overlay.
2. **Simulation**: ball, walls, caps, anti-stall, paddles and the full cap collision model, goals, scoring, serve, and the state machine. Test it all headless.
3. **Playable**: the keyboard adapter, the renderer (arena, paddles, ball, trails, HUD with Latin digits, Persian text backend with self-test), and the countdown, goal and result screens. **Play it**: run `--screenshot-states` and check the images.
4. **Power-ups**: the registry, spawner, effects, all 10 types, icons, toasts and phases, plus prediction and the ghost ball, and the Smart Move. Write the tests.
5. **Control panel**: the schema-driven UI, live link, preview, telemetry, presets, search and undo. Change a slider while the game is running and confirm it applies immediately. Press Save and confirm the JSON on disk updates.
6. **Inputs**: AI, mouse, network with `send_fake_tracking.py`, replay, filters and calibration.
7. **Polish and robustness**: audio, ambient effects, performance profiling, the soak test, and exhibition mode.
8. **Docs**: the README and CONFIG_REFERENCE. Rerun the full test suite.

Don't stop after a stage. If something blocks you, say exactly what it is, and keep building everything else.

---

## 24. Acceptance checklist (every item must be true)

- [ ] Starts fullscreen at a logical 1080×1080 (adjustable). The circle is perfect, and pixels outside the mask are exactly black (the test passes).
- [ ] The rim has a P1 goal (left, red), a P2 goal (right, red), and top and bottom bumper walls whose size is an editable % and that bounce with no score.
- [ ] The timer sits just below the top wall. The scores sit just above the bottom wall, P1 on the left and P2 on the right. All digits are Latin.
- [ ] A/D moves P1 and ←/→ moves P2, simultaneously, along their rim tracks with editable padding.
- [ ] The paddles are semicircular domes facing the center. Where the ball hits changes where it goes, and it feels physical.
- [ ] The ball never gets stuck bouncing between the walls.
- [ ] A ball crossing the left arc scores for P2 and one crossing the right arc scores for P1, exactly once. The serve then goes toward the player who conceded, at a random angle.
- [ ] The match ends at 60 s or 7 goals (both editable and switchable) with the full final and result sequence.
- [ ] The 3‑2‑1‑GO countdown has rings, flashes and a charging ball. Flashes stay within safety limits.
- [ ] The trail and glow always show the last toucher, for each ball separately.
- [ ] All 10 power-ups are implemented, and types 1–6 are on by default. Green means good for the collector and red means bad. Each icon shows its effect. Expand affects me, shrink affects the opponent, and trajectory reveal helps the opponent.
- [ ] Adding a power-up is one new file, and it shows up in the panel automatically.
- [ ] The trajectory preview shows a tiny dotted path, a ghost ball at the paddle contact point, and a bounce-out arrow. It never changes the real game state.
- [ ] Persian text renders joined and right-to-left, with ZWNJ handled correctly.
- [ ] The control panel edits **every** setting with a slider or exact field, applies changes **live** while the game runs, saves to JSON atomically, and supports presets, revert and reset.
- [ ] The engine has no keyboard code, and the network adapter drives the paddles from `send_fake_tracking.py`.
- [ ] All tests pass, including the soak test. The README is complete.

When you finish, report:
- what you built,
- the exact commands to run the game, the panel and the tests,
- where the JSON lives,
- the test results and the fps you measured,
- known limitations,
- the next steps for LiDAR and CCTV.

---

## Appendix A: Default Persian strings (editable under `text.*`)

| key | text |
|---|---|
| title | هاکی بازار |
| attract_prompt | برای شروع، روبه‌روی هم بایستید |
| ready | آماده‌اید؟ |
| go | شروع! |
| goal | گل! |
| golden_goal | گل طلایی! |
| final | پایان معاملات! |
| winner | برنده |
| draw | مساوی |
| slogan | بازار همیشه در حرکته؛ آماده‌ی تغییر باش. |
| paused | توقف |
| step_in | وارد زمین شوید |
| smart_hit | واکنش به‌موقع! |
| player_1 / player_2 | بازیکن 1 / بازیکن 2 |
| (power-up toasts) | see the §11.4 table |

## Appendix B: Common misreadings to avoid

- ❌ Paddles moving left and right across the screen. ✅ They slide **along the rim** (up and down the left and right arcs).
- ❌ Paddles shaped as arcs that hug the rim. ✅ They are small **semicircle domes facing the center**.
- ❌ A "center divider" wall between the players. ✅ The walls are **arcs on the rim** at the top and bottom, sized by percentage.
- ❌ Shrink colored red. ✅ Shrink hits **the opponent**, so it is **green**. Only effects that help the opponent are red (trajectory reveal, and slow-down if it is enabled).
- ❌ Scoring decided by who touched the ball last. ✅ The **arc that was crossed** decides. Last touch decides only **who collects power-ups**, plus the trail color.
- ❌ Persian digits. ✅ **Latin digits** inside Persian text.
- ❌ A mask drawn first, or effects drawn after the mask. ✅ The mask is drawn **last**, and a test proves it.
- ❌ Hardcoded constants in the code. ✅ Everything comes from the schema, JSON and the panel, live.
