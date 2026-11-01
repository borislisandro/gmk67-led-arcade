"""Minimal, dependency-free VIA (QMK raw HID) client for Linux ``/dev/hidraw*``.

The GMK67 V2 exposes VIA on a raw-HID interface (usage page 0xFF60, usage 0x61,
32-byte reports). Each request is answered with a 32-byte reply that echoes the
command id, or ``0xFF`` (``id_unhandled``) for unknown commands.
"""
from __future__ import annotations

import glob
import os
import select
from dataclasses import dataclass

REPORT = 32

# VIA command ids (protocol v12)
GET_PROTOCOL_VERSION = 0x01
GET_KEYBOARD_VALUE = 0x02
CUSTOM_SET_VALUE = 0x07
CUSTOM_GET_VALUE = 0x08
CUSTOM_SAVE = 0x09
DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE = 0x0D
DYNAMIC_KEYMAP_MACRO_GET_BUFFER = 0x0E
DYNAMIC_KEYMAP_MACRO_SET_BUFFER = 0x0F
DYNAMIC_KEYMAP_GET_LAYER_COUNT = 0x11
DYNAMIC_KEYMAP_GET_BUFFER = 0x12
DYNAMIC_KEYMAP_SET_BUFFER = 0x13
UNHANDLED = 0xFF

# Custom-value channel 3 = QMK RGB Matrix
CH_RGB_MATRIX = 3
RGBM_BRIGHTNESS, RGBM_EFFECT, RGBM_SPEED, RGBM_COLOR = 1, 2, 3, 4

# RGB Matrix effect ids exposed by the GMK67 V2 firmware (subset)
EFFECT_NONE, EFFECT_SOLID = 0, 1

_VIA_DESCRIPTOR_PREFIX = bytes([0x06, 0x60, 0xFF, 0x09, 0x61])
GMK67_V2 = (0x36B0, 0x3068)


class ViaError(RuntimeError):
    pass


@dataclass
class HidrawInfo:
    path: str
    vid: int
    pid: int
    name: str


def find_via_devices(vid_pid: tuple[int, int] | None = None) -> list[HidrawInfo]:
    """List hidraw nodes whose report descriptor is the VIA raw-HID interface."""
    out = []
    for sysdir in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(f"{sysdir}/device/report_descriptor", "rb") as f:
                desc = f.read()
            with open(f"{sysdir}/device/uevent") as f:
                ue = dict(line.strip().split("=", 1) for line in f if "=" in line)
        except OSError:
            continue
        if not desc.startswith(_VIA_DESCRIPTOR_PREFIX):
            continue
        _bus, vid, pid = ue.get("HID_ID", "0:0:0").split(":")
        info = HidrawInfo("/dev/" + os.path.basename(sysdir), int(vid, 16), int(pid, 16),
                          ue.get("HID_NAME", "?"))
        if vid_pid is None or (info.vid, info.pid) == vid_pid:
            out.append(info)
    return out


class ViaDevice:
    def __init__(self, path: str | None = None, timeout: float = 0.5):
        if path is None:
            devs = find_via_devices(GMK67_V2) or find_via_devices()
            if not devs:
                raise ViaError("no VIA raw-HID device found (is the keyboard plugged in via USB?)")
            path = devs[0].path
        self.path = path
        self.timeout = timeout
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError as e:
            raise ViaError(f"no permission to open {path}; install udev/99-gmk67.rules "
                           "(see README) or run with sudo") from e

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- transport ------------------------------------------------------
    def send(self, *payload: int) -> None:
        """Write one report without waiting for a reply."""
        data = bytes(payload)[:REPORT]
        os.write(self.fd, b"\x00" + data + bytes(REPORT - len(data)))

    def query(self, *payload: int, timeout: float | None = None) -> bytes | None:
        """Write one report and return the 32-byte reply (``None`` on timeout)."""
        self.drain()
        self.send(*payload)
        r, _, _ = select.select([self.fd], [], [], self.timeout if timeout is None else timeout)
        return os.read(self.fd, REPORT) if r else None

    def drain(self) -> None:
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, REPORT)

    def _checked(self, *payload: int) -> bytes:
        r = self.query(*payload)
        if r is None:
            raise ViaError(f"timeout waiting for reply to 0x{payload[0]:02x}")
        if r[0] == UNHANDLED and payload[0] != UNHANDLED:
            raise ViaError(f"command 0x{payload[0]:02x} not supported by firmware")
        return r

    # ---- info -----------------------------------------------------------
    def protocol_version(self) -> int:
        r = self._checked(GET_PROTOCOL_VERSION)
        return (r[1] << 8) | r[2]

    def layer_count(self) -> int:
        return self._checked(DYNAMIC_KEYMAP_GET_LAYER_COUNT)[1]

    # ---- RGB matrix (global lighting) -----------------------------------
    def rgb_get(self, value_id: int) -> tuple[int, int]:
        r = self._checked(CUSTOM_GET_VALUE, CH_RGB_MATRIX, value_id)
        return r[3], r[4]

    def rgb_set(self, value_id: int, a: int, b: int = 0, wait: bool = True) -> None:
        if wait:
            self._checked(CUSTOM_SET_VALUE, CH_RGB_MATRIX, value_id, a, b)
        else:
            self.send(CUSTOM_SET_VALUE, CH_RGB_MATRIX, value_id, a, b)

    def lighting_snapshot(self) -> dict[int, tuple[int, int]]:
        return {v: self.rgb_get(v) for v in (RGBM_BRIGHTNESS, RGBM_EFFECT, RGBM_SPEED, RGBM_COLOR)}

    def lighting_restore(self, snap: dict[int, tuple[int, int]]) -> None:
        """Restore values in RAM. Deliberately never calls ``custom_save`` (no EEPROM wear)."""
        for vid in (RGBM_EFFECT, RGBM_SPEED, RGBM_COLOR, RGBM_BRIGHTNESS):
            a, b = snap[vid]
            self.rgb_set(vid, a, b)

    # ---- backup ---------------------------------------------------------
    def read_keymap(self, rows: int = 6, cols: int = 16) -> bytes:
        size = self.layer_count() * rows * cols * 2
        return self._read_buffer(DYNAMIC_KEYMAP_GET_BUFFER, size)

    def read_macros(self) -> bytes:
        r = self._checked(DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE)
        return self._read_buffer(DYNAMIC_KEYMAP_MACRO_GET_BUFFER, (r[1] << 8) | r[2])

    def _read_buffer(self, cmd: int, size: int) -> bytes:
        out = bytearray()
        for off in range(0, size, 28):
            n = min(28, size - off)
            r = self._checked(cmd, off >> 8, off & 0xFF, n)
            out += r[4:4 + n]
        return bytes(out)

    def write_keymap(self, data: bytes) -> None:
        self._write_buffer(DYNAMIC_KEYMAP_SET_BUFFER, data)

    def write_macros(self, data: bytes) -> None:
        self._write_buffer(DYNAMIC_KEYMAP_MACRO_SET_BUFFER, data)

    def _write_buffer(self, cmd: int, data: bytes) -> None:
        for off in range(0, len(data), 28):
            chunk = data[off:off + 28]
            self._checked(cmd, off >> 8, off & 0xFF, len(chunk), *chunk)
