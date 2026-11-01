"""Per-key output through an OpenRGB SDK server (``openrgb --server``).

This is the backend that gives *real* per-key games on any keyboard OpenRGB can
drive in Direct mode — including a GMK67 flashed with OpenRGB-enabled QMK. It
speaks the OpenRGB network protocol directly (protocol version 0, which every
server still accepts), so no Python dependency is needed.
"""
from __future__ import annotations

import re
import socket
import struct
import time

from ..color import Frame
from ..layout import Layout
from . import Backend

MAGIC = b"ORGB"
REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
UPDATE_LEDS = 1050
SET_CUSTOM_MODE = 1100
DEVICE_TYPE_KEYBOARD = 5

# OpenRGB LED name (lower-cased, after "Key: ") -> layout key id
_ALIASES = {
    "escape": "ESC", "esc": "ESC", "-": "MINUS", "=": "EQUAL", "backspace": "BSPC",
    "tab": "TAB", "[": "LBRC", "]": "RBRC", "\\ (ansi)": "BSLS", "\\": "BSLS",
    "caps lock": "CAPS", ";": "SCLN", "'": "QUOT", "enter": "ENTER",
    "left shift": "LSHIFT", ",": "COMMA", ".": "DOT", "/": "SLASH",
    "right shift": "RSHIFT", "up arrow": "UP", "left control": "LCTRL",
    "left windows": "LGUI", "left alt": "LALT", "space": "SPACE", "right alt": "RALT",
    "right fn": "FN", "left fn": "FN", "fn": "FN", "left arrow": "LEFT",
    "down arrow": "DOWN", "right arrow": "RIGHT", "delete": "DEL", "page up": "PGUP",
    "page down": "PGDN",
}


def led_name_to_key(name: str, layout: Layout) -> str | None:
    n = re.sub(r"^key:\s*", "", name.strip().lower())
    kid = _ALIASES.get(n) or n.upper()
    return kid if kid in layout else None


class _Reader:
    def __init__(self, data: bytes):
        self.d, self.i = data, 0

    def take(self, fmt: str):
        v = struct.unpack_from("<" + fmt, self.d, self.i)
        self.i += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def skip(self, n: int) -> None:
        self.i += n

    def string(self) -> str:
        n = self.take("H")
        s = self.d[self.i:self.i + n].rstrip(b"\x00").decode("utf-8", "replace")
        self.i += n
        return s


def parse_controller(data: bytes) -> dict:
    """Parse a protocol-0 ``REQUEST_CONTROLLER_DATA`` reply."""
    r = _Reader(data)
    r.take("I")                                   # data_size
    dev = {"type": r.take("i"), "name": r.string()}
    for field in ("description", "version", "serial", "location"):
        dev[field] = r.string()
    num_modes = r.take("H")
    r.take("i")                                   # active mode
    for _ in range(num_modes):
        r.string()
        r.take("iIIIIIIII")                       # value..color_mode
        r.skip(4 * r.take("H"))                   # mode colours
    for _ in range(r.take("H")):                  # zones
        r.string()
        r.take("iIII")
        r.skip(r.take("H"))                       # optional matrix map blob
    dev["leds"] = []
    for _ in range(r.take("H")):
        dev["leds"].append(r.string())
        r.take("I")
    return dev


class OpenRGBClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6742, timeout: float = 2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, dev: int, pkt: int, payload: bytes = b"") -> None:
        self.sock.sendall(MAGIC + struct.pack("<III", dev, pkt, len(payload)) + payload)

    def recv(self) -> tuple[int, int, bytes]:
        hdr = self._exact(16)
        if hdr[:4] != MAGIC:
            raise IOError("bad OpenRGB packet header")
        dev, pkt, size = struct.unpack("<III", hdr[4:])
        return dev, pkt, self._exact(size)

    def _exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise IOError("OpenRGB server closed the connection")
            buf += chunk
        return buf

    def request(self, dev: int, pkt: int, payload: bytes = b"") -> bytes:
        self.send(dev, pkt, payload)
        while True:
            _d, p, data = self.recv()
            if p == pkt:
                return data

    def controllers(self) -> list[dict]:
        count = struct.unpack("<I", self.request(0, REQUEST_CONTROLLER_COUNT))[0]
        return [parse_controller(self.request(i, REQUEST_CONTROLLER_DATA)) for i in range(count)]

    def update_leds(self, dev: int, colors: list[tuple[int, int, int]]) -> None:
        body = struct.pack("<H", len(colors)) + b"".join(bytes((r, g, b, 0)) for r, g, b in colors)
        self.send(dev, UPDATE_LEDS, struct.pack("<I", 4 + len(body)) + body)

    def close(self) -> None:
        self.sock.close()


class OpenRGBBackend(Backend):
    name = "openrgb"

    def __init__(self, layout: Layout, host: str, port: int, device: str | None = None,
                 max_fps: float = 60.0):
        self.layout, self.host, self.port, self.device = layout, host, port, device
        self.min_dt = 1.0 / max_fps
        self._last_sent = 0.0
        self._last_colors: list | None = None

    def open(self) -> None:
        self.client = OpenRGBClient(self.host, self.port)
        self.client.send(0, SET_CLIENT_NAME, b"gmk67-led-arcade\x00")
        devs = self.client.controllers()
        pick = None
        for i, d in enumerate(devs):
            if self.device and self.device.lower() in d["name"].lower():
                pick = i
                break
            if not self.device and d["type"] == DEVICE_TYPE_KEYBOARD and pick is None:
                pick = i
        if pick is None:
            names = ", ".join(d["name"] for d in devs) or "none"
            raise RuntimeError(f"no matching OpenRGB keyboard (found: {names})")
        self.dev_index = pick
        self.led_keys = [led_name_to_key(n, self.layout) for n in devs[pick]["leds"]]
        mapped = sum(k is not None for k in self.led_keys)
        if mapped == 0:
            raise RuntimeError(f"OpenRGB device {devs[pick]['name']!r} has no recognisable key LEDs")
        self.client.send(pick, SET_CUSTOM_MODE)   # switch device to Direct/Custom mode
        self.description = f"{devs[pick]['name']} ({mapped} keys mapped)"

    def update(self, frame: Frame, status: list[str], now: float) -> None:
        colors = [frame.get(k, (0, 0, 0)) if k else (0, 0, 0) for k in self.led_keys]
        if colors == self._last_colors or now - self._last_sent < self.min_dt:
            return
        self.client.update_leds(self.dev_index, colors)
        self._last_colors, self._last_sent = colors, now

    def close(self) -> None:
        try:
            self.client.update_leds(self.dev_index, [(0, 0, 0)] * len(self.led_keys))
            time.sleep(0.05)
            self.client.close()
        except Exception:
            pass
