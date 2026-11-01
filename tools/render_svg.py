#!/usr/bin/env python3
"""Render game frames to SVG for the documentation (docs/img/*.svg)."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ledarcade.color import Frame  # noqa: E402
from ledarcade.games import GAMES  # noqa: E402
from ledarcade.input import KeyEvent  # noqa: E402
from ledarcade.layout import GMK67  # noqa: E402

U = 54          # px per key unit
PAD = 4


def svg(frame: Frame, title: str) -> str:
    w, h = GMK67.width * U + 2 * PAD, len(GMK67.rows) * U + 2 * PAD
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
           f'width="{w:.0f}" height="{h:.0f}" role="img" aria-label="{title}">',
           f'<rect width="100%" height="100%" rx="14" fill="#16161a"/>']
    for k in GMK67.keys:
        x, y = PAD + k.x * U + 3, PAD + k.y * U + 3
        c = frame.get(k.id)
        lit = c is not None and max(c) > 0
        fill = f"rgb{c}" if lit else "#1c1c20"
        if not k.led:
            out.append(f'<circle cx="{x + U / 2 - 3}" cy="{y + U / 2 - 3}" r="{U / 2 - 8}" fill="#0d0d10" stroke="#444"/>')
            continue
        lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) if lit else 0
        txt = "#111" if lum > 140 else ("#ccc" if lit else "#666")
        glow = f' filter="url(#g)"' if lit else ""
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{k.w * U - 6:.1f}" height="{U - 6}" rx="7" '
                   f'fill="{fill}"{glow}/>')
        label = k.label.replace("&", "&amp;").replace("<", "&lt;")
        out.append(f'<text x="{x + (k.w * U - 6) / 2:.1f}" y="{y + U / 2:.1f}" fill="{txt}" '
                   f'font-family="sans-serif" font-size="13" text-anchor="middle">{label}</text>')
    out.insert(1, '<defs><filter id="g"><feGaussianBlur stdDeviation="0.6"/></filter></defs>')
    out.append("</svg>")
    return "\n".join(out)


def scenarios():
    rng = random.Random(4)
    keys = {k.id for k in GMK67.keys if k.evdev is not None}

    s = GAMES["snake"](GMK67, rng, keys)
    s.reset(0)
    s.body = ["K", "J", "H", "G", "F", "R", "E", "W", "S", "Z"]
    s.apple, s.golden = "P", False
    yield "snake", s.render(0.2)

    m = GAMES["minesweeper"](GMK67, random.Random(11), keys)
    m.reset(0)
    for t, k in enumerate(["G", "P", "Z"]):
        m.on_key(KeyEvent(k, True), t)
        m.on_key(KeyEvent(k, False), t + 0.05)
    hidden_mines = [k for k in m.mine_set][:2]
    for k in hidden_mines:
        m.flags.add(k)
    yield "minesweeper", m.render(5)

    w = GAMES["whack"](GMK67, rng, keys)
    w.reset(0)
    w.moles = {"T": (0.0, 1.5), "L": (0.0, 1.5), "3": (1.0, 1.5)}
    w.flashes = {"N": ((0, 255, 80), 9)}
    yield "whack", w.render(1.2)

    lo = GAMES["lightsout"](GMK67, rng, keys)
    lo.reset(0)
    yield "lightsout", lo.render(0)

    r = GAMES["ripple"](GMK67, rng, keys)
    r.reset(0)
    r.on_key(KeyEvent("H", True), 0)
    yield "ripple", r.render(0.35)


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "docs/img"
    os.makedirs(outdir, exist_ok=True)
    for name, frame in scenarios():
        path = os.path.join(outdir, f"{name}.svg")
        with open(path, "w") as f:
            f.write(svg(frame, name))
        print("wrote", path)
