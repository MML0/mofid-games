"""
Local UDP link between the engine (floor_game.py, owns the lidar) and the
setup window (lidar_setup.py). JSON only (no pickle): numpy arrays are sent
as base64 float32 / uint8.

    engine -> setup   127.0.0.1:7011   state of every frame (points of every new scan)
    setup  -> engine  127.0.0.1:7012   {"cmd": "set", "values": {...}, "final": bool}
                                       {"cmd": "rescan"}
"""

import base64
import json
import socket

import numpy as np


HOST = "127.0.0.1"
SETUP_PORT = 7011
ENGINE_PORT = 7012
MAX_PACKET = 60000


def pack_array(a, dtype=np.float32):

    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode("ascii")


def unpack_array(s, dtype=np.float32):

    return np.frombuffer(base64.b64decode(s), dtype=dtype)



class Endpoint:

    def __init__(self, listen_port, send_port):

        self.send_to = (HOST, send_port)
        self.out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.inp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            self.inp.bind((HOST, listen_port))
            self.inp.setblocking(False)
            self.listening = True
        except OSError as e:
            print(f"Link: port {listen_port} busy ({e}); is another copy running?")
            self.listening = False


    def send(self, message):

        data = json.dumps(message, separators=(",", ":")).encode("utf-8")

        if len(data) > MAX_PACKET:
            return False

        try:
            self.out.sendto(data, self.send_to)
            return True
        except OSError:
            return False


    def receive(self):
        """All waiting messages (oldest first)."""

        out = []

        if not self.listening:
            return out

        while True:
            try:
                data, _ = self.inp.recvfrom(65535)
            except (BlockingIOError, ConnectionResetError):
                break
            except OSError:
                break

            try:
                out.append(json.loads(data.decode("utf-8")))
            except ValueError:
                pass

        return out


    def close(self):

        self.out.close()
        self.inp.close()
