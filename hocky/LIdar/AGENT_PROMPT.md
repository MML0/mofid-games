# Prompt for the integration agent

Copy everything below the line into the agent, together with this folder and the game's repository.

---

You are integrating a finished lidar foot-tracking input into my existing, finished game.

## The game

A modified air hockey game played on a circular interactive floor. Several players (1 to 8,
usually 2–4) stand around the circle. Each owns a sector of the arena and controls a virtual
paddle **with their feet** by walking along their part of the circle. Everyone hits a shared puck
across the arena and tries to score in the other players' zones. Spectators watch from all sides
(360°). The game repository is: **<PATH OR URL OF MY GAME REPO>**.

## What you are given

The folder `LIdar/` (this package) is a **finished and tested input device**. Don't redesign it.
Read these first, in this order:

1. `docs/INTEGRATION.md`: the full integration guide (architecture, OSC contract, sector math,
   calibration, settings, tests). **This is your main reference.**
2. `README.md`, section "Floor game".
3. `game_settings.py` (`GameSettings.sectors()`) and `samples/session_2players.settings.json`.

In short, `python floor_game.py --port COMx` runs a separate process that owns the lidar and sends,
every frame (~60 Hz), for each player:

```
OSC  /paddle  [player:int 1..N, x:float mm, y:float mm, angle:float deg, active:int 0/1, confidence:float 0..1]
     to 127.0.0.1:7000 (change with --osc-ip / --osc-port)
```

The paddle is already smoothed, predicted, kept on the circle, and clamped away from the dividing
lines (the border limit). Sector k belongs to player k. The sectors are defined by `players`,
`line_angle`, `equal_sectors`, `sector_1..8` and `border_gap` in `game_settings.json`
(formula in INTEGRATION.md §4).

## Your task

1. **Explore the game repo first.** Find the engine / framework (Unity, Godot, Unreal,
   TouchDesigner, web, Python, ...), how paddles / players are currently controlled (mouse,
   keyboard, touch, network), where the arena center, radius and player zones / goals are defined,
   and how many players it supports. Write a short summary of what you found before you change code.
2. **Add an OSC input adapter** to the game, using the engine's normal OSC library or plugin
   (e.g. extOSC / OscJack for Unity, a GDScript UDP + OSC parser for Godot, the OSC In CHOP / DAT for
   TouchDesigner, `python-osc` for Python, a small UDP-to-WebSocket bridge for a browser game). It
   listens on a configurable port (default 7000) and parses `/paddle`.
3. **Drive each player's paddle from `/paddle`** through the existing paddle / input code, without
   bypassing the game's physics:
   - Use the **angle**: `pos = arena_center + arena_radius * (cos(angle), sin(angle))` in the game's
     own units. Don't map the mm `x, y` unless the game really works in floor millimetres.
   - Add config values: OSC port, angle offset (deg), mirror X, mirror Y, and player index mapping.
     The projected image may be rotated or mirrored compared with the lidar map: mirror X is
     `angle' = 180 - angle`, mirror Y is `angle' = -angle`, then add the offset.
   - `active = 0`: nobody in that sector. Do what the game already does for an empty player slot
     (hide the paddle, AI, or a wall). If the game has no such rule, **ask me** and don't invent one.
   - If the game's paddle physics needs a velocity, derive it from successive positions. Don't add
     extra smoothing; the input is already smoothed.
4. **Match the sectors.** The game's player zones / goals must use the same layout as the lidar.
   Prefer reading `game_settings.json` (path in the game config), or copy the values into the game
   config. Document which one you chose. Player 1 = the sector that starts at `line_angle`, then
   counter-clockwise.
5. **Keep the old controls** (mouse / keyboard / touch) as a fallback, with a switch, so the game can
   be tested without the lidar.
6. **Test without hardware**: run
   `python floor_game.py --headless --replay samples/session_2players.pkl --settings samples/session_2players.settings.json --loop`
   while the game runs, and check that P1's paddle walks around the left half and later P2's around
   the right half. `python tools/osc_monitor.py <port>` shows the raw messages (stop it before the game
   uses the same port). Run `python tests/test_tracker.py` and `python tests/test_replay.py` to confirm
   the lidar package still passes if you touched it.
7. **Write the docs** in the game repo: how to start the lidar and the game together (start order,
   ports, firewall if they run on two PCs), the new config values, and the on-site calibration order
   (lidar calibration, then arena diameter / center, then the angle offset / mirror in the game until the
   paddle is under the player's feet).

## Rules

- Don't change the tracking algorithm, its settings, or the OSC format unless something is truly
  impossible otherwise. If you must, explain why first and keep `tests/` passing.
- Don't open the lidar COM port from the game. Only `floor_game.py` may open it.
- Don't change game rules, scoring, or physics beyond what the input needs. Ask me if something
  is unclear (e.g. the number of players, what an empty slot does, the arena size).
- Small, reviewable commits with clear messages, and no unrelated refactors.

## Done means

- With the replay running, the game's paddles move along the circle, each in its own sector, never
  into the border zone, with no jumps.
- Inactive players are handled the way the game already handles empty slots.
- The old controls still work behind a switch.
- The README / docs in the game repo explain setup, config and calibration.
- A short report back to me: files changed, config values added, how to run, anything you couldn't
  test (e.g. with the real lidar), and open questions.
