#!/usr/bin/env python3
"""The LiDAR foot tracker (LIdar/floor_game.py), started by the game when a player's input is "lidar".

    python lidar_tracker.py --port COM4 --osc-port 7000 --headless
    python lidar_tracker.py --replay LIdar/samples/session_2players.pkl --settings LIdar/samples/session_2players.settings.json --loop

Every option is floor_game.py's (see LIdar/docs/INTEGRATION.md), plus --parent PID: the tracker quits when that
process ends, so a crashed game never leaves the LiDAR's serial port held. In the Windows build this file is
LidarTracker.exe; when the tracker opens its setup window it starts the same .exe with lidar_setup.py, and that is
sent to the setup window here. The LIdar folder itself is used as it was delivered.
"""

import os
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
sys.path.insert(0, os.path.join(HERE, "LIdar"))
sys.path.insert(1, HERE)


def _watch_parent(pid: int) -> None:
    """Quit at once when the game is gone, however it ended."""
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if handle:
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            os._exit(0)
        return
    while True:
        if os.getppid() != pid:
            os._exit(0)
        time.sleep(0.5)


def _shims() -> None:
    """Stand-ins for the two packages the tracker imports, when they are not installed. python-osc is only used to
    send, which the game's own OSC code does as well; pyserial is only needed for the real LiDAR, not a replay."""
    try:
        import pythonosc.udp_client  # noqa: F401
    except ImportError:
        from land_hockey.inputs.osc import UDPClient

        pkg = types.ModuleType("pythonosc")
        client = types.ModuleType("pythonosc.udp_client")
        client.SimpleUDPClient = UDPClient
        pkg.udp_client = client
        sys.modules.update({"pythonosc": pkg, "pythonosc.udp_client": client})
    try:
        import serial  # noqa: F401
    except ImportError:
        stub = types.ModuleType("serial")

        class SerialException(Exception):
            pass

        def missing(*_a, **_k):
            raise SerialException("pyserial is not installed: pip install pyserial")

        stub.Serial = missing
        stub.SerialException = SerialException
        sys.modules["serial"] = stub


def find_port() -> str | None:
    """The LiDAR's serial port: its USB adapter is a Silicon Labs CP210x. None if it is not plugged in."""
    from serial.tools import list_ports

    ports = list(list_ports.comports())
    for p in ports:
        text = f"{p.device} {p.description} {p.manufacturer or ''}".lower()
        if p.vid == 0x10C4 or "cp210" in text or "silicon labs" in text:
            return p.device.replace("/dev/tty.", "/dev/cu.")  # macOS: the call-out device does not wait for a carrier
    usb = [p.device for p in ports if "usbserial" in p.device.lower() or "ttyusb" in p.device.lower()]
    return usb[0].replace("/dev/tty.", "/dev/cu.") if usb else None


def main() -> None:
    args = sys.argv[1:]
    if "--parent" in args:
        i = args.index("--parent")
        try:
            pid = int(args[i + 1])
            threading.Thread(target=_watch_parent, args=(pid,), daemon=True).start()
        except (IndexError, ValueError):
            pass
        del args[i:i + 2]
    _shims()
    if args and os.path.basename(args[0]) == "lidar_setup.py":  # the tracker opening its setup window
        sys.argv = args
        import lidar_setup

        lidar_setup.main()
        return
    if "--port" in args and args[args.index("--port") + 1:args.index("--port") + 2] == ["auto"]:
        i = args.index("--port")
        try:
            port = find_port()
        except ImportError:
            port = None
        if port is None:
            print("No LiDAR found: plug in its USB cable, or set the serial port by hand (COM4, /dev/cu.usbserial-...)")
            sys.exit(2)
        print(f"LiDAR found on {port}")
        args[i + 1] = port
    sys.argv = ["floor_game.py"] + args
    import floor_game

    floor_game.main()


if __name__ == "__main__":
    main()
