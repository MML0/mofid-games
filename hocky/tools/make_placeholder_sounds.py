#!/usr/bin/env python3
"""(Re)generate the placeholder sound effects in assets/sounds/ (standard library only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from land_hockey.audio.synth import generate_all  # noqa: E402
from land_hockey.paths import SOUNDS_DIR  # noqa: E402

if __name__ == "__main__":
    for p in generate_all(SOUNDS_DIR, overwrite="--force" in sys.argv):
        print(p)
