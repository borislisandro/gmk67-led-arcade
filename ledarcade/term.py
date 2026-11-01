"""Raw terminal handling: alternate screen, hidden cursor, no echo, non-blocking stdin."""
from __future__ import annotations

import os
import sys
import termios
import tty


class Terminal:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self._saved = None

    def __enter__(self) -> "Terminal":
        if os.isatty(self.fd):
            self._saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)          # keeps ISIG, so Ctrl+C still works
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        return self

    def __exit__(self, *exc) -> None:
        self.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        if self._saved is not None:
            termios.tcflush(self.fd, termios.TCIFLUSH)   # drop keys typed during the game
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved)

    @staticmethod
    def write(s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def read_available(self) -> bytes:
        """Everything currently buffered on stdin, without blocking."""
        import select
        data = b""
        while select.select([self.fd], [], [], 0)[0]:
            chunk = os.read(self.fd, 1024)
            if not chunk:
                break
            data += chunk
        return data
