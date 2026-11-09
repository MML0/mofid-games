"""Build the branded orb faces in assets/orbs/ from the client's square artwork.

Each face is a round 512 px PNG named after its power-up. The crop is centered on the artwork's name and leaves it clear
of the coin's rim. Artwork that was drawn for the coin already is used whole.

    python tools/make_orb_faces.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_hockey.paths import ORBS_DIR  # noqa: E402

SOURCE = ROOT / "گروه مالی مفید" / "icons"
FACE = 512
ART_SCALE = 2084 / 1932  # the boxes below were measured on a 1932 px view of the 2084 px artwork
FILL = 0.92  # the artwork's corners reach this fraction of the coin's radius

# power-up -> artwork file, box around the name and logo (left, top, right, bottom)
ARTWORK = {
    "expand": ("طرح حامی.png", (313, 702, 1617, 1228)),
    "speed_up": ("صندوق   عیار.png", (241, 660, 1690, 1295)),
    "double_ball": ("صندوق   توان.png", (287, 682, 1690, 1248)),
    "trajectory_reveal": ("بورس ویو.png", (255, 557, 1675, 1403)),
}

# power-up -> artwork used edge to edge
WHOLE_ARTWORK = {"shrink": "سقوط شاخص بورس.webp"}

# power-up -> (artwork background, new background): the artwork is drawn in two flat colors, so every pixel is a mix
# of its background and its ink, and only the background's share is swapped
RECOLOR = {"expand": ((64, 154, 204), (60, 170, 92))}  # طرح حامی on green instead of its blue


def round_off(square: pygame.Surface) -> pygame.Surface:
    """A copy with everything outside the inscribed circle transparent, with a clean edge."""
    out = pygame.Surface(square.get_size(), pygame.SRCALPHA)
    out.blit(square, (0, 0))
    n = out.get_width()
    centers = np.arange(n, dtype=np.float32) + 0.5 - n / 2
    dist = np.hypot(centers[:, None], centers[None, :])
    alpha = pygame.surfarray.pixels_alpha(out)
    alpha[:] = (np.clip(n / 2 - dist + 0.5, 0, 1) * 255).astype(np.uint8)
    del alpha
    return out


def crop_face(name: str, box: tuple) -> pygame.Surface:
    art = pygame.image.load(str(SOURCE / name))
    left, top, right, bottom = (v * ART_SCALE for v in box)
    cx, cy = (left + right) / 2, (top + bottom) / 2
    radius = math.hypot(right - left, bottom - top) / 2 / FILL
    w, h = art.get_size()
    radius = min(radius, cx, cy, w - cx, h - cy)
    side = int(radius * 2)
    square = pygame.Surface((side, side), pygame.SRCALPHA)
    square.blit(art, (0, 0), pygame.Rect(int(cx - radius), int(cy - radius), side, side))
    return round_off(pygame.transform.smoothscale(square, (FACE, FACE)))


def recolor(face: pygame.Surface, old_bg: tuple, new_bg: tuple) -> pygame.Surface:
    """Swap the artwork's background color, keeping the ink and the anti-aliased edges between them."""
    rgb = pygame.surfarray.pixels3d(face).astype(np.float32)
    old, new = np.array(old_bg, np.float32), np.array(new_bg, np.float32)
    flat = rgb.reshape(-1, 3)
    ink = flat[np.argmax(np.linalg.norm(flat - old, axis=1))]  # the color farthest from the background
    axis = ink - old
    share = np.clip(((rgb - old) @ axis) / float(axis @ axis), 0, 1)[..., None]  # 0 = background, 1 = ink
    out = face.copy()
    pixels = pygame.surfarray.pixels3d(out)
    pixels[:] = np.clip(new + (ink - new) * share, 0, 255).astype(np.uint8)
    del pixels
    return out


def whole_face(name: str) -> pygame.Surface:
    art = pygame.image.load(str(SOURCE / name)).convert_alpha()
    return round_off(pygame.transform.smoothscale(art, (FACE, FACE)))


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    ORBS_DIR.mkdir(parents=True, exist_ok=True)
    faces = {tid: crop_face(name, box) for tid, (name, box) in ARTWORK.items()}
    faces.update({tid: whole_face(name) for tid, name in WHOLE_ARTWORK.items()})
    for tid, (old_bg, new_bg) in RECOLOR.items():
        faces[tid] = recolor(faces[tid], old_bg, new_bg)
    for tid, face in faces.items():
        pygame.image.save(face, str(ORBS_DIR / f"{tid}.png"))
        print("wrote", tid)


if __name__ == "__main__":
    main()
