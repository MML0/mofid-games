"""Event-driven sound playback. Fails silently (with a log line) if the mixer is unavailable."""

from __future__ import annotations

import logging
import time

import pygame

from ..paths import SOUNDS_DIR
from .synth import SOUNDS, generate_all

log = logging.getLogger(__name__)

CATEGORY = {"hit_low": "hits", "hit_mid": "hits", "hit_high": "hits", "wall": "hits", "good": "powerups",
            "bad": "powerups", "spawn": "powerups", "effect_end": "powerups", "split": "powerups", "shield": "powerups",
            "goal": "match", "beep": "match", "go": "match", "tick": "match", "end": "match", "smart": "match"}


class Audio:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sounds: dict = {}
        self.last: dict = {}
        self.ok = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 256)
            missing = [n for n in SOUNDS if not (SOUNDS_DIR / f"{n}.wav").exists()]
            if missing:
                generate_all(SOUNDS_DIR)
            for name in SOUNDS:
                p = SOUNDS_DIR / f"{name}.wav"
                try:
                    self.sounds[name] = pygame.mixer.Sound(str(p))
                except (pygame.error, FileNotFoundError) as exc:
                    log.warning("sound %s unavailable: %s", p, exc)
            pygame.mixer.set_num_channels(24)
            self.ok = True
        except pygame.error as exc:
            log.warning("audio disabled: %s", exc)

    def play(self, name: str, vol: float = 1.0) -> None:
        cfg = self.cfg
        if not self.ok or not cfg["audio.enabled"]:
            return
        s = self.sounds.get(name)
        if s is None:
            return
        now = time.perf_counter()
        if now - self.last.get(name, 0) < 0.04:
            return
        self.last[name] = now
        v = cfg["audio.master"] * cfg[f"audio.{CATEGORY.get(name, 'match')}"] * vol
        if v <= 0.001:
            return
        ch = s.play()
        if ch:
            ch.set_volume(min(1.0, v))

    def handle_events(self, events) -> None:
        for e in events:
            et = e["type"]
            if et == "paddle_hit":
                sp = e.get("speed", 500)
                self.play("hit_high" if sp > 950 else "hit_mid" if sp > 600 else "hit_low")
                if e.get("smart"):
                    self.play("smart")
            elif et == "wall_bounce":
                self.play("wall", 0.7)
            elif et == "goal":
                self.play("goal", 0.5 if e.get("demo") else 1.0)
            elif et == "powerup_collected":
                self.play("bad" if e.get("cls") == "bad" else "good")
            elif et == "orb_spawned":
                self.play("spawn")
            elif et == "effect_ended" and not e.get("replaced"):
                self.play("effect_end", 0.6)
            elif et == "countdown_beat":
                self.play("go" if e["label"] == "go" else "beep", 0.8 if e["label"] == "ready" else 1.0)
            elif et == "timer_tick":
                self.play("tick")
            elif et == "match_end":
                self.play("end")
            elif et == "shield_block":
                self.play("shield")
            elif et == "ball_split":
                self.play("split")
