"""Persian (RTL) + Latin text rendering for pygame, with Latin digits everywhere.

Backends for Persian runs:
  harfbuzz  - pygame-ce Font.set_script("Arab") + set_direction(RTL): SDL_ttf shapes with HarfBuzz (best).
  reshaper  - arabic_reshaper presentation forms, reversed (fallback for builds without HarfBuzz).
Mixed strings are split into RTL and LTR runs (a tiny bidi pass), rendered separately and laid out
right-to-left, so Latin digits inside Persian text keep their correct order.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

import pygame

from ..paths import FONTS_DIR

log = logging.getLogger(__name__)

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
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
               outline_color=(0, 0, 0)) -> pygame.Surface:
        text = latin_digits(str(text))
        color = tuple(int(c) for c in color[:3])
        ck = (text, int(size), color, key, outline, tuple(outline_color), self.backend, self.cfg.get(f"fonts.{key}", key))
        surf = self.cache.get(ck)
        if surf is not None:
            self.cache.move_to_end(ck)
            return surf
        surf = self._compose(text, int(size), color, key)
        if outline > 0:
            surf = self._outline(text, int(size), surf, outline, outline_color, key)
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

    def _outline(self, text, size, surf, r, ocol, key) -> pygame.Surface:
        base = self._compose(text, size, ocol, key)
        w, h = surf.get_width() + 2 * r, surf.get_height() + 2 * r
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r + 1:
                    out.blit(base, (r + dx, r + dy))
        out.blit(surf, (r, r))
        return out

    def clear(self) -> None:
        self.cache.clear()
        self.fonts.clear()
        self.backend = self._choose_backend()
