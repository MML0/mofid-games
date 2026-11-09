"""Persian (RTL) + Latin text rendering for pygame, with Latin digits everywhere.

Backends for Persian runs:
  harfbuzz  - pygame-ce Font.set_script("Arab") + set_direction(RTL): SDL_ttf shapes with HarfBuzz (best).
  reshaper  - arabic_reshaper presentation forms, reversed (fallback for builds without HarfBuzz).
Mixed strings are split into RTL and LTR runs (a tiny bidi pass), rendered separately and laid out
right-to-left, so Latin digits inside Persian text keep their correct order.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict

import pygame

from ..paths import FONTS_DIR

log = logging.getLogger(__name__)

# Latin digits, and the Persian ی / ک for the Arabic ي / ك that an Arabic keyboard types (ي shows two dots at a word's end)
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩\u064a\u0643", "01234567890123456789\u06cc\u06a9")
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
_JOINERS = set(".,:/%×+-")


def latin_digits(s: str) -> str:
    return s.translate(_FA_DIGITS)


def is_rtl_char(ch: str) -> bool:
    o = ord(ch)
    return 0x0590 <= o <= 0x08FF or 0xFB1D <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def has_rtl(s: str) -> bool:
    return any(is_rtl_char(c) for c in s)


def _is_ltr(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def split_runs(text: str) -> list[tuple[bool, str]]:
    """Split into (is_rtl, chunk) runs in logical order (paragraph direction RTL)."""
    runs: list[tuple[bool, str]] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _is_ltr(ch):
            j = i + 1
            while j < n and (_is_ltr(text[j]) or (text[j] in _JOINERS and j + 1 < n and _is_ltr(text[j + 1]))
                             or (text[j] == " " and j + 1 < n and _is_ltr(text[j + 1]) and not has_rtl(text[j:]))):
                j += 1
            runs.append((False, text[i:j]))
            i = j
        else:
            j = i + 1
            while j < n and not _is_ltr(text[j]):
                j += 1
            runs.append((True, text[i:j]))
            i = j
    return runs


class TextRenderer:
    def __init__(self, cfg, max_cache: int = 600):
        self.cfg = cfg
        self.fonts: dict = {}
        self.cache: OrderedDict = OrderedDict()
        self.max_cache = max_cache
        self.backend = self._choose_backend()
        log.info("Persian text backend: %s", self.backend)

    def _choose_backend(self) -> str:
        pref = self.cfg["text.shaping_backend"]
        probe = pygame.font.Font(None, 12)
        hb = hasattr(probe, "set_script") and hasattr(probe, "set_direction") and hasattr(pygame, "DIRECTION_RTL")
        if pref == "harfbuzz" and hb:
            return "harfbuzz"
        if pref == "reshaper" or not hb:
            try:
                import arabic_reshaper  # noqa: F401
                return "reshaper"
            except ImportError:
                return "harfbuzz" if hb else "none"
        return "harfbuzz"

    def font(self, key: str, size: int, rtl: bool) -> pygame.font.Font:
        fname = self.cfg.get(f"fonts.{key}", key)
        size = max(4, int(size))
        k = (fname, size, rtl and self.backend == "harfbuzz")
        f = self.fonts.get(k)
        if f is None:
            path = FONTS_DIR / fname
            try:
                f = pygame.font.Font(str(path), size)
            except (FileNotFoundError, OSError, pygame.error):
                log.warning("font %s missing; using the default font", path)
                f = pygame.font.Font(None, size)
            if k[2]:
                try:
                    f.set_script("Arab")
                    f.set_direction(pygame.DIRECTION_RTL)
                except (AttributeError, pygame.error):
                    pass
            self.fonts[k] = f
        return f

    def _shape_reshaper(self, run: str) -> str:
        import arabic_reshaper

        return arabic_reshaper.reshape(run)[::-1].translate(_MIRROR)

    def _render_run(self, run: str, rtl: bool, key: str, size: int, color) -> pygame.Surface:
        if rtl:
            f = self.font(key, size, True)
            txt = self._shape_reshaper(run) if self.backend == "reshaper" else run
        else:
            f = self.font("digits" if run.strip().isdigit() else ("latin" if key == "persian" else key), size, False)
            txt = run
        return f.render(txt, True, color)

    def render(self, text: str, size: int, color, key: str = "persian", outline: int = 0,
               outline_color=(0, 0, 0), glow: float = 0.0) -> pygame.Surface:
        """outline > 0 adds a soft blurred drop shadow; glow > 0 adds a blurred neon halo in the text color."""
        text = latin_digits(str(text))
        color = tuple(int(c) for c in color[:3])
        shadow_a = self.cfg["text.shadow_alpha"] if outline else 0.0
        ck = (text, int(size), color, key, outline, tuple(outline_color), round(glow, 2), round(shadow_a, 2),
              self.backend, self.cfg.get(f"fonts.{key}", key))
        surf = self.cache.get(ck)
        if surf is not None:
            self.cache.move_to_end(ck)
            return surf
        surf = self._compose(text, int(size), color, key)
        if shadow_a > 0 or glow > 0:
            surf = self._effects(text, int(size), surf, shadow_a, tuple(outline_color), key, glow, color)
        self.cache[ck] = surf
        if len(self.cache) > self.max_cache:
            self.cache.popitem(last=False)
        return surf

    def _compose(self, text: str, size: int, color, key: str) -> pygame.Surface:
        if not text:
            return pygame.Surface((1, 1), pygame.SRCALPHA)
        if not has_rtl(text):
            f = self.font("digits" if text.strip().replace(":", "").replace("+", "").isdigit() else
                          ("latin" if key == "persian" else key), size, False)
            return f.render(text, True, color)
        parts = [self._render_run(chunk, rtl, key, size, color) for rtl, chunk in split_runs(text)]
        parts.reverse()  # visual order for an RTL paragraph
        w = sum(p.get_width() for p in parts)
        h = max(p.get_height() for p in parts)
        out = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        x = 0
        for p in parts:
            out.blit(p, (x, (h - p.get_height()) // 2))
            x += p.get_width()
        return out

    @staticmethod
    def _blur(src: pygame.Surface, radius: int, fill) -> pygame.Surface:
        """Smooth blur via an image pyramid: halve repeatedly, then double back up (gaussian-like, no blockiness)."""
        w, h = src.get_size()
        levels = max(1, min(5, int(round(math.log2(max(2, radius))))))
        s = src
        sizes = []
        for _ in range(levels):
            sizes.append(s.get_size())
            nw, nh = max(1, s.get_width() // 2), max(1, s.get_height() // 2)
            s = pygame.transform.smoothscale(s, (nw, nh))
        for size in reversed(sizes):
            s = pygame.transform.smoothscale(s, size)
        return s

    def _effects(self, text, size, surf, shadow_a, scol, key, glow, color) -> pygame.Surface:
        pad = max(6, int(size * (0.27 if shadow_a > 0 else 0.22)))
        W, H = surf.get_width() + 2 * pad, surf.get_height() + 2 * pad
        out = pygame.Surface((W, H), pygame.SRCALPHA)
        out.fill((*color, 0))
        if shadow_a > 0:
            # a drop shadow the way light makes one: wide, soft and a little below, plus a faint close one that
            # seats the letters. No dark rim hugging the strokes.
            dark = self._compose(text, size, scol, key)
            for radius, drop, share in ((0.13, 0.06, 0.8), (0.04, 0.025, 0.4)):
                base = pygame.Surface((W, H), pygame.SRCALPHA)
                base.fill((*scol, 0))  # same RGB in transparent pixels: no dark/light fringes when blurring
                base.blit(dark, (pad, pad + max(1, int(size * drop))))
                sh = self._blur(base, max(2, int(size * radius)), scol)
                sh.set_alpha(int(255 * min(1.0, shadow_a * share)))
                out.blit(sh, (0, 0))
        if glow > 0:
            base = pygame.Surface((W, H), pygame.SRCALPHA)
            base.fill((*color, 0))
            base.blit(surf, (pad, pad))
            g = self._blur(base, max(2, int(size * 0.12)), color)
            g.set_alpha(int(255 * min(1.0, glow)))
            out.blit(g, (0, 0))
            if glow > 1.0:
                g.set_alpha(int(255 * min(1.0, glow - 1.0)))
                out.blit(g, (0, 0))
        out.blit(surf, (pad, pad))
        return out

    def clear(self) -> None:
        self.cache.clear()
        self.fonts.clear()
        self.backend = self._choose_backend()
