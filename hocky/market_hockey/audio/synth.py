"""Placeholder sound effects synthesized with the standard library only (wave + math)."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050


def _write(path: Path, samples) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))


def _env(i, n, a=0.005, r=0.5):
    t = i / RATE
    dur = n / RATE
    att = min(1.0, t / a) if a > 0 else 1.0
    rel = max(0.0, 1 - max(0.0, t - (dur - dur * r)) / (dur * r)) if r > 0 else 1.0
    return att * rel


def tone(freqs, dur, vol=0.5, wave_="sine", decay=6.0, noise=0.0, sweep=0.0):
    n = int(RATE * dur)
    rnd = random.Random(1)
    out = []
    phase = [0.0] * len(freqs)
    for i in range(n):
        t = i / RATE
        s = 0.0
        for k, f in enumerate(freqs):
            ff = f * (1 + sweep * t / dur)
            phase[k] += 2 * math.pi * ff / RATE
            p = phase[k]
            if wave_ == "square":
                v = 1.0 if math.sin(p) >= 0 else -1.0
            elif wave_ == "tri":
                v = 2 / math.pi * math.asin(math.sin(p))
            else:
                v = math.sin(p)
            s += v / len(freqs)
        if noise:
            s = s * (1 - noise) + rnd.uniform(-1, 1) * noise
        s *= vol * math.exp(-decay * t) * _env(i, n, 0.004, 0.2)
        out.append(s)
    return out


def seq(parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


SOUNDS = {
    "hit_low": lambda: tone([392, 784], 0.12, 0.6, "tri", 22),
    "hit_mid": lambda: tone([523, 1046], 0.11, 0.6, "tri", 24),
    "hit_high": lambda: tone([698, 1396], 0.10, 0.6, "tri", 26),
    "wall": lambda: tone([180, 90], 0.14, 0.55, "sine", 18, noise=0.15),
    "good": lambda: seq([tone([660], 0.07, 0.5, "tri", 8), tone([880], 0.07, 0.5, "tri", 8), tone([1320], 0.16, 0.5, "tri", 9)]),
    "bad": lambda: tone([300, 305], 0.38, 0.45, "square", 5, sweep=-0.45),
    "spawn": lambda: tone([1200], 0.10, 0.25, "sine", 18, sweep=0.4),
    "effect_end": lambda: tone([700], 0.14, 0.3, "sine", 12, sweep=-0.4),
    "goal": lambda: seq([tone([523, 659, 784], 0.16, 0.6, "tri", 4), tone([659, 784, 1046], 0.42, 0.6, "tri", 3, noise=0.05)]),
    "beep": lambda: tone([880], 0.14, 0.5, "sine", 6),
    "go": lambda: tone([1320, 1760], 0.45, 0.55, "tri", 3),
    "tick": lambda: tone([1500], 0.04, 0.35, "sine", 30),
    "end": lambda: seq([tone([784], 0.16, 0.5, "tri", 5), tone([659], 0.16, 0.5, "tri", 5), tone([523, 1046], 0.55, 0.55, "tri", 3)]),
    "smart": lambda: seq([tone([1568], 0.05, 0.4, "sine", 10), tone([2093], 0.05, 0.4, "sine", 10), tone([2637], 0.14, 0.4, "sine", 9)]),
    "shield": lambda: tone([440, 880, 1320], 0.25, 0.45, "tri", 8, noise=0.1),
    "split": lambda: tone([900, 1350], 0.16, 0.45, "tri", 10, sweep=0.3),
}


def generate_all(directory: Path, overwrite: bool = False) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    made = []
    for name, fn in SOUNDS.items():
        p = directory / f"{name}.wav"
        if overwrite or not p.exists():
            _write(p, fn())
            made.append(p)
    return made
