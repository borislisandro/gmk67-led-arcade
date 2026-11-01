"""Echo: a memory game. The keyboard plays a sequence of keys, you play it back.
Every round the sequence grows by one key."""
from __future__ import annotations

from ..color import Frame, hsv, scale
from ..input import KeyEvent
from .base import Game

OK = (0, 255, 80)
BAD = (255, 0, 0)


class Echo(Game):
    name = "echo"
    title = "Echo"
    blurb = "watch the sequence, then play it back"
    controls = "Repeat the keys in the order they lit up"
    all_keys = True
    pool_size = 12

    def reset(self, now: float) -> None:
        cells = [k for k in self.cells if k != "ESC"]
        self.pool = self.rng.sample(cells, min(self.pool_size, len(cells)))
        self.seq: list[str] = []
        self.pos = 0
        self.mode = "show"
        self.flash: tuple[str, tuple, float] | None = None
        self.mistake: str | None = None
        self.next_round(now + 0.6)

    def colour(self, key: str) -> tuple:
        k = self.layout[key]
        return hsv(k.cx / self.layout.width * 0.85)

    def next_round(self, start: float) -> None:
        self.seq.append(self.rng.choice(self.pool))
        self.mode, self.pos = "show", 0
        self.on_time = max(0.25, 0.6 - 0.025 * len(self.seq))
        self.gap = max(0.08, 0.2 - 0.01 * len(self.seq))
        self.show_start = start

    def update(self, now: float) -> None:
        if self.mode == "show" and now - self.show_start >= len(self.seq) * (self.on_time + self.gap):
            self.mode, self.pos = "input", 0

    def on_key(self, ev: KeyEvent, now: float) -> None:
        if not ev.pressed or self.mode != "input" or ev.key == "ESC":
            return
        want = self.seq[self.pos]
        if ev.key != want:
            self.mistake = ev.key
            self.flash = (want, OK, now + 10)
            self.finish(now, won=False)
            return
        self.flash = (ev.key, self.colour(ev.key), now + 0.25)
        self.pos += 1
        if self.pos == len(self.seq):
            self.score = len(self.seq)
            self.emit("level")
            self.next_round(now + 0.9)

    def render(self, now: float) -> Frame:
        # Show the pool very dimly so the player knows which keys are in play.
        f: Frame = {k: scale(self.colour(k), 0.08) for k in self.pool}
        if self.mode == "show" and now >= self.show_start:
            slot = self.on_time + self.gap
            i, t = divmod(now - self.show_start, slot)
            if int(i) < len(self.seq) and t < self.on_time:
                k = self.seq[int(i)]
                f[k] = self.colour(k)
        if self.flash and now < self.flash[2]:
            f[self.flash[0]] = self.flash[1]
        if self.over and self.mistake:
            f[self.mistake] = BAD if int((now - self.over_at) * 4) % 2 == 0 else (0, 0, 0)
        return f

    def status(self) -> list[str]:
        phase = "watch…" if self.mode == "show" else f"your turn ({self.pos}/{len(self.seq)})"
        return [f"Round: {len(self.seq)}   Best completed: {self.score}   {phase}"]
