"""Command line entry point: ``python -m ledarcade [game] [options]``."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .backends import BACKENDS, Backend, make_backend
from .engine import ensure_tty, run
from .games import GAMES
from .input import EvdevInput
from .layout import GMK67
from .term import Terminal


def pick_game_interactively() -> str:
    names = list(GAMES)
    print("\n  gmk67-led-arcade\n")
    for i, n in enumerate(names, 1):
        g = GAMES[n]
        print(f"   {i}. {g.title:<12} {g.blurb}")
    while True:
        choice = input("\n  Pick a game [1]: ").strip() or "1"
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            return names[int(choice) - 1]
        if choice in GAMES:
            return choice


def open_backends(names: list[str], terminal: Terminal, args) -> tuple[list[Backend], list[str]]:
    """Open the requested backends. ``auto`` = simulator + the best hardware backend found."""
    opts = dict(openrgb_host=args.openrgb_host, openrgb_port=args.openrgb_port,
                openrgb_device=args.openrgb_device, hidraw=args.hidraw)
    backends: list[Backend] = []
    notes: list[str] = []
    wanted = names
    auto = "auto" in names
    if auto:
        wanted = ["terminal", "openrgb", "gmk67-ambient"]
    for n in wanted:
        if auto and n == "gmk67-ambient" and any(b.name == "openrgb" for b in backends):
            continue                                 # OpenRGB already drives the keys
        b = make_backend(n, GMK67, terminal, **opts)
        try:
            b.open()
        except Exception as e:                       # noqa: BLE001 - report and continue
            if not auto:
                raise SystemExit(f"backend {n!r} failed: {e}")
            notes.append(f"{n}: unavailable ({e})")
            continue
        backends.append(b)
        notes.append(f"{n}: {getattr(b, 'description', 'on')}")
    return backends, notes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ledarcade", description="Games played on keyboard RGB lighting.")
    p.add_argument("game", nargs="?", choices=list(GAMES), help="game to play (menu if omitted)")
    p.add_argument("-b", "--backend", default="auto",
                   help=f"comma-separated outputs: auto, {', '.join(BACKENDS)} (default: auto)")
    p.add_argument("--no-evdev", action="store_true", help="read keys from the terminal instead of evdev")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--grab", dest="grab", action="store_true", default=None,
                   help="grab the keyboard so key presses don't reach other apps")
    g.add_argument("--no-grab", dest="grab", action="store_false")
    p.add_argument("--seed", type=int, help="random seed (reproducible games)")
    p.add_argument("--fps", type=float, default=60.0)
    p.add_argument("--openrgb-host", default="127.0.0.1")
    p.add_argument("--openrgb-port", type=int, default=6742)
    p.add_argument("--openrgb-device", help="substring of the OpenRGB device name to use")
    p.add_argument("--hidraw", help="VIA hidraw node for gmk67-ambient (auto-detected)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    ensure_tty()
    game_name = args.game or pick_game_interactively()
    game_cls = GAMES[game_name]

    evdev = None
    input_note = "terminal (limited keys)"
    if not args.no_evdev:
        grab = game_cls.all_keys if args.grab is None else args.grab
        try:
            evdev = EvdevInput(GMK67, grab=grab)
            input_note = f"evdev {', '.join(evdev.paths)}" + (" [grabbed]" if grab else "")
        except OSError as e:
            input_note = f"terminal (evdev unavailable: {e})"

    best = 0
    summary = ""
    backends: list[Backend] = []
    try:
        with Terminal() as term:
            backends, notes = open_backends(args.backend.split(","), term, args)
            footer = ["Outputs: " + " | ".join(notes), f"Input: {input_note}"]
            summary = "\n".join(footer)
            term.write("\x1b[2J")
            best = run(game_cls, GMK67, backends, term, evdev, fps=args.fps, seed=args.seed,
                       footer=footer)
    except KeyboardInterrupt:
        pass
    finally:
        for b in backends:
            try:
                b.close()
            except Exception:  # noqa: BLE001
                pass
        if evdev:
            evdev.close()
    print(f"{game_cls.title}: best score {best}")
    if summary:
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
