#!/usr/bin/env python3
"""Market Hockey control panel: every setting as a slider/field, live-linked to the running game.

    python settings_app.py
"""

from market_hockey.paths import install_crash_log
from market_hockey.ui.settings_window import main

if __name__ == "__main__":
    install_crash_log("control_panel")
    main()
