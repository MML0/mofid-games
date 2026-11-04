"""
Setup window of the floor game: live lidar view + every setting.

floor_game.py opens it by itself (key S opens it again). It shows what the
lidar sees right now and the game on top of it, so you can calibrate and see
the result at once. Every change goes live to the running game and is saved
to game_settings.json.

    1. Lidar tab    keep the floor empty, press "Scan background". Turn /
                    mirror the map until it matches the room. White points
                    on the empty floor = noise: raise Background gap.
    2. Arena tab    drag the circle onto the play area, set the diameter.
    3. the rest     players, border limit, tracking and paddle feel.

Map    wheel zoom, right drag pan, V fit view
       drag the center cross, the circle edge, or a line's round handle
Keys   B scan background   Tab next settings tab   ESC close this window

Run    python lidar_setup.py      (needs floor_game.py running, any order)
"""

import argparse
import math
import os
import time

import numpy as np
import pygame

from game_settings import GameSettings
from game_view import BACK, DIM, LINE, TEXT, View, draw_arena, draw_chips, handle_points
from link import ENGINE_PORT, SETUP_PORT, Endpoint, unpack_array
from settings_ui import SettingsPanel


WIDTH = 1240
HEIGHT = 900
PANEL_WIDTH = 380
FPS = 60

SCAN_POINT = (45, 90, 150)
BG_POINT = (60, 60, 66)
FOOT_POINT = (235, 235, 235)
LIDAR = (230, 60, 60)
RING = (24, 26, 32)

GUIDE = {
    "Lidar": [
        "1. Keep the floor empty and press Scan background.",
        "2. Rotate / mirror until the map matches the room (red line = lidar 0°).",
        "3. White points on the empty floor are noise: raise Background gap.",
    ],
    "Arena": [
        "Drag the circle onto the play area: the cross moves it, the edge sets the size.",
        "Only feet inside the two thin rings are tracked.",
    ],
    "Players": ["Drag a round handle to turn the dividing lines."],
}


def main():

    parser = argparse.ArgumentParser(description="Floor game setup window")
    parser.add_argument("--settings", default=None)
    parser.add_argument("--tab", type=int, default=0, help="settings tab to show first")
    parser.add_argument("--time", type=float, default=None, help="close after N seconds")
    parser.add_argument("--shot", default=None, help="save a screenshot when it closes")
    args = parser.parse_args()
    started = time.time()

    cfg = GameSettings(args.settings) if args.settings else GameSettings()
    cfg.load()

    link = Endpoint(SETUP_PORT, ENGINE_PORT)

    os.environ["SDL_VIDEO_WINDOW_POS"] = "900,40"
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Floor game - lidar setup")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 16)
    small = pygame.font.SysFont("Segoe UI", 13)
    big = pygame.font.SysFont("Segoe UI", 26)
    label_font = pygame.font.SysFont("Segoe UI", 14, bold=True)

    view = View()
    auto_view = True
    drag = None
    state = {}              # newest message from the engine
    points = None           # (x, y, mask) of the newest scan
    background = None       # (bx, by)
    last_message = 0.0
    calib_left = None
    calib_at = 0.0


    # -------------------------
    # SETTINGS
    # -------------------------

    def changed(final):

        link.send({"cmd": "set", "values": cfg.values(), "final": bool(final)})

        if final:
            try:
                cfg.save()
                panel.flash("Saved")
            except OSError as e:
                print(f"Settings not saved: {e}")
                panel.flash("Save failed!")


    def rescan():

        link.send({"cmd": "rescan"})
        panel.flash("Scanning background...")


    panel = SettingsPanel(cfg, changed, [("Scan background (B)", rescan)], PANEL_WIDTH)
    panel.pin_open()
    panel.tab = args.tab
    panel.extra.update(GUIDE)


    # -------------------------
    # VIEW
    # -------------------------

    def map_size():

        w, h = screen.get_size()

        return max(w - PANEL_WIDTH, 2), max(h, 2)


    def fit():
        """Arena with its tracking band, and the lidar itself."""

        r = cfg.radius + cfg.band_out + 300
        x0, x1 = min(cfg.center_x - r, -300), max(cfg.center_x + r, 300)
        y0, y1 = min(cfg.center_y - r, -300), max(cfg.center_y + r, 300)
        mw, mh = map_size()
        top, bottom = 70, 30
        view.zoom = min(max(min(mw / (x1 - x0), (mh - top - bottom) / (y1 - y0)), 0.01), 5.0)
        view.x = (x0 + x1) / 2
        view.y = (y0 + y1) / 2 + (top - bottom) / 2 / view.zoom


    def draw_points(xs, ys, color, size=2):

        mw, mh = map_size()
        z = view.zoom
        sx = (mw / 2 + (xs - view.x) * z).astype(np.int32)
        sy = (mh / 2 - (ys - view.y) * z).astype(np.int32)
        ok = (sx >= 0) & (sx < mw - size) & (sy >= 0) & (sy < mh - size)

        for px, py in zip(sx[ok].tolist(), sy[ok].tolist()):
            screen.fill(color, (px, py, size, size))


    # -------------------------
    # LOOP
    # -------------------------

    running = True

    while running:

        screen = pygame.display.get_surface()
        mw, mh = map_size()
        view.size = (mw, mh)

        # messages from the engine (keep the newest)
        for message in link.receive():

            last_message = time.time()

            if "calib" in message:
                calib_left = message["calib"]
                calib_at = time.time()
                continue

            state = message

            # P in the game window switched the game dots: show it here too
            if "game_dots" in message and bool(message["game_dots"]) != cfg.game_dots:
                cfg.game_dots = bool(message["game_dots"])

            if "x" in message:
                points = (unpack_array(message["x"]), unpack_array(message["y"]),
                          unpack_array(message["mask"], np.uint8).astype(bool))

            if "bx" in message:
                background = (unpack_array(message["bx"]), unpack_array(message["by"]))

        if calib_left is not None and time.time() - calib_at > 0.5:
            calib_left = None

        # events
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False
                continue

            map_drag = drag is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP)

            if not map_drag and panel.handle(event):
                continue

            if event.type == pygame.KEYDOWN:

                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_b:
                    rescan()
                elif event.key == pygame.K_v:
                    auto_view = True
                elif event.key == pygame.K_TAB:
                    panel.tab = (panel.tab + 1) % len(cfg.tabs)

            elif event.type == pygame.MOUSEWHEEL:
                if pygame.mouse.get_pos()[0] < mw:
                    auto_view = False
                    view.zoom_at(1.15 ** event.y, pygame.mouse.get_pos())

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and event.pos[0] < mw:

                mx, my = event.pos
                cx, cy = view.to_screen(cfg.center_x, cfg.center_y)
                ring = abs(math.hypot(mx - cx, my - cy) - cfg.radius * view.zoom)

                for k, (hx, hy) in enumerate(handle_points(view, cfg)):
                    if math.hypot(mx - hx, my - hy) < 14:
                        drag = ("line", k)
                        break
                else:
                    if math.hypot(mx - cx, my - cy) < 18:
                        wx, wy = view.to_map(mx, my)
                        drag = ("center", wx - cfg.center_x, wy - cfg.center_y)
                    elif ring < 10:
                        drag = ("size",)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and event.pos[0] < mw:
                drag = ("pan", event.pos, view.x, view.y)
                auto_view = False

            elif event.type == pygame.MOUSEMOTION and drag is not None:

                wx, wy = view.to_map(*event.pos)

                if drag[0] == "center":
                    cfg.set("center_x", wx - drag[1])
                    cfg.set("center_y", wy - drag[2])

                elif drag[0] == "size":
                    cfg.set("diameter", 2 * math.hypot(wx - cfg.center_x, wy - cfg.center_y))

                elif drag[0] == "line":
                    k = drag[1]
                    a = math.degrees(math.atan2(wy - cfg.center_y, wx - cfg.center_x))
                    delta = (a - cfg.lines()[k] + 180) % 360 - 180

                    if cfg.equal_sectors or k == 0 or cfg.players < 2:
                        cfg.set("line_angle", (cfg.line_angle + delta + 180) % 360 - 180)
                    else:
                        sizes = cfg.sector_sizes()
                        delta = min(max(delta, 10 - sizes[k - 1]), sizes[k] - 10)
                        sizes[k - 1] += delta
                        sizes[k] -= delta
                        for i, s in enumerate(sizes):
                            cfg.set(f"sector_{i + 1}", s)

                elif drag[0] == "pan":
                    _, start, vx, vy = drag
                    view.x = vx - (event.pos[0] - start[0]) / view.zoom
                    view.y = vy + (event.pos[1] - start[1]) / view.zoom

                if drag[0] != "pan":
                    changed(False)

            elif event.type == pygame.MOUSEBUTTONUP and drag is not None:

                if drag[0] != "pan":
                    changed(True)

                drag = None

        panel.tick()
        panel.place(screen.get_size())

        if auto_view and drag is None:
            fit()


        # -------------------------
        # DRAW
        # -------------------------

        screen.fill(BACK)
        lidar = view.to_screen(0, 0)

        # 1 m rings around the lidar
        for r in range(1000, 8001, 1000):
            pygame.draw.circle(screen, RING, lidar, int(r * view.zoom), 1)

        if background is not None:
            draw_points(background[0], background[1], BG_POINT)

        if points is not None:
            x, y, mask = points
            draw_points(x[~mask], y[~mask], SCAN_POINT)
            draw_points(x[mask], y[mask], FOOT_POINT, 3)

        # lidar and its 0° direction (shows Rotate / Mirror)
        zx, zy = cfg.to_world(0.0, 45 / view.zoom)
        pygame.draw.line(screen, LIDAR, lidar, view.to_screen(float(zx), float(zy)), 2)
        pygame.draw.circle(screen, LIDAR, lidar, 5)

        draw_arena(screen, view, cfg, state if "players" in state else None, label_font, small, setup=True)

        # status line
        connected = time.time() - last_message < 2.0
        x = draw_chips(screen, font, state if connected and "players" in state else None, 16, 12)

        if connected and "hz" in state:
            info = f"Lidar {state['hz']:.1f} Hz   {state.get('points', 0) if points is None else len(points[0])} points"
            info += f"   CRC {state.get('crc', 0)}"
            screen.blit(small.render(info, True, DIM), (x + 6, 16))

        mx, my = pygame.mouse.get_pos()

        if mx < mw:
            wx, wy = view.to_map(mx, my)
            r, a = cfg.polar(wx, wy)
            screen.blit(small.render(
                f"x {wx:.0f}  y {wy:.0f} mm    from arena center {float(r):.0f} mm  {float(a):.0f}°",
                True, (70, 74, 86)), (16, mh - 24))

        if not connected:
            text = big.render("Waiting for the game (floor_game.py)...", True, TEXT)
            screen.blit(text, (mw // 2 - text.get_width() // 2, mh // 2 - 20))

        elif calib_left is not None:
            text = big.render(f"Scanning the empty floor  {calib_left:.0f}", True, (255, 200, 60))
            screen.blit(text, (mw // 2 - text.get_width() // 2, 60))

        pygame.draw.line(screen, LINE, (mw, 0), (mw, mh), 1)
        panel.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

        if args.time is not None and time.time() - started >= args.time:
            running = False

    if args.shot:
        pygame.image.save(screen, args.shot)

    link.close()
    pygame.quit()



if __name__ == "__main__":
    main()
