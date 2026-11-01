"""Snake on the keycaps: a green snake slithers across the keys, red apples appear
on random keys, and you steer with the arrow keys."""
from __future__ import annotations

import math

from ..color import Frame, mix, scale
from ..input import KeyEvent
from ..layout import DOWN, LEFT, OPPOSITE, RIGHT, UP
from .base import Game

HEAD = (40, 255, 40)
BODY_NEAR = (0, 200, 0)
BODY_FAR = (0, 50, 10)
APPLE = (255, 0, 0)
GOLDEN = (255, 170, 0)
DEAD = (255, 0, 0)

ARROWS = {"UP": UP, "DOWN": DOWN, "LEFT": LEFT, "RIGHT": RIGHT}


class Snake(Game):
    name = "snake"
    title = "Snake"
    blurb = "eat the red apples, don't bite yourself"
    controls = "Arrow keys: steer • the board wraps around at the edges"

    start_interval = 0.42
    min_interval = 0.14
    speedup = 0.015
    wrap = True

    def reset(self, now: float) -> None:
        self.body: list[str] = ["G", "F", "D"]
        self.direction = RIGHT
        self.queue: list[str] = []
        self.vx: float | None = None
        self.last_vertical = False
        self.interval = self.start_interval
        self.next_step = now + 0.8          # short grace period before moving
        self.apple: str | None = None
        self.golden = False
        self.spawn_apple()

    # ---- input ----------------------------------------------------------
    def on_key(self, ev: KeyEvent, now: float) -> None:
        if not ev.pressed or ev.key not in ARROWS:
            return
        d = ARROWS[ev.key]
        last = self.queue[-1] if self.queue else self.direction
        if d != last and d != OPPOSITE[last] and len(self.queue) < 3:
            self.queue.append(d)

    # ---- logic ----------------------------------------------------------
    def free_cells(self) -> list[str]:
        taken = set(self.body)
        return [k.id for k in self.layout.led_keys if k.id not in taken]

    def spawn_apple(self) -> None:
        free = self.free_cells()
        if not free:
            self.apple = None
            return
        self.apple = self.rng.choice(free)
        self.golden = self.rng.random() < 0.12      # golden apple: worth 3, grows 1

    def update(self, now: float) -> None:
        while now >= self.next_step and not self.over:
            self.next_step += self.interval
            self.step(now)

    def step(self, now: float) -> None:
        if self.queue:
            self.direction = self.queue.pop(0)
        vertical = self.direction in (UP, DOWN)
        vx = self.vx if (vertical and self.last_vertical) else None
        new, self.vx = self.layout.step(self.body[0], self.direction, vx, wrap=self.wrap)
        self.last_vertical = vertical
        eating = new == self.apple
        tail_moves_away = not eating
        blocked = self.body[:-1] if tail_moves_away else self.body
        if new is None or new in blocked:
            self.finish(now, won=False)
            return
        self.body.insert(0, new)
        if eating:
            self.score += 3 if self.golden else 1
            self.emit("eat")
            self.interval = max(self.min_interval, self.interval - self.speedup)
            self.spawn_apple()
            if self.apple is None:
                self.finish(now, won=True)
        else:
            self.body.pop()

    # ---- drawing --------------------------------------------------------
    def render(self, now: float) -> Frame:
        f: Frame = {}
        if self.apple:
            pulse = 0.65 + 0.35 * math.sin(now * 8)
            f[self.apple] = scale(GOLDEN if self.golden else APPLE, pulse)
        n = len(self.body)
        for i, k in enumerate(reversed(self.body)):
            f[k] = mix(BODY_FAR, BODY_NEAR, (i + 1) / n)
        f[self.body[0]] = HEAD
        if self.over and not self.won:
            on = int((now - self.over_at) * 4) % 2 == 0 and now - self.over_at < 2.0
            for k in self.body:
                f[k] = DEAD if on else scale(DEAD, 0.25)
        return f

    def status(self) -> list[str]:
        speed = round((self.start_interval - self.interval) / self.speedup) + 1
        return [f"Score: {self.score}   Length: {len(self.body)}   Speed: {speed}"]
