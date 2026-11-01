"""Physical model of the Zuoya GMK67 (V2, ANSI) keyboard.

Every game in this library treats the keyboard as a *graph of keys* rather than
a perfect grid: rows are staggered and some keys are wide (Space is 6.25u), so
"the key above" is computed geometrically from key positions.

Geometry comes from the vendor VIA definition (``ZUOYA GMK67 V2.JSON``) and the
matrix positions / keycodes were confirmed by reading the keymap off a real
board over the VIA protocol (see ``docs/FEASIBILITY.md``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Directions used by movement-based games.
UP, DOWN, LEFT, RIGHT = "up", "down", "left", "right"
DIRECTIONS = (UP, DOWN, LEFT, RIGHT)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}


@dataclass(frozen=True)
class Key:
    id: str                 # stable identifier used everywhere ("ESC", "A", "SPACE", ...)
    label: str              # short legend for on-screen rendering
    x: float                # left edge, in key units (1u = one standard key)
    y: int                  # row index, 0 = top (number row)
    w: float                # width in key units
    matrix: tuple[int, int]  # (row, col) in the firmware's switch matrix
    evdev: int | None       # Linux input keycode (None = key sends nothing, e.g. Fn)
    led: bool = True        # has an RGB LED that games may draw on

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def x2(self) -> float:
        return self.x + self.w


# (id, label, width, matrix_row, matrix_col, linux_keycode)
# A ``None`` entry is a horizontal gap of the given width.
_ROWS: list[list[tuple | float]] = [
    [("ESC", "Esc", 1, 0, 0, 1),
     ("1", "1", 1, 1, 1, 2), ("2", "2", 1, 1, 2, 3), ("3", "3", 1, 1, 3, 4),
     ("4", "4", 1, 1, 4, 5), ("5", "5", 1, 1, 5, 6), ("6", "6", 1, 1, 6, 7),
     ("7", "7", 1, 1, 7, 8), ("8", "8", 1, 1, 8, 9), ("9", "9", 1, 1, 9, 10),
     ("0", "0", 1, 1, 10, 11), ("MINUS", "-", 1, 1, 11, 12), ("EQUAL", "=", 1, 1, 12, 13),
     ("BSPC", "Bksp", 2, 1, 13, 14), ("KNOB", "Knob", 1, 1, 14, 113)],
    [("TAB", "Tab", 1.5, 2, 0, 15),
     ("Q", "Q", 1, 2, 1, 16), ("W", "W", 1, 2, 2, 17), ("E", "E", 1, 2, 3, 18),
     ("R", "R", 1, 2, 4, 19), ("T", "T", 1, 2, 5, 20), ("Y", "Y", 1, 2, 6, 21),
     ("U", "U", 1, 2, 7, 22), ("I", "I", 1, 2, 8, 23), ("O", "O", 1, 2, 9, 24),
     ("P", "P", 1, 2, 10, 25), ("LBRC", "[", 1, 2, 11, 26), ("RBRC", "]", 1, 2, 12, 27),
     ("BSLS", "\\", 1.5, 2, 13, 43), ("DEL", "Del", 1, 2, 14, 111)],
    [("CAPS", "Caps", 1.75, 3, 0, 58),
     ("A", "A", 1, 3, 1, 30), ("S", "S", 1, 3, 2, 31), ("D", "D", 1, 3, 3, 32),
     ("F", "F", 1, 3, 4, 33), ("G", "G", 1, 3, 5, 34), ("H", "H", 1, 3, 6, 35),
     ("J", "J", 1, 3, 7, 36), ("K", "K", 1, 3, 8, 37), ("L", "L", 1, 3, 9, 38),
     ("SCLN", ";", 1, 3, 10, 39), ("QUOT", "'", 1, 3, 11, 40),
     ("ENTER", "Enter", 2.25, 3, 13, 28), ("PGUP", "PgUp", 1, 3, 14, 104)],
    [("LSHIFT", "Shift", 2.25, 4, 0, 42),
     ("Z", "Z", 1, 4, 2, 44), ("X", "X", 1, 4, 3, 45), ("C", "C", 1, 4, 4, 46),
     ("V", "V", 1, 4, 5, 47), ("B", "B", 1, 4, 6, 48), ("N", "N", 1, 4, 7, 49),
     ("M", "M", 1, 4, 8, 50), ("COMMA", ",", 1, 4, 9, 51), ("DOT", ".", 1, 4, 10, 52),
     ("SLASH", "/", 1, 4, 11, 53), ("RSHIFT", "Shift", 1.75, 4, 13, 54),
     ("UP", "↑", 1, 4, 14, 103), ("PGDN", "PgDn", 1, 3, 15, 109)],
    [("LCTRL", "Ctrl", 1.25, 5, 0, 29), ("LGUI", "Win", 1.25, 5, 1, 125),
     ("LALT", "Alt", 1.25, 5, 2, 56), ("SPACE", "Space", 6.25, 5, 5, 57),
     ("RALT", "Alt", 1.25, 5, 9, 100), ("FN", "Fn", 1.25, 5, 10, None),
     0.5,
     ("LEFT", "←", 1, 5, 13, 105), ("DOWN", "↓", 1, 5, 14, 108),
     ("RIGHT", "→", 1, 5, 15, 106)],
]

# The knob is a rotary encoder with a push switch; it has no RGB LED.
_NO_LED = {"KNOB"}


class Layout:
    """A keyboard as an ordered collection of keys plus geometric helpers."""

    def __init__(self, name: str, keys: Iterable[Key]):
        self.name = name
        self.keys: list[Key] = list(keys)
        self.by_id: dict[str, Key] = {k.id: k for k in self.keys}
        self.by_evdev: dict[int, Key] = {k.evdev: k for k in self.keys if k.evdev is not None}
        self.rows: list[list[Key]] = []
        for k in self.keys:
            while len(self.rows) <= k.y:
                self.rows.append([])
            self.rows[k.y].append(k)
        for row in self.rows:
            row.sort(key=lambda k: k.x)
        self.width = max(k.x2 for k in self.keys)
        self.led_keys: list[Key] = [k for k in self.keys if k.led]
        self._neigh: dict[str, list[str]] = {}

    def __getitem__(self, key_id: str) -> Key:
        return self.by_id[key_id]

    def __contains__(self, key_id: str) -> bool:
        return key_id in self.by_id

    # ---- geometry -------------------------------------------------------
    def key_at(self, row: int, x: float, led_only: bool = True) -> Key:
        """Key in ``row`` whose span contains ``x`` (nearest centre if in a gap)."""
        candidates = [k for k in self.rows[row] if k.led or not led_only]
        for k in candidates:
            if k.x <= x < k.x2:
                return k
        return min(candidates, key=lambda k: abs(k.cx - x))

    def step(self, key_id: str, direction: str, vx: float | None = None,
             wrap: bool = True) -> tuple[str | None, float]:
        """Move one key in ``direction``.

        ``vx`` is a "virtual column" carried across consecutive vertical moves so
        that moving straight up/down through staggered rows does not drift
        sideways. Returns ``(new_key_id or None if a wall was hit, new_vx)``.
        """
        k = self.by_id[key_id]
        if direction in (LEFT, RIGHT):
            row = [r for r in self.rows[k.y] if r.led]
            i = row.index(k) + (1 if direction == RIGHT else -1)
            if not 0 <= i < len(row):
                if not wrap:
                    return None, k.cx
                i %= len(row)
            nk = row[i]
            return nk.id, nk.cx
        x = k.cx if vx is None else vx
        y = k.y + (-1 if direction == UP else 1)
        if not 0 <= y < len(self.rows):
            if not wrap:
                return None, x
            y %= len(self.rows)
        return self.key_at(y, x).id, x

    def neighbours(self, key_id: str) -> list[str]:
        """Keys that physically touch ``key_id`` (same row sides + overlapping spans above/below)."""
        if key_id in self._neigh:
            return self._neigh[key_id]
        k = self.by_id[key_id]
        out: list[str] = []
        row = [r for r in self.rows[k.y] if r.led]
        if k in row:
            i = row.index(k)
            out += [row[j].id for j in (i - 1, i + 1) if 0 <= j < len(row)]
        for y in (k.y - 1, k.y + 1):
            if 0 <= y < len(self.rows):
                for o in self.rows[y]:
                    if o.led and o.x < k.x2 - 0.05 and o.x2 > k.x + 0.05:
                        out.append(o.id)
        self._neigh[key_id] = out
        return out


def gmk67() -> Layout:
    keys: list[Key] = []
    for y, row in enumerate(_ROWS):
        x = 0.0
        for item in row:
            if isinstance(item, (int, float)):
                x += item
                continue
            kid, label, w, mr, mc, code = item
            keys.append(Key(kid, label, x, y, float(w), (mr, mc), code, kid not in _NO_LED))
            x += w
    return Layout("Zuoya GMK67 V2 (ANSI)", keys)


GMK67 = gmk67()
