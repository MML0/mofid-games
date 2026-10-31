"""Live link between the control panel and the running game: JSON over UDP on localhost.

panel -> game:  {"type":"set","path":...,"value":...,"seq":n}
                {"type":"set_many","values":{...}}
                {"type":"command","name":...,"args":{...}}
                {"type":"hello"}
game  -> panel: {"type":"state", ...telemetry...}   {"type":"ack","seq":n,"ok":bool,"warning":...}
"""

from __future__ import annotations

import json
import logging
import socket
import time

log = logging.getLogger(__name__)
HOST = "127.0.0.1"
MAX_DATAGRAM = 8000  # macOS refuses UDP datagrams over 9216 bytes by default


def _encode(msg: dict) -> bytes:
    return json.dumps(msg, ensure_ascii=False).encode("utf-8")


def _decode(data: bytes) -> dict | None:
    try:
        msg = json.loads(data.decode("utf-8"))
        return msg if isinstance(msg, dict) else None
    except (UnicodeDecodeError, ValueError):
        return None


class LiveLinkServer:
    """Game side. Non-blocking; poll() once per frame."""

    def __init__(self, port: int):
        self.port = port
        self.clients: dict[tuple, float] = {}
        self.sock: socket.socket | None = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((HOST, port))
            s.setblocking(False)
            self.sock = s
            self.port = s.getsockname()[1]
            log.info("live link listening on %s:%d", HOST, port)
        except OSError as exc:
            log.warning("live link disabled (port %d): %s", port, exc)

    @property
    def ok(self) -> bool:
        return self.sock is not None

    def poll(self) -> list[tuple[dict, tuple]]:
        out = []
        if not self.sock:
            return out
        for _ in range(500):
            try:
                data, addr = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except ConnectionResetError:  # Windows reports ICMP port-unreachable on UDP; just skip it
                continue
            except OSError:
                break
            msg = _decode(data)
            if msg is not None:
                self.clients[addr] = time.monotonic()
                out.append((msg, addr))
        return out

    def send(self, msg: dict, addr: tuple) -> None:
        if self.sock:
            try:
                self.sock.sendto(_encode(msg), addr)
            except OSError:
                pass

    def broadcast(self, msg: dict) -> None:
        now = time.monotonic()
        for addr, seen in list(self.clients.items()):
            if now - seen > 6.0:
                del self.clients[addr]
                continue
            self.send(msg, addr)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None


class LiveLinkClient:
    """Control panel side."""

    def __init__(self, game_port: int):
        self.game_addr = (HOST, game_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((HOST, 0))
        self.sock.setblocking(False)
        self.last_state_time = 0.0
        self.seq = 0
        self.warnings: list[str] = []

    def send(self, msg: dict) -> None:
        data = _encode(msg)
        if len(data) > MAX_DATAGRAM:
            if msg.get("type") == "set_many" and len(msg["values"]) > 1:
                items = list(msg["values"].items())
                half = len(items) // 2
                self.send({"type": "set_many", "values": dict(items[:half])})
                self.send({"type": "set_many", "values": dict(items[half:])})
                return
            name = msg.get("path") or ", ".join(msg.get("values", {})) or msg.get("type")
            self.warnings.append(f"{name} is too large to apply live: press Save and restart the game")
            log.warning(self.warnings[-1])
            return
        try:
            self.sock.sendto(data, self.game_addr)
        except OSError:
            pass

    def take_warnings(self) -> list[str]:
        out, self.warnings = self.warnings, []
        return out

    def set(self, path: str, value) -> None:
        self.seq += 1
        self.send({"type": "set", "path": path, "value": value, "seq": self.seq})

    def set_many(self, values: dict) -> None:
        self.send({"type": "set_many", "values": values})

    def command(self, name: str, **args) -> None:
        self.send({"type": "command", "name": name, "args": args})

    def hello(self) -> None:
        self.send({"type": "hello"})

    def poll(self) -> list[dict]:
        out = []
        for _ in range(200):
            try:
                data, _ = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except ConnectionResetError:  # Windows reports ICMP port-unreachable on UDP; just skip it
                continue
            except OSError:
                break
            msg = _decode(data)
            if msg is not None:
                if msg.get("type") == "state":
                    self.last_state_time = time.monotonic()
                out.append(msg)
        return out

    @property
    def connected(self) -> bool:
        return time.monotonic() - self.last_state_time < 2.0

    def close(self) -> None:
        self.sock.close()
