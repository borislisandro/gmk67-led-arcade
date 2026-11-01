"""Tiny colour toolkit. Colours are plain ``(r, g, b)`` tuples with 0-255 channels."""
from __future__ import annotations

import colorsys

RGB = tuple[int, int, int]
Frame = dict[str, RGB]   # key id -> colour; keys missing from the frame are off

OFF: RGB = (0, 0, 0)
WHITE: RGB = (255, 255, 255)
RED: RGB = (255, 0, 0)
GREEN: RGB = (0, 255, 0)
BLUE: RGB = (0, 0, 255)
YELLOW: RGB = (255, 200, 0)
ORANGE: RGB = (255, 90, 0)
PURPLE: RGB = (160, 0, 255)
CYAN: RGB = (0, 220, 255)
MAGENTA: RGB = (255, 0, 160)


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> RGB:
    """``h`` in turns (0..1), ``s``/``v`` in 0..1."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


def scale(c: RGB, f: float) -> RGB:
    f = max(0.0, f)
    return tuple(min(255, round(ch * f)) for ch in c)  # type: ignore[return-value]


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = min(1.0, max(0.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def to_hsv_bytes(c: RGB) -> tuple[int, int, int]:
    """RGB -> QMK-style (hue, sat, val) bytes, 0-255 each."""
    h, s, v = colorsys.rgb_to_hsv(*(ch / 255 for ch in c))
    return round(h * 255) % 256, round(s * 255), round(v * 255)
