"""The main loop: input -> game -> every backend, at a fixed frame rate."""
from __future__ import annotations

import os
import random
import select
import time

from .backends import Backend
from .games.base import Game
from .input import EvdevInput, decode_terminal_bytes, KeyEvent
from .layout import Layout
from .term import Terminal

ESC_HOLD_TO_QUIT = 1.0
RESTART_DELAY = 0.8

# Keys a terminal can deliver (used when evdev is unavailable)
TERMINAL_KEYS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | {
    "MINUS", "EQUAL", "LBRC", "RBRC", "BSLS", "SCLN", "QUOT", "COMMA", "DOT", "SLASH",
    "SPACE", "ENTER", "TAB", "BSPC", "UP", "DOWN", "LEFT", "RIGHT", "DEL", "PGUP", "PGDN", "ESC"}


def playable_keys(layout: Layout, evdev: EvdevInput | None) -> set[str]:
    if evdev is not None:
        return {k.id for k in layout.keys if k.evdev is not None}
    return {k for k in TERMINAL_KEYS if k in layout}


def run(game_cls: type[Game], layout: Layout, backends: list[Backend], terminal: Terminal,
        evdev: EvdevInput | None, fps: float = 60.0, seed: int | None = None,
        footer: list[str] | None = None) -> int:
    rng = random.Random(seed)
    playable = playable_keys(layout, evdev)

    def new_game(now: float) -> Game:
        g = game_cls(layout, rng, playable)
        g.reset(now)
        return g

    now = time.monotonic()
    game = new_game(now)
    best = 0
    esc_down_at: float | None = None
    frame_dt = 1.0 / fps
    wait_fds = [terminal.fd] + (evdev.fileno_list() if evdev else [])
    quit_hint = ("hold Esc to quit" if game_cls.all_keys and evdev else "Esc to quit")

    while True:
        now = time.monotonic()
        raw = terminal.read_available()
        events: list[KeyEvent] = evdev.read() if evdev else decode_terminal_bytes(raw, layout)

        for ev in events:
            if ev.key == "ESC":
                esc_down_at = now if ev.pressed else None
                if ev.pressed and (game.over or not game_cls.all_keys or evdev is None):
                    return best
            if game.over:
                if ev.pressed and ev.key in ("SPACE", "ENTER") and now - game.over_at > RESTART_DELAY:
                    game = new_game(now)
                    break
                continue
            game.on_key(ev, now)
        if esc_down_at is not None and now - esc_down_at >= ESC_HOLD_TO_QUIT:
            return best

        if not game.over:
            game.update(now)
        best = max(best, game.score)
        frame = game.render(now)

        status = [f"\x1b[1m{game.title}\x1b[0m — {game.blurb}", ""] + game.status()
        if game.over:
            msg = "\x1b[32mYOU WIN!\x1b[0m" if game.won else "\x1b[31mGAME OVER\x1b[0m"
            status += ["", f"{msg}  score {game.score}  (best {best}) — Space/Enter: play again"]
        status += ["", f"\x1b[2m{game.controls} • {quit_hint}\x1b[0m"]
        status += [f"\x1b[2m{line}\x1b[0m" for line in footer or []]

        for e in game.drain_events():
            for b in backends:
                b.event(e)
        for b in backends:
            b.update(frame, status, now)

        remaining = frame_dt - (time.monotonic() - now)
        if remaining > 0:
            select.select(wait_fds, [], [], remaining)


def ensure_tty() -> None:
    if not os.isatty(0):
        raise SystemExit("ledarcade needs an interactive terminal (stdin is not a TTY)")
