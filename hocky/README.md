# Market Hockey · هاکی بازار

A two-player circular projection-floor game for **Mofid Securities (کارگزاری مفید)**, inspired by air hockey and
the META LiDAR projection floor. It is built with Python, **pygame-ce** (the game) and **Tkinter** (the control
panel). Every parameter lives in JSON and can be edited live while the game runs.

## Quick start

```bash
cd /Users/dayhimit/Documents/MML/projects/mofid/hocky
python3 -m venv .venv                       # already done in this folder
.venv/bin/pip install -r requirements.txt   # already done
.venv/bin/python main.py --windowed         # play in a window
.venv/bin/python main.py                    # fullscreen (projector)
.venv/bin/python settings_app.py            # control panel (separate window, live-linked)
.venv/bin/python -m pytest -q               # tests
```

On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.
If `pygame-ce` has no wheel for your Python, create the venv with Python 3.12.

## Controls

| Key | Action |
|---|---|
| **Space / Enter** | start a match (or skip the result screen) |
| **A / D** | Player 1 (left) paddle: toward *their* left / right |
| **← / →** | Player 2 (right) paddle: toward *their* left / right |
| W/S, ↑/↓ | optional alternates: move the paddles up and down on screen |
| P | pause |
| R (hold ½ s) | reset to the attract screen |
| F1 | open the control panel |
| F2 | projector calibration overlay |
| F3 | debug overlay (FPS, effects, inputs). While it is on, keys **1–0** spawn power-ups and **B** adds a ball |
| F11 | fullscreen on/off |
| Esc ×2 | quit |

`Display & Projection → Exhibition mode` disables F1–F3 and the debug keys. **Ctrl+Shift+D** still toggles debug.

## The game

- **Arena.** The playfield is a perfect circle inside a square canvas (1080×1080 by default, adjustable). Everything outside the circle is masked to pure black, and a test checks that no pixels leak.
- **Rim.** The rim is split into four arcs:
  - **left arc**: Player 1's red goal line
  - **right arc**: Player 2's red goal line
  - **top and bottom**: solid bumper walls (`walls.top_percent` / `bottom_percent`, % of the circumference). The ball bounces off them and they never score.
- **HUD.** The timer sits just below the top wall. The scores sit just above the bottom wall, P1 on the left and P2 on the right. All digits are Latin.
- **Paddles.** Each paddle is a semicircular dome (flat side to the rim) that slides along the rim, set in by `paddles.p1.rim_padding`.
  - The bounce is physical: the dome's normal decides the outgoing angle, so a hit on the left side of the dome goes to the player's left.
  - `aim_blend` mixes in arcade steering. `max_outgoing_angle_deg` and `min_forward` stop the ball from being sent backward.
- **Scoring.** A ball that crosses the left arc gives P2 a point, and one that crosses the right arc gives P1 a point. The arc decides, not the last touch.
- **Serve.** After a goal, the ball is served **toward the player who conceded**, at a random angle within `serve.angle_variation_deg`.
- **Match end.** The match ends at **60 s or 7 goals**, whichever comes first. Both limits are editable and can be switched off. A tie can end as a draw or go to a golden goal.
- **Trails.** The trail and glow always show **who touched the ball last**. That player collects any power-up the ball passes through. A ball nobody has touched passes through orbs harmlessly.
- **Flow.** Attract demo (AI vs AI) → intro → «آماده‌اید؟» 3‑2‑1 «شروع!» with rings and flashes → play → goal slow-motion → «پایان معاملات!» → winner screen and slogan.

### Power-ups

Green means good for whoever collects it, and red means it helps the opponent. Each icon pictures its effect. Orbs float in the 5 center slots and are **pulled gently toward a ball**. The magnet is set in `Power-ups → Magnet`: strength, radius, falloff, max drift and return spring.

| | Power-up | Default | Effect |
|---|---|---|---|
| 🟢 | Expand | on | **your** paddle grows (×1.5, 8 s) |
| 🟢 | Shrink | on | **opponent's** paddle shrinks (×0.6, 8 s) |
| 🟢 | Speed up («نوسان بازار») | on | the ball speeds up (×1.4, 6 s) with a flame trail |
| 🟢 | Random path | on | the ball's direction jumps (or wobbles), always toward the opponent |
| 🟢 | Double ball («حجم معاملات») | on | splits into 2 balls, each with its own owner and trail |
| 🔴 | Trajectory reveal | on | your **opponent** sees a tiny dotted path, a ghost ball where it meets their paddle, and the bounce-out arrow |
| 🔴 | Slow down («بازار آرام») | off | the ball slows down |
| 🟢 | Dim ball («اصلاح بازار») | off | the ball dims (never invisible) |
| 🟢 | Shield («حد نوسان») | off | a barrier over your goal blocks one ball |
| 🟢 | Bull market | off | your next goal counts double |

The PDF's match **phases** (no power-ups in the warm-up, more in the peak) and the **Smart Move** («واکنش به‌موقع!»: a fast flick right at contact) are both implemented and configurable.

## Live editing and saving

- `settings_app.py` edits **every** setting (424) with sliders, exact-value fields, color pickers, dropdowns and key capture.
- Changes go to the running game **live** over UDP on 127.0.0.1:9201. A green dot means the setting applies live; an orange dot means it applies on restart.
- **Save** (⌘/Ctrl+S) writes `config/settings.json` atomically and keeps `config/settings.prev.json` as a backup. Live edits are *not* saved until you press Save.
- Other tools: **Presets** (`config/presets/*.json`: default, kids_easy, pro, calibration), Revert, Reset to defaults, search (⌘/Ctrl+F) and undo (⌘/Ctrl+Z).
- The right side shows a live layout preview with safe-area warnings, game telemetry, and test buttons (spawn orb, extra ball, debug, calibrate).
- `docs/CONFIG_REFERENCE.md` lists every key with its default and range. Regenerate it with `.venv/bin/python -m market_hockey.config.generate_defaults`.

## Projector calibration

1. Run fullscreen on the projector (`Display & Projection → Display index`), then press **F2**.
2. Align the thin white circle with the physical circle. Use `arena.mask_radius` and `arena.center_offset_x/y`, or the `display.output_*` scale and offsets.
3. Use `display.rotation` / `flip_h` / `flip_v` for ceiling or rear projection, and `arena.layout_rotation_deg` if the players stand on a different axis.
4. Check the color swatches on the projector and adjust `colors.projection_boost`.

## Persian text

pygame-ce shapes Persian with HarfBuzz (`Font.set_script("Arab")` + RTL direction), so letters join correctly and the zero-width non-joiner (ZWNJ) works. Mixed strings are split into RTL and LTR runs, so Latin digits stay in the right order. Digits are always Latin (۰–۹ are converted). `arabic-reshaper` is the fallback backend (`HUD & Text → Persian shaping`).

To check the rendering, run `.venv/bin/python main.py --selftest-text out/` and look at the PNGs.

Fonts: IRANSansX (copied into `assets/fonts/`). The brand book's primary font, **Dana**, isn't available. Drop `Dana-*.ttf` into `assets/fonts/` and pick it in `HUD & Text → Fonts`.

All in-game texts are editable in `HUD & Text → Messages` and in each power-up's section.

## Adding or removing a power-up

Create one file, `market_hockey/powerups/types/wide.py`:

```python
from ..base import PowerUpType
from ..registry import register

@register
class Wide(PowerUpType):
    id = "wide"; name = "Wide paddle"; order = 11; icon = "expand"
    default_class = "good"; duration = 5.0
    toast_c = "بالکر پهن شد!"

    def extra_schema(self, sb, p):
        sb.f(f"{p}.multiplier", 2.0, 1.1, 3.0, 0.1, "×", "Size multiplier")

    def collect(self, engine, ball, collector):
        engine.add_effect(self, self.effect(engine, "paddle_size", ("player", collector),
                                            self.p(engine.cfg, "multiplier"), collector))
        return {"affects": ("player", collector)}
```

It appears in the spawner, the JSON and the control panel automatically.

- **To remove a power-up**, untick *Enabled* (or delete the file).
- **Custom icons**: put `assets/icons/<id>.png` in place to replace the drawn icon.
- **Effect kinds** available to `self.effect(...)`: `paddle_size`, `ball_speed`, `dim`, `reveal`, `shield`, `bull`, `wobble`. Effects are computed from the active list every step, so expiry always restores the previous state.

## LiDAR, TouchDesigner or CCTV pose tracking

The engine only consumes *"player position 0..1 along their arc"*. Set `Inputs → Player 1/2 input` to **network**, then send JSON over UDP (default `127.0.0.1:9100`; set *Listen on* to `0.0.0.0` for another machine):

```json
{"type":"tracking","players":[{"id":"p1","x":-0.92,"y":0.20,"conf":0.9},{"id":"p2","x":0.90,"y":-0.10,"conf":0.8}]}
{"type":"blobs","blobs":[{"x":-0.92,"y":0.2},{"x":0.9,"y":-0.1}]}
```

- **Coordinates** are normalized to the arena: center (0,0), rim = 1, +y up. A per-player `"u"` (0..1) skips the mapping.
- **Blobs** are assigned to players by which goal arc they're on.
- **Calibration**: offset, scale, rotation and flip are in `Inputs → Network`.
- **Filters**: One Euro smoothing, spike rejection, confidence gate, hold-when-lost and absent timeout.
- **Test without hardware**: `.venv/bin/python tools/send_fake_tracking.py` (or `--blobs`).
- **TouchDesigner**: send that JSON from a UDP Out DAT.
- **CCTV pose** (MediaPipe / YOLO-pose): run the model in a separate process and send the ankle midpoint per person. Don't import vision models into the game.
- **Other inputs**: `ai` (single-player vs CPU), `mouse` (debug) and `replay` (record with `input.record`, play back from `input.replay_file`).

## Tools

- `main.py --screenshot-states DIR`: headless PNGs of every state
- `--export-icons DIR`: power-up badges
- `--selftest-text DIR`: Persian rendering check
- `tools/make_placeholder_sounds.py [--force]`: regenerate the synthesized sound effects
- `logs/matches.csv`: one row per match (scores, power-ups, smart hits)
- `logs/market_hockey.log`: the log

## Project layout

```
main.py · settings_app.py · config/ (settings.json, defaults.json, presets/) · assets/ (fonts, sounds, icons)
market_hockey/
  config/      schema.py (every setting), store.py (validation, atomic JSON), live_link.py
  core/        geometry.py, collisions.py, entities.py, engine.py   (pure Python, no pygame)
  powerups/    base.py, registry.py, effects.py, types/*.py         (one file per power-up)
  prediction/  trajectory.py
  inputs/      keyboard, ai, mouse, network (LiDAR/pose), replay, filters, manager
  render/      renderer.py, text.py (Persian), icons.py, glow.py, particles.py, overlays.py
  audio/       synth.py (placeholder sounds), audio.py
  ui/          settings_window.py, widgets.py, preview.py, theme.py
tests/         geometry, physics, scoring, power-ups, prediction, config, inputs, text/mask, soak
```

## Troubleshooting

- **Persian letters are disconnected**: set `HUD & Text → Persian shaping` to `reshaper`, then run `--selftest-text`.
- **The panel says "Game offline"**: start the game. The panel connects on port 9201 and pushes all its current values.
- **Wrong monitor**: change `display.display_index`, then restart.
- **Low FPS**: lower `fx.max_particles`, `trails.glow` or `display.fps_cap`. Use F3 to see the FPS.
- **No sound**: check `Audio → Sound enabled`. The game runs silently if the mixer can't start.
