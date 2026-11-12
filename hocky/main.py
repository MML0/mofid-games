#!/usr/bin/env python3
"""Land Hockey (لند هاکی): run the game.

    python main.py                      # fullscreen, using config/settings.json
    python main.py --windowed           # windowed (development)
    python main.py --screenshot-states out/   # headless PNGs of every state
    python main.py --export-icons out/        # power-up badge PNGs
    python main.py --selftest-text out/       # Persian text rendering check
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a console without Persian letters must never stop the game
        if stream is not None:
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="Land Hockey (لند هاکی)")
    ap.add_argument("--windowed", action="store_true", help="run in a window instead of fullscreen")
    ap.add_argument("--config", type=Path, default=None, help="settings JSON (default config/settings.json)")
    ap.add_argument("--seed", type=int, default=None, help="random seed")
    ap.add_argument("--seconds", type=float, default=None, help="quit after N seconds (smoke test)")
    ap.add_argument("--screenshot-states", type=Path, metavar="DIR")
    ap.add_argument("--export-icons", type=Path, metavar="DIR")
    ap.add_argument("--selftest-text", type=Path, metavar="DIR")
    args = ap.parse_args()

    from land_hockey import app
    from land_hockey.paths import SETTINGS_PATH, install_crash_log

    install_crash_log("game")

    if args.screenshot_states:
        for p in app.capture_states(args.screenshot_states, seed=args.seed or 7):
            print(p)
        return 0
    if args.export_icons:
        for p in app.export_icons(args.export_icons):
            print(p)
        return 0
    if args.selftest_text:
        for p in app.selftest_text(args.selftest_text):
            print(p)
        return 0
    if not SETTINGS_PATH.exists():
        from land_hockey.config.generate_defaults import main as gen
        gen()
    game = app.GameApp(config_path=args.config or SETTINGS_PATH, windowed=args.windowed, seed=args.seed)
    try:
        game.run(seconds=args.seconds)
    except KeyboardInterrupt:
        game.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
