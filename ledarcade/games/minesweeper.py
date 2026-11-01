"""Minesweeper where every keycap is a cell: press a key to dig it up.

The clue number is shown as a colour (1 blue, 2 green, 3 yellow, ...). A key's
neighbours are the keys physically touching it, so the staggered rows give the
puzzle a slightly hexagonal flavour.
"""
from __future__ import annotations

import math

from ..color import Frame, hsv, scale
from ..input import KeyEvent
from .base import Game

HIDDEN = (70, 70, 90)
FLAG = (170, 0, 255)
MINE = (255, 0, 0)
CLUE = {1: (0, 90, 255), 2: (0, 220, 0), 3: (255, 200, 0), 4: (255, 90, 0),
        5: (255, 0, 0), 6: (255, 0, 160), 7: (255, 255, 255), 8: (255, 255, 255)}
CLUE_NAMES = "1 blue • 2 green • 3 yellow • 4 orange • 5 red • 6 pink"
LONG_PRESS = 0.35


class Minesweeper(Game):
    name = "minesweeper"
    title = "Keysweeper"
    blurb = "uncover every key that isn't hiding a mine"
    controls = "Tap a key: dig • hold it (or type Shift+key in a terminal): flag"
    all_keys = True
    mines = 10

    def reset(self, now: float) -> None:
        self.board = self.cells
        self.adj = {k: [n for n in self.layout.neighbours(k) if n in self.board] for k in self.board}
        self.mine_set: set[str] = set()
        self.revealed: set[str] = set()
        self.flags: set[str] = set()
        self.held: dict[str, float] = {}
        self.placed = False
        self.exploded: str | None = None

    def place_mines(self, safe: str) -> None:
        forbidden = {safe, *self.adj[safe]}
        pool = [k for k in self.board if k not in forbidden]
        self.mine_set = set(self.rng.sample(pool, min(self.mines, len(pool))))
        self.counts = {k: sum(n in self.mine_set for n in self.adj[k]) for k in self.board}
        self.placed = True

    # ---- input ----------------------------------------------------------
    def on_key(self, ev: KeyEvent, now: float) -> None:
        k = ev.key
        if k not in self.board:
            return
        if ev.pressed:
            self.held[k] = now
            return
        t0 = self.held.pop(k, now)
        if ev.shifted or now - t0 >= LONG_PRESS:
            self.toggle_flag(k)
        else:
            self.dig(k, now)

    def toggle_flag(self, k: str) -> None:
        if k in self.revealed:
            return
        self.flags ^= {k}

    def dig(self, k: str, now: float) -> None:
        if k in self.flags or k in self.revealed:
            return
        if not self.placed:
            self.place_mines(k)
        if k in self.mine_set:
            self.exploded = k
            self.finish(now, won=False)
            return
        stack = [k]
        while stack:                                   # flood-fill empty areas
            c = stack.pop()
            if c in self.revealed or c in self.flags:
                continue
            self.revealed.add(c)
            if self.counts[c] == 0:
                stack += [n for n in self.adj[c] if n not in self.revealed]
        self.emit("point")
        self.score = len(self.revealed)
        if len(self.revealed) == len(self.board) - len(self.mine_set):
            self.finish(now, won=True)

    # ---- drawing --------------------------------------------------------
    def render(self, now: float) -> Frame:
        f: Frame = {}
        for k in self.board:
            if k in self.revealed:
                c = self.counts[k]
                if c:
                    f[k] = CLUE.get(c, CLUE[8])
            elif k in self.flags:
                f[k] = FLAG
            else:
                f[k] = HIDDEN
                t0 = self.held.get(k)
                if t0 is not None:                     # visual feedback while holding
                    f[k] = FLAG if now - t0 >= LONG_PRESS else (110, 110, 120)
        if self.over:
            t = now - self.over_at
            for m in self.mine_set:
                if self.won:
                    f[m] = hsv(t * 0.5 + self.board.index(m) / len(self.board))
                else:
                    blink = 0.4 + 0.6 * (math.sin(t * 10) > 0)
                    f[m] = scale(MINE, blink if m == self.exploded else 0.8)
        return f

    def status(self) -> list[str]:
        left = self.mines - len(self.flags)
        return [f"Mines: {self.mines}   Flags left: {left}   Cleared: {len(self.revealed)}"
                f"/{len(self.board) - self.mines}",
                f"Clues: {CLUE_NAMES} • dark = 0 • grey = hidden • purple = flag"]
