"""
Drawing shared by the game window (floor_game.py) and the setup window
(lidar_setup.py), plus the snapshot of the game state that the engine sends
to the setup window.
"""

import math

import pygame


PLAYER_COLORS = [
    (255, 92, 92), (70, 170, 255), (255, 200, 60), (90, 220, 140),
    (190, 120, 255), (255, 140, 60), (60, 220, 220), (240, 110, 190),
]

BACK = (9, 10, 13)
LINE = (58, 62, 74)
DIM = (95, 100, 115)
TEXT = (200, 204, 214)


def dark(color, f):

    return tuple(int(c * f) for c in color)


def player_color(i):

    return PLAYER_COLORS[i % len(PLAYER_COLORS)]



def snapshot(game, scan_t):
    """Plain-data copy of the game state (players, paddles, feet)."""

    players = [(p.active, p.seen, p.conf, p.x, p.y, len(p.feet)) for p in game.players]
    mine = {id(f) for p in game.players for f in p.feet}
    feet = [(f.id, f.x, f.y, f.owner, f.confirmed, f.last_seen != scan_t, id(f) in mine)
            for f in game.tracker.feet]

    return {"players": players, "paddles": list(game.paddles), "feet": feet}



class View:
    """Map mm <-> screen px for a pygame surface area of size (w, h)."""

    def __init__(self):

        self.zoom = 0.15
        self.x = 0.0
        self.y = 0.0
        self.size = (2, 2)


    def to_screen(self, x, y):

        w, h = self.size

        return int(w / 2 + (x - self.x) * self.zoom), int(h / 2 - (y - self.y) * self.zoom)


    def to_map(self, sx, sy):

        w, h = self.size

        return (sx - w / 2) / self.zoom + self.x, (h / 2 - sy) / self.zoom + self.y


    def fit(self, cx, cy, r, top=0, bottom=0, side=0):
        """Center on (cx, cy) and zoom so a circle of radius r just fits."""

        w, h = self.size
        self.zoom = min(max(min(w - 2 * side, h - top - bottom) / (2 * max(r, 1.0)), 0.01), 5.0)
        self.x = cx
        self.y = cy + (top - bottom) / 2 / self.zoom


    def zoom_at(self, factor, pos):

        wx, wy = self.to_map(*pos)
        self.zoom = min(max(self.zoom * factor, 0.01), 5.0)
        nx, ny = self.to_map(*pos)
        self.x += wx - nx
        self.y += wy - ny



def arc(screen, view, cfg, color, a0, a1, r, width):
    """Arc around the arena center from a0 to a1 (deg, counter-clockwise)."""

    steps = max(2, int(abs(a1 - a0) / 2) + 1)
    pts = []

    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append(view.to_screen(cfg.center_x + math.cos(a) * r, cfg.center_y + math.sin(a) * r))

    pygame.draw.lines(screen, color, False, pts, width)


def handle_points(view, cfg):
    """Screen position of every dividing line's drag handle (setup window)."""

    r = cfg.radius + cfg.band_out + 250
    out = []

    for a in cfg.lines():
        rad = math.radians(a)
        out.append(view.to_screen(cfg.center_x + math.cos(rad) * r, cfg.center_y + math.sin(rad) * r))

    return out


def draw_arena(screen, view, cfg, snap, label_font, small=None, setup=False):
    """Circle, sectors, feet, players and paddles. setup=True adds the tracking band, handles and IDs."""

    z = view.zoom
    R = cfg.radius
    center = view.to_screen(cfg.center_x, cfg.center_y)

    if setup:
        for r in (R - cfg.band_in, R + cfg.band_out):
            if r > 0:
                pygame.draw.circle(screen, (34, 38, 48), center, max(1, int(r * z)), 1)

    # dividing lines
    line_end = R + (cfg.band_out if setup else 0)

    for a in cfg.lines():
        rad = math.radians(a)
        end = view.to_screen(cfg.center_x + math.cos(rad) * line_end, cfg.center_y + math.sin(rad) * line_end)
        pygame.draw.line(screen, LINE, center, end, 1)

    if setup:
        for hx, hy in handle_points(view, cfg):
            pygame.draw.circle(screen, (120, 126, 140), (hx, hy), 6, 2)

    # circle: player color where a paddle may go, grey on the borders
    width = max(2, int(z * 25)) if not setup else 3

    for i, (start, size) in enumerate(cfg.sectors()):
        gap = cfg.gap(size)
        arc(screen, view, cfg, dark(player_color(i), 0.45), start + gap, start + size - gap, R, width)
        if gap > 0:
            arc(screen, view, cfg, LINE, start - gap, start + gap, R, max(1, width // 2))

    pygame.draw.line(screen, LINE, (center[0] - 6, center[1]), (center[0] + 6, center[1]), 1)
    pygame.draw.line(screen, LINE, (center[0], center[1] - 6), (center[0], center[1] + 6), 1)

    if snap is None:
        return

    players = snap["players"]

    # feet
    foot_r = max(4, int(z * 40))

    for fid, fx, fy, owner, confirmed, lifted, mine in snap["feet"]:

        pos = view.to_screen(fx, fy)

        if not confirmed or owner is None or owner >= len(players):
            if setup:
                pygame.draw.circle(screen, DIM, pos, 3, 1)
            continue

        color = player_color(owner)

        if not mine:
            pygame.draw.circle(screen, DIM, pos, foot_r, 1)          # someone else
        elif lifted:
            pygame.draw.circle(screen, dark(color, 0.7), pos, foot_r, 1)
        else:
            pygame.draw.circle(screen, color, pos, foot_r)

        if setup and small is not None:
            screen.blit(small.render(str(fid), True, DIM), (pos[0] + foot_r + 2, pos[1] - 8))

    # players and paddles
    paddle_r = max(8, int(cfg.paddle_size / 2 * z))

    for i, ((active, seen, conf, px, py, _), (angle, x, y)) in enumerate(zip(players, snap["paddles"])):

        color = player_color(i)
        pos = view.to_screen(x, y)

        if active:

            body = view.to_screen(px, py)

            # player is not on the line: show where they really are
            if math.hypot(body[0] - pos[0], body[1] - pos[1]) > paddle_r * 0.6:
                pygame.draw.line(screen, dark(color, 0.5), body, pos, 1)

            pygame.draw.circle(screen, dark(color, 0.8), body, max(4, foot_r - 1), 1)

            pygame.draw.circle(screen, color if seen else dark(color, 0.7), pos, paddle_r)
            text = label_font.render(str(i + 1), True, BACK)

        else:
            pygame.draw.circle(screen, dark(color, 0.55), pos, paddle_r, 2)
            text = label_font.render(str(i + 1), True, dark(color, 0.7))

        screen.blit(text, text.get_rect(center=pos))


def draw_chips(screen, font, snap, x, y):
    """P1 P2 ... status chips (filled = tracked). Returns the x after the last chip."""

    if snap is None:
        return x

    for i, p in enumerate(snap["players"]):

        color = player_color(i)
        r = 6

        if p[0]:
            pygame.draw.circle(screen, color, (x + r, y + 10), r)
        else:
            pygame.draw.circle(screen, dark(color, 0.6), (x + r, y + 10), r, 2)

        t = font.render(f"P{i + 1}", True, color if p[0] else DIM)
        screen.blit(t, (x + 2 * r + 6, y))
        x += 2 * r + 6 + t.get_width() + 18

    return x
