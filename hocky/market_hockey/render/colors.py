"""Color helpers."""

from __future__ import annotations

import colorsys


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = str(h).lstrip("#")
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return (255, 255, 255)


def scale(c, k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


def mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def boost(c, amount: float) -> tuple[int, int, int]:
    """Lift value/saturation for projection while keeping the hue."""
    r, g, b = (v / 255 for v in c[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    v = min(1.0, v + (1 - v) * amount * 1.2)
    s = min(1.0, s + (1 - s) * amount * 0.3)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def delta_e(a, b) -> float:
    """CIE76 color difference (good enough to warn about confusable colors)."""
    return ((_lab(a)[0] - _lab(b)[0]) ** 2 + (_lab(a)[1] - _lab(b)[1]) ** 2 + (_lab(a)[2] - _lab(b)[2]) ** 2) ** 0.5


def _lab(c):
    def lin(v):
        v /= 255
        return ((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92

    r, g, b = (lin(v) for v in c[:3])
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)
