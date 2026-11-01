"""Output backends. Each one receives the full game frame every engine tick.

A backend only needs ``open()``, ``update(frame, status, now)`` and ``close()``;
``event(name)`` is optional and receives game events such as ``"eat"`` or ``"die"``.
"""
from __future__ import annotations

from ..color import Frame


class Backend:
    name = "base"

    def open(self) -> None:
        pass

    def update(self, frame: Frame, status: list[str], now: float) -> None:
        raise NotImplementedError

    def event(self, name: str) -> None:
        pass

    def close(self) -> None:
        pass


def make_backend(name: str, layout, terminal, **opts) -> Backend:
    if name == "terminal":
        from .terminal import TerminalBackend
        return TerminalBackend(layout, terminal)
    if name == "openrgb":
        from .openrgb import OpenRGBBackend
        return OpenRGBBackend(layout, host=opts.get("openrgb_host", "127.0.0.1"),
                              port=opts.get("openrgb_port", 6742),
                              device=opts.get("openrgb_device"))
    if name == "gmk67-ambient":
        from .via_ambient import ViaAmbientBackend
        return ViaAmbientBackend(path=opts.get("hidraw"))
    raise ValueError(f"unknown backend {name!r} (choose: {', '.join(BACKENDS)})")


BACKENDS = ("terminal", "openrgb", "gmk67-ambient")
