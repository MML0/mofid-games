"""Every input source the game knows, as "module:Class" inside market_hockey.inputs (imported on first use).

To add a sensor (a LiDAR, a depth camera, ...): write one InputAdapter subclass in its own file and add one line here.
The control panel's dropdown, the JSON validation and tests/test_input_contract.py pick it up automatically.
"""

from __future__ import annotations

import importlib

ADAPTERS = {
    "keyboard": "keyboard:KeyboardAdapter",
    "ai": "ai:AIAdapter",
    "mouse": "mouse:MouseAdapter",
    "network": "network:NetworkAdapter",
    "lidar": "lidar:LidarAdapter",
    "replay": "replay:ReplayAdapter",
}


def load(name: str):
    """The adapter class for a source name. Raises KeyError / ImportError / AttributeError if it cannot be loaded."""
    module, cls = ADAPTERS[name].split(":")
    return getattr(importlib.import_module(f"{__package__}.{module}"), cls)
