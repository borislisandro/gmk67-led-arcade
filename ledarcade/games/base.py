from __future__ import annotations

import random

from ..color import Frame
from ..input import KeyEvent
from ..layout import Layout


class Game:
    """Base class for every game.

    The engine calls, in a loop: ``on_key`` for each input event, ``update(now)``
    once per frame (while not over), then ``render(now)`` -> :data:`Frame`.
    Games keep their own timers using ``now`` (``time.monotonic()`` seconds).
    """

    name = "base"
    title = "Base"
    blurb = ""
    controls = ""
    #: The game uses (almost) every key as input -> ESC must be *held* to quit,
    #: and the keyboard is grabbed by default so Super/Alt don't trigger the desktop.
    all_keys = False

    def __init__(self, layout: Layout, rng: random.Random, playable: set[str]):
        self.layout = layout
        self.rng = rng
        #: keys the current input source can actually report
        self.playable = playable
        self.over = False
        self.won = False
        self.over_at = 0.0
        self.score = 0
        self._events: list[str] = []

    # ---- hooks ----------------------------------------------------------
    def reset(self, now: float) -> None:
        pass

    def on_key(self, ev: KeyEvent, now: float) -> None:
        pass

    def update(self, now: float) -> None:
        pass

    def render(self, now: float) -> Frame:
        return {}

    def status(self) -> list[str]:
        return [f"Score: {self.score}"]

    # ---- helpers --------------------------------------------------------
    def emit(self, event: str) -> None:
        self._events.append(event)

    def drain_events(self) -> list[str]:
        ev, self._events = self._events, []
        return ev

    def finish(self, now: float, won: bool) -> None:
        if self.over:
            return
        self.over, self.won, self.over_at = True, won, now
        self.emit("win" if won else "lose")

    @property
    def cells(self) -> list[str]:
        """LED keys that the player can also press."""
        return [k.id for k in self.layout.led_keys if k.id in self.playable]
