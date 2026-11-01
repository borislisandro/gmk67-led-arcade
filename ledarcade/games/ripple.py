"""Ripple: not really a game - a lighting toy and per-key mapping test. A slow
rainbow drifts across the board and every key you press sends out a ripple."""
from __future__ import annotations

import math

from ..color import Frame, hsv, mix
from ..input import KeyEvent
from .base import Game

SPEED = 9.0      # key-units per second
WIDTH = 1.2


class Ripple(Game):
    name = "ripple"
    title = "Ripple"
    blurb = "lighting toy / LED mapping test"
    controls = "Press any key"
    all_keys = True

    def reset(self, now: float) -> None:
        self.ripples: list[tuple[float, float, float, float]] = []   # x, y, born, hue

    def on_key(self, ev: KeyEvent, now: float) -> None:
        if ev.pressed and ev.key in self.layout:
            k = self.layout[ev.key]
            self.ripples.append((k.cx, k.y + 0.5, now, self.rng.random()))
            self.score += 1

    def update(self, now: float) -> None:
        self.ripples = [r for r in self.ripples if now - r[2] < 2.0]

    def render(self, now: float) -> Frame:
        f: Frame = {}
        for k in self.layout.led_keys:
            base = hsv(k.cx / 20 - now * 0.1, 1.0, 0.18)
            c = base
            for x, y, born, hue in self.ripples:
                d = math.hypot(k.cx - x, (k.y + 0.5 - y) * 1.1)
                front = (now - born) * SPEED
                strength = max(0.0, 1 - abs(d - front) / WIDTH) * max(0.0, 1 - (now - born) / 2)
                if strength > 0:
                    c = mix(c, hsv(hue), strength)
            f[k.id] = c
        return f

    def status(self) -> list[str]:
        return [f"Presses: {self.score}"]
