#!/usr/bin/env python3
"""GMK67 V2 utility: inspect, benchmark, back up / restore, and probe the firmware.

    sudo python3 tools/gmk67.py info
    sudo python3 tools/gmk67.py bench
    sudo python3 tools/gmk67.py backup  [file.json]
    sudo python3 tools/gmk67.py restore  file.json
    sudo python3 tools/gmk67.py probe        # interactive: YOU watch the keyboard

``sudo`` is only needed until udev/99-gmk67.rules is installed (see README).
Every lighting change made here is RAM-only and is undone on exit; nothing is
saved to the keyboard's EEPROM except by ``restore``.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ledarcade.via import (EFFECT_NONE, EFFECT_SOLID, RGBM_BRIGHTNESS, RGBM_COLOR,  # noqa: E402
                           RGBM_EFFECT, UNHANDLED, ViaDevice, find_via_devices)

HIDDEN_EFFECT = 46          # accepted by the firmware but not listed in the VIA menu


def cmd_info(dev: ViaDevice) -> None:
    for d in find_via_devices():
        print(f"VIA device: {d.path}  {d.vid:04x}:{d.pid:04x}  {d.name}")
    print(f"protocol version : {dev.protocol_version()}")
    print(f"layers           : {dev.layer_count()}")
    snap = dev.lighting_snapshot()
    print(f"rgb matrix       : brightness={snap[1][0]} effect={snap[2][0]} speed={snap[3][0]} "
          f"hue={snap[4][0]} sat={snap[4][1]}")


def cmd_bench(dev: ViaDevice, n: int = 300) -> None:
    snap = dev.lighting_snapshot()
    lat = []
    try:
        t = time.perf_counter()
        for i in range(n):
            t0 = time.perf_counter()
            dev.rgb_set(RGBM_COLOR, (i * 4) & 0xFF, 255)
            lat.append(time.perf_counter() - t0)
        dt = time.perf_counter() - t
    finally:
        dev.lighting_restore(snap)
    lat.sort()
    print(f"{n} global colour changes in {dt:.3f}s = {n / dt:.0f}/s; "
          f"median {lat[n // 2] * 1e3:.2f} ms, p95 {lat[int(n * .95)] * 1e3:.2f} ms")


def cmd_backup(dev: ViaDevice, path: str) -> None:
    data = {"keymap": dev.read_keymap().hex(), "macros": dev.read_macros().hex(),
            "lighting": {str(k): v for k, v in dev.lighting_snapshot().items()},
            "taken": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    print(f"saved keymap ({len(data['keymap']) // 2} B), macros ({len(data['macros']) // 2} B) "
          f"and lighting to {path}")


def cmd_restore(dev: ViaDevice, path: str) -> None:
    with open(path) as f:
        data = json.load(f)
    km, mac = bytes.fromhex(data["keymap"]), bytes.fromhex(data["macros"])
    if dev.read_keymap() != km:
        dev.write_keymap(km)
        print("keymap restored")
    if dev.read_macros() != mac:
        dev.write_macros(mac)
        print("macros restored")
    dev.lighting_restore({int(k): tuple(v) for k, v in data["lighting"].items()})
    print("lighting restored (RAM; use VIA's Save if you want it persisted)")


# ---------------------------------------------------------------------------
# Visual probe for an undocumented per-key command
# ---------------------------------------------------------------------------
RED3 = bytes((255, 0, 0))


def _patterns() -> list[bytes]:
    """Payload layouts commonly used by vendor per-key protocols (after cmd, sub)."""
    return [
        b"".join(bytes((i, 255, 0, 0)) for i in range(7)),     # (index, r, g, b) * n
        bytes((0, 9)) + RED3 * 9,                               # start, count, rgb * n
        bytes((0,)) + RED3 * 9,                                 # start, rgb * n
        RED3 * 10,                                              # rgb * n
        bytes((0xFF,)) * 30,                                    # all-ones
    ]


def candidates(cmd: int) -> list[bytes]:
    return [bytes((cmd, sub)) + p for sub in range(256) for p in _patterns()]


def ask(q: str) -> bool:
    while True:
        a = input(f"  >> {q} [y/n] ").strip().lower()
        if a in ("y", "yes", "n", "no"):
            return a.startswith("y")


def blast(dev: ViaDevice, pkts: list[bytes], seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for p in pkts:
            dev.send(*p)
        dev.drain()


def cmd_probe(dev: ViaDevice, cmd: int, seconds: float) -> None:
    results: dict = {"cmd": cmd, "notes": []}
    snap = dev.lighting_snapshot()
    keymap = dev.read_keymap()
    print(__doc__.split("\n")[0])
    print("\nWatch the keyboard while this runs. Answer each question honestly - a wrong\n"
          "'yes' only costs a few extra questions.\n")
    try:
        dev.rgb_set(RGBM_EFFECT, EFFECT_SOLID)
        dev.rgb_set(RGBM_COLOR, 170, 255)
        dev.rgb_set(RGBM_BRIGHTNESS, max(snap[RGBM_BRIGHTNESS][0], 120))
        if not ask("Is the whole keyboard solid BLUE right now?"):
            print("The VIA connection may not be driving the LEDs - stopping.")
            return
        dev.rgb_set(RGBM_EFFECT, HIDDEN_EFFECT)
        time.sleep(0.3)
        desc = input(f"  >> Hidden effect {HIDDEN_EFFECT} is active now. Describe what the keys look "
                     "like (e.g. 'all off', 'some keys lit', 'rainbow'): ")
        results["effect46"] = desc
        for name, effect in (("hidden effect 46", HIDDEN_EFFECT), ("solid blue", EFFECT_SOLID),
                             ("effect none", EFFECT_NONE)):
            dev.rgb_set(RGBM_EFFECT, effect)
            dev.rgb_set(RGBM_COLOR, 170, 255)
            time.sleep(0.3)
            pkts = candidates(cmd)
            print(f"\n[{name}] sending {len(pkts)} candidate 0x{cmd:02X} packets for {seconds:.0f}s ...")
            blast(dev, pkts, seconds)
            if not ask("Did ANY key change colour, even for a moment?"):
                results["notes"].append(f"{name}: no visible change")
                continue
            while len(pkts) > 1:
                half = pkts[: len(pkts) // 2]
                dev.rgb_set(RGBM_EFFECT, effect)       # reset the picture between tries
                time.sleep(0.4)
                print(f"   narrowing down: {len(pkts)} candidates left ...")
                blast(dev, half, seconds)
                pkts = half if ask("Did a key change this time?") else pkts[len(pkts) // 2:]
            found = pkts[0].hex(" ")
            print(f"\n*** candidate per-key packet under '{name}': {found}")
            results["notes"].append(f"{name}: change caused by {found}")
            results.setdefault("found", []).append({"baseline": name, "packet": found})
    finally:
        dev.lighting_restore(snap)
        if dev.read_keymap() != keymap:
            print("WARNING: keymap changed during probe! restore it with: tools/gmk67.py restore <backup>")
        out = "probe_results.json"
        with open(out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nLighting restored. Results written to {out} - please share it (or paste it) "
              "so the per-key backend can be built on top of it.")


def main() -> None:
    args = sys.argv[1:] or ["info"]
    with ViaDevice() as dev:
        if args[0] == "info":
            cmd_info(dev)
        elif args[0] == "bench":
            cmd_bench(dev)
        elif args[0] == "backup":
            cmd_backup(dev, args[1] if len(args) > 1 else f"gmk67-backup-{time.strftime('%Y%m%d-%H%M%S')}.json")
        elif args[0] == "restore" and len(args) > 1:
            cmd_restore(dev, args[1])
        elif args[0] == "probe":
            cmd = int(args[1], 0) if len(args) > 1 else 0xBB
            r = dev.query(cmd)
            if r is not None and r[0] == UNHANDLED:
                print(f"note: 0x{cmd:02X} is answered with 'unhandled' - probing anyway")
            dev.drain()
            cmd_probe(dev, cmd, seconds=3.0)
        else:
            print(__doc__)
            sys.exit(2)


if __name__ == "__main__":
    main()
