"""Keyboard input sources.

* :class:`EvdevInput` reads the physical keyboard through Linux evdev. It sees
  every key (including modifiers) with real press/release timing, which games
  such as Minesweeper (long-press to flag) rely on. Needs read access to
  ``/dev/input/event*`` (membership of the ``input`` group is enough).
* :class:`TerminalInput` decodes stdin. It works everywhere (including over
  SSH or with the on-screen simulator only) but only sees printable keys,
  arrows and a few specials, and has no real "release" events.
"""
from __future__ import annotations

import fcntl
import glob
import os
import select
import struct
from dataclasses import dataclass

from .layout import Layout

EV_KEY = 1
EVIOCGRAB = 0x40044590
_EVENT = struct.Struct("llHHi")


@dataclass(frozen=True)
class KeyEvent:
    key: str             # layout key id
    pressed: bool        # True = key down, False = key up
    shifted: bool = False  # terminal fallback: key was typed with Shift (e.g. "A")


def find_keyboard_event_nodes(prefer: tuple[str, ...] = ("GMK67", "RDMCTMZT")) -> list[str]:
    """Event nodes of the preferred keyboard (USB or its 2.4 GHz dongle), else every keyboard."""
    nodes = sorted(glob.glob("/dev/input/by-id/*-event-kbd"))
    preferred = []
    for p in prefer:
        preferred = [n for n in nodes if p.lower() in n.lower()]
        if preferred:
            break
    return [os.path.realpath(n) for n in (preferred or nodes)]


class EvdevInput:
    def __init__(self, layout: Layout, paths: list[str] | None = None, grab: bool = False):
        self.layout = layout
        self.paths = paths or find_keyboard_event_nodes()
        if not self.paths:
            raise OSError("no keyboard event devices found under /dev/input/by-id")
        self.fds: list[int] = []
        for p in self.paths:
            fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)   # PermissionError propagates
            self.fds.append(fd)
        self.grabbed = False
        if grab:
            for fd in self.fds:
                fcntl.ioctl(fd, EVIOCGRAB, 1)
            self.grabbed = True

    def fileno_list(self) -> list[int]:
        return self.fds

    def read(self) -> list[KeyEvent]:
        out: list[KeyEvent] = []
        for fd in select.select(self.fds, [], [], 0)[0]:
            try:
                data = os.read(fd, _EVENT.size * 64)
            except BlockingIOError:
                continue
            for i in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _s, _us, etype, code, value = _EVENT.unpack_from(data, i)
                if etype != EV_KEY or value == 2:       # ignore autorepeat
                    continue
                k = self.layout.by_evdev.get(code)
                if k is not None:
                    out.append(KeyEvent(k.id, value == 1))
        return out

    def close(self) -> None:
        for fd in self.fds:
            if self.grabbed:
                try:
                    fcntl.ioctl(fd, EVIOCGRAB, 0)
                except OSError:
                    pass
            os.close(fd)
        self.fds = []


_SPECIAL = {
    b"\x1b[A": "UP", b"\x1b[B": "DOWN", b"\x1b[C": "RIGHT", b"\x1b[D": "LEFT",
    b"\x1bOA": "UP", b"\x1bOB": "DOWN", b"\x1bOC": "RIGHT", b"\x1bOD": "LEFT",
    b"\x1b[3~": "DEL", b"\x1b[5~": "PGUP", b"\x1b[6~": "PGDN",
}
_CHARS = {
    " ": "SPACE", "\r": "ENTER", "\n": "ENTER", "\t": "TAB", "\x7f": "BSPC", "\x08": "BSPC",
    "-": "MINUS", "=": "EQUAL", "[": "LBRC", "]": "RBRC", "\\": "BSLS", ";": "SCLN",
    "'": "QUOT", ",": "COMMA", ".": "DOT", "/": "SLASH",
    "_": "MINUS", "+": "EQUAL", "{": "LBRC", "}": "RBRC", "|": "BSLS", ":": "SCLN",
    '"': "QUOT", "<": "COMMA", ">": "DOT", "?": "SLASH",
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
    "(": "9", ")": "0",
}


def decode_terminal_bytes(data: bytes, layout: Layout) -> list[KeyEvent]:
    """Turn raw stdin bytes into press+release pairs."""
    out: list[KeyEvent] = []
    i = 0
    while i < len(data):
        for seq, kid in _SPECIAL.items():
            if data.startswith(seq, i):
                out += [KeyEvent(kid, True), KeyEvent(kid, False)]
                i += len(seq)
                break
        else:
            ch = chr(data[i])
            i += 1
            if ch == "\x1b":
                kid, shifted = "ESC", False
            elif ch.isalnum() and ch.isascii():
                kid, shifted = ch.upper(), ch.isupper()
            else:
                kid, shifted = _CHARS.get(ch), ch in '_+{}|:"<>?!@#$%^&*()'
            if kid and kid in layout:
                out += [KeyEvent(kid, True, shifted), KeyEvent(kid, False, shifted)]
    return out
