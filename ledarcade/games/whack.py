"""Whack-a-Key: keys light up like moles popping out of holes; hit them before
they turn red and hide again."""
from __future__ import annotations

from ..color import Frame, mix, scale
from ..input import KeyEvent
from .base import Game

FRESH = (255, 230, 0)
OLD = (255, 0, 0)
HIT = (0, 255, 80)
WRONG = (255, 0, 0)
FLASH = 0.25
HEART = "\u2665"


class Whack(Game):
    name = "whack"
    title = "Whack-a-Key"
    blurb = "hit the glowing keys before they vanish"
    controls = "Press the lit keys"
    all_keys = True
    round_time = 45.0
    lives = 5

    def reset(self, now: float) -> None:
        self.moles: dict[str, tuple[float, float]] = {}      # key -> (born, lifetime)
        self.flashes: dict[str, tuple[tuple, float]] = {}    # key -> (colour, until)
        self.start = now
        self.next_spawn = now + 0.6
        self.escaped = 0
        self.lives_left = self.lives
        self.time_left = self.round_time

    def difficulty(self, now: float) -> float:
        return min(1.0, (now - self.start) / self.round_time)

    def update(self, now: float) -> None:
        d = self.difficulty(now)
        self.time_left = max(0.0, self.round_time - (now - self.start))
        for k, (born, life) in list(self.moles.items()):
            if now - born > life:
                del self.moles[k]
                self.flashes[k] = (WRONG, now + FLASH)
                self.escaped += 1
                self.lives_left -= 1
                self.emit("miss")
        if self.lives_left <= 0:
            self.finish(now, won=False)
            return
        if now - self.start >= self.round_time:
            self.finish(now, won=True)
            return
        max_moles = 1 + int(d * 3)
        if now >= self.next_spawn and len(self.moles) < max_moles:
            free = [k for k in self.cells if k not in self.moles and k != "ESC"]
            k = self.rng.choice(free)
            self.moles[k] = (now, 1.8 - 1.0 * d)
            self.next_spawn = now + self.rng.uniform(0.35, 1.0) * (1.0 - 0.55 * d)
        self.flashes = {k: v for k, v in self.flashes.items() if v[1] > now}

    def on_key(self, ev: KeyEvent, now: float) -> None:
        if not ev.pressed or ev.key == "ESC":
            return
        if ev.key in self.moles:
            born, life = self.moles.pop(ev.key)
            speed_bonus = 1 + int(3 * (1 - (now - born) / life))
            self.score += speed_bonus
            self.flashes[ev.key] = (HIT, now + FLASH)
            self.emit("point")
        else:
            self.score = max(0, self.score - 1)
            self.flashes[ev.key] = (scale(WRONG, 0.5), now + FLASH / 2)

    def render(self, now: float) -> Frame:
        f: Frame = {}
        for k, (born, life) in self.moles.items():
            f[k] = mix(FRESH, OLD, (now - born) / life)
        for k, (c, _until) in self.flashes.items():
            f[k] = c
        return f

    def status(self) -> list[str]:
        hearts = HEART * self.lives_left + "\u00b7" * (self.lives - self.lives_left)
        return [f"Score: {self.score}   Lives: {hearts}   Time left: {self.time_left:4.1f}s"]
