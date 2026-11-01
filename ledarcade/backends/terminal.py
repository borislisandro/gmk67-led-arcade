"""On-screen simulator: draws the keyboard with true-colour ANSI blocks."""
from __future__ import annotations

from ..color import Frame, RGB
from ..layout import Layout
from . import Backend

UNIT = 6          # terminal columns per 1u of key width
UNLIT: RGB = (34, 34, 38)


def _fg_for(bg: RGB) -> str:
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return "\x1b[38;2;10;10;10m" if lum > 140 else "\x1b[38;2;200;200;200m"


class TerminalBackend(Backend):
    name = "terminal"

    def __init__(self, layout: Layout, terminal):
        self.layout = layout
        self.term = terminal
        self._last: tuple | None = None

    def render_lines(self, frame: Frame) -> list[str]:
        lines: list[str] = []
        for row in self.layout.rows:
            top, mid = [], []
            col = 0
            for k in row:
                start, end = round(k.x * UNIT), round(k.x2 * UNIT) - 1
                pad = " " * (start - col)
                bg = frame.get(k.id, UNLIT) if k.led else (15, 15, 15)
                if bg == (0, 0, 0):
                    bg = UNLIT
                width = end - start
                label = (k.label if k.led else "◯")[:width].center(width)
                b = f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m"
                top.append(f"{pad}{b}{_fg_for(bg)}{label}\x1b[0m")
                mid.append(f"{pad}{b}{' ' * width}\x1b[0m")
                col = end
            lines += ["".join(top), "".join(mid), ""]
        return lines

    def update(self, frame: Frame, status: list[str], now: float) -> None:
        key = (tuple(sorted(frame.items())), tuple(status))
        if key == self._last:
            return
        self._last = key
        out = ["\x1b[H"]
        for line in self.render_lines(frame) + [""] + status:
            out.append(line + "\x1b[K\n")
        out.append("\x1b[J")
        self.term.write("".join(out))
