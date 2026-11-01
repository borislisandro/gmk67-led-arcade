"""Stock-firmware GMK67 backend: drives the *whole board* colour over VIA.

The stock GMK67 V2 firmware cannot address individual LEDs (see
docs/FEASIBILITY.md), but it changes the global colour in ~2 ms. This backend
turns the game frame into one "mood" colour (the average hue of the lit keys)
and flashes the board on game events, so the physical keyboard reacts to the
game while the on-screen simulator shows the exact per-key picture.

Lighting is only changed in RAM and is restored on exit; ``custom_save`` is
never sent, so nothing is written to the keyboard's EEPROM.
"""
from __future__ import annotations

import colorsys
import math

from ..color import Frame, RGB, hsv, to_hsv_bytes
from ..via import (EFFECT_SOLID, RGBM_BRIGHTNESS, RGBM_COLOR, RGBM_EFFECT, ViaDevice)
from . import Backend

# event -> list of (colour, seconds)
FLASHES: dict[str, list[tuple[RGB, float]]] = {
    "eat":   [((255, 255, 255), 0.08)],
    "point": [((255, 255, 255), 0.08)],
    "miss":  [((255, 0, 0), 0.15)],
    "die":   [((255, 0, 0), 0.25), ((0, 0, 0), 0.15)] * 3,
    "lose":  [((255, 0, 0), 0.25), ((0, 0, 0), 0.15)] * 3,
    "win":   [(hsv(i / 12), 0.08) for i in range(24)],
    "level": [((0, 120, 255), 0.12), ((0, 0, 0), 0.08)] * 2,
}


def mood(frame: Frame) -> RGB:
    """Average colour of lit keys, renormalised to full brightness."""
    lit = [c for c in frame.values() if max(c) > 8]
    if not lit:
        return (0, 0, 0)
    # average in vector-hue space so red+green doesn't turn muddy brown
    x = y = 0.0
    for r, g, b in lit:
        h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        x += math.cos(2 * math.pi * h) * s
        y += math.sin(2 * math.pi * h) * s
    h = (math.atan2(y, x) / (2 * math.pi)) % 1.0
    sat = min(1.0, math.hypot(x, y) / len(lit) * 1.2)
    return hsv(h, sat, 0.6)


class ViaAmbientBackend(Backend):
    name = "gmk67-ambient"

    def __init__(self, path: str | None = None, max_hz: float = 120.0):
        self.path = path
        self.min_dt = 1.0 / max_hz
        self.queue: list[tuple[RGB, float]] = []
        self.flash_until = 0.0
        self.current: tuple | None = None
        self.last_sent = 0.0

    def open(self) -> None:
        self.dev = ViaDevice(self.path)
        self.snapshot = self.dev.lighting_snapshot()
        self.max_brightness = max(self.snapshot[RGBM_BRIGHTNESS][0], 1)
        self.dev.rgb_set(RGBM_EFFECT, EFFECT_SOLID)

    def event(self, name: str) -> None:
        if name in FLASHES:
            self.queue = list(FLASHES[name])
            self.flash_until = 0.0

    def _put(self, c: RGB, now: float) -> None:
        h, s, v = to_hsv_bytes(c)
        state = (h, s, round(v / 255 * self.max_brightness))
        if state == self.current or now - self.last_sent < self.min_dt:
            return
        if self.current is None or state[:2] != self.current[:2]:
            self.dev.rgb_set(RGBM_COLOR, h, s)
        if self.current is None or state[2] != self.current[2]:
            self.dev.rgb_set(RGBM_BRIGHTNESS, state[2])
        self.current, self.last_sent = state, now

    def update(self, frame: Frame, status: list[str], now: float) -> None:
        if now < self.flash_until:
            return
        if self.queue:
            colour, dur = self.queue.pop(0)
            self.last_sent = 0.0                  # flashes bypass rate limiting
            self._put(colour, now)
            self.flash_until = now + dur
            return
        self._put(mood(frame), now)

    def close(self) -> None:
        try:
            self.dev.lighting_restore(self.snapshot)
        finally:
            self.dev.close()
