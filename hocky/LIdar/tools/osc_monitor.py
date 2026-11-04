"""
Print the OSC that floor_game.py sends, to check an integration.

    python tools/osc_monitor.py            listens on 127.0.0.1:7000
    python tools/osc_monitor.py 7001       another port

Shows one line per player, updated in place (~10 times a second), plus
/foot messages if "Send feet" is on. Only one program can listen on a UDP
port: stop the game / TouchDesigner receiver first, or send to another port.
"""

import sys
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


port = int(sys.argv[1]) if len(sys.argv) > 1 else 7000
paddles = {}
feet = {}
last = [0.0]


def on_paddle(address, player, x, y, angle, active, conf):

    paddles[player] = (x, y, angle, active, conf)
    show()


def on_foot(address, fid, x, y, player):

    feet[fid] = (x, y, player, time.time())


def show():

    if time.time() - last[0] < 0.1:
        return

    last[0] = time.time()
    now = time.time()
    live_feet = sum(1 for f in feet.values() if now - f[3] < 0.3)
    parts = [f"P{p} {'ON ' if a else 'off'} x={x:8.1f} y={y:8.1f} angle={ang:6.1f} conf={c:.2f}"
             for p, (x, y, ang, a, c) in sorted(paddles.items())]
    print("  |  ".join(parts) + (f"  |  feet {live_feet}" if feet else ""), end="\r", flush=True)


dispatcher = Dispatcher()
dispatcher.map("/paddle", on_paddle)
dispatcher.map("/foot", on_foot)

print(f"Listening for /paddle and /foot on 127.0.0.1:{port}  (Ctrl+C to stop)")

try:
    BlockingOSCUDPServer(("127.0.0.1", port), dispatcher).serve_forever()
except KeyboardInterrupt:
    print()
