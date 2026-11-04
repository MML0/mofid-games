"""Just enough OSC 1.0 for the LiDAR link: encode a message, decode messages and bundles. No dependencies.

Supports the argument types trackers send: i (int32), f (float32), d (float64), h (int64), s (string), T / F / N.
"""

from __future__ import annotations

import struct

_SIZES = {"i": (">i", 4), "f": (">f", 4), "d": (">d", 8), "h": (">q", 8)}


def _pad(n: int) -> int:
    return (n + 4) & ~3  # a string's length with its terminating zero, rounded up to 4


def _string(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(b"\0", pos)
    return data[pos:end].decode("utf-8"), pos + _pad(end - pos)


def encode(address: str, args) -> bytes:
    """One OSC message. ints become i, floats f, strings s, bools T / F."""
    tags, body = ",", b""
    for a in args:
        if isinstance(a, bool):
            tags += "T" if a else "F"
        elif isinstance(a, int):
            tags += "i"
            body += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            body += struct.pack(">f", a)
        else:
            raw = str(a).encode("utf-8")
            tags += "s"
            body += raw + b"\0" * (_pad(len(raw)) - len(raw))

    def text(s: str) -> bytes:
        raw = s.encode("utf-8")
        return raw + b"\0" * (_pad(len(raw)) - len(raw))

    return text(address) + text(tags) + body


def decode(data: bytes, depth: int = 0) -> list[tuple[str, list]]:
    """Every message in a packet as (address, args). Raises ValueError (or IndexError / struct.error) if malformed."""
    if data.startswith(b"#bundle\0"):
        if depth > 4:
            raise ValueError("bundles nested too deep")
        out, pos = [], 16  # "#bundle\0" and the 8-byte time tag
        while pos + 4 <= len(data):
            (size,) = struct.unpack_from(">i", data, pos)
            pos += 4
            if size < 0 or pos + size > len(data):
                raise ValueError("bad bundle element size")
            out += decode(data[pos:pos + size], depth + 1)
            pos += size
        return out
    address, pos = _string(data, 0)
    if not address.startswith("/"):
        raise ValueError("not an OSC address")
    if pos >= len(data):
        return [(address, [])]
    tags, pos = _string(data, pos)
    if not tags.startswith(","):
        raise ValueError("no type tags")
    args = []
    for t in tags[1:]:
        if t in _SIZES:
            fmt, n = _SIZES[t]
            args.append(struct.unpack_from(fmt, data, pos)[0])
            pos += n
        elif t == "s":
            s, pos = _string(data, pos)
            args.append(s)
        elif t in "TFN":
            args.append({"T": True, "F": False, "N": None}[t])
        else:
            raise ValueError(f"unsupported OSC type {t!r}")
    return [(address, args)]


class UDPClient:
    """Drop-in for python-osc's SimpleUDPClient (send_message only), so the tracker runs without python-osc."""

    def __init__(self, address: str, port: int):
        import socket

        self.target = (address, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_message(self, address: str, value) -> None:
        args = value if isinstance(value, (list, tuple)) else [value]
        try:
            self.sock.sendto(encode(address, args), self.target)
        except OSError:  # nobody listening yet, or the network went away: the next frame tries again
            pass
