"""Tiny local web server for the supervisor page (standard library only, runs on a background thread).

The HTTP threads never touch the game: they read a snapshot the main loop publishes, and push commands into
a queue the main loop applies once per frame. POSTs must be application/json, so other websites open in the
same browser cannot trigger them (cross-origin JSON needs a CORS preflight this server never grants).
"""

from __future__ import annotations

import json
import logging
import queue
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..paths import ASSETS_DIR, FONTS_DIR
from . import history

log = logging.getLogger(__name__)
WEB_DIR = ASSETS_DIR / "web"
MAX_BODY = 8192


def local_addresses() -> list[str]:
    """IPv4 addresses other devices on the network can use to reach this computer (no packets are sent)."""
    found: list[str] = []
    try:  # the address of the interface that would route to the internet / LAN
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    import ipaddress

    lan, other = [], []
    for ip in found:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified or a.is_multicast
                or a in ipaddress.ip_network("198.18.0.0/15")):  # VPN / proxy tunnels, not reachable by phones
            continue
        if ip in lan or ip in other:
            continue
        (lan if any(a in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
         else other).append(ip)
    return lan + other


class _Server(ThreadingHTTPServer):
    allow_reuse_address = sys.platform != "win32"  # on Windows it lets two servers share a port without any error


class SupervisorServer:
    def __init__(self, bind: str = "127.0.0.1", port: int = 8765, history_path=None):
        self.bind, self.port = bind, int(port)
        self.history_path = history_path
        self.commands: queue.Queue = queue.Queue()
        self._snap: dict = {}
        self._lock = threading.Lock()
        self.httpd: _Server | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.bind in ("0.0.0.0", "") else self.bind
        return f"http://{host}:{self.port}/"

    def urls(self) -> list[str]:
        """Local address first, then every network address phones/tablets can use."""
        out = [f"http://127.0.0.1:{self.port}/"]
        if self.bind in ("0.0.0.0", ""):
            out += [f"http://{ip}:{self.port}/" for ip in local_addresses()]
        return out

    def start(self) -> bool:
        server = self

        class Handler(_Handler):
            owner = server

        try:
            self.httpd = _Server((self.bind, self.port), Handler)
        except OSError as exc:
            log.warning("supervisor page disabled (port %s): %s", self.port, exc)
            return False
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="supervisor-web", daemon=True)
        self.thread.start()
        log.info("supervisor page at %s", self.url)
        return True

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def publish(self, snap: dict) -> None:
        with self._lock:
            self._snap = snap

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._snap)

    def drain(self) -> list[tuple[str, dict]]:
        out = []
        while True:
            try:
                out.append(self.commands.get_nowait())
            except queue.Empty:
                return out


class _Handler(BaseHTTPRequestHandler):
    owner: SupervisorServer = None  # set per server
    server_version = "LandHockey"

    def log_message(self, fmt, *args):  # keep the console quiet
        log.debug("web: " + fmt, *args)

    # ---- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, path: Path, ctype: str) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._json({"error": "not found"}, 404)
            return
        self._send(200, data, ctype)

    # ---- routes
    def do_GET(self):  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            self._file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif route.startswith("/fonts/"):
            name = Path(route[len("/fonts/"):]).name  # no directory traversal
            if name.lower().endswith((".ttf", ".otf")):
                self._file(FONTS_DIR / name, "font/ttf")
            else:
                self._json({"error": "not found"}, 404)
        elif route == "/api/state":
            self._json(self.owner.snapshot())
        elif route == "/api/history":
            recs = history.read_all(self.owner.history_path)
            self._json({"matches": recs[:500], "leaderboard": history.leaderboard(recs), "count": len(recs)})
        elif route == "/api/history.csv":
            body = history.to_csv(history.read_all(self.owner.history_path)).encode("utf-8-sig")
            self._send(200, body, "text/csv; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="land_hockey_history.csv"'})
        else:
            self._json({"error": "not found"}, 404)

    do_HEAD = do_GET

    def do_POST(self):  # noqa: N802
        route = self.path.split("?", 1)[0]
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._json({"error": "content-type must be application/json"}, 415)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            self._json({"error": "too large"}, 413)
            return
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            self._json({"error": "bad json"}, 400)
            return
        cmds = {"/api/names": "names", "/api/name": "name", "/api/start": "start", "/api/pause": "pause",
                "/api/reset": "reset", "/api/clear_names": "clear_names"}
        cmd = cmds.get(route)
        if cmd is None:
            self._json({"error": "not found"}, 404)
            return
        if cmd == "names":
            body = {"p1": str(body.get("p1", ""))[:40], "p2": str(body.get("p2", ""))[:40]}
        elif cmd == "name":
            try:
                idx = 1 if int(body.get("player", 0)) == 1 else 0
            except (TypeError, ValueError):
                idx = 0
            body = {"player": idx, "name": str(body.get("name", ""))[:40]}
        self.owner.commands.put((cmd, body))
        self._json({"ok": True})
